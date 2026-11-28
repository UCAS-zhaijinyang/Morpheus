import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import config
from daily_schedule_generation import export_weekly_schedule_to_daily
from department_goal_coordination import WeeklyPlan
from weekly_goal_distribution import summarize_weekly_schedule


class PlanningPipelineTests(unittest.TestCase):
    def test_two_department_meetings_reach_the_matching_employee_schedule(self):
        staff = [
            {"id": "f1", "role": "Finance manager", "department": "Finance"},
            {"id": "f2", "role": "Analyst", "department": "Finance"},
            {"id": "p1", "role": "Planning lead", "department": "Planning"},
        ]
        roles = {person["id"]: person["role"] for person in staff}
        dept_goals = {
            "Finance": {"f1": "Agree the accounting cutoff", "f2": "Balance the quarterly ledger"},
            "Planning": {"p1": "Prepare the planning forecast"},
        }
        directive = "Finance provides the reconciled ledger to Planning."
        def stage(prompt, *, role_context, output_dir, log_dir, session_prefix):
            participants = role_context
            if session_prefix.endswith("head_council"):
                self.assertIn("id=f1", participants)
                self.assertIn("id=p1", participants)
                self.assertNotIn("id=f2", participants)
                answer = directive
            else:
                self.assertIn(directive, prompt)
                name = "Finance" if "id=f1" in participants else "Planning"
                self.assertEqual("id=f2" in participants, name == "Finance")
                answer = ("discussion " * 800) + json.dumps(dept_goals[name])
            return SimpleNamespace(planner_response="Prepare the plan", answer=answer)
        def extract(system_prompt, minutes):
            goals = json.loads(minutes[minutes.index("{"):])
            for member in staff:
                self.assertEqual(member["id"] in system_prompt, member["id"] in goals)
            return json.dumps([{"week": 1, "id": i, "detailed_goals": [g]} for i, g in goals.items()])
        def schedule(prompt, assignment):
            self.assertNotIn("all the members", prompt)
            data = json.loads(assignment)
            self.assertEqual(data["detailed_goals"], [dept_goals[data["department"]][data["employee_id"]]])
            return json.dumps({"Monday": [{"Time": "10:00", "Activity": data["detailed_goals"][0]}]})

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            profiles = base / "profiles"
            profiles.mkdir()
            for person in staff:
                person.update(name=person["id"], mbti="INTJ", age=30)
                (profiles / (person["id"] + ".jsonc")).write_text(json.dumps(person))
            meetings = base / "meetings"
            with (patch.multiple(config, meeting_log_dir=str(meetings),
                                 company_config_path=str(base / "company.json"),
                                 agent_registry_path=str(base / "agents.json")),
                  patch("hierarchical_meeting.run_human_tool_task", side_effect=stage),
                  patch("weekly_goal_distribution.run_llm", side_effect=extract),
                  patch("daily_schedule_generation.days", ("Monday",)),
                  patch("daily_schedule_generation.run_llm", side_effect=schedule)):
                WeeklyPlan(str(profiles))
                self.assertEqual(len(list(meetings.glob("*/*_meeting_detailed_actions.log"))), 3)
                summarize_weekly_schedule(str(meetings), list(roles), roles, 1)
                for person in staff:
                    member = person["id"]
                    export_weekly_schedule_to_daily(str(base / "daily"), 1, member, roles, staff)
                    daily = json.loads((base / "daily" / "week_1" / f"{member}_week_1_Monday.json").read_text())
                    self.assertEqual(daily[0]["department"], person["department"])
                    self.assertEqual(daily[0]["Activity"], dept_goals[person["department"]][member])

    def test_flat_minutes_and_wrong_roster(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "meeting_response.csv").write_text("legacy meeting minutes")
            roles = {"a": "lead", "b": "analyst"}
            wrong = [{"week": 1, "id": "a", "detailed_goals": ["Draft summary"]}] * 2
            good = [wrong[0], {"week": 1, "id": "b", "detailed_goals": ["Review budget"]}]
            with (patch.object(config, "max_attempt", 2),
                  patch("weekly_goal_distribution.run_llm", side_effect=[json.dumps(wrong), json.dumps(good)])):
                summarize_weekly_schedule(tmp, list(roles), roles, 1)
            previous = (root / "meeting_schedule_week_1.json").read_text()
            self.assertTrue(all(row["planning_protocol"] == "all_hands" for row in json.loads(previous)))
            with (patch.object(config, "max_attempt", 1),
                  patch("weekly_goal_distribution.run_llm", return_value=json.dumps(wrong)),
                  self.assertRaises(ValueError)):
                summarize_weekly_schedule(tmp, list(roles), roles, 1)
            self.assertEqual(previous, (root / "meeting_schedule_week_1.json").read_text())

    def test_legacy_week_file_and_days_off_are_preserved_on_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "meeting_schedule_week_1.json").write_text(json.dumps([{"id": "a", "detailed_goals": "Review"}]))
            profile = {"id": "a", "name": "Ana", "mbti": "INTJ", "age": 30, "role": "Analyst"}
            activity = {"Time": "10:00", "Activity": "Review"}
            first = {"Monday": [activity], "Tuesday": [activity], "Wednesday": [activity]}
            second = {"Monday": [activity], "Tuesday": []}
            with (patch.multiple(config, meeting_log_dir=tmp, agent_registry_path=str(root / "agents.json")),
                  patch("daily_schedule_generation.days", ("Monday", "Tuesday", "Wednesday")),
                  patch("daily_schedule_generation.run_llm", side_effect=[json.dumps(first), json.dumps(second)])):
                for _ in range(2):
                    export_weekly_schedule_to_daily(tmp, 1, "a", {"a": "Analyst"}, [profile])
            for day in ("Tuesday", "Wednesday"):
                self.assertEqual(json.loads((root / "week_1" / f"a_week_1_{day}.json").read_text()), [])
            self.assertEqual(json.loads((root / "week_1/a_week_1_Monday.json").read_text()), [activity])
