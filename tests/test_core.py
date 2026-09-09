import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import edgar
import main
import server


FORM_D_XML = b"""<?xml version='1.0'?>
<edgarSubmission>
  <submissionType>D</submissionType>
  <primaryIssuer>
    <cik>0002100000</cik><entityName>Example Robotics, Inc.</entityName>
    <issuerAddress><street1>1 Market St</street1><street2>Suite 5</street2><city>SAN FRANCISCO</city><stateOrCountry>CA</stateOrCountry><stateOrCountryDescription>CALIFORNIA</stateOrCountryDescription><zipCode>94105</zipCode></issuerAddress>
    <issuerPhoneNumber>(415) 555-0137</issuerPhoneNumber><jurisdictionOfInc>DELAWARE</jurisdictionOfInc><entityType>Corporation</entityType>
    <yearOfInc><withinFiveYears>true</withinFiveYears><value>2025</value></yearOfInc>
  </primaryIssuer>
  <relatedPersonsList>
    <relatedPersonInfo><relatedPersonName><firstName>Jordan</firstName><lastName>Lee</lastName></relatedPersonName><relatedPersonRelationshipList><relationship>Executive Officer</relationship><relationship>Director</relationship></relatedPersonRelationshipList></relatedPersonInfo>
    <relatedPersonInfo><relatedPersonName><firstName>Sam</firstName><middleName>A</middleName><lastName>Patel</lastName></relatedPersonName><relatedPersonRelationshipList><relationship>Director</relationship></relatedPersonRelationshipList></relatedPersonInfo>
  </relatedPersonsList>
  <offeringData>
    <industryGroup><industryGroupType>Other Technology</industryGroupType></industryGroup>
    <issuerSize><revenueRange>$1 - $5M</revenueRange></issuerSize>
    <federalExemptionsExclusions><item>06b</item><item>3C</item></federalExemptionsExclusions>
    <typeOfFiling><newOrAmendment><isAmendment>false</isAmendment></newOrAmendment><dateOfFirstSale><value>2026-09-01</value></dateOfFirstSale></typeOfFiling>
    <durationOfOffering><moreThanOneYear>false</moreThanOneYear></durationOfOffering>
    <typesOfSecuritiesOffered><isEquityType>true</isEquityType><isDebtType>true</isDebtType></typesOfSecuritiesOffered>
    <minimumInvestmentAccepted>25000</minimumInvestmentAccepted>
    <offeringSalesAmounts><totalOfferingAmount>8000000</totalOfferingAmount><totalAmountSold>5200000</totalAmountSold><totalRemaining>2800000</totalRemaining></offeringSalesAmounts>
    <investors><hasNonAccreditedInvestors>false</hasNonAccreditedInvestors><totalNumberAlreadyInvested>12</totalNumberAlreadyInvested></investors>
    <salesCommissionsFindersFees><salesCommissions><dollarAmount>10000</dollarAmount></salesCommissions><findersFees><dollarAmount>2000</dollarAmount></findersFees></salesCommissionsFindersFees>
    <signatureBlock><signature><signatureName>/s/ Jordan Lee</signatureName><nameOfSigner>Jordan Lee</nameOfSigner><signatureTitle>Chief Executive Officer</signatureTitle></signature></signatureBlock>
  </offeringData>
</edgarSubmission>"""

