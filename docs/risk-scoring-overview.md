# Heimdal Risk Scoring System

## Overview

Heimdal's scoring engine evaluates vessels in real time by running 24+ rules against incoming AIS positions, enrichment data (Global Fishing Watch), and static vessel profiles. Each rule can produce **anomaly events** with point values. Points are aggregated per vessel into an **aggregate score** that determines a **risk tier**.

### Risk Tiers

| Tier | Threshold | Meaning |
|------|-----------|---------|
| Green | < 30 points | Normal operations |
| Yellow | 30 -- 99 points | Elevated concern, warrants monitoring |
| Red | >= 100 points | High risk, likely illicit activity |
| Blacklisted | Sanctions match (confidence >= 0.9, matched on IMO or MMSI) | Confirmed sanctioned vessel |

### Score Calculation

```
aggregate_score = SUM(
  FOR EACH rule_id:
    MIN(
      SUM(points from active anomalies) * escalation_multiplier,
      MAX_PER_RULE[rule_id] * escalation_multiplier
    )
)
```

Each rule has a **per-rule cap** (MAX_PER_RULE) that prevents any single signal from dominating the total score. Repeat offenders receive escalation multipliers (1.5x on 2nd event, 2.0x on 3rd+, within a 30-day decay window).

---

## Infrastructure Sabotage Detection

Three dedicated rules detect suspicious behaviour near submarine cables and pipelines. These are among the highest-scoring rules in the system because deliberate infrastructure damage represents a severe national-security threat.

### How Infrastructure Is Modelled

Submarine cables and pipelines are stored in the `infrastructure_routes` table as PostGIS `GEOGRAPHY LINESTRING` geometries. Each route carries:

- **name** and **type** (cable / pipeline)
- **operator**
- **buffer_nm** -- the corridor radius in nautical miles (typically 5--10 nm)

Vessels entering a corridor are detected via `ST_DWithin` spatial queries.

### Rule: Cable Slow Transit

**Rule ID:** `cable_slow_transit` | **Max cap:** 140 points (highest single-rule cap in the system)

Detects a vessel **loitering** at low speed inside an infrastructure corridor.

| Condition | Severity | Points |
|-----------|----------|--------|
| Speed < 7 kn inside corridor for 30--60 min | High | 40 |
| Speed < 7 kn inside corridor for >= 60 min | Critical | 100 |
| Shadow-fleet escalation (concurrent sanctions_match, gfw_port_visit, flag_hopping, or insurance_class_risk anomalies) | -- | +40 |

**Why it matters:** Vessels engaged in cable-cutting or tampering need to maintain position over the target. Extended low-speed transit directly above a cable is the primary observable indicator of sabotage preparation or execution.

**Exclusions:** Cable-laying vessels (ship type 33) and service vessels (tugs, pilots, SAR, law enforcement) are excluded since they routinely operate slowly near cables for legitimate purposes.

**State tracking:** Entry time into the corridor is persisted in Redis so the rule works correctly across evaluation cycles.

**End condition:** Vessel exits the corridor or accelerates above 7 knots.

### Rule: Cable Alignment

**Rule ID:** `cable_alignment` | **Max cap:** 100 points

Detects a vessel whose **course over ground (COG) aligns with the bearing of a cable** for a sustained period.

| Condition | Severity | Points |
|-----------|----------|--------|
| COG within 20 deg of cable bearing for 15--60 min | High | 40 |
| COG within 20 deg of cable bearing for >= 60 min | Critical | 100 |

**Why it matters:** A vessel deliberately tracking along a cable's path (rather than crossing it) is a strong indicator of reconnaissance or active tampering. Normal shipping traffic crosses cables at various angles; sustained parallel tracking is anomalous.

**Technical detail:** The cable bearing at the vessel's nearest point is computed using PostGIS `ST_LineLocatePoint` to find the closest segment, then interpolating points 0.1% before and after to derive a directional vector. The comparison accounts for bidirectional cable routing (a vessel can follow a cable in either direction) and 360-degree wraparound.

**Reset threshold:** COG divergence > 30 degrees ends the event.

**Exclusions:** Cable-laying and service vessels (ship types 31--33, 50--59).

### Rule: Open-Water Speed Anomaly Near Infrastructure

**Rule ID:** `infra_speed_anomaly` | **Max cap:** 15 points

Detects an **abrupt speed reduction** coinciding with corridor entry.

| Condition | Severity | Points |
|-----------|----------|--------|
| Speed drops > 50% of 2-hour baseline upon entering corridor | Moderate | 15 |

**Requirements:** At least 4 historical positions spanning >= 2 hours before the current position, providing a reliable speed baseline.

**Why it matters:** A vessel that has been cruising at normal speed and suddenly slows down as it enters an infrastructure corridor may be preparing to loiter over a cable or pipeline. This rule catches the transition moment that the slow-transit rule would only flag later.

**Exclusions:** Suppressed within 10 nm of a port (speed reduction near ports is normal for approach/departure).

