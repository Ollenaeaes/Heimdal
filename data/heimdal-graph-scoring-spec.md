# Heimdal Graph Scoring Specification

## Shadow Fleet Detection Through Open-Source Maritime Data Fusion

**Version:** 0.4  
**Author:** Olle / Heimdal  
**Date:** 2026-03-26

---

## 1. Purpose

This specification defines how Heimdal constructs a vessel risk graph from four open data sources and assigns a traffic light classification (Green / Yellow / Red / Purple) to tanker vessels operating in the Baltic Sea and Norwegian coastal areas. The system is designed to identify shadow fleet vessels — tankers transporting sanctioned cargo outside the G7 price cap compliance framework — using defensible inference chains that hold up in journalism and enforcement contexts.

The core insight is that shadow fleet detection does not require classified intelligence or proprietary satellite imagery. It requires combining open datasets that individually contain noise but collectively produce high-confidence classifications through geographic inference, regulatory absence, and behavioral pattern matching.

---

## 2. Data Sources

### 2.1 Paris MoU Inspection Data (Bulk XML, 2016–present)

**Source:** Paris MoU public bulk data (parismou.org), XML format.

**Join key:** IMO number.

**Fields used for scoring:**

| Field | Scoring relevance |
|-------|-------------------|
| IMO number | Universal join key |
| Ship name | Identity tracking, rename detection |
| Flag state (at inspection) | Flag history, transition detection |
| Ship type | Filter to tankers (crude, product, chemical) |
| Gross tonnage | Size classification (Aframax threshold ~80,000 GT) |
| Keel-laid date | Vessel age calculation |
| Classification society / RO | Class at time of inspection, transition detection |
| ISM company number | Fleet-level risk propagation |
| Owner | Ownership at time of inspection |
| P&I / insurance certificates | Insurer identification (CLC, bunker convention) |
| Inspection date | Recency calculation |
| Inspection port / country | Geographic activity pattern |
| Deficiency codes | Severity and category scoring |
| Deficiency count | Aggregate condition indicator |
| ISM-flagged deficiencies | Management system failure indicator |
| Detention (yes/no) | Severe condition indicator |
| Action taken codes | Deficiency severity classification |

**Derived signals:**

- **Last inspection recency:** Months since last Paris MoU inspection. For tankers of Aframax size or larger, absence >24 months is a strong negative signal.
- **RO at last inspection vs. current IACS status:** Detects class dropout when cross-referenced with IACS CSV.
- **ISM company fleet risk:** If any vessel under the same ISM company number is sanctioned (Purple) or Red, all vessels under that company inherit elevated risk.
- **P&I provider at last inspection:** IG club membership indicates price cap compliance infrastructure. Non-IG or absent P&I indicates operation outside the Western compliance framework.
- **Inspection trajectory:** A vessel with clean inspections 2016–2019 under an IACS-member RO and a white-list flag that then disappears from the database is a qualitatively different signal from a chronically substandard vessel.

### 2.2 OpenSanctions (FollowTheMoney Graph, updated daily)

**Source:** OpenSanctions bulk data or API (opensanctions.org). FollowTheMoney entity graph model.

**Join key:** IMO number (mapped to `Vessel` schema entities).

**Entity types used:**

| Schema type | Usage |
|-------------|-------|
| `Vessel` | Direct vessel match. Properties: name, flag, imoNumber, callSign, tonnage, type, buildDate, previousName, topics. |
| `Sanction` | Linked to Vessel via entity references. Contains sanctioning authority, programme, listing date. |
| `Company` | Vessel owners, operators, ISM managers. Linked via `Ownership` relationship entities. |
| `Person` | Beneficial owners, directors. Linked via `Directorship`, `Ownership`. |

**Topic tags on Vessel entities:**

| Tag | Meaning |
|-----|---------|
| `sanction` | Formally designated under a sanctions programme |
| `debarment` | Debarred from specific activities |
| `poi` | Person/entity of interest, not formally sanctioned |
| `crime.fraud` | Linked to fraud investigations |

**Additional tags observed in vessel search results:**

- "Shadow fleet" — tagged by data contributors (e.g., KSE list, national designations)
- "Maritime detention" — detained by port/coastal state authorities

**Derived signals:**

- **Direct sanctions match:** Vessel IMO maps to a `Vessel` entity with a linked `Sanction` entity → **Purple** (immediate, no further scoring needed).
- **Shadow fleet tag without formal sanction:** Vessel tagged as shadow fleet by a contributing dataset but no `Sanction` entity linked → strong Red indicator.
- **Ownership graph depth:** Number of `Ownership` hops between vessel and ultimate beneficial owner. Deep or opaque chains (3+ layers, shell companies in UAE/Hong Kong) are risk indicators.
- **Flag history via `previousName` and `country` arrays:** Multiple flag changes, especially to/from permissive registries (Gabon, Cameroon, Comoros, Palau, Cameroon).
- **Company creation date:** Owning `Company` entity created after February 2022 is a strong signal when combined with other indicators.
- **Cross-vessel ownership:** If the same `Company` entity owns multiple vessels, sanctions or Red status on one propagates risk to siblings.

### 2.3 IACS Vessels-in-Class (CSV, periodic updates)

**Source:** IACS public CSV (iacs.org.uk/membership/vessels-in-class/).

**Join key:** IMO number.

**Fields:**

| Field | Scoring relevance |
|-------|-------------------|
| IMO number | Universal join key |
| Ship name | Identity verification |
| Class society | Current classification society (IACS member) |
| Date of survey | Last survey date |
| Date of next survey | Survey compliance — lapsed = risk |
| Date of latest status | When class status last changed |
| Status code | In class / suspended / withdrawn |
| Reason for status | Why status changed |

**Derived signals:**

- **Not present in IACS CSV:** Vessel has no IACS-member classification. For a tanker of any significant size, this means either (a) classed by a non-IACS society, or (b) unclassed. Both are strong risk signals — over 90% of cargo-carrying tonnage is IACS-classed, and legitimate tanker operators maintain IACS class for insurance and charterer requirements.
- **Status: suspended or withdrawn:** Class lost, likely due to overdue surveys or unresolved conditions. Strong standalone risk signal.
- **Survey overdue:** Next survey date has passed without a new record. The vessel is technically out of compliance with its class requirements.
- **Class transition:** Vessel was IACS-classed at last Paris MoU inspection but is no longer in IACS CSV. Cross-reference timing with OpenSanctions ownership changes to identify shadow fleet transition window.

### 2.4 AIS Data (aisstream.io, real-time with gaps)

**Source:** aisstream.io WebSocket feed. Coverage is intermittent — not a complete AIS record.

**Join key:** IMO number and MMSI.

**Fields per position report:**

| Field | Scoring relevance |
|-------|-------------------|
| MMSI | Radio identity — encodes flag via MID |
| IMO number | Universal join key |
| Ship name | Identity verification |
| Latitude / Longitude | Position |
| SOG / COG | Speed and course |
| Navigation status | At anchor, underway, moored, etc. |
| Timestamp | Time of report |
| Destination (if available) | Declared destination from AIS static data |

**Derived signals — geographic inference:**

The Baltic Sea and Norwegian Arctic coast have constrained geography that enables origin inference for tanker traffic. The system exploits this by defining **terminal exclusion zones** — areas where legitimate hydrocarbon terminals exist — and **staging areas** — anchorage zones used by shadow fleet vessels.

