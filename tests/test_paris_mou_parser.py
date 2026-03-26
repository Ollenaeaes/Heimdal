"""Tests for the Paris MoU THETIS XML parser."""

import tempfile
from pathlib import Path

from shared.parsers.paris_mou import parse_paris_mou_xml

NS = "urn:getPublicInspections.xmlData.business.thetis.emsa.europa.eu"

# Test fixture: 3 inspections
# 1. With deficiencies (one has isGroundDetention=true, one is ISM area 15xxx)
# 2. Clean inspection (no deficiencies)
# 3. Inspection with CLC certificate (509) and class certificate, no deficiencies element
TEST_XML = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<InspectionResultsReceipt xmlns:urn="{NS}">
  <urn:Inspection urn:InspectionID="1001" urn:ReportingAuthority="DK"
      urn:PlaceOfInspection="DKEBJ" urn:DateOfFirstVisit="2025-05-02Z"
      urn:DateOfFinalVisit="2025-05-03Z" urn:PSCInspectionType="INITIAL_INSPECTION">
    <urn:ShipParticulars urn:IMO="9692624">
      <urn:Name urn:Value="FUGRO ZENITH" urn:EffectDate="2025-05-02Z"/>
      <urn:Flag urn:Value="BS" urn:EffectDate="2025-05-02Z"/>
      <urn:ShipType urn:Value="376" urn:EffectDate="2020-09-28Z"/>
      <urn:KeelDate urn:Value="2013-07-22Z" urn:EffectDate="2020-09-28Z"/>
      <urn:CallSign urn:Value="C6IE6" urn:EffectDate="2025-05-02Z"/>
      <urn:GrossTonnage urn:Value="4983" urn:EffectDate="2020-09-28Z"/>
    </urn:ShipParticulars>
    <urn:ISMCompany urn:IMO="5312062" urn:Name="Fugro Marine Services BV"
        urn:Address="Veurse Achterweg 10" urn:City="Leidschendam" urn:Country="NL"/>
    <urn:ClassCertificates>
      <urn:ClassCertificate urn:IssuingAuthority="128" urn:ClassStatus="DELIVERED"
          urn:DateOfStatus="2025-05-02Z" urn:IssueDate="2025-01-23Z" urn:ExpiryDate="2030-01-16Z"/>
    </urn:ClassCertificates>
    <urn:StatutoryCertificates>
      <urn:StatutoryCertificate urn:CertificateCode="511" urn:IssuingAutorityType="RO"
          urn:IssuingAuthority="128" urn:DateOfIssue="2022-08-31Z" urn:DateOfExpiry="2027-11-09Z"/>
    </urn:StatutoryCertificates>
    <urn:Deficiencies>
      <urn:Deficiency urn:DefectiveItemCode="11117" urn:NatureOfDefectCode="1011"
          urn:isGroundDetention="true" urn:isRORelated="false" urn:isAccidentalDamage="false"/>
      <urn:Deficiency urn:DefectiveItemCode="15201" urn:NatureOfDefectCode="2001"
          urn:isGroundDetention="false" urn:isRORelated="true" urn:isAccidentalDamage="false"/>
    </urn:Deficiencies>
  </urn:Inspection>

  <urn:Inspection urn:InspectionID="1002" urn:ReportingAuthority="NL"
      urn:PlaceOfInspection="NLRTM" urn:DateOfFirstVisit="2025-06-10Z"
      urn:DateOfFinalVisit="2025-06-10Z" urn:PSCInspectionType="MORE_DETAILED">
    <urn:ShipParticulars urn:IMO="9801234">
      <urn:Name urn:Value="ATLANTIC VOYAGER" urn:EffectDate="2025-06-10Z"/>
      <urn:Flag urn:Value="PA" urn:EffectDate="2025-06-10Z"/>
      <urn:ShipType urn:Value="100" urn:EffectDate="2020-01-01Z"/>
      <urn:GrossTonnage urn:Value="32000" urn:EffectDate="2020-01-01Z"/>
    </urn:ShipParticulars>
    <urn:ISMCompany urn:IMO="1234567" urn:Name="Atlantic Shipping Co"
        urn:Address="Harbor Rd" urn:City="Rotterdam" urn:Country="NL"/>
    <urn:Deficiencies/>
  </urn:Inspection>

  <urn:Inspection urn:InspectionID="1003" urn:ReportingAuthority="GB"
      urn:PlaceOfInspection="GBSOU" urn:DateOfFirstVisit="2025-07-15Z"
      urn:DateOfFinalVisit="2025-07-16Z" urn:PSCInspectionType="INITIAL_INSPECTION">
    <urn:ShipParticulars urn:IMO="9555555">
      <urn:Name urn:Value="PACIFIC STAR" urn:EffectDate="2025-07-15Z"/>
      <urn:Flag urn:Value="LR" urn:EffectDate="2025-07-15Z"/>
      <urn:ShipType urn:Value="200" urn:EffectDate="2018-03-01Z"/>
      <urn:KeelDate urn:Value="2016-11-05Z" urn:EffectDate="2018-03-01Z"/>
      <urn:GrossTonnage urn:Value="15500" urn:EffectDate="2018-03-01Z"/>
    </urn:ShipParticulars>
    <urn:ISMCompany urn:IMO="9988776" urn:Name="Pacific Maritime Ltd"
        urn:Address="Dock St" urn:City="Southampton" urn:Country="GB"/>
    <urn:ClassCertificates>
      <urn:ClassCertificate urn:IssuingAuthority="256" urn:ClassStatus="IN_CLASS"
          urn:DateOfStatus="2025-07-15Z" urn:IssueDate="2024-06-01Z" urn:ExpiryDate="2029-06-01Z"/>
    </urn:ClassCertificates>
    <urn:StatutoryCertificates>
      <urn:StatutoryCertificate urn:CertificateCode="509" urn:IssuingAutorityType="Flag"
          urn:IssuingAuthority="42" urn:DateOfIssue="2023-01-15Z" urn:DateOfExpiry="2028-01-15Z"/>
      <urn:StatutoryCertificate urn:CertificateCode="510" urn:IssuingAutorityType="RO"
          urn:IssuingAuthority="99" urn:DateOfIssue="2023-06-01Z" urn:DateOfExpiry="2028-06-01Z"/>
    </urn:StatutoryCertificates>
    <urn:Deficiencies>
      <urn:Deficiency urn:DefectiveItemCode="01101" urn:NatureOfDefectCode="3001"
          urn:isGroundDetention="false" urn:isRORelated="false" urn:isAccidentalDamage="true"/>
    </urn:Deficiencies>
  </urn:Inspection>
