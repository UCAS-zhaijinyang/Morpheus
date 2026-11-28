import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trajectory_schema import EventEnvelope, TrajectoryContext, new_event


class TrajectorySchemaTests(unittest.TestCase):
    def test_context_and_event_preserve_causal_metadata(self):
        context = TrajectoryContext(
            scenario_id="scope_expansion",
            attack_id="scope_expansion",
            attack_stage=2,
            human_principal="employee-1",
            human_intent={"purpose": "summarize records"},
            agent_intent={"operation": "retrieve_and_send"},
            source_ids="ehr-q4",
            resource_ids=["ehr-q4"],
            recipient="external-ai",
        )
        event = EventEnvelope.from_context(
            "tool_call",
            context,
            task_id="task-1",
            operation="send",
            tool_call={"recipient": "external-ai"},
        )

        payload = event.to_dict()
        self.assertEqual(payload["trace_id"], context.trace_id)
        self.assertEqual(payload["scenario_id"], "scope_expansion")
        self.assertEqual(payload["attack_stage"], 2)
        self.assertEqual(payload["source_ids"], ["ehr-q4"])
        self.assertEqual(payload["recipient"], ["external-ai"])
        json.dumps(payload)

    def test_new_event_has_stable_ids_and_complete_core_fields(self):
        event = new_event("schedule_event", human_principal="employee-2")
        self.assertTrue(event["trace_id"].startswith("trace-"))
        self.assertTrue(event["event_id"].startswith("event-"))
        self.assertEqual(event["human_principal"], "employee-2")
        for field in (
            "parent_event_id",
            "task_id",
            "attack_id",
            "human_intent",
            "agent_intent",
            "tool_call",
            "tool_result",
            "executor_agent_id",
            "recorded_at",
        ):
            self.assertIn(field, event)


if __name__ == "__main__":
    unittest.main()
