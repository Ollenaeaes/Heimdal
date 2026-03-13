"""Parser for Equasis Ship Folder PDFs.

Extracts structured data from Equasis Ship Folder PDFs using pdfplumber.
"""

import io
import re
from typing import Optional

import pdfplumber


def parse_equasis_pdf(pdf_bytes: bytes) -> dict:
    """Parse an Equasis Ship Folder PDF and return structured data.

    Returns dict with keys:
    - ship_particulars: dict with IMO, name, call_sign, mmsi, gross_tonnage, dwt, ship_type, build_year, flag, status, last_update
    - management: list of dicts with company_imo, role, company_name, address, date_of_effect
    - classification_status: list of dicts with society, date_change, status, reason
    - classification_surveys: list of dicts with society, date_survey, date_next_survey
    - safety_certificates: list of dicts with society, date_survey, date_expiry, date_status, status, reason, type
    - psc_inspections: list of dicts with authority, port, date, detention (bool), psc_organisation, inspection_type, duration_days (int or None), deficiencies (int or None)
    - human_element_deficiencies: list of dicts with psc_org, authority, port, date, count (int)
    - name_history: list of dicts with name, date_of_effect, source
    - flag_history: list of dicts with flag, date_of_effect, source
    - company_history: list of dicts with company, role, date_of_effect, sources
    - edition_date: str (e.g. "13/03/2026") or None

    Raises ValueError if the PDF is not a valid Equasis Ship Folder.
    """
    try:
        pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception as exc:
        raise ValueError(f"Could not open PDF: {exc}") from exc

    if not pdf.pages:
        raise ValueError("PDF has no pages")

    page_texts = []
    for page in pdf.pages:
        text = page.extract_text() or ""
        page_texts.append(text)

    all_text = "\n".join(page_texts)

    if "Equasis" not in all_text or "Ship folder" not in all_text:
        raise ValueError("Not a valid Equasis Ship Folder PDF")

    # Remove footer lines
    clean_text = re.sub(r"Equasis - Ship folder.*?Page \d+/\d+", "", all_text)

    edition_date = _extract_edition_date(all_text)

    result = {
        "ship_particulars": _parse_ship_particulars(clean_text),
        "management": _parse_management(clean_text),
        "classification_status": _parse_classification_status(clean_text),
        "classification_surveys": _parse_classification_surveys(clean_text),
        "safety_certificates": _parse_safety_certificates(clean_text),
        "psc_inspections": _parse_psc_inspections(clean_text),
        "human_element_deficiencies": _parse_human_element_deficiencies(clean_text),
        "name_history": _parse_name_history(clean_text),
        "flag_history": _parse_flag_history(clean_text),
        "company_history": _parse_company_history(clean_text),
        "edition_date": edition_date,
    }

    return result


def _extract_edition_date(text: str) -> Optional[str]:
    match = re.search(r"Edition date (\d{2}/\d{2}/\d{4})", text)
    return match.group(1) if match else None


def _extract_section(text: str, start_pattern: str, end_pattern: str) -> Optional[str]:
    """Extract text between two section headers."""
    start_match = re.search(r"\u2022\s*" + start_pattern, text)
    if not start_match:
        start_match = re.search(start_pattern, text)
    if not start_match:
        return None

    remaining = text[start_match.end():]

    end_match = re.search(r"\u2022\s*(?:" + end_pattern + ")", remaining)
    if not end_match:
        end_match = re.search(end_pattern, remaining)
    if end_match:
        return remaining[:end_match.start()]
    return remaining


