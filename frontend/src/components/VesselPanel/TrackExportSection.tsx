import { useState, useCallback } from 'react';
import { CollapsibleSection } from './CollapsibleSection';

interface TrackExportSectionProps {
  mmsi: number;
}

const RETENTION_DAYS = 30;

export function TrackExportSection({ mmsi }: TrackExportSectionProps) {
  const [format, setFormat] = useState<'json' | 'csv'>('json');
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 7);
    return d.toISOString().slice(0, 10);
  });
  const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const today = new Date().toISOString().slice(0, 10);

  const handleExport = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const start = new Date(startDate + 'T00:00:00Z');
      const end = new Date(endDate + 'T23:59:59Z');
      const now = new Date();
      const retentionCutoff = new Date(now);
      retentionCutoff.setDate(retentionCutoff.getDate() - RETENTION_DAYS);

      let url: string;
      if (start >= retentionCutoff) {
        // Within hot DB retention — use existing track endpoint
        url = `/api/vessels/${mmsi}/track?start=${start.toISOString()}&end=${end.toISOString()}`;
      } else {
        // Includes cold storage data — use export endpoint
        url = `/api/vessels/${mmsi}/track/export?start=${start.toISOString()}&end=${end.toISOString()}&format=${format}`;
      }

      const res = await fetch(url);
      if (!res.ok) throw new Error(`Export failed: ${res.status}`);

      if (format === 'csv' && start < retentionCutoff) {
        // CSV from export endpoint — already formatted
        const csvText = await res.text();
        if (!csvText.trim() || csvText.split('\n').length <= 1) {
          setError('No data available for this date range');
          return;
        }
        downloadFile(
          csvText,
          `track-${mmsi}-${startDate}-${endDate}.csv`,
          'text/csv',
        );
      } else {
        // JSON response (either from track or export endpoint)
        const data = await res.json();
        if (!Array.isArray(data) || data.length === 0) {
          setError('No data available for this date range');
          return;
        }

        if (format === 'csv') {
          // Convert JSON to CSV client-side (hot DB path returns JSON)
          const csv = jsonToCsv(data);
          downloadFile(
            csv,
            `track-${mmsi}-${startDate}-${endDate}.csv`,
            'text/csv',
          );
        } else {
          const jsonStr = JSON.stringify(data, null, 2);
          downloadFile(
            jsonStr,
            `track-${mmsi}-${startDate}-${endDate}.json`,
            'application/json',
          );
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setLoading(false);
    }
  }, [mmsi, startDate, endDate, format]);

  return (
    <CollapsibleSection title="Track Export" testId="track-export-section">
      <div className="space-y-3">
          {/* Date range (no 30-day limit for export) */}
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-xs text-gray-500 block mb-1">Start</label>
              <input
                type="date"
                value={startDate}
                max={endDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full px-2 py-1 text-xs bg-[#1F2937] text-gray-300 border border-[#374151] rounded focus:border-[#3B82F6] focus:outline-none"
                data-testid="export-start-date"
              />
            </div>
            <div className="flex-1">
              <label className="text-xs text-gray-500 block mb-1">End</label>
              <input
                type="date"
                value={endDate}
                max={today}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full px-2 py-1 text-xs bg-[#1F2937] text-gray-300 border border-[#374151] rounded focus:border-[#3B82F6] focus:outline-none"
                data-testid="export-end-date"
              />
            </div>
          </div>

          {/* Format selector */}
          <div>
            <label className="text-xs text-gray-500 block mb-1">Format</label>
            <div className="flex gap-2">
              <button
                onClick={() => setFormat('json')}
                className={`flex-1 py-1 text-xs rounded transition-colors ${
                  format === 'json'
                    ? 'bg-[#3B82F6] text-white'
                    : 'bg-[#1F2937] text-gray-400 hover:text-white'
                }`}
                data-testid="export-format-json"
              >
                JSON
              </button>
              <button
                onClick={() => setFormat('csv')}
                className={`flex-1 py-1 text-xs rounded transition-colors ${
                  format === 'csv'
                    ? 'bg-[#3B82F6] text-white'
                    : 'bg-[#1F2937] text-gray-400 hover:text-white'
                }`}
                data-testid="export-format-csv"
              >
                CSV
              </button>
            </div>
          </div>

          {/* Export button */}
          <button
            onClick={handleExport}
            disabled={loading}
            className="w-full py-2 bg-[#3B82F6] hover:bg-[#2563EB] disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-medium rounded transition-colors flex items-center justify-center gap-2"
            data-testid="export-button"
          >
            {loading && (
              <span className="animate-spin inline-block w-3 h-3 border border-white border-t-transparent rounded-full" />
            )}
            {loading ? 'Exporting...' : 'Export'}
          </button>

          {/* Error / empty message */}
          {error && (
            <div className="text-xs text-yellow-400" data-testid="export-message">
              {error}
            </div>
          )}
        </div>
    </CollapsibleSection>
  );
}

function jsonToCsv(data: Record<string, unknown>[]): string {
  const headers = ['timestamp', 'lat', 'lon', 'sog', 'cog', 'heading'];
  const rows = data.map((row) =>
    headers.map((h) => {
      const val = row[h];
      if (val === null || val === undefined) return '';
      return String(val);
    }).join(','),
  );
  return [headers.join(','), ...rows].join('\n');
}

function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
