import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from schedule_constraints import compact_schedule_entries, enforce_daily_schedule_limit


class ScheduleConstraintTests(unittest.TestCase):
    def test_compacts_overflow_without_dropping_activity_text(self):
        schedule = [
            {"Time": f"{10 + index}:00", "Activity": f"Activity {index}"}
            for index in range(8)
        ]

        compacted = compact_schedule_entries(schedule, max_entries=4)

        self.assertEqual(len(compacted), 4)
        combined_text = " ".join(item["Activity"] for item in compacted)
        for index in range(8):
            self.assertIn(f"Activity {index}", combined_text)

    def test_applies_limit_to_each_day(self):
        schedule = {
            "Monday": [{"Time": "10:00", "Activity": str(index)} for index in range(5)],
            "Tuesday": [{"Time": "10:00", "Activity": "one"}],
        }

        limited = enforce_daily_schedule_limit(schedule, max_entries=4)

        self.assertEqual(len(limited["Monday"]), 4)
        self.assertEqual(len(limited["Tuesday"]), 1)


if __name__ == "__main__":
    unittest.main()