def _parse_ship_particulars(text: str) -> dict:
    sp = {}
    m = re.search(r"IMO number\s*:\s*(\d+)", text)
    sp["imo"] = int(m.group(1)) if m else None

    m = re.search(r"Name of ship\s*:\s*(.+)", text)
    sp["name"] = m.group(1).strip() if m else None

    m = re.search(r"Call sign\s*:\s*(\S+)", text)
    sp["call_sign"] = m.group(1) if m else None

    m = re.search(r"MMSI\s*:\s*(\d+)", text)
    sp["mmsi"] = int(m.group(1)) if m else None

    m = re.search(r"Gross tonnage\s*:\s*(\d+)", text)
    sp["gross_tonnage"] = int(m.group(1)) if m else None

    m = re.search(r"DWT\s*:\s*(\d+)", text)
    sp["dwt"] = int(m.group(1)) if m else None

    m = re.search(r"Type of ship\s*:\s*(.+?)(?:\s*\()", text)
    sp["ship_type"] = m.group(1).strip() if m else None

    m = re.search(r"Year of build\s*:\s*(\d{4})", text)
    sp["build_year"] = int(m.group(1)) if m else None

    m = re.search(r"Flag\s*:\s*(.+?)(?:\s*\(since)", text)
    sp["flag"] = m.group(1).strip() if m else None

    m = re.search(r"Status of ship\s*:\s*(.+?)(?:\s*\(since)", text)
    sp["status"] = m.group(1).strip() if m else None

    m = re.search(r"Last update\s*:\s*(\d{2}/\d{2}/\d{4})", text)
    sp["last_update"] = m.group(1) if m else None

    return sp


def _parse_management(text: str) -> list:
    section = _extract_section(text, r"Management detail", r"Classification status")
    if not section:
        return []

    lines = section.strip().split("\n")
    # Skip header
    header_end = 0
    for i, line in enumerate(lines):
        if line.strip() == "effect":
            header_end = i + 1
            break

    lines = lines[header_end:]

    # Group lines by company IMO (7 digits at start)
    groups = []
    current = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^\d{7}", stripped):
            if current:
                groups.append(current)
            current = [stripped]
        else:
            current.append(stripped)
    if current:
        groups.append(current)

    entries = []
    for group_lines in groups:
        entries.append(_parse_management_entry_from_lines(group_lines))
    return entries


def _parse_management_entry_from_lines(lines: list) -> dict:
    """Parse management entry from raw lines (handling column layout)."""
    # The PDF columns are: IMO | Role | Company | Address | Date
    # When extracted as text, columns get interleaved across lines.
    # Strategy: extract IMO and date first, then identify role and company from what remains.

    full_text = " ".join(l.strip() for l in lines)

    # Extract company IMO (first number)
    m = re.match(r"(\d+)\s+", full_text)
    company_imo = int(m.group(1)) if m else None

    # Extract date: "since DD/MM/YYYY" or "during YYYY"
    # Due to column interleaving, "since" and the date may not be adjacent.
    # Find the date marker and the actual date separately.
    date_of_effect = None
    has_since = "since" in full_text.lower()
    has_during = "during" in full_text.lower()
    date_full = re.search(r"(\d{2}/\d{2}/\d{4})", full_text)
    date_year = re.search(r"\b((?:19|20)\d{2})\b", full_text)

    if has_since and date_full:
        date_of_effect = f"since {date_full.group(1)}"
    elif has_during and date_year:
        date_of_effect = f"during {date_year.group(1)}"

    # Identify the role from key phrases in the text
    # The roles can be split across lines, so check in the joined text
    role = None
    if "Ship manager" in full_text and "Commercial" in full_text and "manager" in full_text.split("Commercial")[-1]:
        role = "Ship manager/ Commercial manager"
    elif "Registered" in full_text and "owner" in full_text:
        role = "Registered owner"
    elif "ISM Manager" in full_text or "ISM" in full_text and "Manager" in full_text:
        role = "ISM Manager"
    elif "Commercial" in full_text and "manager" in full_text:
        role = "Commercial manager"
    elif "Ship manager" in full_text:
        role = "Ship manager"

    # Extract company name: find ALL CAPS words (these form the company name)
    # Company names are in ALL CAPS: UNKNOWN, CRESTWAVE MARITIME LTD, etc.
    # Due to column interleaving, they may not be contiguous in the text.
    remaining = full_text
    if m:
        remaining = remaining[m.end():]

    # Find all uppercase words (2+ chars) excluding role keywords and date markers
    role_words = {"ISM", "Manager", "Ship", "Commercial", "Registered"}
    all_caps_words = []
    for word in remaining.split():
        # Include words that are all uppercase and at least 2 chars
        # Also include "LTD", "LLC", etc.
        if word.isupper() and len(word) >= 2 and word not in role_words:
            all_caps_words.append(word)

    company_name = " ".join(all_caps_words) if all_caps_words else None

    # Address: everything that's not IMO, role, company, or date
    # For simplicity, we'll extract it as what remains
    address = None
    # Not critical for the spec, skip detailed address parsing

    return {
        "company_imo": company_imo,
        "role": role,
        "company_name": company_name,
        "address": address,
        "date_of_effect": date_of_effect,
    }