### Combined Infrastructure Sabotage Signal

When multiple infrastructure rules fire simultaneously, the combined score can reach **255 points** (140 + 100 + 15), immediately placing the vessel in the **red tier**. The shadow-fleet escalation on cable_slow_transit adds further weight when the vessel already has other risk indicators (sanctions links, flag-hopping, etc.), creating a composite picture of a high-risk actor near critical infrastructure.

---

## GNSS Jamming and Spoofing Detection

GNSS interference detection operates on two levels: individual vessel-level spoofing rules that detect manipulated AIS position data, and a clustering algorithm that identifies geographic zones of probable jamming activity.

### Spoofing Detection Rules

Five rules detect various forms of AIS/GNSS manipulation:

#### 1. Land Position (`spoof_land_position`)

Vessel reports a position **on land** (beyond a 100m coastal buffer, checked against a GSHHG-derived land mask polygon).

| Condition | Severity | Points |
|-----------|----------|--------|
| Single land position | Moderate | 15 |
| 3+ consecutive land positions | Critical | 100 |

**Why it matters:** GNSS jamming or spoofing can cause a vessel's reported position to jump onto land. A single occurrence may be a transient GPS glitch; repeated land positions indicate sustained interference or deliberate coordinate fabrication.

#### 2. Impossible Speed (`spoof_impossible_speed`)

Implied speed between two consecutive positions exceeds the **physical limits** for the vessel type (1.5x safety margin applied).

| Vessel Type | Speed Threshold |
|-------------|----------------|
| Tanker | 27 kn |
| Cargo | 24 kn |
| Container | 37.5 kn |
| Default | 45 kn |

| Condition | Severity | Points |
|-----------|----------|--------|
| Single violation | High | 40 |
| 2+ violations within 24h | Critical | 100 |

**Why it matters:** When GNSS coordinates are spoofed or jammed, the calculated speed between real and false positions often exceeds what any vessel can physically achieve. This is one of the most reliable indicators of position manipulation.

#### 3. Duplicate MMSI (`spoof_duplicate_mmsi`)

The same MMSI number is observed **more than 10 nm apart within 5 minutes**.

| Condition | Severity | Points |
|-----------|----------|--------|
| Always | Critical | 100 |

**Why it matters:** Two vessels cannot physically occupy locations 10+ nm apart simultaneously. This indicates either MMSI cloning (identity theft) or coordinated spoofing where a vessel's identity is being replayed at a different location to mask its true position.

#### 4. Frozen Position (`spoof_frozen_position`)

Vessel reports **identical coordinates, COG, and SOG for > 2 hours** while supposedly underway, or exhibits a **box pattern** (2--4 oscillating coordinate values for > 1 hour).

| Condition | Severity | Points |
|-----------|----------|--------|
| Frozen position or box pattern | High | 40 |

**Why it matters:** GNSS spoofing devices sometimes feed a fixed coordinate to the AIS transponder, resulting in a vessel that appears stationary while actually moving. The box pattern is a known signature of certain spoofing devices that alternate between a small set of fake positions.

#### 5. Identity Mismatch (`spoof_identity_mismatch`)

Static AIS data contradicts known vessel characteristics.

| Condition | Severity | Points |
|-----------|----------|--------|
| Reported dimensions differ > 20% from registry | High | 40 |
| Flag (nation) doesn't match MMSI's MID code | High | 40 |
| IMO number belongs to a scrapped/deleted vessel (zombie) | Critical | 100 |

**Why it matters:** Vessels engaged in sanctions evasion or illicit operations often manipulate their AIS identity data. Dimension mismatches suggest a different vessel is using a stolen identity. Flag-MID mismatches indicate the MMSI has been altered. Zombie IMOs (reusing scrapped vessel identities) are a hallmark of dark fleet operations.

### GNSS Interference Zone Clustering

**Module:** `services/scoring/gnss_clustering.py`

After individual spoofing events are scored, a post-processing step clusters them into **geographic interference zones**. This transforms vessel-level anomalies into an area-level threat picture.

#### Clustering Logic

1. Filter all active anomalies to spoofing rules only (rule_id starts with `spoof_`)
2. Group events using greedy clustering:
   - Haversine distance <= 20 nm
   - Time difference <= 1 hour
3. **Minimum cluster size:** 3 events required to form a zone
4. For each qualifying cluster:
   - Compute centroid from member event positions
   - If an existing zone is within 20 nm and 24 hours: **refresh** it (extend expiry, increment affected count)
   - If no match: **create** a new zone with a PostGIS convex hull polygon encompassing all event positions

#### Zone Properties

| Field | Description |
|-------|-------------|
| `detected_at` | When the zone was first identified |
| `expires_at` | Auto-expires after 24 hours unless refreshed |
| `geometry` | Convex hull polygon (GEOGRAPHY) of contributing events |
| `affected_count` | Cumulative number of spoofing events in the zone |
| `details` | JSONB with contributing rule IDs and refresh timestamps |

