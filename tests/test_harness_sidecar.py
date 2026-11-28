import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import config
from audit_log import rebuild_agent_behavior_csv
from deepseek_runtime import _semantic_steps, run_human_tool_task


class HarnessSidecarTests(unittest.TestCase):
    def test_trajectory_context_is_persisted_without_entering_stub_prompts(self):
        with tempfile.TemporaryDirectory() as directory:
            context = {
                "trace_id": "trace-fixed",
                "scenario_id": "threat-example",
                "attack_id": "attack-example",
                "attack_stage": 2,
                "human_intent": {"declared_goal": "SIDE_CAR_ONLY"},
                "agent_intent": {"objective": "SIDE_CAR_AGENT_ONLY"},
            }
            with patch.dict(os.environ, {"MORPHEUS_HARNESS_STUB": "1"}, clear=False):
                with patch.object(
                    config,
                    "agent_registry_path",
                    os.path.join(directory, "agents.json"),
                ):
                    result = run_human_tool_task(
                        "Inspect the assigned work item.",
                        output_dir=directory,
                        log_dir=directory,
                        human_principal="employee-1",
                        trajectory_context=context,
                    )

            self.assertNotIn("SIDE_CAR_ONLY", result.planner_response)
            self.assertNotIn("SIDE_CAR_AGENT_ONLY", result.planner_response)
            records = [
                json.loads(line)
                for line in (Path(directory) / "harness_events.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            handoff = next(
                record
                for record in records
                if record.get("event_type") == "human_agent_handoff"
            )
            self.assertEqual(handoff["trace_id"], "trace-fixed")
            self.assertEqual(handoff["attack_id"], "attack-example")
            self.assertEqual(handoff["planner_session_id"], result.planner_session_id)
            self.assertEqual(handoff["executor_session_id"], result.executor_session_id)
            self.assertTrue(all(step["task_id"] for step in result.semantic_steps))

    def test_rebuild_uses_canonical_steps_when_raw_notifications_are_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handoff = {
                "event_type": "human_agent_handoff",
                "execution_mode": "enterprise_agent",
                "task_id": "task-1",
                "trace_id": "trace-1",
                "planner_session_id": "planner-1",
                "executor_session_id": "executor-1",
                "human_principal": "employee-1",
                "executor_agent_id": "enterprise-workflow-agent",
                "executor_agent_type": "enterprise",
            }
            canonical = {
                "event_type": "agent_step",
                "task_id": "task-1",
                "trace_id": "trace-1",
                "event_id": "event-1",
                "session_id": "executor-1",
                "executor_agent_id": "enterprise-workflow-agent",
                "executor_agent_type": "enterprise",
                "agent_role": "tool_agent",
                "semantic_action": "tool_execute",
                "trajectory_action": "executor_agent_action",
                "tool_result_action": "tool_result",
                "actual_tool_call": True,
                "actual_tool_result": True,
                "tool_name": "repository",
                "source_event_type": "harness_step",
            }
            (root / "harness_events.jsonl").write_text(
                "\n".join(json.dumps(record) for record in (handoff, canonical)) + "\n",
                encoding="utf-8",
            )

            counts = rebuild_agent_behavior_csv(root)

            self.assertEqual(counts["enterprise_agent"], 1)
            row = list(
                __import__("csv").DictReader(
                    (root / "enterprise_agent_behavior.csv").open(newline="")
                )
            )[0]
            self.assertEqual(row["trajectory_action"], "executor_agent_action")
            self.assertEqual(row["tool_result_action"], "tool_result")
            self.assertEqual(row["actual_tool_result"], "True")

    def test_semantic_step_ids_and_parent_ids_are_stable(self):
        notifications = []
        for seq, event_type in ((1, "step/start"), (2, "assistant/message"), (3, "step/end")):
            data = {"turn": 1, "step": 1}
            if event_type == "assistant/message":
                data["message"] = {"content": "plan"}
            notifications.append(
                {
                    "session_id": "planner-1",
                    "role": "human_planner",
                    "payload": {
                        "event": {"type": event_type, "seq": seq, "data": data}
                    },
                }
            )
        context = {"trace_id": "trace-1", "handoff_id": "handoff-1"}
        first = _semantic_steps(notifications, task_id="task-1", audit_context=context)
        second = _semantic_steps(notifications, task_id="task-1", audit_context=context)
        self.assertEqual(
            [(step["event_id"], step["parent_event_id"]) for step in first],
            [(step["event_id"], step["parent_event_id"]) for step in second],
        )
        self.assertEqual(first[0]["trajectory_action"], "employee_agent_plan")
        self.assertEqual(first[0]["tool_result"], {})


if __name__ == "__main__":
    unittest.main()