def _parse_classification_status(text: str) -> list:
    section = _extract_section(text, r"Classification status\n", r"Classification surveys")
    if not section:
        return []

    lines = section.strip().split("\n")
    # Skip header (find line "status")
    header_end = 0
    for i, line in enumerate(lines):
        if line.strip() == "status":
            header_end = i + 1
            break

    data_lines = lines[header_end:]
    # Join into single text for parsing
    # Text looks like:
    # "Russian Maritime Register of during Delivered"
    # "Shipping 08/2025"
    # "Registro Italiano Navale (IACS) since Withdrawn by society for other reasons"
    # "27/06/2025"
    data_text = " ".join(l.strip() for l in data_lines if l.strip())

    entries = []
    # Strategy: find each date marker (during/since + date) and status keyword
    # Build entries by finding: society ... date_marker ... status [reason]

    # First, normalize date markers with their dates that may be on next line
    # "during\nDD/MM/YYYY" -> "during DD/MM/YYYY"
    # This is already handled by joining lines.

    # Pattern: everything up to (during|since) is society, then date, then status, then reason
    # But "during" comes before status in the text: "Russian Maritime Register of Shipping during 08/2025 Delivered"
    # And "Registro Italiano Navale (IACS) since 27/06/2025 Withdrawn by society for other reasons"

    # Reorder: the text after joining is:
    # "Russian Maritime Register of during Delivered Shipping 08/2025 Registro Italiano Navale (IACS) since Withdrawn by society for other reasons 27/06/2025"
    # This is still jumbled. Let me parse line by line instead.

    # Re-examine: the lines are:
    # "Russian Maritime Register of during Delivered"
    # "Shipping 08/2025"
    # "Registro Italiano Navale (IACS) since Withdrawn by society for other reasons"
    # "27/06/2025"

    # Group: lines starting with a known society keyword start a new entry
    groups = []
    current = []
    for line in data_lines:
        stripped = line.strip()
        if not stripped:
            continue
        # New entry starts with a society name (capital letter, and contains society keywords)
        if current and _starts_with_society(stripped):
            groups.append(" ".join(current))
            current = [stripped]
        else:
            current.append(stripped)
    if current:
        groups.append(" ".join(current))

    for group_text in groups:
        entry = _parse_single_classification_status(group_text)
        if entry:
            entries.append(entry)

    return entries


def _starts_with_society(text: str) -> bool:
    """Check if text starts with a classification society name."""
    prefixes = [
        "Russian", "Registro", "Lloyd", "Bureau", "DNV", "American",
        "Korean", "China", "Japanese", "Indian", "Nippon", "NK", "CCS",
        "Polish", "Croatian", "Turkish",
    ]
    return any(text.startswith(p) for p in prefixes)


