import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from employee_agent_runtime import simulate_activity
from scenario_catalog import load_scenario
from trajectory_recording import project_trace


class TrajectoryRecordingTests(unittest.TestCase):
    def test_employee_record_contains_only_activity(self):
        record = simulate_activity(
            employee_id="e1", activity="Review the handover", sim_time="10:00",
            scenario=load_scenario("cumulative_scope_change"),
            context={"run_id": "run-1", "previous_activity_trace_id": "prior", "department": "Records",
                     "agent_backend": "symbolic"},
        )
        original = copy.deepcopy(record)
        employee = project_trace(record, "employee")
        self.assertEqual(employee["employee"], record["employee"])
        self.assertEqual(employee["trace_id"], record["trace_id"])
        self.assertEqual(set(employee), {"schema_version", "recording", "trace_id", "employee"})
        self.assertNotIn("agent", employee)
        self.assertNotIn("scenario", employee)
        self.assertNotIn("context", employee)
        self.assertEqual(project_trace(record, "full"), {**original, "recording": "full"})
        self.assertEqual(record, original)

    def test_unsupported_recording_names_are_rejected(self):
        for name in ("compact", "summary", "agent"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                project_trace({}, name)
