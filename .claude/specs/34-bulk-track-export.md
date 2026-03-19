# Spec 34: Bulk Track Data Export via Email

**Slug:** `bulk-track-export`
**Wave:** 16
**Depends on:** Spec 31 (auth-backend — user context + SMTP), Spec 30 (track export + cold Parquet reader)
**Status:** approved

---

## Overview

Users can request bulk downloads of all track data (including cold Parquet storage) for one or more vessels over any time range. These exports are too large and CPU-intensive to serve synchronously — instead the user submits a request, a background job processes it during low-load intervals, and they receive an email with a download link when it's ready. Download links expire after 5 days.

---

## Design Principles

1. **Minimum CPU impact.** The Hostinger VPS has limited resources. Export jobs run:
   - One at a time (single-worker queue, no parallelism)
   - During a configurable low-load window (default: 02:00–06:00 UTC), OR on a slow interval (one job every 10 minutes) outside the window
   - With `nice`-level IO priority — yielding to real-time ingest/scoring
   - With chunk-based processing (read + write in chunks, never hold full dataset in memory)
2. **No new infrastructure.** Job queue is a DB table, not Redis/Celery/RabbitMQ.
3. **Disk-conscious.** Completed exports are compressed (gzip). Files are purged after 5 days by the same background task.

---

## Business Rules

1. Only authenticated users can request exports (requires login).
2. Users can request track data for **1–10 vessels** per export job.
3. Time range: any range up to the full history. No artificial cap — but the UI shows an estimated size/row count before submitting.
4. Formats: JSON (`.json.gz`) or CSV (`.csv.gz`) — always gzip-compressed.
5. After submitting: user sees "Your export has been queued. You'll receive an email at {email} when it's ready. This may take up to several hours."
6. When complete: email with download link sent to user's registered email.
7. Download links expire after **5 days**. After that, the file is deleted.
8. Users can see their export history (pending/ready/expired) in the UI.
9. Rate limit: max **3 pending exports per user** at a time.
10. If an export job fails (e.g. corrupt Parquet file), the user gets an email saying it failed with a "Try again" prompt.

---

## Database

### Migration 016_export_jobs.sql

```sql
CREATE TABLE IF NOT EXISTS export_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'expired')),
    -- Request parameters
    mmsis           INTEGER[] NOT NULL,
    time_start      TIMESTAMPTZ,                   -- NULL = from beginning of history
    time_end        TIMESTAMPTZ,                   -- NULL = up to now
    format          TEXT NOT NULL DEFAULT 'csv'
                    CHECK (format IN ('json', 'csv')),
    -- Result
    file_path       TEXT,                          -- path on disk to compressed file
    file_size_bytes BIGINT,
    row_count       BIGINT,
    download_token  TEXT UNIQUE,                   -- URL-safe random token for download link
    -- Lifecycle
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,                   -- completed_at + 5 days
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_export_jobs_user ON export_jobs(user_id);
CREATE INDEX idx_export_jobs_pending ON export_jobs(status, created_at) WHERE status = 'pending';
CREATE INDEX idx_export_jobs_download ON export_jobs(download_token) WHERE download_token IS NOT NULL;
CREATE INDEX idx_export_jobs_expired ON export_jobs(expires_at) WHERE status = 'completed';
```

---

## API Endpoints

### POST /api/exports (requires auth)
- Body: `{ mmsis: number[], start?: string, end?: string, format: "json" | "csv" }`
- Validates: 1–10 MMSIs, user has < 3 pending jobs
- Returns estimated row count (quick COUNT query against vessel_positions + cold storage file sizes)
- Creates export_job with status=pending
- Returns 201 `{ id, status: "pending", estimated_rows, message: "You'll receive an email when ready" }`

### GET /api/exports (requires auth)
- Lists user's export jobs (newest first, paginated)
- Returns: id, status, mmsis, time range, format, file_size, row_count, created_at, expires_at, download_url (if completed)

### GET /api/exports/download/{token} (public — token is auth)
- Validates download_token, checks not expired
- Streams the gzip file with appropriate Content-Disposition header
- Returns 404 if expired or invalid token
- Returns 410 Gone if file has been purged

### DELETE /api/exports/{id} (requires auth)
- Cancels a pending job, or deletes a completed export file early
- Only the owning user can delete

---

## Background Job Runner

### Architecture

Runs as an **asyncio background task inside the API server** (same pattern as the inactivity lifecycle task). NOT a separate container.

```python
async def export_job_runner():
    """Process one export job at a time, with CPU-conscious scheduling."""
    while True:
        job = await pick_next_job()      # oldest pending, SKIP LOCKED
        if job:
            await process_export_job(job)
            await asyncio.sleep(60)      # 1 min cooldown between jobs
        else:
            await asyncio.sleep(300)     # 5 min poll when idle

        # Housekeeping: purge expired files
        await purge_expired_exports()
```

### Job Processing (`process_export_job`)