def _parse_single_classification_status(text: str) -> Optional[dict]:
    """Parse a single classification status entry from joined text.

    Text examples:
    - "Russian Maritime Register of during Delivered Shipping 08/2025"
    - "Registro Italiano Navale (IACS) since Withdrawn by society for other reasons 27/06/2025"
    """
    # Find date: DD/MM/YYYY or MM/YYYY
    date_full = re.search(r"(\d{2}/\d{2}/\d{4})", text)
    date_short = re.search(r"(\d{2}/\d{4})", text)

    # Find date marker
    since_match = re.search(r"\bsince\b", text)
    during_match = re.search(r"\bduring\b", text)

    date_change = None
    if since_match and date_full:
        date_change = f"since {date_full.group(1)}"
    elif during_match and date_short:
        date_change = f"during {date_short.group(1)}"

    # Find status
    status = None
    reason = None
    status_keywords = ["Delivered", "Withdrawn", "Classed", "Suspended"]
    for kw in status_keywords:
        if kw in text:
            status = kw
            # Find reason after status keyword
            idx = text.index(kw) + len(kw)
            after = text[idx:].strip()
            # Remove date parts from after
            after = re.sub(r"\d{2}/\d{2}/\d{4}", "", after)
            after = re.sub(r"\d{2}/\d{4}", "", after)
            after = after.strip()
            if after:
                reason = after
            break

    # Society: everything before the date marker
    marker_pos = None
    if since_match:
        marker_pos = since_match.start()
    elif during_match:
        marker_pos = during_match.start()

    society = text[:marker_pos].strip() if marker_pos else text.strip()

    # The society name may be split: "Russian Maritime Register of" with "Shipping" after the date
    # We need to reconstruct: look for society continuation words after status/date
    # Check if there are leftover capitalized words that belong to the society
    if date_change and status:
        # Get everything that's not date, status, reason, or date marker
        remaining = text
        remaining = remaining.replace(status, "", 1)
        if reason:
            remaining = remaining.replace(reason, "", 1)
        remaining = re.sub(r"\bsince\b", "", remaining, count=1)
        remaining = re.sub(r"\bduring\b", "", remaining, count=1)
        remaining = re.sub(r"\d{2}/\d{2}/\d{4}", "", remaining)
        remaining = re.sub(r"\d{2}/\d{4}", "", remaining)
        remaining = re.sub(r"\s+", " ", remaining).strip()
        if remaining:
            society = remaining

    return {
        "society": society,
        "date_change": date_change,
        "status": status,
        "reason": reason,
    }


def _parse_classification_surveys(text: str) -> list:
    section = _extract_section(text, r"Classification surveys", r"Safety management certificate")
    if not section:
        return []

    lines = section.strip().split("\n")
    header_end = 0
    for i, line in enumerate(lines):
        if "survey" in line.lower():
            header_end = i + 1

    data_lines = lines[header_end:]
    data_text = " ".join(l.strip() for l in data_lines if l.strip())

    entries = []
    pattern = r"(.+?)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})"
    for m in re.finditer(pattern, data_text):
        entries.append({
            "society": m.group(1).strip(),
            "date_survey": m.group(2),
            "date_next_survey": m.group(3),
        })

    return entries


def _parse_safety_certificates(text: str) -> list:
    section = _extract_section(
        text, r"Safety management certificate",
        r"Ship inspections|List of port state control"
    )
    if not section:
        return []

    lines = section.strip().split("\n")
    header_end = 0
    for i, line in enumerate(lines):
        if re.search(r"Type\s*$", line.strip()):
            header_end = i + 1
            break

    data_lines = lines[header_end:]
    data_text = " ".join(l.strip() for l in data_lines if l.strip())

    entries = []
    parts = re.split(r"(Convention|Flag)", data_text)
    i = 0
    while i < len(parts) - 1:
        entry_text = parts[i].strip()
        cert_type = parts[i + 1] if i + 1 < len(parts) else None

        if entry_text:
            dates = re.findall(r"\d{2}/\d{2}/\d{4}", entry_text)
            if dates:
                society = entry_text[:entry_text.index(dates[0])].strip()
                entries.append({
                    "society": society,
                    "date_survey": dates[0] if len(dates) >= 1 else None,
                    "date_expiry": dates[1] if len(dates) >= 2 else None,
                    "date_status": dates[2] if len(dates) >= 3 else None,
                    "status": None,
                    "reason": None,
                    "type": cert_type,
                })
        i += 2

    return entries


