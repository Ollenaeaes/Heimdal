"""Parser for Equasis Ship Folder and Company Folder PDFs.

Extracts structured data from Equasis PDFs using pdfplumber.
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

    if "Equasis" not in all_text:
        raise ValueError("Not a valid Equasis PDF")

    # Detect document type
    is_company_folder = "Company folder" in all_text
    is_ship_folder = "Ship folder" in all_text

    if is_company_folder:
        return parse_company_folder(all_text, pdf)
    elif is_ship_folder:
        return _parse_ship_folder(all_text)
    else:
        raise ValueError("Not a valid Equasis PDF: missing 'Ship folder' or 'Company folder' header")


def _parse_ship_folder(all_text: str) -> dict:
    """Parse a Ship Folder PDF from its extracted text."""
    # Remove footer lines
    clean_text = re.sub(r"Equasis - Ship folder.*?Page \d+/\d+", "", all_text)

    edition_date = _extract_edition_date(all_text)

    result = {
        "document_type": "ship_folder",
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
        "p_and_i": _parse_p_and_i(clean_text),
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
    name = m.group(1).strip() if m else None
    if name:
        # Strip trailing "(since ..." artefact from multi-line PDF extraction
        name = re.sub(r"\s*\(since$", "", name)
    sp["name"] = name

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


def _parse_p_and_i(text: str) -> list:
    """Parse P&I information section.

    Format:
        • P&I information
        Name of P&I insurer Recorded
        on
        <insurer name> <dd/mm/yyyy>
        <insurer name continued (optional)>
    """
    entries = []

    section = _extract_section(text, r"P&I information", r"List of port state control|PSC inspections|Human element|Name history|Flag|Company|Equasis")
    if not section:
        return entries

    lines = [l.strip() for l in section.strip().split("\n") if l.strip()]

    # Skip header lines ("Name of P&I insurer", "Recorded", "on")
    data_start = 0
    for i, line in enumerate(lines):
        if line.lower().startswith("on") and len(line) <= 3:
            data_start = i + 1
            break
        if "recorded" in line.lower():
            # "on" might be on the same line or next
            if i + 1 < len(lines) and lines[i + 1].lower().strip() == "on":
                data_start = i + 2
            else:
                data_start = i + 1
            break

    # Parse insurer entries: lines with a date dd/mm/yyyy
    data_lines = lines[data_start:]
    current_name_parts = []
    current_date = None

    for line in data_lines:
        # Skip page footer and section boundary lines
        if line.startswith("Equasis -") or line == "Ship inspections":
            continue

        date_match = re.search(r"(\d{2}/\d{2}/\d{4})", line)
        if date_match:
            # If we had a previous entry, save it
            if current_name_parts and current_date:
                entries.append({
                    "insurer": " ".join(current_name_parts).strip(),
                    "recorded_on": current_date,
                })
                current_name_parts = []

            # Extract name part (before the date)
            name_part = line[:date_match.start()].strip()
            current_date = date_match.group(1)
            if name_part:
                current_name_parts = [name_part]
            else:
                current_name_parts = []
        else:
            # Continuation line for insurer name
            if line and not line.startswith("Name of"):
                current_name_parts.append(line)

    # Save last entry
    if current_name_parts and current_date:
        entries.append({
            "insurer": " ".join(current_name_parts).strip(),
            "recorded_on": current_date,
        })

    return entries


# ===================================================================
# Company Folder Parser
# ===================================================================


def parse_company_folder(all_text: str, pdf) -> dict:
    """Parse an Equasis Company Folder PDF.

    Returns dict with keys:
    - document_type: "company_folder"
    - company_particulars: dict with company_imo, company_name, address, last_update
    - documents_of_compliance: list of dicts
    - inspection_synthesis: list of dicts with role, ships_in_company, inspections, detentions, etc.
    - fleet: list of dicts with imo, ship_name, gross_tonnage, ship_type, year_of_build, current_flag, current_class, acting_as
    - edition_date: str or None
    """
    # Remove footer lines
    clean_text = re.sub(r"Equasis - Company folder.*?Page \d+/\d+", "", all_text)
    edition_date = _extract_company_edition_date(all_text)

    # Extract tables from all pages for fleet parsing
    all_tables = []
    for page in pdf.pages:
        tables = page.extract_tables()
        if tables:
            all_tables.extend(tables)

    result = {
        "document_type": "company_folder",
        "company_particulars": _parse_company_particulars(clean_text),
        "documents_of_compliance": _parse_documents_of_compliance(clean_text),
        "inspection_synthesis": _parse_inspection_synthesis(clean_text),
        "fleet": _parse_fleet_from_tables(all_tables, clean_text),
        "edition_date": edition_date,
    }

    return result


def _extract_company_edition_date(text: str) -> Optional[str]:
    match = re.search(r"Edition date (\d{2}/\d{2}/\d{4})", text)
    return match.group(1) if match else None


def _parse_company_particulars(text: str) -> dict:
    result = {}

    m = re.search(r"IMO number\s*:\s*(\d+)", text)
    result["company_imo"] = m.group(1) if m else None

    m = re.search(r"Name of company\s*:\s*(.+?)(?:\n|$)", text)
    result["company_name"] = m.group(1).strip() if m else None

    m = re.search(r"Address\s*:\s*(.+?)(?:Last update|$)", text, re.DOTALL)
    if m:
        addr = m.group(1).strip()
        # Clean up multi-line address
        addr = re.sub(r"\s+", " ", addr).strip()
        result["address"] = addr
    else:
        result["address"] = None

    m = re.search(r"Last update\s*:\s*(\d{2}/\d{2}/\d{4})", text)
    result["last_update"] = m.group(1) if m else None

    return result


def _parse_documents_of_compliance(text: str) -> list:
    """Parse the Documents of Compliance section."""
    section = _extract_section(text, r"Documents of compliance", r"Synthesis of inspections|Company fleet")
    if not section:
        return []

    lines = section.strip().split("\n")
    # Skip header lines
    header_end = 0
    for i, line in enumerate(lines):
        if "Reason" in line:
            header_end = i + 1
            break

    entries = []
    data_lines = lines[header_end:]
    current_lines = []
    for line in data_lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Heuristic: new entry starts with a country name (capitalized word)
        if current_lines and re.match(r"^[A-Z][a-z]", stripped):
            entries.append(_parse_doc_compliance_entry(current_lines))
            current_lines = [stripped]
        else:
            current_lines.append(stripped)
    if current_lines:
        entries.append(_parse_doc_compliance_entry(current_lines))

    return entries


def _parse_doc_compliance_entry(lines: list) -> dict:
    full_text = " ".join(lines)
    date_match = re.search(r"(\d{2}/\d{2}/\d{4})", full_text)

    statuses = ["Delivered", "Withdrawn", "Suspended"]
    status = None
    reason = None
    for s in statuses:
        if s in full_text:
            status = s
            idx = full_text.index(s) + len(s)
            after = full_text[idx:].strip()
            after = re.sub(r"\d{2}/\d{2}/\d{4}", "", after).strip()
            if after:
                reason = after
            break

    return {
        "flag": lines[0].split()[0] if lines else None,
        "ship_type": None,  # Complex to parse from interleaved text
        "classification_society": None,
        "status": status,
        "date_of_status": date_match.group(1) if date_match else None,
        "reason": reason,
    }


def _parse_inspection_synthesis(text: str) -> list:
    """Parse the Synthesis of Inspections section."""
    section = _extract_section(text, r"Synthesis of inspections", r"Company fleet|Fleet")
    if not section:
        return []

    lines = section.strip().split("\n")
    # Skip headers
    header_end = 0
    for i, line in enumerate(lines):
        if "detention" in line.lower() and i > 0:
            header_end = i + 1
            break

    entries = []
    data_lines = lines[header_end:]

    role_patterns = [
        "Registered owner",
        "ISM Manager",
        "Ship manager",
    ]

    for line in data_lines:
        stripped = line.strip()
        if not stripped:
            continue

        for rp in role_patterns:
            if rp in stripped:
                numbers = re.findall(r"\b(\d+)\b", stripped)
                entry = {"role": rp}
                if len(numbers) >= 5:
                    entry["ships_in_company"] = int(numbers[0])
                    entry["inspections_company"] = int(numbers[1])
                    entry["detentions_company"] = int(numbers[2])
                    entry["inspections_all"] = int(numbers[3])
                    entry["detentions_all"] = int(numbers[4])
                elif len(numbers) >= 1:
                    entry["ships_in_company"] = int(numbers[0])
                entries.append(entry)
                break

    return entries


def _parse_fleet_from_tables(tables: list, text: str) -> list:
    """Parse fleet vessels from pdfplumber-extracted tables.

    Falls back to text-based parsing if table extraction fails.
    """
    fleet = []
    seen_imos = set()

    # Try table-based extraction first
    for table in tables:
        if not table or len(table) < 2:
            continue

        # Check if this is a fleet table by looking at headers
        header = table[0]
        if not header:
            continue
        header_text = " ".join(str(cell or "") for cell in header).lower()
        if "imo" not in header_text or "ship" not in header_text:
            continue

        # Parse data rows
        for row in table[1:]:
            if not row or len(row) < 5:
                continue

            cells = [str(cell or "").strip() for cell in row]

            # Find IMO (7-digit number)
            imo = None
            for cell in cells:
                m = re.search(r"\b(\d{7})\b", cell)
                if m:
                    imo = int(m.group(1))
                    break

            if not imo or imo in seen_imos:
                continue
            seen_imos.add(imo)

            vessel = _parse_fleet_row(cells, header)
            vessel["imo"] = imo
            fleet.append(vessel)

    # If table extraction found vessels, supplement with text-based extraction
    # for any IMOs missed due to pdfplumber table boundary issues
    if fleet:
        # Find company IMO to exclude it from fleet
        company_imo = None
        company_match = re.search(r"imo\s*(?:company\s*)?(?:number)?\s*:?\s*(\d{7})", text, re.IGNORECASE)
        if company_match:
            company_imo = int(company_match.group(1))

        text_fleet = _parse_fleet_from_text(text)
        for vessel in text_fleet:
            vimo = vessel.get("imo")
            if vimo and vimo not in seen_imos and vimo != company_imo:
                fleet.append(vessel)
                seen_imos.add(vimo)
        return fleet

    # Fallback: text-based extraction only
    return _parse_fleet_from_text(text)


def _parse_fleet_row(cells: list, header: list) -> dict:
    """Parse a single fleet table row into a vessel dict."""
    vessel: dict = {}

    # Map header columns to values
    header_lower = [str(h or "").strip().lower() for h in header]

    for i, h in enumerate(header_lower):
        if i >= len(cells):
            break
        val = cells[i].strip()
        if not val:
            continue

        if "ship" in h and "type" not in h:
            vessel["ship_name"] = val
        elif "gross" in h or "tonnage" in h:
            m = re.search(r"(\d+)", val)
            vessel["gross_tonnage"] = int(m.group(1)) if m else None
        elif "ship type" in h or ("type" in h and "ship" not in h):
            vessel["ship_type"] = val
        elif "year" in h or "build" in h:
            m = re.search(r"(\d{4})", val)
            vessel["year_of_build"] = int(m.group(1)) if m else None
        elif "flag" in h:
            vessel["current_flag"] = val
        elif "class" in h:
            vessel["current_class"] = val
        elif "acting" in h:
            vessel["acting_as"] = val

    return vessel


def _parse_fleet_from_text(text: str) -> list:
    """Fallback: parse fleet from raw text using IMO number patterns."""
    fleet = []
    seen_imos = set()

    # Find the Fleet section
    fleet_match = re.search(r"Fleet\n", text)
    if not fleet_match:
        return fleet

    fleet_text = text[fleet_match.end():]

    # Find all 7-digit IMO numbers
    imo_positions = list(re.finditer(r"\b(\d{7})\b", fleet_text))

    for i, m in enumerate(imo_positions):
        imo = int(m.group(1))
        if imo in seen_imos:
            continue
        seen_imos.add(imo)

        # Get text between this IMO and the next
        start = m.start()
        end = imo_positions[i + 1].start() if i + 1 < len(imo_positions) else len(fleet_text)
        block = fleet_text[start:end]

        vessel = {"imo": imo}

        # Extract ship name (ALL CAPS word(s) after IMO, may wrap across lines)
        name_match = re.search(r"\d{7}\s+([A-Z][A-Z\s]+?)(?:\s+\d)", block)
        if name_match:
            raw_name = name_match.group(1).strip()
            # Check if name continues on next line (e.g. "VLADIMIR\nVIZE")
            after_imo = block[len(str(imo)):].lstrip()
            name_lines = []
            for line in after_imo.split("\n"):
                line = line.strip()
                # Name lines are ALL CAPS and don't contain digits
                if line and re.match(r"^[A-Z][A-Z\s\-\.]+$", line):
                    name_lines.append(line)
                else:
                    break
            if name_lines:
                vessel["ship_name"] = " ".join(name_lines)
            else:
                vessel["ship_name"] = raw_name

        # Gross tonnage
        gt_match = re.search(r"(\d{4,6})\s+(?:Crude|Oil|Chemical|Bulk|Container|General)", block)
        if gt_match:
            vessel["gross_tonnage"] = int(gt_match.group(1))

        # Ship type
        type_match = re.search(r"(Crude Oil Tanker|Oil Products Tanker|Chemical/?\s*Oil Products Tanker|Bulk Carrier|Container Ship|General Cargo)", block, re.IGNORECASE)
        if type_match:
            vessel["ship_type"] = type_match.group(1).strip()

        # Year of build
        year_match = re.search(r"\b(19\d{2}|20[0-2]\d)\b", block)
        if year_match:
            vessel["year_of_build"] = int(year_match.group(1))

        # Current flag
        flag_match = re.search(r"(Russia|Panama|Liberia|Marshall Islands|Cameroon|Gabon|Palau|Togo|Malta|Cyprus|Greece|China|India|Turkey|Singapore)", block, re.IGNORECASE)
        if flag_match:
            vessel["current_flag"] = flag_match.group(1)

        # Current class (abbreviations)
        class_match = re.search(r"\b(IRS|RMRS|BV|DNV|LR|ABS|NK|RINA|KR|CCS|PRS|CRS|HR|NV)\b", block)
        if class_match:
            # Collect all class abbreviations
            classes = re.findall(r"\b(IRS|RMRS|BV|DNV|LR|ABS|NK|RINA|KR|CCS|PRS|CRS|HR|NV)\b", block)
            vessel["current_class"] = " ".join(classes[:3])  # Cap at 3

        # Acting as (roles)
        roles = []
        for role_pattern in [r"Registered\s+owner", r"ISM Manager", r"Ship manager/?\s*Commercial\s*manager"]:
            rm = re.search(role_pattern, block, re.IGNORECASE)
            if rm:
                # Find associated date
                after = block[rm.end():]
                date_m = re.search(r"\(since\s+(\d{2}/\d{2}/\d{4})\)", after)
                roles.append({
                    "role": rm.group(0).strip(),
                    "since": date_m.group(1) if date_m else None,
                })
        if roles:
            # Format as string matching the table-extraction format
            parts = []
            for r in roles:
                part = r["role"]
                if r.get("since"):
                    part += f"\n(since\n{r['since']})"
                parts.append(part)
            vessel["acting_as"] = "\n".join(parts)

        fleet.append(vessel)

    return fleet
