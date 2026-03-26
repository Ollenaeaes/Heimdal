# Heimdal ADS-B Integration Spec

## Purpose

Heimdal is a maritime OSINT platform focused on shadow fleet and sanctions evasion tracking. This module adds ADS-B aircraft data for two purposes:

1. **GNSS interference detection** — Use aircraft as canaries to detect jamming and spoofing zones, producing time-bounded interference polygons that overlay on the existing AIS vessel map.
2. **Enforcement aircraft tracking** — Persist tracks of military, coast guard, and police aviation relevant to maritime surveillance (e.g., P-8 Poseidon patrols, coast guard Dash-8s, police helicopters).

All civilian aircraft data is processed for interference detection and then discarded. Only derived interference zones and curated government/military tracks are stored.

---

## Data Source: adsb.lol

**Why adsb.lol and not OpenSky Network:** OpenSky's REST API does not expose NACp (Navigation Accuracy Category for Position), NIC, or any navigation integrity fields. Their state vectors only include basic position/velocity. Since NACp degradation is the primary signal for detecting GNSS jamming from ADS-B data, OpenSky is useless for this purpose.

adsb.lol follows the ADS-B Exchange v2 API format and exposes the full set of navigation integrity fields including `nac_p`, `nic`, `rc`, `sil`, `gva`, `sda`, and an experimental `gpsOkBefore` field that directly flags GPS degradation.

### API Details

- **Base URL:** `https://api.adsb.lol`
- **Format:** ADS-B Exchange v2 compatible JSON
- **Auth:** Currently none required for the OpenAPI endpoints. May require an API key in the future (obtainable by feeding adsb.lol).
- **License:** ODbL 1.0 — derived products are fine, must attribute.
- **Rate limits:** Dynamic based on server load. No published hard numbers. Be respectful — poll no more than once every 5–10 seconds per bounding box.
- **Military filtering:** adsb.lol does NOT filter military aircraft, unlike Flightradar24. This is critical for the enforcement tracking use case.
- **Docs:** https://api.adsb.lol/docs and https://github.com/adsblol/api

### Key Endpoints

**Aircraft by geographic area:**
```
GET /v2/point/{lat}/{lon}/{radius_nm}
```
Returns all aircraft within radius (nautical miles) of the given point.

**Military aircraft:**
```
GET /v2/mil
```
Returns all currently tracked military aircraft globally.

**Aircraft by ICAO hex:**
```
GET /v2/hex/{icao_hex}
```
Returns data for a specific aircraft by its ICAO 24-bit address.

### Fields Relevant to Heimdal

Each aircraft object in the response includes (when available):

| Field | Type | Use in Heimdal |
|-------|------|----------------|
| `hex` | string | ICAO 24-bit address, primary key for aircraft lookup |
| `lat`, `lon` | float | Aircraft position |
| `alt_baro` | int/string | Barometric altitude in feet, or "ground" |
| `gs` | float | Ground speed in knots |
| `track` | float | True track over ground, degrees |
| `flight` | string | Callsign |
| `t` | string | Aircraft ICAO type code from database |
| `r` | string | Registration from database |
| `dbFlags` | int | Bitfield: `dbFlags & 1` = military |
| `nac_p` | int | **Navigation Accuracy for Position** — primary jamming signal |
| `nic` | int | Navigation Integrity Category |
| `rc` | int | Radius of Containment in meters |
| `sil` | int | Source Integrity Level |
| `gva` | int | Geometric Vertical Accuracy |
| `version` | int | ADS-B version (0, 1, or 2) |
| `gpsOkBefore` | float | **Experimental: timestamp when GPS was last known good** — direct GPS degradation flag. Only present when GPS is lost/degraded, shown for 15 min after event. |
| `seen` | float | Seconds since last message |
| `seen_pos` | float | Seconds since last position update |
| `category` | string | Emitter category (A0–D7) |

### NACp Values and Their Meaning

NACp encodes the 95% accuracy bound of the aircraft's reported position. Lower values mean worse accuracy — which under normal conditions should not happen to modern aircraft in flight.

| NACp | Accuracy Bound | Interpretation |
|------|---------------|----------------|
| 11 | < 3m | Normal, high-quality GNSS |
| 10 | < 10m | Normal |
| 9 | < 30m | Normal |
| 8 | < 93m | Acceptable, common value |
| 7 | < 185m | Slightly degraded, worth noting |
| 6 | < 556m | Degraded — possible interference |
| 5 | < 926m | Degraded — likely interference |
| 4 | < 1852m | Severely degraded — strong interference signal |
| 3 | < 3704m | Severely degraded |
| 2 | < 7408m | Effectively unusable |
| 1 | < 18.5km | Effectively unusable |
| 0 | Unknown | No accuracy info — could be interference or old transponder |