def _parse_psc_inspections(text: str) -> list:
    entries = []

    psc_sections = re.split(r"\u2022\s*List of port state control\n", text)

    for section_text in psc_sections[1:]:
        next_section = re.search(r"\u2022\s+", section_text)
        if next_section:
            section_text = section_text[:next_section.start()]

        lines = section_text.strip().split("\n")
        header_end = 0
        for i, line in enumerate(lines):
            if re.search(r"deficiencies\s*$", line.strip()):
                header_end = i + 1
                break

        lines = lines[header_end:]
        _parse_psc_lines(lines, entries)

    return entries


def _parse_psc_lines(lines: list, entries: list):
    current_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if "Human element" in stripped or "Privates inspections" in stripped:
            break

        has_date = bool(re.search(r"\d{2}/\d{2}/\d{4}", stripped))

        if has_date and current_lines:
            current_text = " ".join(current_lines)
            if re.search(r"\d{2}/\d{2}/\d{4}", current_text):
                entries.append(_parse_psc_entry(current_lines))
                current_lines = [stripped]
            else:
                current_lines.append(stripped)
        elif has_date:
            current_lines = [stripped]
        elif current_lines:
            current_lines.append(stripped)

    if current_lines:
        current_text = " ".join(current_lines)
        if re.search(r"\d{2}/\d{2}/\d{4}", current_text):
            entries.append(_parse_psc_entry(current_lines))


def _parse_psc_entry(lines: list) -> dict:
    full_text = " ".join(lines)

    date_match = re.search(r"(\d{2}/\d{2}/\d{4})", full_text)
    date = date_match.group(1) if date_match else None

    detention_match = re.search(r"\d{2}/\d{2}/\d{4}\s+([YN])\s", full_text)
    detention = None
    if detention_match:
        detention = detention_match.group(1) == "Y"

    before_date = full_text[:date_match.start()].strip() if date_match else full_text

    psc_orgs = [
        "Paris MoU", "Tokyo MoU", "Mediterranean MoU", "Black Sea MoU",
        "Indian Ocean MoU", "US Coast Guard", "Riyadh MoU", "Abuja MoU",
        "Vina del Mar Agreement",
    ]
    psc_org = None
    for org in psc_orgs:
        if org in full_text:
            psc_org = org
            break

    inspection_types = [
        "More detailed inspection",
        "Expanded inspection",
        "Initial inspection",
        "Standard Examination",
        "Concentrated inspection",
        "Follow up inspection",
    ]
    inspection_type = None
    for it in inspection_types:
        if it.lower() in full_text.lower():
            inspection_type = it
            break

    duration_days = None
    deficiencies = None

    if detention_match:
        after_detention = full_text[detention_match.end():]
        nums_text = after_detention
        if psc_org:
            nums_text = nums_text.replace(psc_org, "")
        if inspection_type:
            for it in inspection_types:
                nums_text = re.sub(re.escape(it), "", nums_text, flags=re.IGNORECASE)
        numbers = re.findall(r"\b(\d+)\b", nums_text)
        if len(numbers) >= 2:
            duration_days = int(numbers[-2])
            deficiencies = int(numbers[-1])
        elif len(numbers) == 1:
            duration_days = int(numbers[0])
            deficiencies = None

    authority = None
    port = None
    if before_date:
        authority, port = _split_authority_port(before_date)

    return {
        "authority": authority,
        "port": port,
        "date": date,
        "detention": detention,
        "psc_organisation": psc_org,
        "inspection_type": inspection_type,
        "duration_days": duration_days,
        "deficiencies": deficiencies,
    }


