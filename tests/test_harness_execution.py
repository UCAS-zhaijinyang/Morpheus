import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import config
from daily_schedule_generation import export_weekly_schedule_to_daily
from scenario_catalog import load_scenario
from schedule_constraints import planning_source
from harness_runner import build_parser, run_schedules


class ScheduleExecutionSourceTests(unittest.TestCase):
    def test_daily_schedule_snapshots_are_isolated_by_employee_and_day(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profiles = root / "profiles"
            schedules = root / "schedules" / "week_1"
            profiles.mkdir()
            schedules.mkdir(parents=True)
            activities = {
                "analyst-a": {"Monday": "Review finance handover", "Tuesday": "Archive finance handover"},
                "analyst-b": {"Monday": "Review staffing handover", "Tuesday": "Archive staffing handover"},
            }
            for employee, days in activities.items():
                (profiles / f"{employee}.jsonc").write_text(json.dumps({"id": employee}))
                for day, activity in days.items():
                    (schedules / f"{employee}_week_1_{day}.json").write_text(
                        json.dumps([{"Time": "10:00", "Activity": activity}])
                    )
            args = build_parser(horizon=True).parse_args([
                "--profile-dir", str(profiles), "--schedule-dir", str(schedules.parent),
                "--output-dir", str(root / "runs"), "--weeks", "1", "--recording", "employee",
                "--agent-backend", "symbolic",
            ])
            with patch.object(config, "work_days", ("Monday", "Tuesday")):
                run_dir, manifest = run_schedules(args, horizon=True)
            self.assertEqual(manifest["events"], 4)
            for employee, days in activities.items():
                for day, activity in days.items():
                    folder = run_dir / employee / "week_1"
                    snapshot = json.loads((folder / f"{day}.schedule.json").read_text())
                    trace = json.loads((folder / f"{day}.jsonl").read_text())
                    self.assertEqual(snapshot[0]["Activity"], activity)
                    self.assertEqual(trace["employee"]["activity"], activity)
                self.assertFalse((run_dir / employee / "week_1" / "schedule.json").exists())

    def test_weekly_assignment_survives_both_recording_levels(self):
        profile = {"id": "analyst-1", "name": "Analyst", "role": "Analyst", "department": "home",
                   "mbti": "INTJ", "container_id": "local", "interests": "", "personality": "", "age": 35}
        source = {"department": "finance", "department_head": "finance-3",
                  "planning_protocol": "department_head_council_then_department_meetings"}
        roles = {profile["id"]: profile["role"]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schedules = root / "schedules"
            (root / "analyst-1.jsonc").write_text(json.dumps(profile))
            (root / "meeting_schedule_week_1.json").write_text(json.dumps(
                [{"week": 1, "id": profile["id"], "detailed_goals": ["Draft the quarterly report"], **source}]
            ))
            model_schedule = {"Monday": [{"Time": "11:00", "Activity": "Draft the quarterly report"}]}
            with patch.multiple(config, meeting_log_dir=str(root), profile_output_dir=str(root)), \
                    patch('daily_schedule_generation.days', ('Monday', 'Tuesday')), \
                    patch('daily_schedule_generation.run_llm', return_value=json.dumps(model_schedule)):
                export_weekly_schedule_to_daily(str(schedules), 1, profile['id'], roles, [profile])
            common = ['--profile-dir', str(root), '--schedule-dir', str(schedules),
                      '--output-dir', str(root / 'runs'), '--date', 'Monday', '--week', '1']
            parser = build_parser()
            with patch.object(config, 'harness_stub_mode', True):
                for recording in ('employee', 'full'):
                    run_dir, manifest = run_schedules(
                        parser.parse_args(common + ['--recording', recording, '--agent-backend', 'symbolic'])
                    )
                    trace = json.loads(
                        (run_dir / profile['id'] / 'week_1' / 'Monday.jsonl').read_text()
                    )
                    self.assertEqual(manifest['recording'], recording)
                    self.assertEqual(trace['recording'], recording)
                    if recording == 'employee':
                        self.assertEqual(set(trace), {'schema_version', 'recording', 'trace_id', 'employee'})
                        self.assertEqual(trace['employee']['activity'], 'Draft the quarterly report')
                        self.assertFalse((run_dir / '.state').exists())
                    else:
                        self.assertEqual(planning_source(trace['context']), source)
                        self.assertIn('agent', trace)
                        self.assertEqual(trace['employee']['activity'], 'Draft the quarterly report')
                        self.assertTrue((run_dir / '.state' / profile['id'] / 'memory.json').exists())

                attack_common = common + ['--scenario', 'scope_expansion', '--activity-index', '0']
                employee_run, _ = run_schedules(
                    parser.parse_args(attack_common + ['--recording', 'employee', '--agent-backend', 'symbolic'])
                )
                employee_trace = json.loads(
                    (employee_run / profile['id'] / 'week_1' / 'Monday.jsonl').read_text()
                )
                employee_schedule = json.loads(
                    (employee_run / profile['id'] / 'week_1' / 'Monday.schedule.json').read_text()
                )
                self.assertEqual(
                    employee_trace['employee']['activity'],
                    load_scenario('scope_expansion')['employee_activity']
                )
                self.assertEqual(employee_schedule[0]['Attack'], 'True')
                self.assertEqual(employee_schedule[0]['AttackScenario'], 'scope_expansion')

                full_run, _ = run_schedules(
                    parser.parse_args(attack_common + ['--recording', 'full', '--agent-backend', 'symbolic'])
                )
                full_trace = json.loads(
                    (full_run / profile['id'] / 'week_1' / 'Monday.jsonl').read_text()
                )
                full_schedule = json.loads(
                    (full_run / profile['id'] / 'week_1' / 'Monday.schedule.json').read_text()
                )
                self.assertEqual(full_schedule[0]['Activity'], 'Draft the quarterly report')
                self.assertEqual(full_trace['scenario']['variant'], 'scope_expansion')
                self.assertTrue(any(event['event_type'] == 'intervention_applied'
                                    for event in full_trace['events']))

if __name__ == '__main__':
    unittest.main()
