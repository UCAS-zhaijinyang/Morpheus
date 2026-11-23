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
from scale_simulation import _run_member, _load_horizon, _parse_time
from agent_behavior_log import rebuild_agent_behavior_csv


class ScaleSimulationTests(unittest.TestCase):
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

    def test_horizon_clamps_events_to_configured_workday(self):
        with tempfile.TemporaryDirectory() as directory:
            schedule_dir = Path(directory)
            week_dir = schedule_dir / "week_1"
            week_dir.mkdir()
            schedule = [
                {"Time": "08:00", "Activity": "Log in"},
                {"Time": "14:00", "Activity": "Complete the task"},
                {"Time": "21:00", "Activity": "Log out"},
            ]
            path = week_dir / "employee-1_week_1_Monday.json"
            path.write_text(json.dumps(schedule), encoding="utf-8")

            events = _load_horizon(
                schedule_dir,
                "employee-1",
                1,
                ("Monday",),
                _parse_time("10:00"),
                _parse_time("19:00"),
            )

            self.assertEqual([event["time"] for event in events], [
                "10:00:00",
                "14:00:00",
                "19:00:00",
            ])

    def test_stub_horizon_writes_auditable_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schedule_dir = root / "schedules"
            week_dir = schedule_dir / "week_1"
            week_dir.mkdir(parents=True)
            (week_dir / "employee-1_week_1_Monday.json").write_text(
                json.dumps([
                    {"Time": "10:00", "Activity": "Log in and review the queue."},
                    {"Time": "11:00", "Activity": "Complete the assigned analysis task."},
                ]),
                encoding="utf-8",
            )
            profile = {
                "id": "employee-1",
                "name": "Employee One",
                "role": "Analyst",
                "description": "Analyze assigned work.",
                "personality": "Methodical.",
            }

            with patch.dict(os.environ, {"MORPHEUS_HARNESS_STUB": "1"}, clear=False):
                result = _run_member(
                    profile,
                    schedule_dir,
                    root / "output",
                    1,
                    ("Monday",),
                    _parse_time("10:00"),
                    _parse_time("19:00"),
                )

            member_dir = root / "output" / "employee-1"
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["event_count"], 2)
            self.assertTrue((member_dir / "trajectory.jsonl").exists())
            self.assertTrue((member_dir / "behavior_policy.csv").exists())
            self.assertTrue((member_dir / "final_schedule.csv").exists())
            self.assertTrue((member_dir / "logon.csv").exists())
            self.assertTrue((member_dir / "agent_audit.jsonl").exists())
            self.assertTrue((member_dir / "horizon_result.json").exists())
            trajectory = [
                json.loads(line)
                for line in (member_dir / "trajectory.jsonl").read_text().splitlines()
            ]
            self.assertEqual(trajectory[0]["execution_mode"], "enterprise_agent")
            self.assertEqual(trajectory[0]["agent_id"], "enterprise-workflow-agent")
            self.assertEqual(trajectory[0]["batch_agent_id"], "enterprise-workflow-agent")
            self.assertEqual(trajectory[0]["caller_agent_id"], "employee-agent-employee-1")
            self.assertEqual(trajectory[0]["caller_agent_type"], "employee")
            self.assertEqual(trajectory[0]["executor_agent_id"], "enterprise-workflow-agent")
            self.assertEqual(
                trajectory[0]["delegation_chain"],
                ["employee-agent-employee-1", "enterprise-workflow-agent"],
            )
            self.assertTrue((member_dir / "personal_agent_behavior.csv").exists())
            self.assertTrue((member_dir / "enterprise_agent_behavior.csv").exists())
            with (member_dir / "enterprise_agent_behavior.csv").open(newline="") as handle:
                agent_rows = list(csv.DictReader(handle))
            self.assertEqual(len(agent_rows), 0)
            self.assertFalse((member_dir / "agent_steps.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