def _split_authority_port(text: str) -> tuple:
    multi_word_authorities = [
        "United States of America",
        "China Peoples's Republic",
        "China People's Republic",
    ]
    for auth in multi_word_authorities:
        if text.startswith(auth):
            port = text[len(auth):].strip().rstrip(",")
            return auth, port

    parts = text.split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1].strip().rstrip(",")
    return text, None


def _parse_human_element_deficiencies(text: str) -> list:
    section = _extract_section(text, r"Human element deficiencies", r"Privates inspections|Oil Companies")
    if not section:
        return []

    lines = section.strip().split("\n")
    header_end = 0
    for i, line in enumerate(lines):
        if re.search(r"deficiencies\s*$", line.strip()):
            header_end = i + 1
            break

    lines = lines[header_end:]
    entries = []
    current_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        has_date = bool(re.search(r"\d{2}/\d{2}/\d{4}", stripped))
        if has_date and current_lines:
            entries.append(_parse_hed_entry(current_lines))
            current_lines = [stripped]
        elif has_date:
            current_lines = [stripped]
        elif current_lines:
            current_lines.append(stripped)

    if current_lines:
        entries.append(_parse_hed_entry(current_lines))
    return entries


def _parse_hed_entry(lines: list) -> dict:
    full_text = " ".join(lines)

    psc_orgs = [
        "Paris MoU", "Tokyo MoU", "Mediterranean MoU", "Black Sea MoU",
        "Indian Ocean MoU", "US Coast Guard",
    ]
    psc_org = None
    for org in psc_orgs:
        if org in full_text:
            psc_org = org
            break

    date_match = re.search(r"(\d{2}/\d{2}/\d{4})", full_text)
    date = date_match.group(1) if date_match else None

    numbers = re.findall(r"\b(\d+)\b", full_text)
    count = int(numbers[-1]) if numbers else None

    authority = None
    port = None
    if psc_org and date_match:
        between = full_text[full_text.index(psc_org) + len(psc_org):date_match.start()].strip()
        parts = between.split(None, 1)
        if len(parts) >= 2:
            authority = parts[0]
            port = parts[1].strip()
        elif len(parts) == 1:
            authority = parts[0]

    return {
        "psc_org": psc_org,
        "authority": authority,
        "port": port,
        "date": date,
        "count": count,
    }


def _parse_name_history(text: str) -> list:
    section = _extract_section(text, r"Current and former name\(s\)", r"Current and former flag")
    if not section:
        return []

    lines = section.strip().split("\n")
    header_end = 0
    for i, line in enumerate(lines):
        if re.search(r"effect\s*$", line.strip()):
            header_end = i + 1
            break

    data_lines = lines[header_end:]
    # Join all data into one text
    data_text = " ".join(l.strip() for l in data_lines if l.strip())

    # The text looks like:
    # "BLUE since IHS 01/02/2024 Maritime Julia A since IHS 01/09/2022 Maritime ..."
    # Pattern: NAME since|during [IHS] DD/MM/YYYY [Maritime]
    # The "IHS" and date are interleaved because of columns.
    # Actual structure: NAME | since DD/MM/YYYY | IHS Maritime
    # But extracted as: NAME since IHS DD/MM/YYYY Maritime

    entries = []
    # Match: name (since|during) IHS? DD/MM/YYYY Maritime?
    # Or: name (since|during) IHS? YYYY Maritime? (for "during YYYY")
    pattern = r"(.+?)\s+(since|during)\s+(?:IHS\s+)?(\d{2}/\d{2}/\d{4}|\d{4})\s*(?:Maritime)?"

    for m in re.finditer(pattern, data_text):
        name = m.group(1).strip()
        # Clean up: remove trailing "Maritime" from previous entry
        if name.startswith("Maritime "):
            name = name[len("Maritime "):].strip()
        elif name.startswith("Maritime"):
            name = name[len("Maritime"):].strip()

        date_val = m.group(3)
        marker = m.group(2)
        if "/" in date_val:
            date_of_effect = f"{marker} {date_val}"
        else:
            date_of_effect = f"{marker} {date_val}"

        entries.append({
            "name": name,
            "date_of_effect": date_of_effect,
            "source": "IHS Maritime",
        })

    return entries