---

## 3. Geographic Inference Model

### 3.1 Baltic Sea Origin Inference

**Principle:** The Baltic Sea has a limited number of non-Russian crude and product export terminals. If a laden tanker transits south from the Baltic and did not call at any non-Russian terminal, it loaded at a Russian port. The geography leaves no alternative explanation.

**Non-Russian Baltic export terminals (exhaustive for crude/product):**

| Terminal | Country | Approximate position |
|----------|---------|---------------------|
| Gdańsk / Naftoport | Poland | 54.36°N, 18.68°E |
| Butinge | Lithuania | 56.07°N, 21.07°E |
| Nynäshamn | Sweden | 58.90°N, 17.95°E |
| Finnish refineries (Porvoo/Naantali) | Finland | Various |
| Baltic state terminals | Estonia, Latvia, Lithuania | Various |

**Russian Baltic export terminals (primary):**

| Terminal | Approximate position |
|----------|---------------------|
| Primorsk | 60.35°N, 28.70°E |
| Ust-Luga | 59.68°N, 28.40°E |
| St. Petersburg area | 59.90°N, 30.20°E |

**Inference rule:** A tanker observed transiting south along the Swedish EEZ (east of Gotland or through the Danish Straits) that has no AIS record or port call record at any non-Russian Baltic terminal within the preceding voyage is classified as **Russian-origin**.

Port calls at non-Russian terminals produce records: PSC inspection records (Paris MoU), AIS arrival/departure signatures with low-speed mooring patterns, and often VTS reporting data. These vessels will have a "port call footprint" — a cluster of AIS positions at or near a terminal berth with navigation status "moored" or "at anchor." Absence of this footprint at any non-Russian terminal, combined with presence in the Baltic, implies Russian origin.

**Ballast repositioning filter:** A tanker entering the Baltic in ballast (high waterline, light draught if available, or inferred from AIS draught field) that then departs laden, and did not call at a non-Russian terminal, loaded in Russia. A legitimate tanker that discharged in Europe and wanted to reposition would not ballast to the Baltic unless it had business there — and the only crude loading business in the Baltic that doesn't leave a port call record is Russia.

### 3.2 Barents Sea / Norwegian Arctic Origin Inference

**Principle:** Melkøya (Hammerfest) is the only significant non-Russian hydrocarbon export terminal on the Norwegian Arctic coast. A laden tanker heading south past Finnmark that did not originate from Melkøya came from Murmansk or Belokamenka.

**Inference rule:** A tanker observed southbound off northern Norway, laden, with no AIS record at Melkøya, is classified as **Russian-origin** (Murmansk/Belokamenka).

### 3.3 Staging Area Detection (Loiter-Then-Vanish Pattern)

**Principle:** Shadow fleet vessels exhibit a characteristic behavioral pattern: they loiter at anchorage areas for 1–3 days before proceeding to Russian ports (where AIS is switched off or coverage is lost).

**Known staging areas:**

| Area | Description | Typical pattern |
|------|-------------|-----------------|
| Gulf of Finland approaches | South of Helsinki, west of Gogland | Anchor 1–3 days, then proceed to Primorsk/Ust-Luga (AIS lost) |
| Kola Bay approaches | Off Murmansk | Anchor before loading at Murmansk/Belokamenka |
| South of Gotland | Central Baltic | STS transfer zone |
| Skagen / Kattegat approaches | Danish Straits | Waiting area before/after Baltic transit |

**Detection rule:** A tanker observed at anchor (navigation status = 1 or SOG < 1.0 kn) in a defined staging area for >12 hours, which then either (a) goes dark (no AIS for >6 hours while expected to be in coverage), or (b) proceeds toward a Russian port approach, triggers a **staging area flag**.

### 3.4 STS Transfer Detection

**Principle:** Ship-to-ship transfers in the Baltic or Arctic require two vessels to be co-located at very low speed for an extended period. If one vessel is already flagged and transfers cargo to a vessel not yet flagged, the receiving vessel inherits risk.

**Detection rule:** Two tankers observed within 500m of each other, both at SOG < 2.0 kn, for >2 hours, outside of a recognized port or terminal area, triggers an **STS flag** on the non-flagged vessel. This is only relevant in the Baltic Sea and Arctic Sea operational areas.

### 3.5 MMSI / Flag Consistency Check

**Principle:** The MMSI Maritime Identification Digit (digits 1–3) encodes the flag state that issued the radio licence. A legitimate re-flagging includes MMSI reassignment. A stale MMSI indicates either the new flag state didn't issue a new licence (common with fraudulent registries) or the vessel didn't bother to update.

**Detection rule:** If the MMSI MID maps to a different flag state than the flag recorded in OpenSanctions or the most recent Paris MoU inspection, flag a **MMSI/flag mismatch**. Cross-reference against known MID assignments (ITU MID table).

---

## 4. Graph Construction

### 4.1 What Is a Node

Nodes are entities — things that exist independently. Each node has a **type** and a set of **attributes** (properties stored on the node itself).