</InspectionResultsReceipt>
"""


def _write_fixture_and_parse(xml_content: str = TEST_XML) -> list[dict]:
    """Write XML to a temp file and parse it, returning list of records."""
    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False, encoding="utf-8") as f:
        f.write(xml_content)
        f.flush()
        return list(parse_paris_mou_xml(f.name))


class TestParserYieldCount:
    def test_yields_correct_number_of_records(self):
        records = _write_fixture_and_parse()
        assert len(records) == 3


class TestShipParticulars:
    def test_extracts_imo(self):
        records = _write_fixture_and_parse()
        assert records[0]["imo"] == 9692624

    def test_extracts_ship_name(self):
        records = _write_fixture_and_parse()
        assert records[0]["ship_name"] == "FUGRO ZENITH"

    def test_extracts_flag_state(self):
        records = _write_fixture_and_parse()
        assert records[0]["flag_state"] == "BS"

    def test_extracts_ship_type(self):
        records = _write_fixture_and_parse()
        assert records[0]["ship_type"] == "376"

    def test_extracts_gross_tonnage(self):
        records = _write_fixture_and_parse()
        assert records[0]["gross_tonnage"] == 4983

    def test_extracts_keel_laid_date(self):
        records = _write_fixture_and_parse()
        assert records[0]["keel_laid_date"] == "2013-07-22"


class TestInspectionFields:
    def test_inspection_id(self):
        records = _write_fixture_and_parse()
        assert records[0]["inspection_id"] == "1001"

    def test_reporting_authority(self):
        records = _write_fixture_and_parse()
        assert records[0]["reporting_authority"] == "DK"

    def test_inspection_date(self):
        records = _write_fixture_and_parse()
        assert records[0]["inspection_date"] == "2025-05-02"

    def test_inspection_end_date(self):
        records = _write_fixture_and_parse()
        assert records[0]["inspection_end_date"] == "2025-05-03"

    def test_inspection_type(self):
        records = _write_fixture_and_parse()
        assert records[0]["inspection_type"] == "INITIAL_INSPECTION"

    def test_inspection_port(self):
        records = _write_fixture_and_parse()
        assert records[0]["inspection_port"] == "DKEBJ"

    def test_port_country_derived_from_inspection_port(self):
        records = _write_fixture_and_parse()
        assert records[0]["port_country"] == "DK"
        assert records[1]["port_country"] == "NL"
        assert records[2]["port_country"] == "GB"


class TestDeficiencies:
    def test_deficiency_count(self):
        records = _write_fixture_and_parse()
        assert records[0]["deficiency_count"] == 2

    def test_deficiency_codes_extracted(self):
        records = _write_fixture_and_parse()
        codes = [d["deficiency_code"] for d in records[0]["deficiencies"]]
        assert codes == ["11117", "15201"]

    def test_nature_of_defect_extracted(self):
        records = _write_fixture_and_parse()
        natures = [d["nature_of_defect"] for d in records[0]["deficiencies"]]
        assert natures == ["1011", "2001"]

    def test_detained_true_when_ground_detention(self):
        records = _write_fixture_and_parse()
        # Inspection 1001 has isGroundDetention=true on first deficiency
        assert records[0]["detained"] is True

    def test_detained_false_when_no_ground_detention(self):
        records = _write_fixture_and_parse()
        # Inspection 1003 has deficiencies but none with isGroundDetention=true
        assert records[2]["detained"] is False

    def test_no_deficiencies_empty_element(self):
        records = _write_fixture_and_parse()
        # Inspection 1002 has empty <urn:Deficiencies/>
        assert records[1]["deficiency_count"] == 0
        assert records[1]["deficiencies"] == []
        assert records[1]["detained"] is False

    def test_is_ro_related_flag(self):
        records = _write_fixture_and_parse()
        assert records[0]["deficiencies"][1]["is_ro_related"] is True
        assert records[0]["deficiencies"][0]["is_ro_related"] is False

    def test_is_accidental_damage_flag(self):
        records = _write_fixture_and_parse()
        assert records[2]["deficiencies"][0]["is_accidental_damage"] is True


class TestISMDeficiency:
    def test_ism_deficiency_from_15xxx_code(self):
        records = _write_fixture_and_parse()
        # Inspection 1001 has deficiency code 15201
        assert records[0]["ism_deficiency"] is True

    def test_ism_deficiency_from_011_code(self):
        records = _write_fixture_and_parse()
        # Inspection 1003 has deficiency code 01101
        assert records[2]["ism_deficiency"] is True

    def test_no_ism_deficiency(self):
        records = _write_fixture_and_parse()
        # Inspection 1002 has no deficiencies
        assert records[1]["ism_deficiency"] is False


class TestCertificates:
    def test_ro_from_class_certificate(self):
        records = _write_fixture_and_parse()
        assert records[0]["ro_at_inspection"] == "128"
        assert records[2]["ro_at_inspection"] == "256"

    def test_no_ro_when_no_class_certificates(self):
        records = _write_fixture_and_parse()
        # Inspection 1002 has no ClassCertificates element
        assert records[1]["ro_at_inspection"] is None

    def test_pi_provider_from_clc_509(self):
        records = _write_fixture_and_parse()
        # Inspection 1003 has CertificateCode 509 with IssuingAuthority 42
        assert records[2]["pi_provider_at_inspection"] == "42"

    def test_no_pi_provider_when_no_clc_cert(self):
        records = _write_fixture_and_parse()
        # Inspection 1001 has cert code 511, not 509/510
        assert records[0]["pi_provider_at_inspection"] is None

    def test_pi_is_ig_member_always_none(self):
        records = _write_fixture_and_parse()
        for r in records:
            assert r["pi_is_ig_member"] is None

    def test_certificates_list_combined(self):
        records = _write_fixture_and_parse()
        # Inspection 1003: 1 class + 2 statutory = 3 certs
        certs = records[2]["certificates"]
        assert len(certs) == 3
        sources = [c["certificate_source"] for c in certs]
        assert sources.count("class") == 1
        assert sources.count("statutory") == 2

    def test_statutory_cert_has_issuing_authority_type(self):
        records = _write_fixture_and_parse()
        # Inspection 1003, first statutory cert (509) has IssuingAutorityType="Flag"
        stat_certs = [c for c in records[2]["certificates"] if c["certificate_source"] == "statutory"]
        assert stat_certs[0]["issuing_authority_type"] == "Flag"
        assert stat_certs[1]["issuing_authority_type"] == "RO"

    def test_class_cert_has_no_issuing_authority_type(self):
        records = _write_fixture_and_parse()
        class_certs = [c for c in records[2]["certificates"] if c["certificate_source"] == "class"]
        assert class_certs[0]["issuing_authority_type"] is None

    def test_no_certificates_when_missing(self):
        records = _write_fixture_and_parse()
        # Inspection 1002 has no certificate elements
        assert records[1]["certificates"] == []


class TestISMCompany:
    def test_ism_company_imo(self):
        records = _write_fixture_and_parse()
        assert records[0]["ism_company_imo"] == "5312062"

    def test_ism_company_name(self):
        records = _write_fixture_and_parse()
        assert records[0]["ism_company_name"] == "Fugro Marine Services BV"


class TestRawData:
    def test_raw_data_includes_inspection_attrs(self):
        records = _write_fixture_and_parse()
        assert records[0]["raw_data"]["InspectionID"] == "1001"
        assert records[0]["raw_data"]["ReportingAuthority"] == "DK"

    def test_raw_data_includes_ship_particulars(self):
        records = _write_fixture_and_parse()
        assert "ShipParticulars" in records[0]["raw_data"]
        assert records[0]["raw_data"]["ShipParticulars"]["IMO"] == "9692624"

    def test_raw_data_includes_deficiencies(self):
        records = _write_fixture_and_parse()
        assert "Deficiencies" in records[0]["raw_data"]
        assert len(records[0]["raw_data"]["Deficiencies"]) == 2
