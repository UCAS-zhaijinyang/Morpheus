import csv
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csv_exports import export_run_csvs
from harness_runner import build_parser, run_schedules


def _run(root, recording):
    profiles = root / "members"
    days = root / "schedules" / "week_1"
    profiles.mkdir()
    days.mkdir(parents=True)
    (profiles / "a.jsonc").write_text('{"id":"a"}', encoding="utf-8")
    (days / "a_week_1_Monday.json").write_text(json.dumps([
        {"Time": "10:00", "Activity": 'Review "handover", records\n归档'},
        {"Time": "14:00", "Activity": "Review the quarterly handover work card"},
    ], ensure_ascii=False), encoding="utf-8")
    args = build_parser().parse_args([
        "--profile-dir", str(profiles), "--schedule-dir", str(days.parent),
        "--output-dir", str(root / "runs"), "--week", "1", "--date", "Monday",
        "--recording", recording, "--agent-backend", "symbolic",
        "--scenario", "false_recipient_directory", "--activity-index", "1",
    ])
    return run_schedules(args)


def _rows(run, name):
    with (run / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_full_csv_projection_roundtrips_the_observed_events(tmp_path):
    run, summary = _run(tmp_path, "full")
    counts = summary["csv_exports"]
    trace_path = run / "a/week_1/Monday.jsonl"
    records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert _rows(run, "final_schedule.csv")[0]["activity"] == records[0]["employee"]["activity"]
    assert counts["agent_tool.csv"] == sum(len(r["agent"]["tool_calls"]) * 2 for r in records)
    calls = {r["call_id"] for r in _rows(run, "agent_tool.csv") if r["action"] == "call"}
    assert all(r["call_id"] in calls for r in _rows(run, "agent_tool.csv"))
    labels = _rows(run, "threat_labels.csv")
    assert [r["scenario_id"] for r in labels] == ["", "false_recipient_directory"]
    assert labels[1]["schedule_attack"] == "False"
    assert json.loads(labels[1]["intervention_events"])[0]["source"] == "document"
    assert _rows(run, "effect.csv")[1]["recipient"] == "tray-B"
    assert json.loads(_rows(run, "rag.csv")[1]["documents"]) == records[1]["agent"]["input"]["documents"]
    assert {r["event_type"] for r in _rows(run, "agent_prompt.csv")} == {
        "employee_prompt", "employee_prompt_drafted",
    }
    assert counts["logon.csv"] == counts["email.csv"] == 0
    assert export_run_csvs(run) == counts


def test_employee_projection_uses_only_the_saved_employee_and_schedule(tmp_path):
    run, summary = _run(tmp_path, "employee")
    assert set(summary["csv_exports"]) == {
        "employee_day.csv", "final_schedule.csv", "email.csv", "logon.csv", "threat_labels.csv",
    }
    assert not (run / "agent_tool.csv").exists()
    activities = _rows(run, "employee_day.csv")
    labels = _rows(run, "threat_labels.csv")
    assert [r["schedule_index"] for r in activities] == ["0", "1"]
    assert labels[1]["trace_id"] == activities[1]["trace_id"]
    assert labels[1]["schedule_attack"] == "True"
    assert all("scenario_id" not in row for row in activities)
    assert export_run_csvs(run) == summary["csv_exports"]
    with pytest.raises(ValueError, match="recording"):
        export_run_csvs(run, "full")


def test_bad_jsonl_does_not_replace_previously_exported_tables(tmp_path):
    run, summary = _run(tmp_path, "full")
    files = list(summary["csv_exports"])
    original = {name: (run / name).read_bytes() for name in files}
    with (run / "a/week_1/Monday.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{\n")
    with pytest.raises(ValueError, match="Monday.jsonl:3"):
        export_run_csvs(run)
    assert original == {name: (run / name).read_bytes() for name in files}
