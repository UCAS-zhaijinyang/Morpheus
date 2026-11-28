import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import config
from simulated_decision import DeepSeekHarnessPolicy
from harness_runner import build_parser, run_schedules


class ModelPolicyTests(unittest.TestCase):
    @patch("deepseek_runtime.run_text_prompt")
    def test_text_only_choices(self, generate):
        policy = DeepSeekHarnessPolicy("custom-model")
        visible = {"conversation": [{"role": "employee", "text": "Review my report."}]}
        for name, expected in (("issued_order", "retain_baseline"), ("observed_updates", "adopt_fixture")):
            generate.return_value = json.dumps({"use": name})
            self.assertEqual(policy(visible)["decision"], expected)
            _, user = generate.call_args.args
            self.assertEqual(json.loads(user), visible)
            self.assertEqual(generate.call_args.kwargs["model"], "custom-model")
        for invalid in ("{}", '["issued_order"]', '{"use":[]}', '{"use":"other"}'):
            with self.subTest(invalid=invalid):
                generate.return_value = invalid
                with self.assertRaisesRegex(ValueError, "supported work-card choice"):
                    policy(visible)

    def test_default_run_uses_harness_and_attributes_fixture_traces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schedules = root / "schedules"
            (schedules / "week_1").mkdir(parents=True)
            (root / "a.jsonc").write_text(json.dumps({"id": "a"}))
            rows = [{"Time": "10:00", "Activity": "Review the handover"}]
            (schedules / "week_1/a_week_1_Monday.json").write_text(json.dumps(rows))
            from enterprise_harness import DEFAULT_SKILLS
            catalog = root / "procedures.json"
            procedures = json.loads(DEFAULT_SKILLS.read_text())
            for skill in procedures:
                skill["revision"] = 7
            catalog.write_text(json.dumps(procedures))
            args = build_parser().parse_args([
                "--week", "1", "--date", "Monday", "--profile-dir", str(root),
                "--schedule-dir", str(schedules), "--output-dir", str(root / "out"),
                "--scenario", "cumulative_scope_change", "--skill-catalog", str(catalog),
            ])
            with patch.dict(os.environ, {"MORPHEUS_HARNESS_STUB": "0", "MORPHEUS_DSH_MODEL": "test-model",
                                         "MORPHEUS_DSH_REASONING_EFFORT": "low"}), \
                    patch.object(config, "harness_stub_mode", False), \
                    patch("deepseek_runtime.run_text_prompt", side_effect=[
                        "Acknowledged one card.", "Acknowledged two cards.",
                        '{"reads":["load_workflow_skill","recall_agent_memory"]}',
                        '{"use":"issued_order"}', "Filed one card in tray-A.",
                    ]) as generate:
                run_dir, summary = run_schedules(args)
            record = json.loads((run_dir / "a/week_1/Monday.jsonl").read_text())
            self.assertEqual(summary["agent_backend"], "deepseek_harness")
            self.assertEqual(summary["agent_model"], "test-model")
            self.assertEqual(summary["agent_reasoning_effort"], "low")
            self.assertEqual(summary["skill_catalog"], str(catalog.resolve()))
            self.assertEqual(record["agent"]["input"]["skill"]["revision"], 7)
            self.assertEqual(summary["agent_backend"], record["context"]["agent_backend"])
            self.assertEqual(summary["agent_model"], record["context"]["agent_model"])
            self.assertEqual(record["agent"]["decision"], "retain_baseline")
            self.assertEqual(record["agent"]["output"]["text"], "Filed one card in tray-A.")
            ack1, ack2, plan, choice, final = generate.call_args_list
            conversation = record["agent"]["input"]["conversation"]
            self.assertEqual(json.loads(ack1.args[1])["conversation"], conversation[:1])
            self.assertEqual(json.loads(ack2.args[1])["conversation"], conversation[:3])
            directory = json.loads(plan.args[1])
            self.assertEqual(directory["conversation"], conversation)
            self.assertIn("recall_agent_memory", directory["tool_directory"])
            self.assertIsNone(record["agent"]["input"]["lookup_result"])
            self.assertEqual(record["agent"]["input"]["documents"], [])
            self.assertEqual([c["tool_name"] for c in record["agent"]["tool_calls"]],
                             ["load_workflow_skill", "recall_agent_memory", "file_work_note"])
            self.assertEqual(json.loads(choice.args[1]), record["agent"]["input"])
            self.assertEqual(json.loads(final.args[1])["service_receipt"], record["agent"]["tool_results"][-1]["data"])
            self.assertTrue(all(call.kwargs["model"] == "test-model" for call in generate.call_args_list))
            with patch.dict(os.environ, {"MORPHEUS_HARNESS_STUB": "1"}):
                stub_dir, summary = run_schedules(args)
                self.assertEqual(summary["agent_backend"], "deepseek_harness_stub")
                self.assertIsNone(summary["agent_model"])
                stub_record = json.loads((stub_dir / "a/week_1/Monday.jsonl").read_text())
                self.assertEqual(stub_record["context"]["agent_backend"], "deepseek_harness_stub")
            with patch("deepseek_runtime.run_text_prompt", side_effect=RuntimeError("provider unavailable")):
                with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
                    run_schedules(args)
            statuses = sorted(json.loads(m.read_text())["status"] for m in (root / "out").glob("*/manifest.json"))
            self.assertEqual(statuses, ["completed", "completed", "failed"])