FORM_4_XML = b"""<?xml version='1.0'?>
<ownershipDocument>
  <reportingOwner><reportingOwnerId><rptOwnerName>TEST OWNER</rptOwnerName></reportingOwnerId><reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>0</isOfficer><isTenPercentOwner>0</isTenPercentOwner></reportingOwnerRelationship></reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction><securityTitle><value>Common Stock</value></securityTitle><transactionDate><value>2026-09-01</value></transactionDate><transactionCoding><transactionCode>G</transactionCode></transactionCoding><transactionAmounts><transactionShares><value>100</value></transactionShares><transactionPricePerShare><value>0</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts></nonDerivativeTransaction>
    <nonDerivativeTransaction><securityTitle><value>Common Stock</value></securityTitle><transactionDate><value>2026-09-02</value></transactionDate><transactionCoding><transactionCode>P</transactionCode></transactionCoding><transactionAmounts><transactionShares><value>10</value></transactionShares><transactionPricePerShare><value>25</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts></nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


class FormDTests(unittest.TestCase):
    @patch.object(edgar, "_get", return_value=FORM_D_XML)
    def test_scoped_form_d_parser_and_all_related_people(self, _get):
        row = edgar._parse_formd(2100000, "0002100000-26-000001")
        self.assertEqual(row["company"], "Example Robotics, Inc.")
        self.assertEqual(row["state_code"], "CA")
        self.assertEqual(row["year_of_incorporation"], 2025)
        self.assertEqual(row["date_of_first_sale"], "2026-09-01")
        self.assertEqual(row["securities_offered"], ["Equity", "Debt"])
        self.assertEqual(row["federal_exemptions"], ["06b", "3C"])
        self.assertEqual(row["total_amount_sold_usd"], 5_200_000)
        self.assertEqual(len(row["executives"]), 2)
        self.assertEqual(row["executives"][0]["title"], "Chief Executive Officer")
        self.assertEqual(row["executives"][1]["name"], "Sam A Patel")

    def _hits(self, count=30):
        return [
            {
                "company": f"Operating Company {index}", "cik": 2_100_000 + index,
                "filed": "2026-09-08", "accession": f"00021000{index:02d}-26-000001",
                "filing_index": f"https://sec.example/{index}",
            }
            for index in range(count)
        ]

    @patch.object(edgar, "_parse_formd")
    @patch.object(edgar, "_ftsearch")
    def test_limit_is_exact_not_chunk_sized(self, search, parse):
        search.return_value = (self._hits(), 30)
        parse.return_value = {
            "industry": "Other Technology", "is_pooled_fund": False,
            "total_amount_sold_usd": 2_000_000, "state_code": "CA", "state": "CALIFORNIA",
            "phone": "415-555-0100", "city": "SAN FRANCISCO",
            "executives": [{"name": "A Person", "relationship": "Officer", "title": None}],
        }
        result = edgar.funding_leads(limit=10, scan_cap=30)
        self.assertEqual(result["returned"], 10)
        self.assertEqual(result["scanned"], 10)
        self.assertEqual(len(result["leads"]), 10)

    @patch.object(edgar, "_parse_formd")
    @patch.object(edgar, "_ftsearch")
    def test_post_enrichment_qualification_filters(self, search, parse):
        search.return_value = (self._hits(2), 2)
        parse.side_effect = [
            {"company": "CA Co", "industry": "Other Technology", "is_pooled_fund": False,
             "total_amount_sold_usd": 2_000_000, "state_code": "CA", "state": "CALIFORNIA",
             "phone": "415-555-0100", "city": "SF", "executives": [{"name": "A", "relationship": "Officer", "title": None}]},
            {"company": "NY Co", "industry": "Other Technology", "is_pooled_fund": False,
             "total_amount_sold_usd": 500_000, "state_code": "NY", "state": "NEW YORK",
             "phone": None, "city": "NYC", "executives": []},
        ]
        result = edgar.funding_leads(
            limit=10, scan_cap=10, states=["CA"], min_amount_raised_usd=1_000_000,
            only_with_phone=True, only_with_executives=True,
        )
        self.assertEqual(result["returned"], 1)
        self.assertEqual(result["leads"][0]["company"], "CA Co")
        self.assertEqual(result["leads"][0]["amount_raised_usd"], 2_000_000)
        self.assertEqual(result["leads"][0]["primary_contact_name"], "A")


class FactAndInsiderTests(unittest.TestCase):
    def test_latest_fact_preserves_selected_unit(self):
        facts = {"facts": {"us-gaap": {"Revenues": {"units": {
            "USD": [{"val": 100, "start": "2024-01-01", "end": "2024-12-31", "filed": "2025-02-01", "form": "10-K"}],
            "EUR": [{"val": 120, "start": "2025-01-01", "end": "2025-12-31", "filed": "2026-02-01", "form": "10-K"}],
        }}}}}
        result = edgar._latest_fact(facts, ["Revenues"])
        self.assertEqual(result["value"], 120)
        self.assertEqual(result["unit"], "EUR")
        self.assertEqual(result["annual_unit"], "EUR")

    @patch.object(edgar, "_get", return_value=FORM_4_XML)
    def test_non_market_acquisition_is_not_a_buy(self, _get):
        result = edgar._parse_form4("https://sec.example/form4.xml")
        gift, purchase = result["transactions"]
        self.assertFalse(gift["open_market"])
        self.assertEqual(gift["side"], "ACQUIRED")
        self.assertIn("neutral", gift["signal"])
        self.assertTrue(purchase["open_market"])
        self.assertEqual(purchase["side"], "BUY")
        self.assertIn("BULLISH", purchase["signal"])


class ActorContractTests(unittest.TestCase):
    def test_zero_funding_results_create_no_dataset_items(self):
        result = {
            "leads": [],
            "_meta": {"action": "funding_leads", "retrieved_at": "2026-09-09T00:00:00Z"},
        }
        self.assertEqual(main._dataset_items(result), [])

    @patch.object(main.edgar, "funding_leads")
    def test_string_false_is_false(self, funding):
        funding.return_value = {"record_type": "funding_leads_run", "leads": [], "returned": 0}
        main.run({"action": "funding_leads", "exclude_funds": "false"})
        self.assertFalse(funding.call_args.kwargs["exclude_funds"])

    def test_public_api_caps_result_count(self):
        self.assertEqual(server._cap_input({"limit": 999})["limit"], server.PUBLIC_LIMIT)
        self.assertEqual(server._cap_input({"limit": -2})["limit"], 1)

    def test_error_contract_is_explicitly_non_billable(self):
        result = main.run({"action": "not-a-real-action"})
        self.assertEqual(result["record_type"], "error")
        self.assertEqual(result["_billing"]["billable_items"], 0)
        self.assertEqual(result["_pushed_items"], 0)
        self.assertEqual(result["_meta"]["status"], "failed")

    @patch.object(main.edgar, "company_snapshot")
    def test_core_errors_are_normalized_to_non_billable_contract(self, snapshot):
        snapshot.return_value = {"error": "not found"}
        result = main.run({"action": "snapshot", "symbol": "NOPE"})
        self.assertEqual(result["record_type"], "error")
        self.assertEqual(result["_billing"]["billable_items"], 0)
        self.assertEqual(result["_pushed_items"], 0)
        self.assertEqual(result["_meta"]["action"], "snapshot")

    def test_all_json_contracts_parse_without_duplicate_keys(self):
        def reject_duplicates(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise AssertionError(f"duplicate JSON key: {key}")
                result[key] = value
            return result

        for path in [
            ROOT / ".actor" / "actor.json",
            ROOT / ".actor" / "input_schema.json",
            ROOT / ".actor" / "output_schema.json",
            ROOT / ".actor" / "dataset_schema.json",
            ROOT / "openapi.json",
        ]:
            json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


if __name__ == "__main__":
    unittest.main()
