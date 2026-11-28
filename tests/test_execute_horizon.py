import json
import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config
from harness_runner import build_parser, run_schedules
from audit_log import rebuild_agent_behavior_csv


class ExecuteHorizonTests(unittest.TestCase):
    def test_rebuilds_high_level_actions_from_raw_harness_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            planner = "planner-session"
            executor = "executor-session"
            def notification(session_id, role, event_type, seq, data):
                return {
                    "event_type": "harness_notification",
                    "role": role,
                    "session_id": session_id,
                    "payload": {
                        "event": {
                            "type": event_type,
                            "seq": seq,
                            "data": data,
                        }
                    },
                }

            records = [
                {
                    "event_type": "human_agent_handoff",
                    "planner_session_id": planner,
                    "executor_session_id": executor,
                    "execution_mode": "enterprise_agent",
                    "human_principal": "employee-1",
                    "agent_id": "enterprise-workflow-agent",
                    "agent_type": "enterprise",
                    "executor_agent_id": "enterprise-workflow-agent",
                    "executor_agent_type": "enterprise",
                },
                notification(planner, "human_planner", "step/start", 1, {"turn": 1, "step": 1}),
                notification(planner, "human_planner", "assistant/message", 2, {"turn": 1, "step": 1, "message": {"content": "Plan"}}),
                notification(executor, "tool_agent", "step/start", 3, {"turn": 1, "step": 1}),
                notification(executor, "tool_agent", "tool/call", 4, {"turn": 1, "step": 1, "name": "bash", "arguments": {"command": "pwd"}}),
                notification(executor, "tool_agent", "tool/result", 5, {"turn": 1, "step": 1, "name": "bash", "detail": "ok"}),
                notification(executor, "tool_agent", "step/end", 6, {"turn": 1, "step": 1}),
            ]
            (root / "harness_events.jsonl").write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )

            counts = rebuild_agent_behavior_csv(root)

            self.assertEqual(counts, {"personal_agent": 0, "enterprise_agent": 2})
            with (root / "enterprise_agent_behavior.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(
                [row["semantic_action"] for row in rows],
                ["agent_decision", "tool_execute"],
            )
            self.assertEqual(rows[1]["tool_name"], "bash")

    def test_horizon_preserves_schedules_and_intervenes_at_one_activity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "schedules" / "week_1"
            source.mkdir(parents=True)
            rows = [{"Time": value, "Activity": f"Task {n}"} for n, value in
                    enumerate(["08:00–09:00", "10:00", "11:00", "15:00", "21:00"])]
            text = json.dumps(rows)
            for employee in ("a", "b"):
                (root / f"{employee}.jsonc").write_text(json.dumps({"id": employee}))
                (source / f"{employee}_week_1_Monday.json").write_text(text)
                (source / f"{employee}_week_1_Tuesday.json").write_text("[]")
                (source / f"{employee}_week_1_Wednesday.json").write_text(text)
            args = build_parser(horizon=True).parse_args([
                "--profile-dir", str(root), "--schedule-dir", str(source.parent),
                "--output-dir", str(root / "out"), "--weeks", "1", "--scenario",
                "substituted_tool_value", "--employee", "b", "--activity-index", "3",
                "--agent-backend", "symbolic",
            ])
            with patch.object(config, "work_days", ("Monday", "Tuesday", "Wednesday")):
                result, manifest = run_schedules(args, horizon=True)
            self.assertEqual(manifest["events"], 20)
            self.assertEqual(manifest["agent_backend"], "symbolic")
            self.assertIsNone(manifest["agent_model"])
            for employee in ("a", "b"):
                records = [json.loads(line) for line in
                           (result / employee / "week_1" / "Monday.jsonl").read_text().splitlines()]
                self.assertEqual([r["employee"]["sim_time"] for r in records], [r["Time"] for r in rows])
                self.assertEqual([r["employee"]["activity"] for r in records], [r["Activity"] for r in rows])
                self.assertEqual([i for i, r in enumerate(records) if r["scenario"]], [3] if employee == "b" else [])
                self.assertEqual((source / f"{employee}_week_1_Monday.json").read_text(), text)
                next_records = [json.loads(line) for line in
                                (result / employee / "week_1" / "Wednesday.jsonl").read_text().splitlines()]
                chain = records + next_records
                # A genuine reviewed receipt now supplies the next same-card
                # status after the one scheduled intervention.
                statuses = [r["agent"]["tool_calls"][-1]["arguments"]["value"] for r in chain]
                expected = ["draft"] * len(chain)
                if employee == "b":
                    expected[3:] = ["reviewed"] * (len(chain) - 3)
                self.assertEqual(statuses, expected)
                self.assertEqual([r["context"]["previous_activity_trace_id"] for r in chain],
                                 [None] + [r["trace_id"] for r in chain[:-1]])
                for previous, current in zip(chain, chain[1:]):
                    if current.get("recording") == "full":
                        recalled = [m for m in current["agent"]["input"]["memory"] if "source_trace_id" in m]
                        self.assertEqual([m["source_trace_id"] for m in recalled], [previous["trace_id"]])
                        self.assertEqual(recalled[0]["scope"]["owner"], employee)

            daily = build_parser()
            cli = ["--week", "1", "--date", "Thursday", "--profile-dir", str(root),
                   "--schedule-dir", str(source.parent), "--output-dir", str(root / "out"),
                   "--previous-run", str(result), "--agent-backend", "symbolic"]
            (source / "b_week_1_Thursday.json").write_text(text)
            continued, manifest2 = run_schedules(daily.parse_args(cli))
            self.assertEqual(manifest2["previous_run_id"], manifest["run_id"])
            old = json.loads((result / ".state/b/memory.json").read_text())["records"]
            saved = json.loads((continued / ".state/b/memory.json").read_text())["records"]
            self.assertEqual(saved[:len(old)], old)
            self.assertEqual(len(saved), len(old) + len(rows))
            first = json.loads((continued / "b/week_1/Thursday.jsonl").read_text().splitlines()[0])
            self.assertEqual(first["context"]["previous_activity_trace_id"], old[-1]["source_trace_id"])
            recalled = dict(old[-1])
            recalled.pop("write_origin")
            self.assertEqual(first["agent"]["input"]["memory"][-1], recalled)
            self.assertEqual((continued / ".state/a/memory.json").read_text(), (result / ".state/a/memory.json").read_text())
            args = daily.parse_args(cli + ["--date", "Wednesday"])
            with self.assertRaisesRegex(ValueError, "before the selected calendar"):
                run_schedules(args)

    def test_write_time_summary_survives_separate_daily_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schedules = root / "schedules" / "week_1"
            schedules.mkdir(parents=True)
            (root / "a.jsonc").write_text(json.dumps({"id": "a"}))
            parser = build_parser()
            common = ["--week", "1", "--profile-dir", str(root), "--schedule-dir", str(schedules.parent),
                      "--output-dir", str(root / "out"), "--agent-backend", "symbolic"]
            runs = []
            for day in ("Monday", "Tuesday"):
                path = schedules / f"a_week_1_{day}.json"
                path.write_text(json.dumps([{"Time": "10:00", "Activity": "Prepare the handover"}]))
                placement = (["--scenario", "incorrect_receipt_summary"] if day == "Monday"
                             else ["--previous-run", str(runs[0])])
                dest, _ = run_schedules(parser.parse_args(common + ["--date", day] + placement))
                runs.append(dest)

            first = json.loads((runs[0] / "a/week_1/Monday.jsonl").read_text())
            second = json.loads((runs[1] / "a/week_1/Tuesday.jsonl").read_text())
            receipt = first["agent"]["tool_results"][-1]["data"]
            self.assertEqual(receipt["receipt"]["entries"][0]["record_value"], "draft")
            self.assertIsNone(second["scenario"])
            self.assertEqual(second["context"]["previous_activity_trace_id"], first["trace_id"])
            recalled = second["agent"]["input"]["memory"][-1]
            self.assertEqual(recalled["source_trace_id"], first["trace_id"])
            self.assertEqual(recalled["summary_facts"], {"value": "reviewed"})
            self.assertNotIn("write_origin", recalled)
            self.assertEqual(second["agent"]["input"]["filing_history"]["records"][-1]["receipt"], receipt)
            self.assertEqual(second["agent"]["tool_results"][-1]["data"]["receipt"]["entries"][0]["record_value"],
                             "reviewed")


if __name__ == "__main__":
    unittest.main()