**Jamming detection threshold:** When an aircraft that normally reports NACp ≥ 8 drops to NACp ≤ 5, that is a strong interference signal. When multiple aircraft in the same area show simultaneous NACp degradation, that is a confirmed interference event.

---

## Architecture

### Polling Strategy

Define bounding boxes covering Heimdal's areas of interest. These are the regions where shadow fleet activity and known GNSS interference overlap:

| Region | Approx Bounds | Purpose |
|--------|--------------|---------|
| Baltic Sea | 53°N–60°N, 12°E–30°E | Kaliningrad jamming zone, Baltic shadow fleet corridor |
| Norwegian Coast | 57°N–71°N, 0°E–16°E | Norwegian EEZ, Kystvakten patrol area |
| North Sea | 53°N–62°N, -4°W–8°E | Transit corridor, North Sea enforcement |
| Black Sea (optional) | 41°N–47°N, 27°E–42°E | Major spoofing zone, secondary interest |

For each bounding box, poll adsb.lol using the `/v2/point` endpoint with a center point and radius that covers the box. Use multiple overlapping circles if needed.

**Poll interval:** Every 10 seconds per region. Stagger the polls so they don't all fire simultaneously.

**Note:** Since adsb.lol's point endpoint uses radius in nautical miles, convert the bounding boxes to center + radius. The Baltic box is roughly 480nm across, so use 2–3 overlapping circles.

### Processing Pipeline

For each polled response:

**Step 1: Classify each aircraft**

Look up the `hex` field against the curated aircraft list (`heimdal_aircraft_of_interest.csv`). If found, this is an aircraft of interest — go to Step 3.

If not in the curated list, check `dbFlags & 1` (military flag from the adsb.lol database). If military, go to Step 3.

Otherwise, this is a civilian aircraft — go to Step 2.

**Step 2: Extract interference signal, then discard**

For civilian aircraft, extract only what's needed for the interference grid:

- `lat`, `lon` — where the aircraft is
- `nac_p` — the navigation accuracy
- `nic`, `rc` — additional integrity info
- `gpsOkBefore` — if present, direct GPS degradation flag
- `alt_baro` — altitude (higher aircraft have wider line-of-sight to ground-based jammers)
- Timestamp of the observation

Feed these into the interference detection module (described below). Do not persist the aircraft's identity, callsign, registration, or track. The civilian aircraft ceases to exist in Heimdal after its NACp contribution is recorded.

**Step 3: Persist track of aircraft of interest**

For military, coast guard, and police aircraft, store the full position report in TimescaleDB:

```
Table: adsb_positions (hypertable, partitioned by time)

  time          TIMESTAMPTZ  — observation timestamp
  icao_hex      TEXT         — ICAO 24-bit address
  callsign      TEXT         — flight callsign (nullable)
  lat           DOUBLE       — WGS-84 latitude
  lon           DOUBLE       — WGS-84 longitude
  alt_baro      INTEGER      — barometric altitude in feet (nullable)
  alt_geom      INTEGER      — geometric altitude in feet (nullable)
  ground_speed  REAL         — knots (nullable)
  track         REAL         — true track degrees (nullable)
  vertical_rate REAL         — feet/min (nullable)
  squawk        TEXT         — transponder code (nullable)
  nac_p         SMALLINT     — navigation accuracy (nullable)
  nic           SMALLINT     — navigation integrity (nullable)
  on_ground     BOOLEAN      — is aircraft on the ground
  category      TEXT         — aircraft category from curated list (military/police/coast_guard)
  country       TEXT         — country from curated list
  role          TEXT         — role from curated list (e.g., "US Navy maritime patrol")
```

The `category`, `country`, and `role` fields come from joining against the curated aircraft CSV at ingest time.

### Interference Detection Module

This module consumes the NACp data from all aircraft (Step 2) and produces time-bounded interference zones.

**Data structure for interference grid:**

Use an H3 hex grid (resolution 5 or 6, roughly 8–40 km cells) to spatially bin aircraft observations. For each cell, maintain a rolling window (e.g., 5 minutes):

```
Table: interference_observations (hypertable, short retention — 24–48 hours)

  time          TIMESTAMPTZ
  h3_index      BIGINT       — H3 cell index
  aircraft_count INTEGER     — number of aircraft observed in this cell in this window
  degraded_count INTEGER     — number with NACp ≤ 5
  min_nac_p     SMALLINT     — worst NACp seen
  gps_lost_count INTEGER    — number with gpsOkBefore flag present
```

**Detection logic:**