| Node type | What it represents | Attributes |
|-----------|-------------------|------------|
| **Vessel** | A physical ship | `imo` (primary key), `name`, `mmsi`, `ship_type`, `gross_tonnage`, `build_year`, `score` (computed), `classification` (green/yellow/red/purple), `last_psc_date`, `last_psc_port`, `deficiency_count`, `ism_deficiency` (boolean), `detained` (boolean), `last_seen_date`, `last_seen_lat`, `last_seen_lon` |
| **Company** | A legal entity that owns, manages, or operates vessels | `name`, `jurisdiction`, `incorporation_date`, `ism_company_number` (if this company is an ISM manager), `company_type` (owner / ism_manager / operator), `opensanctions_id` |
| **Person** | A beneficial owner or director | `name`, `nationality`, `date_of_birth`, `opensanctions_id` |
| **ClassSociety** | A classification society (e.g., Lloyd's Register, DNV) | `name`, `iacs_member` (boolean) |
| **FlagState** | A country whose flag a vessel flies | `name`, `iso_code`, `paris_mou_list` (white / grey / black) |
| **PIClub** | A Protection & Indemnity insurance provider | `name`, `ig_member` (boolean) |
| **SanctionProgramme** | A specific sanctions designation list | `name`, `authority` (EU / UK / US / UN), `programme_id` |

**What is NOT a node:**

- **PSC inspection records** are not nodes. An inspection is an *event* that produces attributes on the Vessel node (`last_psc_date`, `deficiency_count`, `detained`) and creates or updates edges from the Vessel to other nodes (CLASSED_BY, INSURED_BY, FLAGGED_AS — each timestamped to the inspection date). A single inspection may update three edges simultaneously.

- **AIS position reports** are not nodes. They are raw data that gets processed into attributes on the Vessel (`last_seen_date`, `last_seen_lat`, `last_seen_lon`) and into scored events (staging area loiter, loiter-then-vanish) that contribute to the vessel's `score`. The one exception: an STS (ship-to-ship transfer) event creates an **edge** between two Vessel nodes.

- **Geographic zones** (staging areas, terminal exclusion zones) are not nodes. They are reference geometry used by the pattern detection engine. The results of geographic inference appear as attributes on the Vessel or as edges (e.g., an STS_PARTNER edge).

### 4.2 What Is an Edge

Edges are relationships. They connect two nodes, always have a direction (from → to), and carry their own attributes. The most important edge attribute is the **time range** (`from_date`, `to_date`) — this is what makes the temporal playback in §9.3 work.

| Edge type | From → To | What it means | Attributes |
|-----------|-----------|---------------|------------|
| **OWNED_BY** | Vessel → Company | This company owns this vessel | `from_date`, `to_date` (null if current) |
| **MANAGED_BY** | Vessel → Company | This company is the ISM safety manager for this vessel | `from_date`, `to_date` |
| **CLASSED_BY** | Vessel → ClassSociety | This classification society certifies the vessel's structural and mechanical condition | `from_date`, `to_date`, `status` (active / suspended / withdrawn) |
| **FLAGGED_AS** | Vessel → FlagState | The vessel is registered under this flag | `from_date`, `to_date` |
| **INSURED_BY** | Vessel → PIClub | This P&I club provides liability insurance for the vessel | `from_date`, `to_date` |
| **SANCTIONED_UNDER** | Vessel → SanctionProgramme | The vessel is formally designated under this sanctions programme | `listing_date` |
| **DIRECTED_BY** | Company → Person | This person is a director of this company | `from_date`, `to_date` |
| **OWNED_BY** | Company → Company | Parent company owns subsidiary (corporate chain) | `from_date`, `to_date` |
| **OWNED_BY** | Company → Person | This person is a beneficial owner of this company | `from_date`, `to_date` |
| **STS_PARTNER** | Vessel → Vessel | These two vessels conducted a ship-to-ship cargo transfer (detected from AIS co-location) | `event_date`, `latitude`, `longitude`, `duration_hours` |

**Note on SIBLING_VESSEL:** This is a *derived* relationship, not a stored edge. Two vessels are siblings if they both have OWNED_BY or MANAGED_BY edges pointing to the same Company node. The graph query engine resolves this at query time (`MATCH (v1:Vessel)-[:MANAGED_BY]->(c:Company)<-[:MANAGED_BY]-(v2:Vessel)`). There is no need to materialise sibling edges — they emerge naturally from the graph structure.

### 4.3 How the Four Data Sources Populate the Graph

Each data source creates or updates specific nodes and edges:

**Paris MoU inspections** create/update:
- Vessel node attributes: `last_psc_date`, `last_psc_port`, `deficiency_count`, `ism_deficiency`, `detained`
- CLASSED_BY edge (Vessel → ClassSociety) with `from_date` = inspection date
- FLAGGED_AS edge (Vessel → FlagState) with `from_date` = inspection date
- INSURED_BY edge (Vessel → PIClub) with `from_date` = inspection date
- MANAGED_BY edge (Vessel → Company) using the ISM company number — this creates the Company node if it doesn't exist
- If the inspection shows a *different* ClassSociety, FlagState, or PIClub than the previous inspection, the old edge gets a `to_date` and a new edge is created. This is how transitions are recorded.

**OpenSanctions** creates/update:
- Vessel nodes (matched on IMO number)
- Company nodes (from ownership graph)
- Person nodes (beneficial owners, directors)
- OWNED_BY edges (Vessel → Company, Company → Company, Company → Person)
- DIRECTED_BY edges (Company → Person)
- SANCTIONED_UNDER edges (Vessel → SanctionProgramme)
- Vessel attributes: topics (shadow_fleet, sanctioned_entity, maritime_detention)
- Company attributes: `jurisdiction`, `incorporation_date`

**IACS CSV** creates/updates:
- CLASSED_BY edge: updates `status` attribute (active / suspended / withdrawn) and `to_date` if class was lost
- ClassSociety node: `iacs_member` = true
- If a vessel is NOT in the IACS CSV, no CLASSED_BY edge to any IACS member exists with a null `to_date` — this absence is the signal

**AIS data** creates/updates:
- Vessel node attributes: `last_seen_date`, `last_seen_lat`, `last_seen_lon`, `mmsi`
- STS_PARTNER edges between two Vessel nodes (from co-location detection)
- Vessel score inputs: staging area events, loiter-then-vanish patterns, transit-without-port-call inferences (these feed into the scoring engine but are not separate graph entities)

### 4.4 Temporal Layering

Every edge that represents a changeable relationship has `from_date` and `to_date`. This enables:

- **Transition detection:** "This vessel was classed by Lloyd's Register from 2015-03 to 2022-07, then by a non-IACS society from 2022-08. The ownership changed to a Dubai shell company in 2022-06 — one month before the class change."

- **Temporal playback:** The graph visualisation (§9.3) uses these dates to animate the network assembling over time. When the slider reaches 2022-06, the OWNED_BY edge to the new company appears. When it reaches 2022-07, the CLASSED_BY edge to Lloyd's Register disappears and the new one appears.

- **Fleet-level timeline:** By querying all vessels connected to a Company node, you can see when each vessel in the fleet transitioned — revealing coordinated build-out patterns where multiple vessels change flag, class, and owner within weeks of each other.

### 4.5 Concrete Example

Clicking "See Graph" on a vessel returns a subgraph. Here is what the data looks like for a hypothetical Red-classified vessel:

**Nodes returned:**

| Node | Type | Key attributes |
|------|------|---------------|
| EXAMPLE STAR (IMO 9876543) | Vessel | score: 9, classification: red, build_year: 2004, gross_tonnage: 105000, last_psc_date: 2019-11-14 |
| Gulf Maritime LLC | Company | jurisdiction: UAE (Dubai), incorporation_date: 2022-08-15, company_type: owner |
| Eastern Holdings Ltd | Company | jurisdiction: Marshall Islands, incorporation_date: 2022-06-01, company_type: holding |
| Person X | Person | nationality: undisclosed |
| EXAMPLE MOON (IMO 9876544) | Vessel | score: n/a, classification: purple (sanctioned) |
| EXAMPLE SUN (IMO 9876545) | Vessel | score: 5, classification: yellow |
| Unrecognised Class Bureau | ClassSociety | iacs_member: false |
| Gabon | FlagState | paris_mou_list: black |
| Lloyd's Register | ClassSociety | iacs_member: true |
| Panama | FlagState | paris_mou_list: white |
| Gard | PIClub | ig_member: true |
| EU Shadow Fleet List | SanctionProgramme | authority: EU |

**Edges returned:**

| From | Edge type | To | Key attributes |
|------|-----------|-----|---------------|
| EXAMPLE STAR | OWNED_BY | Gulf Maritime LLC | from_date: 2022-09-01 |
| EXAMPLE STAR | FLAGGED_AS | Panama | from_date: 2015-03, to_date: 2022-09 |
| EXAMPLE STAR | FLAGGED_AS | Gabon | from_date: 2022-10-01 |
| EXAMPLE STAR | CLASSED_BY | Lloyd's Register | from_date: 2015-03, to_date: 2022-10 |
| EXAMPLE STAR | CLASSED_BY | Unrecognised Class Bureau | from_date: 2022-11-01 |
| EXAMPLE STAR | INSURED_BY | Gard | from_date: 2017-05, to_date: 2019-11-14 |
| Gulf Maritime LLC | OWNED_BY | Eastern Holdings Ltd | from_date: 2022-08-15 |
| Eastern Holdings Ltd | OWNED_BY | Person X | from_date: 2022-06-01 |
| EXAMPLE MOON | OWNED_BY | Gulf Maritime LLC | from_date: 2022-09-15 |
| EXAMPLE SUN | OWNED_BY | Gulf Maritime LLC | from_date: 2022-10-01 |
| EXAMPLE MOON | SANCTIONED_UNDER | EU Shadow Fleet List | listing_date: 2025-06-15 |

**When you press "Play" on the temporal slider:**

1. **2022-06** — Eastern Holdings Ltd node appears (incorporation)
2. **2022-08** — Gulf Maritime LLC node appears (incorporation), OWNED_BY edge to Eastern Holdings appears
3. **2022-09** — EXAMPLE STAR's old OWNED_BY edge ends, new OWNED_BY edge to Gulf Maritime appears. EXAMPLE MOON also connects to Gulf Maritime.
4. **2022-10** — EXAMPLE STAR's Panama flag edge ends, Gabon flag edge appears. EXAMPLE SUN connects to Gulf Maritime.
5. **2022-11** — EXAMPLE STAR's Lloyd's Register edge ends, Unrecognised Class Bureau edge appears
6. **2023-onwards** — AIS-derived events: EXAMPLE STAR's node glows briefly when staging area loiter events occur
7. **2025-06** — EXAMPLE MOON turns purple, SANCTIONED_UNDER edge to EU programme appears

The viewer watches the network being built: shell companies first, then vessel acquisitions, then flag changes, then class dropout, then operational activity, then enforcement catches up. The pattern is visible without any explanation needed.

---

## 5. Traffic Light Classification

### 5.1 Colour Definitions

| Colour | Meaning | Action threshold |
|--------|---------|-----------------|
| **Purple** | Sanctioned vessel. Direct IMO match against OpenSanctions `Sanction` entity. | Automated. No manual review needed. Report to relevant authorities if operating in monitored waters. |
| **Red** | High confidence shadow fleet indicator. Multiple independent signals across data sources. | Flag for attention. Manual Equasis lookup recommended to confirm ownership chain and P&I status. |
| **Yellow** | Single strong signal or partial pattern. Warrants investigation but could have legitimate explanation. | Queue for manual review when capacity allows. |
| **Green** | No indicators, or indicators explained by legitimate activity. | No action. |

### 5.2 Purple Classification (Automated, Deterministic)

**Rule:** Vessel IMO number matches an OpenSanctions `Vessel` entity that has at least one linked `Sanction` entity (i.e., formally designated under a sanctions programme by EU, UK, US, or other authority).

Purple is a direct lookup, not a score. It is absolute and not subject to the scoring model below.

### 5.3 Signal Catalogue

Each signal has a **weight** and a **category**. Signals are grouped into four categories corresponding to the four data sources. Weights reflect standalone diagnostic value.

#### Category A: Paris MoU Signals

| Signal ID | Description | Weight | Condition |
|-----------|-------------|--------|-----------|
| A1 | No Paris MoU inspection in ≥24 months | 3 | Tanker, GT ≥ 50,000 |
| A2 | No Paris MoU inspection in ≥36 months | 4 | Tanker, any size |
| A3 | Last inspection: detained | 2 | — |
| A4 | Last inspection: ≥5 deficiencies | 1 | — |
| A5 | Last inspection: ISM non-conformity | 2 | — |
| A6 | P&I at last inspection: non-IG club | 2 | — |
| A7 | P&I at last inspection: not identifiable | 3 | — |
| A8 | RO changed from IACS member to non-IACS between inspections | 3 | Requires ≥2 inspections |
| A9 | Flag changed between inspections to permissive registry | 2 | See flag list §5.5 |
| A10 | ISM company has another vessel at Purple or Red | 2 | Cross-vessel propagation |
| A11 | Inspection trajectory: clean history then disappearance | 3 | ≥3 clean inspections pre-2020, none after |

#### Category B: OpenSanctions Signals

| Signal ID | Description | Weight | Condition |
|-----------|-------------|--------|-----------|
| B1 | Tagged "shadow fleet" (no formal Sanction) | 4 | — |
| B2 | Owning company created after 2022-02-01 | 2 | — |
| B3 | ≥3 ownership layers (company chain depth) | 2 | — |
| B4 | Owner also owns a Purple vessel | 3 | Cross-vessel propagation |
| B5 | Vessel renamed (previousName exists) | 1 | Standalone weak; strong with B2 |
| B6 | Multiple flag changes in entity history | 2 | ≥3 flags recorded |
| B7 | Owner/company jurisdiction: UAE, Hong Kong, or similar opacity hub | 1 | Standalone weak |

#### Category C: IACS Signals

| Signal ID | Description | Weight | Condition |
|-----------|-------------|--------|-----------|
| C1 | Not present in IACS CSV | 3 | Tanker, GT ≥ 50,000 |
| C2 | Class suspended | 3 | — |
| C3 | Class withdrawn | 4 | — |
| C4 | Survey overdue (next survey date lapsed) | 2 | — |
| C5 | Class society changed from IACS to non-IACS | 3 | Compared against Paris MoU historical RO |

#### Category D: AIS Signals

| Signal ID | Description | Weight | Condition |
|-----------|-------------|--------|-----------|
| D1 | Staging area loiter (Gulf of Finland approaches, ≥12h) | 3 | Navigation status: anchored or SOG < 1.0 kn |
| D2 | Staging area loiter (Kola Bay approaches, ≥12h) | 3 | Same as D1 |
| D3 | Baltic transit, no non-Russian port call footprint | 4 | See §3.1 inference rule |
| D4 | Barents transit, no Melkøya origin | 4 | See §3.2 inference rule |
| D5 | MMSI MID / flag mismatch | 2 | — |
| D6 | STS event with a Purple or Red vessel | 4 | See §3.4 detection rule |
| D7 | Loiter-then-vanish pattern (staging area → dark period ≥6h toward Russian port) | 4 | Combined D1/D2 with subsequent AIS gap |

### 5.4 Scoring Rules

**Total score** = sum of all triggered signal weights.

| Score range | Classification | Rationale |
|-------------|---------------|-----------|
| 0 | Green | No indicators |
| 1–3 | Green | Weak or isolated signal, likely noise |
| 4–5 | Yellow | Single strong signal or two moderate signals. Worth monitoring. |
| 6–8 | Red | Multiple independent signals. High confidence. |
| ≥9 | Red | Strong multi-source pattern. |

**Override rules (bypass score):**

| Condition | Result | Reason |
|-----------|--------|--------|
| B1 (OpenSanctions shadow fleet tag) alone | Minimum Yellow | Someone has already flagged this vessel |
| D3 or D4 (geographic origin inference: Russian) + A7 or A6 (no IG P&I) | Minimum Red | Confirmed Russian cargo outside compliance framework |
| D6 (STS with Purple/Red vessel) | Minimum Red | Cargo chain contamination |
| C3 (class withdrawn) + A1 (no PSC 24 months) | Minimum Yellow | No oversight of any kind |
| A10 or B4 (sibling/owner vessel at Purple) | Minimum Yellow | Fleet-level contamination |

**AIS gap exclusion:** AIS gaps alone (without staging area context or geographic inference) do NOT contribute to scoring. Gaps in aisstream.io coverage are too common to be diagnostic without supporting geographic context. The system scores *patterns* (loiter-then-vanish, transit-without-port-call), not raw signal absence.

### 5.5 Permissive Flag Registry List

Flags that elevate risk when combined with other signals. Membership on this list alone is insufficient for Yellow — it is a multiplier, not a standalone indicator.

Current list (update as registries shift):

- Gabon
- Cameroon
- Comoros
- Palau
- Cook Islands
- Djibouti
- Gambia
- Saint Kitts and Nevis
- Sierra Leone
- Mongolia
- Malawi

This list is derived from flags disproportionately represented in the OpenSanctions vessel search results for shadow fleet entities. It should be reviewed quarterly against new Paris MoU black/grey list publications and OpenSanctions data.

---

## 6. Manual Enrichment Step (Equasis Lookup)

### 6.1 When to Trigger

Equasis lookup is a **manual** step performed by an analyst. It is NOT part of the automated pipeline. It is triggered when:

- A vessel is classified **Yellow** and the analyst wants to confirm or promote to Red.
- A vessel is classified **Red** and the analyst wants to build an evidence package for external communication (journalism, enforcement tip).
- A vessel's P&I status is unknown (no Paris MoU record exists) and the P&I is the missing piece for the geographic inference chain (§3.1, §3.2).

### 6.2 What Equasis Adds

| Data point | Why it matters |
|-----------|---------------|
| Current P&I club | Confirms or denies IG membership — the compliance chain link |
| Full ownership chain | Goes beyond OpenSanctions (which may lag real-world changes) |
| Class history with transfer dates | Precise timeline of class transitions, fills IACS CSV gaps |
| Flag history with dates | Precise re-flagging timeline |
| ISM DOC holder | May differ from registered owner; identifies actual management |
| Survey status | Current survey compliance from the class society's perspective |

### 6.3 What Equasis Does NOT Justify

Equasis should not be used for bulk screening. It is a per-vessel manual lookup. The automated pipeline (Paris MoU + OpenSanctions + IACS + AIS) should surface no more than 20–30 vessels for manual review at any given time. If the Yellow population exceeds this, tighten scoring thresholds.

---

## 7. Output Format

### 7.1 Vessel Risk Card

Each vessel in the system produces a risk card:

```
┌──────────────────────────────────────────────┐
│  [PURPLE/RED/YELLOW/GREEN]                   │
│                                              │
│  VESSEL NAME (IMO 1234567)                   │
│  MMSI: 123456789 | Flag: XX | GT: 80,000    │
│  Type: Crude Oil Tanker | Built: 2004        │
│                                              │
│  Score: 11 (Red)                             │
│  Triggered signals: A1, A7, B2, C1, D3      │
│                                              │
│  Paris MoU: Last inspection 2019-03-14       │
│    RO: Lloyd's Register | P&I: Unknown       │
│    Deficiencies: 2 | Detained: No            │
│                                              │
│  IACS: Not in register                       │
│                                              │
│  OpenSanctions: Entity found                 │
│    Topics: shadow_fleet                      │
│    Owner: [Company], incorporated 2022-08    │
│                                              │
│  AIS: Last seen 2026-03-20                   │
│    Baltic transit observed, no non-Russian    │
│    port call footprint detected              │
│                                              │
│  [Manual Equasis lookup: NOT YET PERFORMED]  │
└──────────────────────────────────────────────┘
```

### 7.2 Evidence Chain

For Red and Purple vessels, the system should be able to produce a narrative evidence chain suitable for external communication:

> Vessel X (IMO Y) was observed transiting the Swedish EEZ southbound on [date]. AIS data shows no port call at any non-Russian Baltic terminal during the preceding voyage. The vessel has no Paris MoU inspection record since [date]. It is not classified by any IACS member society. The vessel's owning entity was incorporated in [jurisdiction] in [date]. No International Group P&I coverage is identifiable.

This chain uses only open data and defensible geographic inference. No tool branding. No exclamation points. No AI-sounding constructions.

---

## 8. Pipeline Architecture — Split Compute Model

Heimdal runs on a constrained VPS (Hostinger, ~$100/month). The server cannot handle the initial historical data build — parsing years of Paris MoU XML, building the full OpenSanctions graph, and computing all AIS-derived signals from scratch. The architecture therefore splits into two phases:

### 8.1 Phase 1: Historical Bootstrap (Local Machine — MacBook M4)

The initial graph build runs locally. This is a one-time batch job (re-run if data sources change structurally) that produces a serialised graph database which is then transferred to the VPS.

**Steps:**

1. **Parse Paris MoU bulk XML (2016–present):** Extract all inspection records. Normalise IMO numbers, flag codes, RO names. Build per-vessel inspection timelines. Identify ISM company numbers and build fleet groupings.

2. **Ingest OpenSanctions bulk data:** Download the full FtM entity dump. Filter to `Vessel`, `Company`, `Person`, `Sanction`, `Ownership` schema types. Build the ownership graph with all edges. Tag vessels with topic labels.

3. **Ingest IACS CSV:** Parse the vessels-in-class file. Index by IMO number. Flag status codes (in class / suspended / withdrawn), compute survey overdue flags.

4. **Process historical AIS data:** Replay any archived AIS position data. Compute staging area events, loiter-then-vanish patterns, transit-without-port-call inferences, STS co-location events. Store as per-vessel event timelines.

5. **Build the graph:** Join all four sources on IMO number. Create vessel nodes with full attribute histories. Create edges (CLASSED_BY, FLAGGED_BY, INSURED_BY, MANAGED_BY, OWNED_BY, SANCTIONED_UNDER, SIBLING_VESSEL, STS_PARTNER). Compute all signal scores.

6. **Export:** Serialise the graph to a format the VPS can load (FalkorDB dump, or a JSON-lines file that the VPS ingestion script can replay). Transfer to VPS via SCP/rsync.

**Local compute requirements:** The M4 MacBook handles this comfortably. Paris MoU XML parsing is CPU-bound but finite (~10 years of data). OpenSanctions bulk is ~500MB JSON. IACS CSV is tiny. AIS historical replay depends on archive size but is embarrassingly parallel.

### 8.2 Phase 2: Daily Operations (VPS — Hostinger)

The VPS runs lightweight daily update jobs that incrementally maintain the graph. These jobs are small and bounded.

| Job | Schedule | What it does | Resource profile |
|-----|----------|--------------|-----------------|
| Paris MoU delta | Weekly (or on release) | Fetch new/updated inspections since last run. Parse, score, update affected vessel nodes. | Low CPU, low memory. Incremental — only new records. |
| OpenSanctions sync | Daily (cron, early morning) | Pull the daily delta from OpenSanctions API or bulk delta file. Update vessel entities, sanctions, ownership edges. Re-score affected vessels. | Low CPU. Delta files are small. |
| IACS CSV refresh | Weekly | Re-download CSV. Diff against previous version. Update class status for changed vessels. Re-score. | Trivial. CSV is <10MB. |
| AIS stream listener | Continuous (background daemon) | WebSocket connection to aisstream.io. Filter to area of interest (Baltic, Norwegian coast, Barents approaches). Store position reports. Run pattern detection on rolling window (staging area, loiter-then-vanish, STS co-location). | Low CPU (filtering is cheap). Memory for rolling window ~100MB. Main cost is the WebSocket connection. |
| Scoring engine | Triggered by any source update | Re-evaluate signals for affected vessels only. Update traffic light classification. | Negligible — scoring is arithmetic on pre-computed signals. |

### 8.3 Data Flow Diagram

```
═══════════════════════════════════════════════════════════
  PHASE 1: LOCAL (MacBook M4) — one-time bootstrap
═══════════════════════════════════════════════════════════

  Paris MoU XML ──┐
  OpenSanctions ──┤
  IACS CSV ───────┤──→ [Graph Builder] ──→ [FalkorDB dump]
  AIS archive ────┘                              │
                                                 │ scp/rsync
                                                 ▼
═══════════════════════════════════════════════════════════
  PHASE 2: VPS (Hostinger) — daily operations
═══════════════════════════════════════════════════════════

  ┌──────────────┐
  │ FalkorDB     │◄── loaded from bootstrap dump
  │ (graph store)│
  └──────┬───────┘
         │
    ┌────┴────────────────────────────────────┐
    │                                         │
    ▼                                         ▼
  ┌────────────┐  ┌────────────┐  ┌────────────────────┐
  │ Daily sync │  │ Weekly sync│  │ AIS stream listener│
  │ OpenSanct. │  │ MoU + IACS │  │ (aisstream.io WS)  │
  └─────┬──────┘  └─────┬──────┘  └─────────┬──────────┘
        │               │                    │
        └───────┬───────┘                    │
                ▼                            ▼
        ┌──────────────┐            ┌──────────────┐
        │ Scoring      │◄───────────│ Pattern      │
        │ Engine       │            │ Detection    │
        └──────┬───────┘            └──────────────┘
               │
               ▼
        ┌──────────────┐
        │ API / Web UI │
        │              │
        │  /map        │ ← Leaflet map with vessel positions
        │  /vessel/:id │ ← Vessel risk card + "See Graph" button
        │  /graph/:id  │ ← Sigma.js subgraph for single vessel
        │  /networks   │ ← Sigma.js full network explorer
        └──────────────┘
```

### 8.4 Update Cadence

| Source | Update frequency | Runs on | Notes |
|--------|-----------------|---------|-------|
| Paris MoU bulk XML (historical) | Once | Local | Bootstrap only |
| Paris MoU delta | Weekly | VPS | Incremental new records |
| OpenSanctions | Daily | VPS | Delta sync |
| IACS CSV | Weekly | VPS | Full re-diff (file is tiny) |
| AIS | Real-time (streaming) | VPS | WebSocket daemon |
| Scoring engine | On any source update | VPS | Re-score affected vessels only |
| Graph re-bootstrap | As needed | Local | If data model changes or corruption |

---

## 9. Graph Visualisation Layer

### 9.1 Technology Stack

| Component | Library | Why |
|-----------|---------|-----|
| **Graph rendering** | Sigma.js v3 | WebGL-based rendering. Handles thousands of nodes/edges without DOM overhead. Critical for a constrained VPS — rendering is offloaded to the client's GPU, not the server's CPU. |
| **Graph data model** | Graphology | The data backend for Sigma.js. Provides the in-memory graph structure in the browser, plus built-in algorithms: ForceAtlas2 layout, community detection, centrality measures, shortest path. |
| **React integration** | @react-sigma/core | React bindings for Sigma.js with TypeScript support. Hooks-based API (`useLoadGraph`, `useRegisterEvents`). Fits the existing Heimdal frontend pattern. |
| **Layout** | graphology-layout-forceatlas2 | Force-directed layout that naturally clusters connected components. Vessels sharing an ISM company or owner will pull together. Disconnected components drift apart. Runs as a web worker to keep UI responsive. |
| **Server-side graph** | FalkorDB | Cypher-compatible graph database. Stores the full graph. Serves subgraph queries to the frontend. Already in the Heimdal stack. |

### 9.2 User Interaction Model

#### Core principle: the graph is a fleet, not a vessel neighbourhood

When the user clicks "See Graph" on a vessel, they are not asking "show me this vessel's connections." They are asking "show me the fleet this vessel belongs to." The vessel is the entry point to identify *which* connected component — then the entire component is loaded.

A connected component is every node reachable from the selected vessel through any chain of edges. If vessel A is owned by Company X, and Company X also owns vessels B and C, and vessel C is managed by ISM Company Y, and ISM Company Y also manages vessel D — then A, B, C, D, Company X, ISM Company Y, and all their flags, class societies, P&I clubs, persons, and sanctions are one component. That's the fleet.

This is what makes the graph useful. You don't see one vessel's story — you see how the entire operation was assembled, how many vessels are in it, who controls them, and whether the pattern of changes is coordinated.

**Entry point 1: Vessel map → "See Graph" button**

The user is on Heimdal's Leaflet map layer. They select a vessel. The risk card appears (§7.1). The "See Graph" button triggers:

```
GET /api/graph/fleet/{imo_number}
```

The API finds the connected component that contains this vessel and returns the entire component. The response is a Graphology-compatible JSON document (nodes array + edges array with all attributes, plus a separate events array for the timeline).

The frontend loads the component into a Graphology instance, runs ForceAtlas2 layout (web worker, 3-5 seconds), and renders via Sigma.js. The selected vessel is highlighted — but all vessels in the fleet are visible.

If the component is very large (>200 nodes), the API can optionally truncate by returning only the core ownership/management skeleton and omitting historical flag/class nodes that are no longer active. This is a performance guardrail, not the default.

**Entry point 2: /networks endpoint — all flagged fleets**

```
GET /api/graph/networks?min_score=4
```

Returns all connected components where at least one vessel scores Yellow or above. Each component is a separate cluster. The frontend renders all clusters simultaneously — ForceAtlas2 naturally separates disconnected components into visual islands.

This is the investigation view. The analyst sees the full landscape: which fleets are largest, which share unexpected connections, where the enforcement chokepoints are. Clicking any vessel node in any cluster loads that fleet's detail view.

**Visual encoding:**

| Node type | Shape/colour | Size |
|-----------|-------------|------|
| Vessel (Green) | Circle, green | Proportional to GT |
| Vessel (Yellow) | Circle, amber | Proportional to GT |
| Vessel (Red) | Circle, red | Proportional to GT |
| Vessel (Purple) | Circle, purple with border | Proportional to GT |
| Company (ISM manager) | Diamond, dark grey | Fixed |
| Company (owner) | Square, blue-grey | Fixed |
| Person | Triangle, light grey | Fixed |
| ClassSociety | Hexagon, teal | Fixed |
| SanctionProgramme | Star, red | Fixed |
| FlagState | Small circle, flag colour | Fixed small |
| PIClub | Rounded square, green if IG member, orange if not | Fixed |

| Edge type | Style |
|-----------|-------|
| OWNED_BY | Solid, medium weight |
| MANAGED_BY (ISM) | Solid, thick weight |
| CLASSED_BY | Dashed, thin |
| SANCTIONED_UNDER | Solid red, thick |
| STS_PARTNER | Solid orange, thick |
| FLAGGED_AS | Dotted, thin |
| INSURED_BY | Dotted, medium |
| DIRECTED_BY | Thin grey |

**Interaction (always available, including during playback):**

- **Hover** on any node: highlight all edges connected to it, dim everything else. Show a tooltip with the node's name and type. This works at any point in the timeline — paused, playing, or scrubbing.
- **Click** on any node: open a detail panel showing all attributes. For vessels: the risk card. For companies: incorporation date, jurisdiction, linked vessels, flags. For persons: nationality, linked companies. For sanctions: programme name, listing date, authority.
- **Click** on a vessel node: the detail panel includes a "Go to this vessel" link that reloads the map view centred on that vessel, and a "Refocus graph" option that re-queries the fleet from this vessel's perspective (useful if the component was truncated).
- **Drag** any node: manually reposition it. ForceAtlas2 respects pinned positions.
- **Zoom / pan**: standard scroll-to-zoom, drag-to-pan on the canvas background.

### 9.3 Temporal Playback ("Play It Forward")

The timeline is not a video. It is an interactive state machine. At every point in the timeline, the graph is fully interactive — you can pause, hover, click, inspect, drag nodes, zoom, and scrub to any other point in time. The playback just controls which temporal state the graph displays.

#### Starting State

When the fleet graph first loads, it shows the **current state** — all nodes and edges that are active today, with full colour and styling. This is the default because the user arrived here from a risk card and wants to understand the current situation.

The timeline slider is positioned at "now." The user can either press Play (which rewinds to the start and plays forward) or drag the slider backward manually to explore the history.

#### What the Timeline Controls

The slider represents a date. At any slider position, the graph shows:

- **Active edges:** Edges where `from_date` ≤ slider date AND (`to_date` is null OR `to_date` > slider date). These are shown in full colour with the styling from §9.2.
- **Ended edges:** Edges where `to_date` ≤ slider date. These are hidden entirely (not shown as faded — they're gone, they were replaced by something else or the relationship ended).
- **Not-yet-existing edges:** Edges where `from_date` > slider date. Hidden.
- **Nodes:** A node is visible if it has at least one visible edge at the current slider date, OR if it is a Vessel node (vessels are always visible once they enter the fleet — they don't disappear, they accumulate changes).

This means dragging the slider backward *removes* the recent changes and reveals the earlier state. Drag it back far enough and you see the fleet as it was before the transition: vessels classed by IACS members, flagged under white-list states, owned by the pre-acquisition entities. Drag it forward and you watch the transition happen.

#### Playback Animation

When the user presses **Play**, the slider rewinds to the earliest event in the fleet's timeline and advances automatically. As the slider moves forward through time:

| What happens at each event | Visual effect |
|---------------------------|--------------|
| New Company node enters the fleet (incorporation) | Node fades in at the graph periphery. ForceAtlas2 pulls it toward its future connections. |
| Vessel ownership transfers (new OWNED_BY edge) | New edge **draws** as an animated line from vessel to new owner (~0.5s). Old OWNED_BY edge simultaneously fades out. |
| Flag changes (new FLAGGED_AS edge) | New flag node appears if not already present, edge draws in. Old flag edge fades out. |
| Class changes (new CLASSED_BY edge) | New edge draws in. Old class edge fades out. |
| Class withdrawn / suspended (CLASSED_BY edge ends with no replacement) | Edge turns **red briefly** (flash, ~0.3s), then disappears. This visual emphasis distinguishes a loss event from a quiet replacement. |
| P&I dropped (INSURED_BY edge ends with no replacement) | Same red flash treatment. The absence of a replacement edge is the signal — the vessel now has no visible INSURED_BY edge. |
| New vessel acquired into the fleet | Vessel node fades in at the periphery. OWNED_BY edge draws inward toward the Company node that already exists. The cluster grows visibly. |
| STS transfer detected | Orange STS_PARTNER edge draws between two vessel nodes. Both vessels pulse briefly. |
| Vessel sanctioned | Vessel node colour transitions to purple. SANCTIONED_UNDER edge draws to the SanctionProgramme node (which appears simultaneously). |
| Staging area loiter event | Vessel node glows/pulses briefly at the event timestamp. No new nodes or edges — this is a behavioural marker on an existing node. |

#### Playback Controls

| Control | Behaviour |
|---------|-----------|
| **Play** | Rewind to earliest event, advance automatically. Animation speed controlled by speed setting. |
| **Pause** | Freeze at current slider position. Graph remains fully interactive — hover, click, drag all work. |
| **Scrub** | Drag slider to any date. Graph snaps to the correct state for that date. No animation — instant state change. |
| **Speed** | 1x, 2x, 5x. At 5x, an 18-month fleet build-out plays in ~20 seconds. |
| **Step** | Forward/back one event at a time. For detailed inspection of the sequence. |

**Critical: pausing does not disable interaction.** The user can pause at the moment a company is incorporated, hover over it to read the jurisdiction and date, click to see all connected entities at that point in time, then resume playback. The timeline and the graph interaction are independent layers.

#### Event Timeline (below the slider)

Below the slider, a row of tick marks shows where events cluster in time. Dense clusters of ticks indicate periods of rapid change — fleet build-out phases. Sparse ticks indicate stable periods. This gives the user a visual preview of *when things happened* before they even press Play, and helps them scrub directly to interesting periods.

#### Timeline Event Types

| Event type | Timestamp source | Affects |
|-----------|-----------------|---------|
| `company_created` | OpenSanctions `incorporation_date` | Company node appears |
| `ownership_transferred` | OWNED_BY edge `from_date` | Edge swap on vessel |
| `vessel_acquired` | OWNED_BY edge `from_date` for a new vessel joining the fleet | New vessel node + edge |
| `flag_changed` | FLAGGED_AS edge `from_date` | Edge swap on vessel |
| `class_changed` | CLASSED_BY edge `from_date` | Edge swap on vessel |
| `class_lost` | CLASSED_BY edge `to_date` with no replacement | Red flash, edge disappears |
| `insurance_changed` | INSURED_BY edge `from_date` | Edge swap on vessel |
| `insurance_lost` | INSURED_BY edge `to_date` with no replacement | Red flash, edge disappears |
| `sts_event` | AIS co-location timestamp | STS_PARTNER edge between vessels |
| `staging_area_loiter` | AIS position timestamp | Vessel node pulse |
| `sanctioned` | Sanction listing date | Vessel turns purple + edge |
| `detained` | Paris MoU detention date or OpenSanctions tag | Vessel node border highlight |

#### Implementation Notes

- **Layout stability:** ForceAtlas2 runs with high gravity and `barnesHutOptimize: true` during playback. Existing nodes stay roughly in place when new nodes appear. New nodes enter near their first connected neighbour.
- **Edge animation:** For v1, animate edge opacity from 0 to 1 over 0.5s. True line-drawing animation (progressive reveal) is a v2 enhancement using a custom Sigma edge program.
- **All state is client-side.** The server sends the complete fleet graph plus the complete event list in one response. All animation and interaction is local. VPS load during playback: zero.
- **Scrubbing is a filter, not a rebuild.** The full Graphology graph is always in memory. Scrubbing toggles `hidden` attributes on nodes and edges based on date comparison. This is O(n) over edges and takes <1ms for typical fleet sizes.

### 9.4 Scope Boundaries: Fleet Graphs on VPS, Full Graph Locally

The VPS serves **fleet-level connected components** — the complete network a single vessel belongs to (§9.2, entry point 1) or the set of all flagged fleets (§9.2, entry point 2). These are bounded by the natural structure of the ownership/management graph. A typical fleet has 5-30 vessels, 2-10 companies, a few persons, and their associated flags/class/P&I nodes — total 30-150 nodes. This is a comfortable payload.

The VPS does **not** serve the full graph. The full graph contains every vessel Heimdal has ever processed, every company, every relationship. For full-graph analysis — community detection across all fleets, finding unexpected connections between supposedly independent fleets, identifying structural chokepoints in the shadow fleet ecosystem — the analyst downloads a dump and works locally:

```
GET /api/graph/dump?format=graphology
```

This returns the complete graph as a Graphology JSON file. The analyst loads it locally on their M4 MacBook using a Sigma.js instance, a Jupyter notebook with NetworkX, or whatever tool they prefer. Full ForceAtlas2 layout on 1,000+ vessels runs comfortably there. This is where publication-quality network diagrams are produced.

### 9.5 API Endpoints

| Endpoint | Method | Description | Response |
|----------|--------|-------------|----------|
| `/api/graph/fleet/{imo}` | GET | Complete connected component (fleet) containing this vessel | Graphology JSON: nodes + edges + events array |
| `/api/graph/fleet/{imo}?max_nodes=N` | GET | Truncated fleet if component exceeds N nodes (default: no limit) | Same format, with `truncated: true` flag |
| `/api/graph/networks` | GET | All connected components with at least one Yellow+ vessel | Array of fleet subgraphs |
| `/api/graph/networks?min_score=N` | GET | Filter by minimum vessel score in fleet | Same format |
| `/api/graph/company/{id}` | GET | Complete connected component containing this company | Same format as fleet |
| `/api/graph/events/{imo}` | GET | Ordered event list for a fleet (drives the timeline slider) | JSON array: `[{type, timestamp, source_node, target_node, edge_type, description}]` |
| `/api/graph/dump` | GET | Full graph export for local analysis | Graphology JSON (large file, not for browser) |

### 9.6 Server-Side Graph Queries (FalkorDB / Cypher)

Example: retrieve the complete connected component containing a vessel:

```cypher
// Step 1: Find all nodes reachable from the vessel (full component)
MATCH (v:Vessel {imo: $imo})
CALL algo.BFS(v, NULL, NULL) YIELD nodes, edges
RETURN nodes, edges
```

If FalkorDB doesn't support BFS as a built-in, the alternative is iterative expansion:

```cypher
// Expand outward until no new nodes are found
MATCH (v:Vessel {imo: $imo})-[*1..6]-(connected)
WITH collect(DISTINCT connected) + [v] AS all_nodes
UNWIND all_nodes AS n
MATCH (n)-[r]-(m)
WHERE m IN all_nodes
RETURN DISTINCT n, r, m
```

The depth limit of 6 hops is a safety bound. In practice, most fleet components are fully reachable within 3-4 hops (vessel → owner → parent company → person → another company → another vessel).

Example: find all fleets containing at least one Red vessel:

```cypher
MATCH (v:Vessel)
WHERE v.score >= 6
MATCH (v)-[*1..6]-(connected)
WITH v, collect(DISTINCT connected) + [v] AS component
RETURN component
```

Example: generate the event timeline for a fleet:

```cypher
MATCH (v:Vessel {imo: $imo})-[*1..6]-(n)
WITH collect(DISTINCT n) AS fleet_nodes
UNWIND fleet_nodes AS n
MATCH (n)-[r]-(m)
WHERE m IN fleet_nodes
WITH r, n, m
ORDER BY r.from_date ASC
RETURN type(r) AS edge_type,
       n.name AS source_name, n.type AS source_type,
       m.name AS target_name, m.type AS target_type,
       r.from_date AS event_date,
       r.to_date AS end_date
```

### 9.7 Performance Considerations on Constrained VPS

The VPS serves the graph data as JSON. All rendering happens client-side via Sigma.js/WebGL. This means:

- **Server CPU cost per request:** One FalkorDB Cypher query (fast — subgraph extraction is what graph databases are optimised for). JSON serialisation. Negligible.
- **Server memory:** FalkorDB holds the full graph in memory. With ~1,000-2,000 vessels, ~500 companies, ~200 persons, and edges — this is a small graph. FalkorDB memory footprint will be well under 500MB.
- **Client-side rendering:** Sigma.js WebGL rendering is limited by the client's GPU, not the server. A subgraph of 50-100 nodes (typical for a 2-hop vessel neighbourhood) renders instantly on any modern browser. The /networks view with all suspicious clusters might have 200-500 nodes — still comfortable for WebGL.
- **Layout computation:** ForceAtlas2 runs in a web worker on the client. No server CPU involved.
- **Bandwidth:** A subgraph JSON response for 100 nodes + 200 edges is ~50-100KB. Negligible.

The bottleneck on the Hostinger VPS is not the graph visualisation layer — it's the AIS WebSocket listener and the daily sync jobs. The graph API is the cheapest part of the system.

---

## 10. Limitations and Known Gaps

1. **Vessels never IACS-classed:** A vessel built at a non-IACS yard and classed by a non-IACS society from construction will never appear in the IACS CSV and won't show a class *transition*. The absence signal (C1) still applies, but the transition signal (C5) won't fire.

2. **Paris MoU covers port calls, not transits:** Vessels that transit European waters without calling at port have no Paris MoU record by design, not by evasion. The AIS geographic inference model (§3) addresses this gap.

3. **OpenSanctions vessel coverage is limited:** Approximately 2,000+ vessel entities. Many shadow fleet vessels are not yet listed. The system is designed to catch vessels *before* they appear in OpenSanctions by using the other three data sources.

4. **AIS coverage from aisstream.io is intermittent:** The system does not rely on continuous AIS data. It relies on pattern detection (staging, loiter-then-vanish, transit-without-port-call) that is robust to coverage gaps. AIS gaps alone are explicitly excluded from scoring.

5. **P&I data ages:** The P&I provider recorded at a 2019 Paris MoU inspection may not reflect current coverage. Vessels transition to non-IG insurers (or lose coverage entirely) without this being captured in any open dataset except Equasis (manual step).

6. **False negatives on grey fleet:** Vessels operating under IG P&I with valid price cap attestations but carrying Russian cargo above the cap price will appear Green. This system detects structural evasion (operating outside the compliance framework), not price cap fraud within it.

---

## 11. Revision History

| Date | Version | Change |
|------|---------|--------|
| 2026-03-25 | 0.1 | Initial draft based on design discussion |
| 2026-03-26 | 0.2 | Added split compute model (local bootstrap / VPS daily ops), graph visualisation layer (Sigma.js + Graphology + FalkorDB), API design. Rewrote §4 with explicit node types, edge types, attributes, and concrete example. |
| 2026-03-26 | 0.3 | Rewrote §9.3 temporal playback: baseline state + transition animation with visual language. Added §9.4 scope boundaries (subgraph on VPS, full graph local via /dump endpoint). |
| 2026-03-26 | 0.4 | Fundamental rewrite of §9.2-9.6. Graph is now fleet-centric (connected component), not vessel-neighbourhood. Entry endpoint changed to `/api/graph/fleet/{imo}`. Timeline starts at current state, user scrubs backward to explore history. Playback is always interactive (pause, hover, click, drag at any point). Added step-forward/back control. Event tick marks below slider. Cypher queries updated for full component traversal. |
