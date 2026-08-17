from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from storm_v2.data_contract import CANONICAL_HIERARCHY, MappingStatus, MetricDomain
from storm_v2.normalization import normalize_sku
from storm_v2.workbook_profiler import EXPECTED_SHEETS, OVERVIEW_SECTIONS, profile_workbook


WORKBOOK = ROOT / "STORM V2 RAW DATA.xlsx"
OOS_LABELS = ("Amazon", "DTC", "Costco")
OTHER_REPORTS = (
    "data_contract.md",
    "source_mapping_matrix.md",
    "data_quality_report.md",
    "phase1_recommendation.md",
)


@unittest.skipUnless(WORKBOOK.exists(), "requires approved local production workbook")
class Phase1ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = profile_workbook(WORKBOOK, ROOT)
        cls.sources = json.loads((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
        cls.mappings = json.loads((ROOT / "config" / "mappings.yaml").read_text(encoding="utf-8"))

    def test_six_sheet_contract(self) -> None:
        self.assertEqual(tuple(self.profile["sheet_names"]), EXPECTED_SHEETS)
        self.assertEqual(len(self.profile["sheet_profiles"]), 6)
        self.assertTrue(all(item["required_headers_present"] for item in self.profile["sheet_profiles"]))

    def test_overview_semantic_sections(self) -> None:
        self.assertEqual(set(self.profile["overview_sections"]), set(OVERVIEW_SECTIONS))
        self.assertTrue(all(self.profile["overview_sections"].values()))

    def test_canonical_hierarchy_is_fixed(self) -> None:
        self.assertEqual(CANONICAL_HIERARCHY, ("Platform", "Channel/Subchannel", "Brand", "Power Source", "SKU"))
        self.assertEqual(self.profile["canonical_hierarchy"], list(CANONICAL_HIERARCHY))

    def test_v1_channels_are_not_canonical_values(self) -> None:
        forbidden = {"3P", "WFS", "1P", "THD Online"}
        configured = {mapping["channel_subchannel"] for mapping in self.mappings["channels"].values()}
        observed = {record.channel_subchannel for record in self.profile["canonical_candidates"]}
        self.assertTrue(forbidden.isdisjoint(configured))
        self.assertTrue(forbidden.isdisjoint(observed))

    def test_dfc_consumer_domain_is_strictly_isolated(self) -> None:
        self.assertTrue(self.profile["dfc_isolated"])
        for record in self.profile["canonical_candidates"]:
            if record.source_sheet == "THD- robot Sell out":
                self.assertIs(record.metric_domain, MetricDomain.THD_DFC_SELLOUT)
            if record.metric_domain is MetricDomain.THD_DFC_SELLOUT:
                self.assertEqual(record.source_sheet, "THD- robot Sell out")
                self.assertEqual(record.channel_subchannel, "DFC")

    def test_unknown_and_unmapped_are_explicit(self) -> None:
        rows = [record for record in self.profile["canonical_candidates"] if record.sku == "KB2618STR"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(record.mapping_status is MappingStatus.UNMAPPED for record in rows))
        self.assertTrue(all(record.brand is None and record.power_source is None for record in rows))

    def test_all_candidates_have_traceability(self) -> None:
        self.assertTrue(self.profile["traceability_complete"])
        for record in self.profile["canonical_candidates"]:
            self.assertTrue(record.source_file)
            self.assertEqual(record.source_sha256, self.profile["hash_before"])
            self.assertTrue(record.source_sheet and record.source_section)
            self.assertTrue(record.source_header and record.source_reference)
            self.assertIn("sku", record.raw_dimensions)

    def test_out_of_scope_is_inventory_only(self) -> None:
        inventory = (ROOT / "reports" / "phase1" / "workbook_inventory.md").read_text(encoding="utf-8")
        for label in OOS_LABELS:
            self.assertIn(label, inventory)
        self.assertIn("OUT_OF_SCOPE_FOR_STORM_V2", inventory)
        for path in (ROOT / "config" / "sources.yaml", ROOT / "config" / "mappings.yaml"):
            content = path.read_text(encoding="utf-8")
            for label in OOS_LABELS:
                self.assertNotIn(label, content)
        for name in OTHER_REPORTS:
            content = (ROOT / "reports" / "phase1" / name).read_text(encoding="utf-8")
            for label in OOS_LABELS:
                self.assertNotIn(label, content)
        for issue in self.profile["quality_issues"]:
            for label in OOS_LABELS:
                self.assertNotIn(label, issue.summary)
        for record in self.profile["canonical_candidates"]:
            self.assertNotIn(record.platform, OOS_LABELS)

    def test_inventory_has_required_out_of_scope_counts(self) -> None:
        counts = {(row["business"], row["sheet"]): row["record_count"] for row in self.profile["inventory_only"]}
        self.assertEqual(counts[("Amazon", "2026 acutal cost")], 24)
        self.assertEqual(counts[("DTC", "2026 acutal cost")], 8)
        self.assertEqual(counts[("Costco", "2026 acutal cost")], 8)
        self.assertEqual(counts[("Amazon", "KPI Rawdata")], 1695)
        self.assertEqual(counts[("DTC", "KPI Rawdata")], 211)

    def test_kpi_is_controllably_replaceable_reference(self) -> None:
        kpi = self.profile["kpi_status"]
        self.assertEqual(kpi["status"], "REFERENCE_BASELINE")
        self.assertEqual(kpi["input_role"], "NOT_WEEKLY_ACTUAL_INPUT")
        self.assertFalse(kpi["weekly_actual_input"])
        self.assertFalse(kpi["phase1_refresh"])
        self.assertFalse(kpi["phase1_recalculate"])
        self.assertTrue(kpi["controlled_update_allowed"])
        self.assertEqual(kpi["controlled_update_requirements"], ["version", "sha256", "approval", "replacement_record"])

    def test_required_warnings_are_non_blocking(self) -> None:
        by_code = {issue.code: issue for issue in self.profile["quality_issues"]}
        required = {
            "ACTUAL_ORDER_UNMAPPED_SKU", "SKU_NORMALIZED_DUPLICATE_EQUIVALENT",
            "ACTUAL_ORDER_MIXED_DATE_TYPES", "OVERVIEW_CACHED_ERROR_VALUES",
            "THD_DFC_POSITIVE_UNITS_ZERO_GMV",
        }
        self.assertTrue(required.issubset(by_code))
        self.assertTrue(all(not by_code[code].blocking for code in required))
        self.assertIn("KB2618STR", by_code["ACTUAL_ORDER_UNMAPPED_SKU"].summary)
        self.assertIn("SK-L-WIRE", by_code["SKU_NORMALIZED_DUPLICATE_EQUIVALENT"].summary)

    def test_sku_normalization_preserves_hyphens(self) -> None:
        self.assertEqual(normalize_sku("\nSK-L-WIRE  "), "SK-L-WIRE")

    def test_workbook_hash_is_unchanged(self) -> None:
        self.assertRegex(self.profile["hash_before"], r"^[0-9A-F]{64}$")
        self.assertEqual(self.profile["hash_after"], self.profile["hash_before"])
        self.assertTrue(self.profile["hash_unchanged"])

    def test_no_blocking_gate(self) -> None:
        self.assertEqual(self.profile["blocking_issue_count"], 0)
        self.assertTrue(self.profile["ready_for_phase2"])


if __name__ == "__main__":
    unittest.main()
