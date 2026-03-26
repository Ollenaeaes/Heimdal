"""
Parser for Paris MoU THETIS XML inspection data.

Handles large (135MB+) single-line XML files using iterparse for memory efficiency.
Supports both .xml and .xml.zip files transparently.
"""

import logging
import zipfile
from collections.abc import Iterator
from pathlib import Path

from lxml import etree

logger = logging.getLogger(__name__)

NS = "urn:getPublicInspections.xmlData.business.thetis.emsa.europa.eu"

IG_PI_CLUBS = {
    "Britannia",
    "Gard",
    "Japan P&I Club",
    "London P&I Club",
    "NorthStandard",
    "Shipowners Club",
    "Skuld",
    "Steamship Mutual",
    "Swedish Club",
    "UK P&I Club",
    "West P&I Club",
    "American Club",
    "MS Amlin",
}


def _attr(elem, name: str) -> str | None:
    """Get a namespaced attribute value from an element."""
    return elem.get(f"{{{NS}}}{name}")


def _collect_raw_attrs(elem) -> dict:
    """Collect all attributes from an element, stripping the namespace prefix."""
    result = {}
    for key, val in elem.attrib.items():
        # Strip namespace from attribute name
        if key.startswith(f"{{{NS}}}"):
            clean_key = key[len(f"{{{NS}}}"):]
        else:
            clean_key = key
        result[clean_key] = val
    return result


def _parse_inspection(inspection_elem) -> dict | None:
    """Parse a single Inspection element into a dict."""
    try:
        inspection_id = _attr(inspection_elem, "InspectionID")
        if not inspection_id:
            logger.warning("Skipping inspection with no InspectionID")
            return None

        reporting_authority = _attr(inspection_elem, "ReportingAuthority")
        inspection_date = _attr(inspection_elem, "DateOfFirstVisit")
        inspection_end_date = _attr(inspection_elem, "DateOfFinalVisit")
        inspection_type = _attr(inspection_elem, "PSCInspectionType")
        inspection_port = _attr(inspection_elem, "PlaceOfInspection")
        port_country = inspection_port[:2] if inspection_port and len(inspection_port) >= 2 else None

        # Raw data: start with inspection-level attributes
        raw_data = _collect_raw_attrs(inspection_elem)

        # Ship particulars
        imo = None
        ship_name = None
        flag_state = None
        ship_type = None
        gross_tonnage = None
        keel_laid_date = None

        ship_elem = inspection_elem.find(f"{{{NS}}}ShipParticulars")
        if ship_elem is not None:
            raw_data["ShipParticulars"] = _collect_raw_attrs(ship_elem)
            imo_str = _attr(ship_elem, "IMO")
            if imo_str:
                try:
                    imo = int(imo_str)
                except ValueError:
                    logger.warning("Invalid IMO '%s' in inspection %s", imo_str, inspection_id)

            for child in ship_elem:
                tag = etree.QName(child.tag).localname
                val = _attr(child, "Value")
                if tag == "Name":
                    ship_name = val
                elif tag == "Flag":
                    flag_state = val
                elif tag == "ShipType":
                    ship_type = val
                elif tag == "GrossTonnage":
                    if val:
                        try:
                            gross_tonnage = int(val)
                        except ValueError:
                            pass
                elif tag == "KeelDate":
                    keel_laid_date = val

        # ISM Company
        ism_company_imo = None
        ism_company_name = None
        ism_elem = inspection_elem.find(f"{{{NS}}}ISMCompany")
        if ism_elem is not None:
            raw_data["ISMCompany"] = _collect_raw_attrs(ism_elem)
            ism_company_imo = _attr(ism_elem, "IMO")
            ism_company_name = _attr(ism_elem, "Name")

        # Class Certificates
        ro_at_inspection = None
        certificates = []

        class_certs_elem = inspection_elem.find(f"{{{NS}}}ClassCertificates")
        if class_certs_elem is not None:
            raw_data["ClassCertificates"] = []
            for cert_elem in class_certs_elem.findall(f"{{{NS}}}ClassCertificate"):
                cert_attrs = _collect_raw_attrs(cert_elem)
                raw_data["ClassCertificates"].append(cert_attrs)

                issuing_authority = _attr(cert_elem, "IssuingAuthority")
                if issuing_authority and ro_at_inspection is None:
                    ro_at_inspection = issuing_authority

                certificates.append({
                    "certificate_type": _attr(cert_elem, "ClassStatus") or "",
                    "issuing_authority": issuing_authority or "",
                    "issuing_authority_type": None,
                    "expiry_date": _attr(cert_elem, "ExpiryDate"),
                    "issue_date": _attr(cert_elem, "IssueDate"),
                    "certificate_source": "class",
                })

        # Statutory Certificates
        pi_provider_at_inspection = None

        stat_certs_elem = inspection_elem.find(f"{{{NS}}}StatutoryCertificates")
        if stat_certs_elem is not None:
            raw_data["StatutoryCertificates"] = []
            for cert_elem in stat_certs_elem.findall(f"{{{NS}}}StatutoryCertificate"):
                cert_attrs = _collect_raw_attrs(cert_elem)
                raw_data["StatutoryCertificates"].append(cert_attrs)

                cert_code = _attr(cert_elem, "CertificateCode") or ""
                issuing_authority = _attr(cert_elem, "IssuingAuthority") or ""
                # Note: the XML has a typo "IssuingAutorityType" (missing 'h')
                issuing_authority_type = _attr(cert_elem, "IssuingAutorityType")

                # P&I provider from CLC (509) or Bunker Convention (510)
                if cert_code in ("509", "510") and issuing_authority and pi_provider_at_inspection is None:
                    pi_provider_at_inspection = issuing_authority

                certificates.append({
                    "certificate_type": cert_code,
                    "issuing_authority": issuing_authority,
                    "issuing_authority_type": issuing_authority_type,
                    "expiry_date": _attr(cert_elem, "DateOfExpiry"),
                    "issue_date": _attr(cert_elem, "DateOfIssue"),
                    "certificate_source": "statutory",
                })

        # Deficiencies
        deficiencies = []
        detained = False
        ism_deficiency = False

        def_container = inspection_elem.find(f"{{{NS}}}Deficiencies")
        if def_container is not None:
            raw_data["Deficiencies"] = []
            for def_elem in def_container.findall(f"{{{NS}}}Deficiency"):
                def_attrs = _collect_raw_attrs(def_elem)
                raw_data["Deficiencies"].append(def_attrs)

                deficiency_code = _attr(def_elem, "DefectiveItemCode") or ""
                nature_of_defect = _attr(def_elem, "NatureOfDefectCode") or ""
                is_ground_detention = (_attr(def_elem, "isGroundDetention") or "").lower() == "true"
                is_ro_related = (_attr(def_elem, "isRORelated") or "").lower() == "true"
                is_accidental_damage = (_attr(def_elem, "isAccidentalDamage") or "").lower() == "true"

                if is_ground_detention:
                    detained = True

                # ISM deficiency: code starts with "011" (certificates area) or in 15xxx range
                if deficiency_code.startswith("011") or deficiency_code.startswith("15"):
                    ism_deficiency = True

                deficiencies.append({
                    "deficiency_code": deficiency_code,
                    "nature_of_defect": nature_of_defect,
                    "is_ground_detention": is_ground_detention,
                    "is_ro_related": is_ro_related,
                    "is_accidental_damage": is_accidental_damage,
                })

        # Charterers (raw data only)
        charterers_elem = inspection_elem.find(f"{{{NS}}}Charterers")
        if charterers_elem is not None:
            raw_data["Charterers"] = []
            for ch_elem in charterers_elem.findall(f"{{{NS}}}Charterer"):
                raw_data["Charterers"].append(_collect_raw_attrs(ch_elem))

        # Strip trailing 'Z' from date strings for cleaner ISO format
        def _clean_date(d: str | None) -> str | None:
            if not d:
                return None
            if d.endswith("Z"):
                return d[:-1]
            return d

        return {
            "inspection_id": inspection_id,
            "reporting_authority": reporting_authority,
            "imo": imo,
            "ship_name": ship_name,
            "flag_state": flag_state,
            "ship_type": ship_type,
            "gross_tonnage": gross_tonnage,
            "keel_laid_date": _clean_date(keel_laid_date),
            "inspection_date": _clean_date(inspection_date),
            "inspection_end_date": _clean_date(inspection_end_date),
            "inspection_type": inspection_type,
            "inspection_port": inspection_port,
            "port_country": port_country,
            "detained": detained,
            "deficiency_count": len(deficiencies),
            "ism_deficiency": ism_deficiency,
            "ro_at_inspection": ro_at_inspection,
            "pi_provider_at_inspection": pi_provider_at_inspection,
            "pi_is_ig_member": None,
            "ism_company_imo": ism_company_imo,
            "ism_company_name": ism_company_name,
            "deficiencies": deficiencies,
            "certificates": certificates,
            "raw_data": raw_data,
        }

    except Exception:
        logger.exception("Error parsing inspection element")
        return None