def _parse_flag_history(text: str) -> list:
    entries = []

    # Find all flag sections
    pattern = r"Current and former flag\(s\)\n(.*?)(?=Current and former classification|\u2022 Company|$)"
    sections = re.findall(pattern, text, re.DOTALL)

    for section in sections:
        lines = section.strip().split("\n")
        header_end = 0
        for i, line in enumerate(lines):
            if re.search(r"effect\s*$", line.strip()):
                header_end = i + 1
                break

        data_lines = lines[header_end:]
        data_text = " ".join(l.strip() for l in data_lines if l.strip())

        # Same pattern as name history: FLAG since|during IHS? DD/MM/YYYY Maritime?
        flag_pattern = r"(.+?)\s+(since|during)\s+(?:IHS\s+)?(\d{2}/\d{2}/\d{4}|\d{4})\s*(?:Maritime)?"

        for m in re.finditer(flag_pattern, data_text):
            flag = m.group(1).strip()
            if flag.startswith("Maritime "):
                flag = flag[len("Maritime "):].strip()
            elif flag.startswith("Maritime"):
                flag = flag[len("Maritime"):].strip()

            date_val = m.group(3)
            marker = m.group(2)
            date_of_effect = f"{marker} {date_val}"

            entries.append({
                "flag": flag,
                "date_of_effect": date_of_effect,
                "source": "IHS Maritime",
            })

    return entries


def _parse_company_history(text: str) -> list:
    entries = []

    # Find all Company sections
    pattern = r"\u2022 Company\n(.*?)(?=\u2022|\Z)"
    sections = re.findall(pattern, text, re.DOTALL)

    for section in sections:
        lines = section.strip().split("\n")
        header_end = 0
        for i, line in enumerate(lines):
            if line.strip() == "effect":
                header_end = i + 1
                break

        data_lines = lines[header_end:]
        current_lines = []

        for line in data_lines:
            stripped = line.strip()
            if not stripped:
                continue

            has_date_marker = bool(re.search(r"(since|during)", stripped))

            if has_date_marker and current_lines:
                current_text = " ".join(current_lines)
                if re.search(r"(since|during)", current_text):
                    entries.append(_parse_company_entry(current_lines))
                    current_lines = [stripped]
                else:
                    current_lines.append(stripped)
            elif current_lines:
                current_lines.append(stripped)
            else:
                current_lines = [stripped]

        if current_lines:
            entries.append(_parse_company_entry(current_lines))

    return entries


def _parse_company_entry(lines: list) -> dict:
    full_text = re.sub(r"\s+", " ", " ".join(lines)).strip()

    date_match = re.search(r"(since\s+\d{2}/\d{2}/\d{4}|during\s+\d{4})", full_text)
    date_of_effect = date_match.group(1) if date_match else None

    sources = None
    if date_match:
        sources_text = full_text[date_match.end():].strip()
        if sources_text:
            sources = sources_text

    before_date = full_text[:date_match.start()].strip() if date_match else full_text

    role_patterns = [
        "Ship manager/ Commercial manager",
        "Ship manager/Commercial manager",
        "ISM Manager",
        "Registered owner",
        "Commercial manager",
        "Ship manager",
    ]

    role = None
    company = before_date
    for rp in role_patterns:
        if rp in before_date:
            idx = before_date.index(rp)
            company = before_date[:idx].strip()
            role = rp
            break

    return {
        "company": company,
        "role": role,
        "date_of_effect": date_of_effect,
        "sources": sources,
    }