#### Interpretation

A GNSS interference zone indicates a geographic area where multiple vessels are simultaneously experiencing position anomalies. This is the signature of:

- **Area-denial jamming** -- a jammer on shore or on a vessel disrupting GPS signals across a wide area (common in conflict zones and near military installations)
- **Coordinated spoofing** -- false GPS signals broadcast to divert or confuse vessels (used to create "ghost fleets" or mask operations near sensitive locations)
- **Electronic warfare** -- military or state-sponsored interference with civilian navigation systems

The 3-event minimum and 20 nm / 1-hour clustering thresholds are calibrated to distinguish genuine interference from isolated GPS glitches or individual vessel manipulation.

---

## How Infrastructure Sabotage and GNSS Jamming Interact

These two threat categories frequently co-occur. State-sponsored infrastructure sabotage operations may use GNSS jamming to:

1. **Mask the sabotage vessel's true position** -- spoofing its AIS to show it elsewhere while it operates over a cable
2. **Disrupt monitoring systems** -- creating widespread interference that degrades situational awareness in the area
3. **Create confusion** -- multiple vessels reporting false positions makes it harder to identify the actual threat actor

Heimdal's scoring system captures this interaction through the **shadow-fleet escalation** on the cable_slow_transit rule: if a vessel near infrastructure also has spoofing anomalies, the combined score escalates further. Additionally, GNSS interference zones near infrastructure routes serve as an independent area-level warning that cable sabotage may be occurring even if the specific sabotage vessel hasn't been identified.

---

## All Scoring Rules Reference

| Rule ID | Category | Max Cap | Description |
|---------|----------|---------|-------------|
| `cable_slow_transit` | Infrastructure | 140 | Loitering at low speed in cable/pipeline corridor |
| `cable_alignment` | Infrastructure | 100 | Course aligned with cable bearing |
| `infra_speed_anomaly` | Infrastructure | 15 | Abrupt slowdown upon entering corridor |
| `spoof_land_position` | GNSS/Spoofing | 100 | Position reported on land |
| `spoof_impossible_speed` | GNSS/Spoofing | 100 | Physically impossible implied speed |
| `spoof_duplicate_mmsi` | GNSS/Spoofing | 100 | Same MMSI in two locations simultaneously |
| `spoof_frozen_position` | GNSS/Spoofing | 40 | Stationary coordinates while underway |
| `spoof_identity_mismatch` | GNSS/Spoofing | 100 | AIS identity contradicts registry data |
| `sanctions_match` | Sanctions | 100 | Direct or fuzzy match to sanctions lists |
| `gfw_ais_disabling` | Dark Activity | 100 | AIS disabled near sanctioned location |
| `gfw_encounter` | STS/Transfer | 100 | Vessel encounter in STS zone or with sanctioned partner |
| `gfw_loitering` | STS/Transfer | 40 | Slow-speed loitering in STS zone |
| `gfw_port_visit` | Port Activity | 40 | Visit to sanctioned or high-risk port |
| `gfw_dark_sar` | Dark Activity | 40 | SAR detection correlated with AIS gap |
| `ais_gap` | Dark Activity | 20 | AIS transmitter offline for 24h+ |
| `sts_proximity` | STS/Transfer | 15 | Near STS zone at low speed |
| `flag_hopping` | Identity | 40 | Frequent flag state changes |
| `vessel_age` | Structural | 10 | Tanker older than 20 years |
| `speed_anomaly` | Behavioural | 10 | Slow steaming or abrupt speed changes |
| `identity_mismatch` | Identity | 100 | Dimension or flag discrepancies |
| `draft_change` | Cargo | 40 | Sudden draught increase at sea |
| `destination_spoof` | Identity | 15 | Placeholder or fake AIS destination |
| `ownership_risk` | Ownership | 60 | Opaque ownership structure indicators |
| `insurance_class_risk` | Compliance | 60 | Missing or substandard insurance/classification |
| `network_score` | Network | varies | BFS proximity to sanctioned vessels in ownership/encounter graph |

---

## Event Lifecycle

Anomaly events follow a lifecycle rather than being fire-and-forget:

- **Active** -- condition is ongoing, event contributes to score
- **Ended** -- condition has ceased (vessel left corridor, speed normalised, etc.), event is archived
- **Superseded** -- replaced by a higher-severity event for the same rule

Only **active** events contribute to the aggregate score. Each rule implements a `check_event_ended()` method that the engine calls on every evaluation cycle to determine whether conditions have changed.

## Escalation for Repeat Offenders

Within a 30-day rolling window:

| Occurrence | Multiplier |
|------------|------------|
| 1st | 1.0x |
| 2nd | 1.5x |
| 3rd+ | 2.0x |

The per-rule cap scales with the multiplier, so a repeat cable_slow_transit offender can accumulate up to 280 points from that single rule (140 * 2.0).
