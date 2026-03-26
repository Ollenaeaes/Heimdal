# Russian Shadow Fleet Operations: Comprehensive Research

**Date:** 2026-03-25
**Purpose:** Deep-dive reference for building shadow fleet detection capabilities into Heimdal

---

## 1. Full Lifecycle of a Vessel Transitioning to Shadow Fleet Operations

### The Acquisition Phase (Weeks 0-4)

The transition begins with **vessel acquisition**. Aging tankers (typically 15-20+ years old) are purchased from legitimate owners, often European companies, at discount prices on the secondary market. The 2008-2011 tanker delivery boom created a large pool of 16-20 year old vessels now available cheaply. The buyer is typically a newly created shell company with no prior maritime track record.

Key observable markers at this stage:
- Sale to a previously unknown entity (single-vessel SPV registered in UAE, Hong Kong, Singapore, or similar jurisdiction)
- Buyer has no fleet history, no website, no public presence
- Purchase price below market value for the vessel age/type

### Ownership Restructuring (Weeks 2-8, overlapping with acquisition)

The new owner immediately restructures the ownership chain:

1. **Registered owner** becomes a single-purpose shell company (often in Marshall Islands, Liberia, or Panama)
2. **Beneficial ownership** hidden behind layered nominee structures -- "Russian nesting dolls" of companies registered across multiple jurisdictions
3. **ISM company / DOC holder** changes to an obscure or newly created ship management company, frequently based in Dubai/UAE, India, or Turkey
4. **Commercial operator** may be a different entity again, sometimes the same address as the registered owner

Observable data points:
- IMO company number changes in IHS/S&P Global Sea-web
- DOC holder changes visible in PSC inspection records
- ISM company details change (Paris MoU THETIS data captures ISM company per inspection)
- New management company has minimal fleet, recently incorporated

### Flag Change (Weeks 2-12)

Flag change typically follows or coincides with ownership change:

**Tier 1 shadow flags (highest concentration of shadow fleet):**
- Gabon (fastest-growing registry 2024; ~98% of tankers classified high-risk; operated by Intershipping Services LLC, UAE -- now EU/UK sanctioned)
- Cameroon (second-largest registry for sanctioned tankers; 13% of sanctioned fleet by number; 28% detention rate at Paris MoU -- worst performer; 144 inspections, 43 detentions in 2024)
- Comoros (38% of sanctioned dark fleet tonnage over 20,000 dwt; Paris MoU black-listed; began de-flagging shadow vessels under pressure in 2025)
- Palau (Paris MoU black list, medium risk category; dismissed registry contractor after US blacklisting)

**Tier 2 shadow flags (significant growth linked to shadow fleet):**
- Sierra Leone (registry up 105%)
- Guinea-Bissau (registry up 340%)
- Guinea (registry up 99,094% in 12 months)
- Sao Tome and Principe
- Tanzania
- Djibouti
- Eswatini

**Fraudulent/non-existent registries detected by Windward:**
- Angola, Aruba, Benin, Curacao, Eswatini, Guinea, Guyana, Mali, Malawi, Mozambique, St Maarten, Timor-Leste
- CREA found 90 vessels operating under false flags in September 2025 -- a six-fold increase from December 2024
- Vessels steal flags of countries that do not have actual maritime registries

Observable data:
- Flag state changes in AIS data and registry records
- Multiple flag changes in rapid succession ("flag hopping")
- Flag state with Paris MoU black/grey listing
- Flag state with USCG high-risk designation
- Flag state where registry growth is anomalous vs. the country's maritime capacity

### Insurance Transition (Weeks 4-16)

This is where the vessel exits the Western compliance ecosystem:

**Step 1: Loss of IG P&I coverage**
- International Group of P&I Clubs (13 mutual clubs covering ~90% of world fleet) will not cover vessels engaged in sanctions-violating trade
- IG clubs require transparency on ownership, trading patterns, and cargo origin
- Vessels carrying Russian crude above the price cap cannot maintain IG coverage
- Observable: vessel disappears from IG club entered-ship lists

**Step 2: Transition to non-IG / opaque insurance**
- Russian insurers step in: **Ingosstrakh** (US/UK sanctioned), **AlfaStrakhovanie** (EU/US/UK sanctioned), **Sogaz** (sanctioned)
- All three backed by **Russian National Reinsurance Company (RNPC)** -- under EU/US/UK sanctions
- Other non-IG providers from Cameroon, Kyrgyzstan, and other non-OPC jurisdictions
- Indian insurers providing some coverage for vessels calling Indian ports

**Step 3: Insurance becomes "unknown"**
- Two-thirds of ships carrying Russian oil have insurers classified as "unknown"
- Among 4,539 tankers with no ties to oil price cap coalition countries, P&I insurance providers are known for only 6.3%
- For vessels carrying Russian oil specifically, just 16.9% have identifiable coverage

**Key statistics (KSE Institute, Feb 2025):**
- Russian crude tankers: only 29.4% have IG coverage
- Russian oil products tankers: 56.2% have IG coverage
- Non-Russian cargo vessels: >90% IG-insured
- Non-IG-insured ships average 18.1 years old vs 14.4 years for IG-covered
- 64.2% of non-IG-insured vessels fly grey-listed, black-listed, or unranked flags

