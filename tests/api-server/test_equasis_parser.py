"""Tests for the Equasis Ship Folder PDF parser."""

import os

import pytest

from equasis_parser import parse_equasis_pdf

FIXTURE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "services", "api-server", "tests", "fixtures"
)


@pytest.fixture
def blue_pdf_bytes():
    pdf_path = os.path.join(FIXTURE_DIR, "ShipFop.pdf")
    with open(pdf_path, "rb") as f:
        return f.read()


def test_ship_particulars(blue_pdf_bytes):
    result = parse_equasis_pdf(blue_pdf_bytes)
    sp = result["ship_particulars"]
    assert sp["imo"] == 9236353
    assert sp["mmsi"] == 613414602
    assert sp["name"] == "BLUE"
    assert sp["call_sign"] == "TJMA05"
    assert sp["gross_tonnage"] == 84789
    assert sp["dwt"] == 165293
    assert sp["ship_type"] == "Crude Oil Tanker"
    assert sp["build_year"] == 2003
    assert sp["flag"] == "Cameroon"
    assert sp["status"] == "In Service/Commission"
    assert sp["last_update"] == "11/03/2026"


def test_management(blue_pdf_bytes):
    result = parse_equasis_pdf(blue_pdf_bytes)
    mgmt = result["management"]
    assert len(mgmt) == 3

    # ISM Manager UNKNOWN
    ism = mgmt[0]
    assert ism["company_imo"] == 9991001
    assert ism["role"] == "ISM Manager"
    assert ism["company_name"] == "UNKNOWN"
    assert ism["date_of_effect"] == "since 07/10/2025"

    # Ship manager / Commercial manager CRESTWAVE
    sm = mgmt[1]
    assert sm["company_imo"] == 6470941
    assert "Ship manager" in sm["role"]
    assert "Commercial manager" in sm["role"]
    assert sm["company_name"] == "CRESTWAVE MARITIME LTD"
    assert sm["date_of_effect"] == "since 07/02/2024"

    # Registered owner CRESTWAVE
    ro = mgmt[2]
    assert ro["company_imo"] == 6470941
    assert ro["role"] == "Registered owner"
    assert ro["company_name"] == "CRESTWAVE MARITIME LTD"
    assert ro["date_of_effect"] == "since 07/02/2024"


def test_classification_status(blue_pdf_bytes):
    result = parse_equasis_pdf(blue_pdf_bytes)
    cs = result["classification_status"]
    assert len(cs) == 2

    # Russian Maritime Register of Shipping, Delivered
    assert "Russian Maritime Register" in cs[0]["society"]
    assert cs[0]["status"] == "Delivered"
    assert cs[0]["date_change"] == "during 08/2025"

    # Registro Italiano Navale, Withdrawn
    assert "Registro Italiano Navale" in cs[1]["society"]
    assert cs[1]["status"] == "Withdrawn"
    assert cs[1]["reason"] is not None
    assert "society" in cs[1]["reason"].lower() or "other" in cs[1]["reason"].lower()


def test_classification_surveys(blue_pdf_bytes):
    result = parse_equasis_pdf(blue_pdf_bytes)
    surveys = result["classification_surveys"]
    assert len(surveys) == 2

    assert "Registro Italiano Navale" in surveys[0]["society"]
    assert surveys[0]["date_survey"] == "22/12/2023"
    assert surveys[0]["date_next_survey"] == "23/01/2028"

    assert "Russian Maritime Register" in surveys[1]["society"]
    assert surveys[1]["date_survey"] == "22/12/2023"
    assert surveys[1]["date_next_survey"] == "23/01/2028"


def test_safety_certificates(blue_pdf_bytes):
    result = parse_equasis_pdf(blue_pdf_bytes)
    certs = result["safety_certificates"]
    assert len(certs) == 2

    assert "Lloyd" in certs[0]["society"]
    assert certs[0]["date_survey"] == "18/11/2021"
    assert certs[0]["date_expiry"] == "29/08/2026"
    assert certs[0]["type"] == "Convention"

    assert "Lloyd" in certs[1]["society"]
    assert certs[1]["date_survey"] == "30/08/2021"
    assert certs[1]["date_expiry"] == "29/08/2026"
    assert certs[1]["type"] == "Convention"


def test_psc_inspections(blue_pdf_bytes):
    result = parse_equasis_pdf(blue_pdf_bytes)
    psc = result["psc_inspections"]

    # Should have at least 30 entries
    assert len(psc) >= 30

    # Find Istanbul detention
    istanbul = [p for p in psc if p.get("port") and "Istanbul" in p["port"]]
    assert len(istanbul) >= 1
    ist = istanbul[0]
    assert ist["date"] == "28/12/2023"
    assert ist["detention"] is True
    assert ist["deficiencies"] == 12

    # Find Piraeus
    piraeus = [p for p in psc if p.get("port") and "Piraeus" in p["port"]]
    assert len(piraeus) >= 1
    pir = piraeus[0]
    assert pir["date"] == "10/11/2023"
    assert pir["detention"] is False
    assert pir["deficiencies"] == 2


def test_human_element_deficiencies(blue_pdf_bytes):
    result = parse_equasis_pdf(blue_pdf_bytes)
    hed = result["human_element_deficiencies"]
    assert len(hed) == 1

    entry = hed[0]
    assert entry["psc_org"] == "Paris MoU"
    assert entry["authority"] == "Canada"
    assert entry["port"] == "Pt Tupper"
    assert entry["date"] == "26/01/2009"
    assert entry["count"] == 1


def test_name_history(blue_pdf_bytes):
    result = parse_equasis_pdf(blue_pdf_bytes)
    names = result["name_history"]
    assert len(names) == 7

    name_list = [n["name"] for n in names]
    assert "BLUE" in name_list
    assert "Julia A" in name_list
    assert "Azul" in name_list
    assert "Icaria" in name_list
    assert "Iskmati Spirit" in name_list
    assert "Arlene" in name_list
    assert "Aegean Eagle" in name_list


def test_flag_history(blue_pdf_bytes):
    result = parse_equasis_pdf(blue_pdf_bytes)
    flags = result["flag_history"]
    assert len(flags) >= 14

    flag_names = [f["flag"] for f in flags]
    assert any("Cameroon" in f for f in flag_names)
    assert any("Liberia" in f for f in flag_names)
    assert any("Greece" in f for f in flag_names)


def test_company_history(blue_pdf_bytes):
    result = parse_equasis_pdf(blue_pdf_bytes)
    companies = result["company_history"]
    assert len(companies) >= 15

    company_names = [c["company"] for c in companies]
    assert any("UNKNOWN" in c for c in company_names)
    assert any("CRESTWAVE" in c for c in company_names)
    assert any("ARCADIA" in c for c in company_names)


def test_edition_date(blue_pdf_bytes):
    result = parse_equasis_pdf(blue_pdf_bytes)
    assert result["edition_date"] == "13/03/2026"


def test_non_equasis_pdf_raises():
    """Non-Equasis PDF should raise ValueError."""
    # Create a minimal valid PDF that is NOT an Equasis document
    # Use a simple PDF with just "Hello World"
    import pdfplumber
    import io

    # Create a minimal PDF manually
    pdf_content = b"""%PDF-1.0
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Hello World) Tj ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000360 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
441
%%EOF"""

    with pytest.raises(ValueError):
        parse_equasis_pdf(pdf_content)


def test_corrupted_bytes_raises():
    """Corrupted/empty bytes should raise ValueError."""
    with pytest.raises(ValueError):
        parse_equasis_pdf(b"")

    with pytest.raises(ValueError):
        parse_equasis_pdf(b"not a pdf at all")