An interference event is declared when, within a single H3 cell and time window:
- `degraded_count >= 2` (multi-aircraft confirmation) AND `degraded_count / aircraft_count >= 0.3` (at least 30% of aircraft affected)
- OR any aircraft has `gpsOkBefore` present (direct GPS loss flag, high confidence even for a single aircraft)

When an event is detected, promote it to a persistent record:

```
Table: interference_events (hypertable, long retention)

  time_start    TIMESTAMPTZ  — when interference was first detected
  time_end      TIMESTAMPTZ  — when interference ceased (updated on close)
  h3_index      BIGINT       — spatial cell
  center_lat    DOUBLE       — cell center latitude
  center_lon    DOUBLE       — cell center longitude
  severity      TEXT         — 'moderate' (NACp 4–5) or 'severe' (NACp ≤ 3 or GPS lost)
  type          TEXT         — 'jamming' (NACp degraded) or 'spoofing' (position anomaly — future)
  confidence    REAL         — 0.0–1.0, based on aircraft count and degradation ratio
  peak_aircraft_affected INTEGER — max simultaneous degraded aircraft
  min_nac_p_observed SMALLINT    — worst NACp during event
  is_active     BOOLEAN      — still ongoing
```

The frontend queries `interference_events` to render colored zones on the map. The playback slider filters by `time_start` / `time_end` to show interference zones appearing and disappearing as the user scrubs through time. The `is_active` flag allows highlighting currently active interference.

### Curated Aircraft Lookup

The `heimdal_aircraft_of_interest.csv` file is loaded into memory at startup as a hash map keyed by ICAO hex. It contains 501 aircraft across Nordic military, Nordic police/coast guard, and NATO maritime patrol assets.

```
Table: aircraft_of_interest (regular table, not hypertable)

  icao_hex      TEXT PRIMARY KEY
  registration  TEXT
  type_code     TEXT
  description   TEXT
  country       TEXT
  category      TEXT  — military / police / coast_guard
  role          TEXT
  source        TEXT  — tar1090-db flag=10 / manual_override
```

This table is refreshed periodically by re-downloading the tar1090-db CSV and re-running the extraction. The 17 manual overrides are maintained in a separate config file and merged during refresh.

---

## Linking ADS-B Interference to AIS Vessel Tracks

This is the payoff. When Heimdal's existing AIS ingest module processes vessel positions, it can now cross-reference against active interference events:

For each AIS position received, check if the vessel's lat/lon falls within an H3 cell that has an active or recent `interference_event`. If so, tag that AIS position with the interference event metadata. This enables the visualization described in the original requirement: play a vessel track forward on the map, see it enter an interference zone (which was detected from ADS-B data), and observe the vessel's AIS positions degrade, jump, or drift.

The AIS positions themselves don't need a schema change — the interference tagging can be done at query time by joining `ais_positions` against `interference_events` on spatial and temporal overlap.

---

## Cost: Zero

| Component | Cost | Notes |
|-----------|------|-------|
| adsb.lol API | Free | ODbL license, attribute in the UI |
| aisstream.io | Free | Existing Heimdal data source |
| TimescaleDB | Free | Already running |
| tar1090-db | Free | GitHub, daily download |
| gpsjam.org CSVs | Free | Optional context layer for historical validation |

---

## Caveats and Limitations

**adsb.lol coverage varies.** It's a community feeder network. Coverage is excellent over Western Europe and the Baltic but thinner over open ocean and remote areas. Aircraft at high altitude are visible to more receivers, so coverage for overflying airliners is better than low-level helicopters.

**NACp is not always present.** Older ADS-B version 0 transponders don't report NACp. These aircraft should be excluded from interference calculations (filter on `version >= 1`).

**NACp 0 is ambiguous.** It means "unknown accuracy," not "no accuracy." It could be interference or just an aircraft that doesn't report this field. Don't count NACp 0 as degraded — only count NACp 1–5 as degraded when the aircraft has been seen reporting NACp ≥ 8 previously.

**gpsOkBefore is experimental.** The adsb.lol/readsb field `gpsOkBefore` is marked as experimental and subject to change. Don't build the entire detection pipeline around it — use it as a high-confidence supplementary signal alongside NACp.

**Military aircraft sometimes go dark.** Aircraft that don't want to be tracked turn off their transponders. The curated list will always be incomplete for actual military operations. It's comprehensive for peacetime patrol and coast guard work.

**Rate limiting.** adsb.lol's rate limits are dynamic. If you start getting 4xx errors, back off. The polling strategy should include exponential backoff. If adsb.lol introduces API keys, you can get one by setting up a feeder — which also improves the network's coverage.

**Attribution required.** ODbL requires attribution. Add "Aircraft data from adsb.lol (ODbL)" to Heimdal's UI where ADS-B data is displayed.
