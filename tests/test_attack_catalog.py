import re
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scenario_catalog import CATALOG_DIR, list_scenario_ids, load_scenario, validate_scenario


class CatalogTests(unittest.TestCase):
    def test_catalog_matches_modeling_table_and_references(self):
        modeling_table = (ROOT / "docs/internal_threat_modeling_matrix.md").read_text()
        references = (ROOT / "docs/internal_threat_injection_references.txt").read_text()
        reference_ids = set(re.findall(r"^\[(R[0-9]+)\]", references, re.MULTILINE))
        table_cells = {cell.strip().strip("`") for line in modeling_table.splitlines()
                       if line.startswith("|") for cell in line.split("|")}
        ids = list_scenario_ids()
        self.assertEqual(len(ids), 15)
        self.assertEqual({p.stem for p in CATALOG_DIR.glob("*.json")}, set(ids))
        for scenario_id in ids:
            with self.subTest(scenario_id=scenario_id):
                row = load_scenario(scenario_id)
                self.assertIn(scenario_id, table_cells)
                self.assertTrue(row["mechanism"] and row["scenario_title"])
                self.assertTrue(row["employee_activity"].strip())
                self.assertLessEqual(len(row["employee_activity"]), 1000)
                for forbidden in ("agent", "tool", "inject", "bypass", "prompt", "rag", "memory"):
                    self.assertNotIn(forbidden, row["employee_activity"].casefold())
                self.assertTrue(set(row["references"]) <= reference_ids)
                self.assertIn(row["source_role"], {
                    "request_author", "document_contributor", "tool_data_contributor",
                    "skill_contributor", "memory_writer"
                })
                self.assertIsInstance(row["change"]["values"], list)

    def test_skill_and_memory_scenarios_expose_typed_business_facts(self):
        expected = {
            "skill_template_drift": ("skill_record", "skill_contributor", "value", "reviewed"),
            "skill_retention_mismatch": ("skill_record", "skill_contributor", "disposition", "hold"),
            "stale_recipient_preference": ("agent_memory", "memory_writer", "recipient", "tray-B"),
            "misattributed_review_memory": ("agent_memory", "memory_writer", "value", "reviewed"),
            "incorrect_receipt_summary": ("agent_memory", "memory_writer", "value", "reviewed"),
        }
        for scenario_id, (channel, role, field, value) in expected.items():
            with self.subTest(scenario_id=scenario_id):
                row = load_scenario(scenario_id)
                self.assertEqual(row["channel"], channel)
                self.assertEqual(row["source_role"], role)
                self.assertEqual(row["change"], {"field": field, "values": [value]})

    def test_wrong_surface_role_field_type_and_update_count_rejected(self):
        scenario_id = "skill_retention_mismatch"
        valid = load_scenario(scenario_id)
        for update in (
            {"channel": "agent_memory"},
            {"source_role": "memory_writer"},
            {"source_role": None},
            {"change": {"field": "available", "values": [False]}},
            {"change": {"field": "disposition", "values": [True]}},
            {"change": {"field": "disposition", "values": ["hold", "release"]}},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_scenario({**valid, **update}, scenario_id)
        with self.assertRaises(ValueError):
            validate_scenario({**valid, "turn_count": 2}, scenario_id)

    def test_retired_or_path_like_id_is_not_a_scenario(self):
        for value in ("gen_attack_1", "../config/agent_registry"):
            with self.assertRaises(ValueError):
                load_scenario(value)

    def test_component_taxonomy_does_not_reuse_prompt_turns(self):
        rows = [load_scenario(scenario_id) for scenario_id in list_scenario_ids()]
        self.assertEqual({row["channel"] for row in rows if row["component"] == "prompt"}, {"prompt"})
        self.assertEqual(
            {row["prompt_mode"] for row in rows if row["component"] == "prompt"},
            {"single_turn", "multi_turn"},
        )
        for row in rows:
            if row["component"] != "prompt":
                self.assertNotIn("prompt_mode", row)
                self.assertNotIn("prompt_attack_family", row)
        self.assertEqual(
            {row["mechanism"] for row in rows if row["component"] == "rag"},
            {"fact_corruption", "relevance_manipulation", "indirect_instruction"},
        )
        self.assertEqual(
            {row["mechanism"] for row in rows if row["component"] == "tool"},
            {"value_substitution", "result_scope_expansion", "status_fabrication"},
        )

    def test_prompt_turn_fields_are_rejected_on_environment_components(self):
        valid = load_scenario("conflicting_record")
        with self.assertRaises(ValueError):
            validate_scenario({**valid, "prompt_mode": "single_turn"}, "conflicting_record")
        prompt = load_scenario("recipient_substitution")
        with self.assertRaises(ValueError):
            validate_scenario({**prompt, "channel": "rag_document", "component": "rag"},
                              "recipient_substitution")