### Classification Society Change (Weeks 4-20)

**Step 1: Withdrawal from IACS member class**
- Russian Maritime Register of Shipping (RMRS) expelled from IACS on March 11, 2022
- Western IACS members (Lloyd's Register, DNV, Bureau Veritas, ABS, etc.) withdraw class from vessels engaged in sanctioned trade
- IACS Transfer of Class agreement means vessels cannot simply hop between IACS members to avoid surveys

**Step 2: Move to non-IACS class or unclassed**
- Vessels shift to non-IACS classification societies with less rigorous survey standards
- Some operate effectively unclassed -- no valid class certificates
- RMRS continues to class some vessels but its certificates are not recognized by Western port states

Observable data:
- Classification society changes visible in IACS weekly snapshots (Heimdal data source)
- Vessel moving from e.g. Lloyd's Register to an unknown or non-IACS society
- Gap between class withdrawal and new class assignment
- Class certificates with non-IACS societies not recognized by major port states

### Operational Pattern Changes (Ongoing from Week 8+)

Once the vessel is fully transitioned, operational behavior changes dramatically:

**AIS behavior changes:**
- Increased "dark" periods (AIS off) -- Russian-linked vessels show 6x more AIS gaps than European vessels
- AIS gaps align with high-risk activity zones (STS transfer areas, Russian ports)
- Geographic spoofing: false position data to simulate port calls at non-Russian ports
- MMSI manipulation to disguise vessel identity
- IMO number fraud (stealing scrapped vessel IMOs, fabricating IMOs, hijacking active vessel IMOs, using IMOs of ships under construction)

**Voyage pattern changes:**
- Russia-dedicated trade routes emerge (Primorsk/Ust-Luga/Murmansk to India/China/Turkey)
- Unusual routing through known shadow fleet corridors
- Elimination of diversified trading (vessel only calls Russian export terminals and delivery destinations)
- Extended "loitering" at anchorages (e.g., 16 days at Ningbo)

**STS transfer activity:**
- Ship-to-ship transfers at known shadow fleet STS zones (see Section 6)
- Coordinated "dark STS chains" where both vessels disable AIS
- Multiple STS transfers per voyage to obscure cargo origin

### Typical Timeline Summary

| Phase | Timeframe | Key Observable |
|-------|-----------|---------------|
| Vessel acquisition | Week 0 | Sale to unknown SPV, price below market |
| Ownership restructuring | Weeks 2-8 | IMO company change, new DOC holder |
| Flag change | Weeks 2-12 | Registration to Tier 1/2 shadow flag |
| Insurance transition | Weeks 4-16 | Disappearance from IG club lists |
| Classification change | Weeks 4-20 | Withdrawal from IACS member, or class lapse |
| First dark voyage | Week 8+ | AIS gaps, Russia-origin loading |
| Full shadow operations | Week 12+ | Regular dark activity, STS transfers |

**Critical insight:** Compliance deterioration typically precedes AIS anomalies. The ownership/flag/insurance changes happen first (weeks 2-16), then operational deception begins (week 8+). This means Heimdal's PSC/classification/ownership data streams can detect shadow fleet candidates BEFORE they start manipulating AIS.

---

## 2. Specific Markers and Indicators by Authority/Organization

### UK OFSI / HM Treasury Maritime Guidance

**Documentation red flags:**
- Counterparty refusal or reluctance to provide price information
- False or misleading attestation statements (violation of regulation 67)
- Missing per-voyage attestations on multi-leg journeys
- Certificates of origin listing countries that don't normally produce oil
- Sudden increase in volume of oil shipments from a given origin
- Inability to produce valid origin certificates and proportional documentation

**Transaction red flags:**
- Prices deviating significantly from standard market rates
- Abnormally high shipping, insurance, or brokering fees (masking price cap exceedances)
- Reluctance to itemize costs across CIF/FOB contract structures
- Ancillary cost inflation to conceal above-cap purchases

**Tier compliance obligations:**
- Tier 1 (direct price access): report all contracts within 40 days
- Tier 2-3: confirm counterparty reporting within 60 days or withdraw services
- Tier 3A/3B: must obtain ancillary cost breakdowns within 30 days or cease engagement

**Oil price cap:** Reduced from $60/bbl to $47.60/bbl effective September 2, 2025

### US OFAC Deceptive Shipping Practices Guidance (Oct 2024)

**AIS manipulation indicators:**
1. Potential misclassification of vessel and class of trade
2. Extended periods without AIS transmission
3. Abnormal traffic or voyage patterns
4. MMSI manipulation to disguise ship name or location

**Vessel deception indicators:**
- Renaming or reflagging vessels to conceal identity
- Falsifying documentation
- Obscuring IMO numbers
- Older vessels slated for recycling being repurposed

**Ownership/transaction red flags:**
- Unusual or opaque purchase structures for tanker sales
- Lack of transparency regarding ultimate beneficial owners
- Buyers or ship management companies with prior associations to illicit or unsafe behavior
- Links to sanctioned persons or countries
- Complex and less efficient trade routes including multiple STS transfers
- Use of shadow payment channels

**Enhanced due diligence requirements:**
- Contact details of buyers
- Source of funds documentation
- Beneficial owner identification copies
- Cross-verification against market intelligence, media, and third-party databases

### EU Sanctions Framework

**EU 18th Package (July 2025) -- new approach:**
- Targeting not just individual ships but networks of facilitating individuals and companies
- Sanctioned Intershipping Services LLC (UAE) -- operator of Gabon and Comoros flag registries
- Ownership, management, and financing of specific ships targeted systemically
- Designation criteria focus on the operator networks, not just the vessels

**Price Cap Coalition Alert 1 (Feb 2024):**
- Coordinated alert across G7/EU on compliance and enforcement
- Focus on intermediary documentation chains

### P&I Clubs (IG Group) Coverage Decision Indicators

**Automatic exclusion triggers:**
- Vessel designated on any major sanctions list (OFAC SDN, EU, UK)
- Vessel trading in violation of price cap without valid attestation chain
- Ownership opacity that prevents satisfactory KYC/CDD
- Flag state that does not cooperate with international maritime conventions

**Enhanced scrutiny triggers:**
- Vessel age >15 years in tanker trade
- Recent ownership change to unknown entity
- Flag change to Paris MoU black/grey listed state
- AIS anomalies reported by maritime intelligence providers
- Classification change away from IACS member
- Voyage pattern changes indicating Russian crude trade

### Port State Control Authorities

**Paris MoU targeting factors (ship risk profile):**
- Flag state performance (white/grey/black list)
- Recognized organization (classification society) performance
- Company performance (ISM DOC holder detention history)
- Ship age
- Ship type (oil tanker = higher priority)
- Number and nature of previous deficiencies
- Previous detentions

**Specific deficiency categories most relevant to shadow fleet detection:**
- 07106: ISM Code not effectively implemented
- 15150: ISM ground for detention (safety management audit required before release)
- Fire safety equipment (alarms, sprinklers, portable extinguishers) -- detainable
- Life-saving appliances (lifeboats, life jackets) -- detainable
- Structural/hull integrity (corrosion, cracks) -- detainable
- Navigation equipment (radar, GPS, VHF) -- detainable
- MARPOL annex I (oil pollution prevention) -- detainable
- Certificates and documentation (statutory certificates, class certificates)

**Shadow fleet PSC pattern:**
- Vessels avoiding Paris MoU / Tokyo MoU member state ports entirely
- When inspected: high deficiency counts, ISM-related failures
- Cameroon-flagged vessels: 28% detention rate (worst in Paris MoU)
- Detention triggers cascade: ISM failure -> expanded inspection -> multiple detainable deficiencies

### Classification Societies (IACS Members)

**Key indicators of shadow fleet transition:**
- Class withdrawal by IACS member (visible in IACS weekly data)
- Transfer to non-IACS society
- Lapsed class certificates (no valid class)
- Overdue surveys (annual, intermediate, or special)
- Conditions of class not rectified within required timeframe
- RMRS classification (expelled from IACS March 2022; certificates not recognized by Western states)

### Maritime Intelligence Firms

**Windward -- Three-tier classification:**
1. **Cleared Fleet:** Stable ownership, consistent flag history, compliant routing, clean documentation
2. **Gray Fleet** (~1,000+ vessels): Ownership changes, irregular trading routes, high-risk port sequences, Russia-associated activity patterns
3. **Dark Fleet** (~1,000+ vessels): Deliberately concealing activity -- prolonged AIS gaps, location manipulation, coordinated dark STS chains, fraudulent flags/identities

**Windward detection layers:**
- AIS: gap detection, pattern anomalies
- SAR (Synthetic Aperture Radar): detects AIS-off vessels
- Electro-Optical imagery: confirms vessel type and STS positioning
- Radio Frequency: detects non-cooperative vessels
- Behavioral analytics: connects signals to patterns
- Ownership intelligence: exposes shell structures
- Document validation: compares paperwork against sensor data

**Kpler -- Shadow fleet methodology:**
- Gray fleet: vessels sold since invasion (mostly Europe to Middle East/Asia buyers not previously in tanker market); behavior-based category requiring heightened verification
- Dark fleet: veterans of Iran/Venezuela sanctions campaigns now carrying Russian crude; evidence of AIS disabling
- Risk dimensions: behavioral (AIS spoofing, dark ops, suspicious routing), associative (relationships with sanctioned vessels), geographic (high-risk zone operations), cargo (crude/products on sanctioned routes), ownership opacity
- Fleet size estimate: ~3,300 ships by December 2025, moving ~3,733 million barrels

**S&P Global -- Tiered classification:**
- Tier 1: Ships designated for sanctions evasion or attributed severe status due to Russia/Iran/Venezuela relationship
- Tier 2: Vessels with opaque ownership; previous Russian/Iranian/Venezuelan nationality; more likely involved in sanctioned activity; or in fleets where majority of ships are sanctioned
- Includes vessels >=27,000 dwt; MR2 (50,000 dwt) is largest class; Aframax (~100,000 dwt) also significant
- Average age of shadow fleet ship: 20 years; 60% are 20+ years old

**Lloyd's List Intelligence -- AIS spoofing research:**
- Identified three observable spoofing signatures: (1) vessels showing stationary positions while claiming movement, (2) perfect circular movement patterns, (3) straight-line back-and-forth motion that defies maritime physics
- Gulf of Oman: at least 14 US-sanctioned tankers used fake AIS to falsely show port calls at Khor al Zubair, Iraq
- Malaysia/South China Sea: 50+ tankers monthly manipulating positional data to disguise cargo transfers before delivery to China

**TankerTrackers.com -- Satellite-first approach:**
- Analysis based entirely on satellite imagery, not AIS data
- Daily satellite imagery + shoreside photography + real-time AIS cross-reference
- Visual identification engine to rapidly identify tankers by hull/deck features
- Determines cargo status (loaded/empty) visually via satellite
- Tracks 77,724+ separate export events
- IMINT + OSINT fusion with geolocated RF signals

---

## 3. Insurance-Specific Indicators

### How P&I Coverage Loss Manifests in Observable Data

1. **Vessel disappears from IG club entered-ship lists** (published annually; some clubs publish quarterly)
2. **Blue Cards become unavailable:** CLC and Bunkers Convention require flag states to issue certificates confirming insurance. Without IG P&I, vessels cannot obtain valid blue cards from compliant flag states
3. **Port state refusal:** Ports can refuse entry to vessels without proof of valid P&I insurance meeting minimum thresholds
4. **PSC inspection findings:** Certificate of Financial Responsibility missing or from unrecognized insurer
5. **Insurance provider field goes blank or "unknown"** in commercial databases (IHS, Equasis)

### Non-IG Insurer Landscape

**Russian insurers (primary shadow fleet coverage):**
- **Ingosstrakh** -- US/UK sanctioned; does not disclose coverage; key shadow fleet insurer
- **AlfaStrakhovanie** -- EU/US/UK sanctioned
- **Sogaz** -- sanctioned
- **Russian National Reinsurance Company (RNPC)** -- EU/US/UK sanctioned; backstops all three
- These four collectively provide little transparency, disclosing coverage for only ~220 tankers

**Other non-IG providers:**
- Indian insurers (serving vessels calling Indian ports)
- Chinese insurers (minimal disclosure)
- Cameroon-based insurers
- Kyrgyzstan-based insurers
- These provide documentation that allows ports and brokers to process voyages but operate outside the international P&I framework that guarantees claims payments

**Key difference:** IG clubs have collective reinsurance pool (claims up to ~$3.1 billion per incident). Non-IG insurers have no pooling arrangement, typically much lower limits, and questionable ability to pay large claims (e.g., major oil spill).

### Certificate of Financial Responsibility Gaps

- CLC (Civil Liability Convention) requires proof of insurance for oil pollution damage -- flag state issues certificate
- Bunkers Convention requires similar for bunker spill liability
- Wreck Removal Convention (Nairobi 2007) requires proof of insurance for wreck removal costs
- Shadow fleet flag states (Gabon, Cameroon, Comoros) issue certificates without verifying insurer adequacy
- **No requirement for audited financials or credit ratings** of the insurer -- just documentation
- KSE Institute recommends: vessels in coalition waters must show proof including audited financials and credit rating from recognized agency

### Oil Pollution Liability (CLC/Bunkers)

The CLC certificate must include:
- Name of ship and port of registration
- Name and principal place of business of owner
- Type of security
- Name and principal place of business of insurer
- Period of validity

**Shadow fleet gap:** Certificates exist but the insurer behind them (e.g., Ingosstrakh backed by RNPC) is sanctioned and may lack the financial capacity to pay a major claim. A Baltic Sea oil spill from a shadow fleet tanker could produce $1B+ in cleanup costs with no realistic claims path.

---

## 4. Temporal Patterns

### Compliance Deterioration vs. AIS Anomalies: What Comes First?

**Compliance deterioration comes first.** The typical sequence is:

1. **Ownership change** (earliest observable signal, weeks 0-4 after purchase)
2. **DOC/ISM company change** (weeks 2-8)
3. **Flag change** (weeks 2-12)
4. **Classification society change or withdrawal** (weeks 4-20)
5. **Insurance transition / loss of IG coverage** (weeks 4-16)
6. **First AIS anomalies** (week 8+, after vessel begins shadow trading)
7. **Established dark activity patterns** (week 12+)

This sequence is critical for Heimdal: **ownership/flag/class/insurance changes are leading indicators; AIS anomalies are lagging indicators.** By the time a vessel starts going dark, it has already been in the shadow fleet pipeline for 2-4 months.

### PSC Deficiency Pattern Evolution

As a vessel enters shadow fleet operations, its PSC profile changes:

**Pre-transition (legitimate trading):**
- Regular PSC inspections at major ports (Rotterdam, Singapore, Houston)
- Low deficiency counts (0-3 per inspection)
- Deficiencies typically minor (documentation, minor equipment)
- No detentions

**Early transition (months 1-6):**
- Ports of call shift away from strict PSC regimes
- Inspection frequency drops (vessel avoiding Paris/Tokyo MoU ports)
- When inspected: deficiency count increases (4-8)
- ISM-related deficiencies begin appearing
- Equipment maintenance starts slipping

**Established shadow fleet (months 6+):**
- Vessel rarely if ever calls at Paris MoU member state ports
- If inspected (e.g., on a rare European call or forced inspection): high deficiency count (8+)
- Detainable deficiencies common: fire safety, life-saving, structural, MARPOL
- ISM code failures (07106, 15150)
- Certificates from non-recognized classification societies
- Possible detention and forced audit

**What to look for in Heimdal's Paris MoU data:**
- Declining inspection frequency over time (vessel drops off the radar)
- Last known inspection date increasingly stale
- When inspected: deficiency count trend rising
- Specific deficiency codes: ISM-related (07xxx, 15150), fire safety (07xxx), structural (01xxx), MARPOL (05xxx), navigation (04xxx), certificates (other)
- Flag state detention rate for the vessel's current flag
- ISM company detention rate (DOC holder performance)

### AIS Gap Patterns

- Russian-linked vessels: 6x more AIS gaps than European-flagged comparison vessels
- Gaps align with: Russian port calls, STS transfer zones, approaches to sanctioned loading terminals
- Gap duration: typically hours to days during loading/discharge; shorter gaps during transit
- Progressive darkening: vessels start with occasional gaps, then increase frequency and duration over time

### Vessel Age at Transition

- **Average shadow fleet vessel: 18-20 years old**
- 93% of shadow fleet aged 15+ years
- 60-64% aged 20+ years
- Sweet spot for acquisition: 15-20 year range (still operational, cheap to buy, owners willing to sell to exit aging asset)
- The 2008-2011 tanker delivery boom created the current pool of transition-age vessels (now 15-18 years old)
- More than 75% are past the 15-year threshold where technical failures increase sharply

---

## 5. What the Major Reports Say

### CREA (Centre for Research on Energy and Clean Air)

**Shadow Fleet Policy Briefing (Aug 2024):**
- Compiled list of 29 core shadow tankers transporting a quarter of all Russia's crude
- By early 2025, 28 of 29 had been sanctioned by UK, US, or EU
- Methodology: tracking vessel movements from Russian export terminals, cross-referencing ownership/flag/insurance data

**Flags of Inconvenience Report (2025):**
- 113 vessels flying false flags transported EUR 4.7 billion of Russian oil in first three quarters of 2025
- 90 vessels operating under false flags in September 2025 (6x increase from December 2024)
- Monthly monitoring of Russian fossil fuel exports with sanctions effectiveness analysis

**Key contribution:** CREA's monthly analysis tracks Russian export revenues and the effectiveness of the price cap, providing a macro view of how much sanctioned oil is still flowing and through which channels.

### Greenpeace Shadow Fleet Reports (2024-2025)

**Baltic Sea Analysis (Sep 2024):**
- Analyzed four years of vessel movement data from Russian Baltic ports (Primorsk, St. Petersburg, Ust-Luga, Vysotsk)
- Found Russian crude tanker traffic along Germany's Baltic coast rose 70% since 2021
- Average age of shadow fleet vessels: 16.6 years (up from 8.9 years pre-war)
- Two-thirds lack P&I insurance

**Investigation Report (Mar 2025):**
- Most tankers sailing from Russian ports lack adequate insurance
- Insured by sanctioned Russian companies (Ingosstrakh, AlfaStrakhovanie, Sogaz) plus firms from Cameroon and Kyrgyzstan
- Estonian checks (Jul-Aug 2024): 20-25% of ~150 checked oil tankers insured by Russian companies

**Key contribution:** Environmental risk quantification and public pressure on Baltic Sea coastal states.

### S&P Global Shadow Fleet Tracking

**Methodology:**
- Two-tier classification system (Tier 1: designated/severe status; Tier 2: opaque ownership, previous sanctioned-nation ties)
- Vessels >= 27,000 dwt
- Maritime Intelligence Risk Suite (MIRS) combines vessel data with corporate intelligence
- Sea-web Vessel Movements for position and port call history

**Key findings:**
- Shadow fleet ~3,300 ships by December 2025
- Average age 20 years; 567 vessels (60%) are 20+ years old
- MR2 tankers (50,000 dwt) are the largest vessel class in the shadow fleet
- Shadow fleet moves ~6-7% of global crude flows

### TankerTrackers.com

**Approach:**
- Satellite imagery-first (not AIS-dependent)
- Daily satellite imagery + shoreside photography
- Visual vessel identification engine (hull/deck features)
- 77,724+ export events tracked
- Imagery intelligence (IMINT) + OSINT, fused with RF signals
- Emphasis on visual confirmation of cargo status (loaded/empty via satellite)

**Key contribution:** Ground truth for AIS manipulation -- they can show where a vessel actually was vs. where it claimed to be.

### Paris MoU Annual Reports

**2024 Report key data:**
- Overall detention rate: 4.03% (up from 3.81% in 2023)
- Cameroon: worst performer, 28% detention rate, 43 detentions from 144 inspections
- Gabon: too few European inspections to rank (ships avoid the Paris MoU region)
- Comoros: black-listed
- Palau: black-listed (medium risk)
- ISM-related deficiencies remain primary detention driver
- Safety detentions remain elevated compared to pre-pandemic era

**Key insight for Heimdal:** Flag state performance data from Paris MoU directly maps to shadow fleet risk. A vessel flagged to a black-listed state with high detention rates is a strong shadow fleet indicator.

---

## 6. Known Limitations of Detection and Evasion Techniques

### AIS Manipulation Techniques Actually Used

1. **Going dark:** Complete AIS shutdown during loading, STS transfers, and transit through monitoring zones. Most basic technique. Detectable by SAR/satellite imagery mismatch.

2. **Geographic spoofing (GNSS manipulation):** Vessel transmits false position data. Example: 14+ US-sanctioned tankers falsely showed port calls at Khor al Zubair, Iraq while actually in the Gulf of Oman. Vessel SKIPPER reported position 500nm off Guyana while actually loading Venezuelan crude. Detectable by: impossible movement signatures (stationary while claiming movement, perfect circular patterns, straight-line oscillation), SAR/EO imagery comparison.

3. **MMSI manipulation:** Changing Maritime Mobile Service Identity to disguise vessel name/location. More sophisticated than basic AIS off. Requires cross-referencing IMO number (which should be permanent) vs. MMSI.

4. **IMO number fraud:**
   - Stealing IMO numbers of scrapped tankers
   - Fabricating entirely new IMO numbers
   - Hijacking IMO numbers of active vessels
   - Using IMO numbers of ships still under construction
   - Requires deep hull history search to detect

5. **Semi-dark operations:** Vessel transmits AIS intermittently -- enough to avoid collision but with gaps during sensitive activities. Harder to flag than complete blackout.

### Ship-to-Ship Transfer Patterns

**Known STS zones for shadow fleet operations:**
- **Gulf of Oman:** Persistent STS location; vessels anchor in Omani territorial waters for transfers
- **Laconian Gulf (Greece):** Mediterranean staging point
- **Hurd's Bank (Malta):** Mediterranean STS zone
- **Waters off Ceuta (Gibraltar):** Mediterranean transfer point
- **Off West Africa coast:** Growing STS activity
- **South China Sea / off Malaysia:** 50+ tankers monthly manipulate positional data for transfers before China delivery
- **Baltic Sea (between Syria and Black Sea route):** Emerging zone

**STS evasion patterns:**
- Both vessels go dark simultaneously during transfer
- Transfer at night
- Remote international waters to avoid coastal state jurisdiction
- Multi-vessel chains: Vessel A -> Vessel B -> Vessel C to completely obscure origin
- Intermediate vessel has clean flag/insurance, acting as "laundering" vessel

### Ownership Obfuscation

**Shell company structures:**
- Subsidiaries seemingly own parent companies in circular structures
- Nominee directors from Ras Al Khaimah/BVI/Jersey while true owners in Moscow
- UAE's 25% UBO (Ultimate Beneficial Ownership) loophole exploited
- Single-purpose vehicles with no web presence, registered at shared office addresses
- When sanctioned, vessel transferred to newly created company -- sometimes at the same address

**Key jurisdictions for shell companies:**
- UAE (Dubai free zones) -- primary hub
- Hong Kong
- Singapore
- Panama (registration)
- Liberia (flagging)
- Marshall Islands (registration)
- British Virgin Islands (holding companies)
- India (Mumbai -- management offices)
- Turkey (growing role as hub)

**Evasion after sanction:**
- Example: Mikati sanctioned July 18, 2025. By July 25, ownership transferred from Azerbaijan entity to "Alga Oceanic Ventures" registered in Samoa (no internet presence). Continued operating.
- Sai Baba (UK-sanctioned Oct 2024): switched from Gabon to Djibouti flag, renamed Lahar by January 2025

### Multiple Flag/Name Changes to Break Audit Trails

- Vessels change name, flag, and ownership simultaneously
- Each change creates a potential break in tracking databases
- If counterparty only checks current name/flag, they may miss the vessel's full history
- IMO number is the permanent identifier, but IMO fraud (above) can defeat even this
- Requires matching every prior IMO number to trace full hull history

### What Detection Cannot Easily Catch

1. **Perfectly legal gray fleet operations:** Vessels technically complying with price cap (Russian oil at $47.60/bbl or below) are legal. Distinguishing gray from dark requires cargo price verification, which is not observable from AIS/satellite.

2. **Well-documented shell structures:** If beneficial ownership is professionally obscured through multiple layers of legitimate-seeming entities, standard due diligence may not penetrate to the true owner.

3. **Vessels that never enter strict PSC jurisdictions:** If a vessel only operates Russia-India or Russia-China, it may never encounter Paris MoU or USCG inspection.

4. **Real-time STS detection:** Unless satellite imagery happens to capture the transfer, STS in international waters during AIS blackout is only detectable retrospectively through voyage analysis (vessel arrives loaded without calling at a loading port).

5. **Insurance documentation fraud:** Certificates of Financial Responsibility may appear valid but be backed by sanctioned or inadequate insurers. Verification requires checking the actual insurer's status, not just the document's existence.

---

## 7. Implications for Heimdal's Data Sources

### Paris MoU THETIS Data (New Automated Source)

The PSC inspection data is exceptionally valuable for shadow fleet detection because it captures signals that precede AIS anomalies:

**High-value fields per inspection:**
- **IMO number:** Key for vessel tracking across all data sources
- **Flag state:** Track flag changes over time
- **ISM company / DOC holder:** Track management company changes
- **Deficiency codes:** 691 codes with "detainable" and "RO-related" flags
- **Detention status:** Binary signal of severe non-compliance
- **Classification society (RO):** Track class changes; detect non-IACS class
- **Certificate status:** Statutory and class certificate validity
- **Charterer information:** May reveal commercial relationships

**Shadow fleet detection queries against THETIS data:**
1. **Flag trajectory:** Vessels that changed from reputable flag to Tier 1/2 shadow flag
2. **ISM company trajectory:** Vessels whose DOC holder changed to a newly created or unknown management company
3. **Deficiency escalation:** Vessels with increasing deficiency counts over successive inspections
4. **Inspection gap:** Vessels that used to be regularly inspected but have dropped off the radar (last inspection increasingly stale)
5. **Detainable deficiency clusters:** Multiple detainable deficiencies in fire safety + structural + ISM = maintenance neglect consistent with shadow fleet
6. **RO-related deficiencies:** High count of classification-society-related deficiencies suggests inadequate class oversight
7. **Certificate gaps:** Missing or expired statutory certificates, especially CLC/Bunkers Convention certificates
8. **Cross-reference with IACS data:** Vessel lost IACS class + PSC deficiency escalation = strong shadow fleet signal

**Temporal analysis enabled by THETIS historical data (2015+):**
- Build per-vessel deficiency timelines
- Identify the "inflection point" where a vessel's compliance profile deteriorates
- Correlate compliance deterioration timing with ownership/flag changes
- Track ISM company performance across their fleet (if DOC holder manages multiple shadow fleet vessels, all their vessels are suspect)

### IACS Weekly Classification Snapshots

- Track class status changes in near-real-time
- Detect class withdrawal, transfer, or lapse
- Cross-reference: vessel loses IACS class -> check THETIS for increased deficiencies -> check AIS for dark activity -> flag for review

### AIS Real-Time Data

- AIS gap detection and pattern analysis
- GNSS manipulation detection (impossible movement signatures)
- Voyage pattern analysis (Russia-only trade routes)
- STS encounter detection (two vessels in close proximity at known STS zones)
- Speed/heading anomalies during dark periods

### OpenSanctions

- Cross-reference vessel IMO, owner, and operator against sanctions lists
- Track when entities are designated and whether vessels are transferred to new entities post-sanction
- Monitor new designations for vessels already flagged by other indicators

---

## Sources

- [Russian Shadow Fleet - Wikipedia](https://en.wikipedia.org/wiki/Russian_shadow_fleet)
- [UK Maritime Services Ban and Oil Price Cap Industry Guidance - GOV.UK](https://www.gov.uk/government/publications/uk-maritime-services-ban-and-oil-price-cap-industry-guidance/uk-maritime-services-ban-and-oil-price-cap-industry-guidance)
- [UK NCA Red Alert: Shadow Fleet Sanctions Evasion](https://www.nationalcrimeagency.gov.uk/who-we-are/publications/753-red-alert-shadow-fleet-sanctions-evasion-and-avoidance-network/file)
- [OFAC Updated Price Cap Coalition Advisory (Oct 2024)](https://ofac.treasury.gov/media/933506/download?inline=)
- [OFAC Sanctions Guidance for Maritime Shipping Industry (Oct 2024)](https://ofac.treasury.gov/media/933556/download?inline=)
- [OFAC Guidance on Detecting and Mitigating Iranian Oil Sanctions Evasion](https://ofac.treasury.gov/media/934236/download?inline=)
- [Price Cap Coalition Compliance Alert 1 (Feb 2024)](https://finance.ec.europa.eu/system/files/2024-02/240201-alert-opc-coalition-compliance-enforcement_en.pdf)
- [False Flags, Fake Docs, and Fraudulent Routes - Institute for Financial Integrity](https://finintegrity.org/false-flags-fake-docs-and-fraudulent-routes/)
- [KSE Institute: Oil Spill Insurance and the Shadow Fleet (Feb 2025)](https://kse.ua/wp-content/uploads/2025/02/Shadow-Fleet-Insurance_Feb2025.pdf)
- [KSE Institute Insurance Gaps Report](https://kse.ua/about-the-school/news/oil-spill-insurance-and-the-shadow-fleet-kse-institute-reveals-insurance-gaps-in-the-global-tanker-fleet-including-vessels-transporting-russian-oil/)
- [CREA: Tackling the Russian Shadow Fleet Policy Briefing (Aug 2024)](https://energyandcleanair.org/publication/policy-briefing-tackling-the-russian-shadow-fleet/)
- [CREA: Flags of Inconvenience Report (2025)](https://energyandcleanair.org/publication/flags-of-inconvenience-113-vessels-flying-a-false-flag-transported-eur-4-7-bn-russian-oil-in-first-three-quarters-of-2025/)
- [CREA: December 2025 Monthly Analysis](https://energyandcleanair.org/december-2025-monthly-analysis-of-russian-fossil-fuel-exports-and-sanctions/)
- [Greenpeace Shadow Fleet Baltic Tankers List (Oct 2024)](https://www.greenpeace.org/static/planet4-sweden-stateless/2024/10/fb3d5709-greenpeace-shadow-fleet-baltic-tankers-list.pdf)
- [Greenpeace Shadow Fleet Investigation (Mar 2025)](https://www.greenpeace.org/static/planet4-italy-stateless/2025/03/b21bfc90-280225_greenpeace_shadowfleet_en.pdf)
- [S&P Global: Maritime Shadow Fleet Formation and Risk (2025)](https://www.spglobal.com/market-intelligence/en/news-insights/research/maritime-shadow-fleet-formation-operation-and-continuing-risk-for-sanctions-compliance-teams-2025)
- [S&P Global: Shadow Fleet Factbox (Nov 2024)](https://www.spglobal.com/commodity-insights/en/news-research/latest-news/crude-oil/111124-factbox-global-shadow-tanker-fleet-moves-growing-volumes-of-sanctioned-oil)
- [Windward: What Is the Shadow Fleet?](https://windward.ai/glossary/what-is-the-shadow-fleet/)
- [Windward: Illuminating Russia's Shadow Fleet](https://windward.ai/knowledge-base/illuminating-russias-shadow-fleet/)
- [Windward: Cameroon Pledges Crackdown on Ship Registry](https://windward.ai/blog/cameroon-pledges-crackdown-on-ship-registry-flagging-13-of-dark-fleet-tankers/)
- [Windward: Gambia Deletes Shadow Fleet Tankers](https://windward.ai/blog/gambia-deletes-shadow-fleet-tankers-in-second-flag-governance-crackdown/)
- [Lloyd's List Intelligence: AIS Spoofing and Vessel Identity Manipulation](https://www.lloydslistintelligence.com/thought-leadership/blogs/the-secret-lives-of-the-shadow-fleet-ais-spoofing-vessel-identity-manipulation)
- [Kpler: Abandoning the Price Cap Would Expand the Shadow Fleet (Dec 2025)](https://www.kpler.com/blog/abandoning-the-price-cap-would-expand-the-shadow-fleet-and-reshape-tanker-markets)
- [Kpler: Grey Fleet Whitepaper (Mar 2025)](https://marketing.kpler.com/hubfs/Tofu%20Content/Grey_Fleet_whitepaper___March_25.pdf)
- [TankerTrackers.com Dark Fleet Stats](https://tankertrackers.com/report/darkfleetinfo)
- [Paris MoU 2024 Annual Report](https://parismou.org/2025/07/2024-paris-mou-annual-report-progress-and-performance-highlights-paris-mou-2024)
- [Paris MoU 2024 Performance Lists](https://parismou.org/2025/07/2024-performance-lists-paris-mou)
- [RUSI: Countering Shadow Fleet Activity through Flag State Reform](https://www.rusi.org/explore-our-research/publications/insights-papers/countering-shadow-fleet-activity-through-flag-state-reform)
- [RUSI Maritime Sanctions Taskforce Conference Report](https://static.rusi.org/maritime-sanctions-taskforce-conference-report.pdf)
- [Atlantic Council: Threats Posed by the Global Shadow Fleet](https://www.atlanticcouncil.org/in-depth-research-reports/report/the-threats-posed-by-the-global-shadow-fleet-and-how-to-stop-it/)
- [CSIS: Ghost Busters -- Options for Breaking Russia's Shadow Fleet](https://www.csis.org/analysis/ghost-busters-options-breaking-russias-shadow-fleet)
- [European Parliament: Russia's Shadow Fleet Briefing (2024)](https://www.europarl.europa.eu/RegData/etudes/BRIE/2024/766242/EPRS_BRI(2024)766242_EN.pdf)
- [EU Sanctions Operator of Comoros and Gabon Flag Registries](https://maritime-executive.com/article/eu-sanctions-operator-of-the-comoros-and-gabon-flag-registries)
- [Pole Star Global: SKIPPER Sanctions Evasion Analysis](https://www.polestarglobal.com/resources/tracking-the-shadow-fleet-a-retrospective-analysis-of-the-skippers-deceptive-operations/)
- [Gibson: 93% of Shadow Fleet Over 15 Years Old](https://safety4sea.com/gibson-93-of-the-shadow-fleet-is-over-15-years-old/)
- [CHIRP Maritime: How to Identify the Shadow Fleet](https://safety4sea.com/chirp-maritime-how-to-identify-the-shadow-fleet/)
- [IG of P&I Clubs: Massive Exit of Tankers Due to Oil Price Cap](https://safety4sea.com/ig-of-pi-clubs-sees-massive-exit-of-tankers-due-to-oil-price-cap/)
- [RFE/RL: What Happens to a Shadow Fleet Ship When Sanctioned](https://www.rferl.org/a/shadow-fleet-explainer-sanctions-russia-iran/33626443.html)
- [Follow the Money: Russia's Dark Fleet Goes Darker](https://www.ftm.eu/articles/switching-ais-off-shadow-fleet-going-even-darker)
- [Follow the Money: European Shipowners Keep Russia's Shadow Fleet Afloat](https://www.ftm.eu/articles/who-is-behind-the-russian-shadow-fleet)
- [Scientific American: How Dark-Fleet Ships Use a Digital Trick to Disappear](https://www.scientificamerican.com/article/what-is-spoofing-how-a-u-s-seized-oil-tanker-reportedly-tried-to-evade/)
- [Worldwide AIS: Identifying Shadow Fleet Using AIS Framework](https://www.worldwideais.org/post/identifying-shadow-fleet-vessels-using-ais-a-strategic-framework-for-compliance-and-risk-leaders)