1. Set status = `processing`, `started_at = NOW()`
2. Open a gzip output stream to a temp file
3. **Read from DB** (recent data, < 30 days):
   - Chunked query: `SELECT ... FROM vessel_positions WHERE mmsi = ANY(:mmsis) AND timestamp BETWEEN :start AND :end ORDER BY timestamp LIMIT 10000 OFFSET :offset`
   - Write each chunk to the gzip stream immediately (don't accumulate in memory)
4. **Read from cold Parquet** (older data):
   - Iterate month-by-month Parquet files (reuse existing `_read_parquet_positions` logic)
   - Filter by MMSI and time range
   - Write in chunks to the gzip stream
5. Move temp file to final location: `/data/exports/{job_id}.{format}.gz`
6. Generate `download_token` (URL-safe random, 64 chars)
7. Set status = `completed`, `file_size_bytes`, `row_count`, `expires_at = NOW() + 5 days`
8. Send email with download link

### Memory Budget

- Target: **< 50MB** peak memory per job
- Achieved by streaming chunks (10K rows at a time) directly to gzip writer
- Never hold the full dataset in memory

### Error Handling

- On exception: set status = `failed`, `error_message = str(e)`
- Send failure notification email
- Failed jobs can be retried via a new request (no auto-retry to avoid CPU waste)

---

## File Management

### Storage Location
`/data/exports/` on the host (bind-mounted into the API server container, same as `/data/raw`)

### Purge Logic (runs as part of the job runner loop)
```sql
-- Find completed exports past their expiry
SELECT id, file_path FROM export_jobs
WHERE status = 'completed' AND expires_at < NOW();
```
- Delete the file from disk
- Set status = `expired`

---

## Email Templates

### Export Ready

```
Subject: [Heimdal] Your track export is ready

Your track data export is ready for download:

  Vessels: {vessel_names_or_mmsis}
  Period:  {start} — {end}
  Format:  {format}
  Size:    {file_size_human}
  Rows:    {row_count}

Download: {app_url}/api/exports/download/{token}

This link expires on {expires_date} (5 days from now).

---
Heimdal Maritime Intelligence
```

### Export Failed

```
Subject: [Heimdal] Track export failed

Your track data export could not be completed:

  Vessels: {vessel_names_or_mmsis}
  Period:  {start} — {end}
  Error:   {error_message}

You can try again from the Heimdal app.

---
Heimdal Maritime Intelligence
```

---

## Frontend Components

### ExportRequestPanel.tsx (in VesselPanel, below TrackExportSection)

- "Bulk Export" collapsible section
- Vessel chips (current vessel pre-selected, can add more via search — reuse lookback vessel search)
- Date range picker (datetime-local, or "All history" checkbox)
- Format toggle: JSON / CSV
- Estimated row count shown after selecting parameters (lightweight API call)
- "Request Export" button → confirmation with "This may take up to several hours" message
- Rate limit feedback: "You have {n}/3 pending exports"

### ExportHistoryPanel.tsx (accessible from HUD bar or user menu)

- Lists user's exports: status badge (pending/processing/ready/expired/failed), vessels, date range, size
- "Download" button for completed exports (opens download link)
- "Cancel" button for pending exports
- Status auto-refreshes every 30s for pending/processing jobs

---

## Stories

### Story 1: Database migration + export job repository
- Migration 016_export_jobs.sql
- `shared/db/export_repository.py`: create_job, get_user_jobs, get_pending_job (SKIP LOCKED), update_status, get_by_download_token, get_expired_jobs, count_user_pending
- Tests: repository CRUD, pending count, expiry queries

### Story 2: Background job runner + chunk-based export
- `services/api-server/jobs/export_runner.py`: job loop, chunked DB reads, chunked Parquet reads, gzip streaming, memory-conscious processing
- Integration with existing `_read_parquet_positions` pattern
- CSV writer (csv.DictWriter to gzip stream) + JSON writer (streaming JSON array to gzip)
- Tests: chunk processing, gzip output, format correctness, memory bounds

### Story 3: API endpoints
- POST /api/exports (with row count estimate), GET /api/exports, GET /api/exports/download/{token}, DELETE /api/exports/{id}
- Auth enforcement, rate limiting (3 pending per user)
- Download endpoint streams file with Content-Disposition
- Tests: CRUD, auth enforcement, rate limit, download valid/expired/missing

### Story 4: Email notifications + file purge
- Email sending on completion/failure (reuse shared/email.py)
- Expired file purge in job runner loop
- Tests: email templates, purge logic, status transitions

### Story 5: Frontend — export request + history
- ExportRequestPanel.tsx: vessel selection, date range, format, estimate, submit
- ExportHistoryPanel.tsx: job list with status, download, cancel
- Auto-refresh for pending jobs
- Tests: form rendering, submission, history display, status refresh

### Implementation Order

```
Group 1 (parallel): Story 1, Story 2
Group 2 (sequential): Story 3              — depends on Story 1
Group 3 (sequential): Story 4              — depends on Story 2
Group 4 (sequential): Story 5              — depends on Story 3
```

---

## Acceptance Criteria

- [ ] Authenticated users can request bulk track exports for 1–10 vessels
- [ ] Export jobs are processed one at a time with minimal CPU impact
- [ ] Peak memory per job stays under 50MB (chunk-based streaming)
- [ ] Both JSON and CSV formats are gzip-compressed
- [ ] User receives email with download link when export is ready
- [ ] User receives email on export failure
- [ ] Download links work for 5 days, then file is purged and status set to expired
- [ ] GET /api/exports/download/{token} returns 410 Gone after expiry
- [ ] Rate limit: max 3 pending exports per user
- [ ] Export history is visible in the UI with status badges
- [ ] Cold Parquet storage is read correctly for historical data
- [ ] Pending exports can be cancelled by the user