def parse_paris_mou_xml(filepath: str | Path) -> Iterator[dict]:
    """Parse a Paris MoU THETIS XML file, yielding one dict per inspection.

    Handles both .xml and .xml.zip files transparently.
    Uses iterparse for memory efficiency on large files (135MB+).
    """
    filepath = Path(filepath)
    count = 0
    errors = 0

    if filepath.suffix == ".zip" or filepath.name.endswith(".xml.zip"):
        with zipfile.ZipFile(filepath, "r") as zf:
            xml_names = [n for n in zf.namelist() if n.endswith(".xml")]
            if not xml_names:
                logger.error("No XML files found in zip: %s", filepath)
                return
            for xml_name in xml_names:
                with zf.open(xml_name) as xml_file:
                    yield from _iterparse_stream(xml_file)
    else:
        with open(filepath, "rb") as f:
            for record in _iterparse_stream(f):
                count += 1
                yield record

    logger.info("Parsed %d inspections from %s (skipped %d errors)", count, filepath, errors)


def _iterparse_stream(stream) -> Iterator[dict]:
    """Parse an XML stream using iterparse, yielding inspection dicts."""
    inspection_tag = f"{{{NS}}}Inspection"

    context = etree.iterparse(stream, events=("end",), tag=inspection_tag)

    for _event, elem in context:
        result = _parse_inspection(elem)
        if result is not None:
            yield result

        # Free memory: clear the element and remove it from parent
        elem.clear()
        while elem.getprevious() is not None:
            parent = elem.getparent()
            if parent is not None:
                parent.remove(elem.getprevious())
            else:
                break
