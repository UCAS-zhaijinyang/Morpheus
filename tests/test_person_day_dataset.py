import csv
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from person_day_dataset import build_person_day_dataset


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row}) or ["trace_id"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _run(root: Path, recording: str = "full", missing: bool = False) -> Path:
    manifest = {
        "run_id": "run-person-day",
        "recording": recording,
        "employees": ["employee-1", "employee-2"] if missing else ["employee-1"],
        "calendar": [{"week": 1, "date": "Monday"}],
        "events": 1,
        "missing_days": 1 if missing else 0,
        "missing_employee_days": ([{"employee_id": "employee-2", "week": 1, "date": "Monday"}]
                                   if missing else []),
        "status": "completed",
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    _write_csv(root / "employee_day.csv", [{
        "trace_id": "trace-1", "employee_id": "employee-1", "week": 1,
        "date": "Monday", "schedule_index": 0, "sim_time": "10:00",
        "activity": "Review the work card",
    }])
    _write_csv(root / "final_schedule.csv", [{
        "trace_id": "trace-1", "id": "employee-1", "index": 0,
        "week": 1, "date": "Monday", "activity": "Review the work card",
    }])
    _write_csv(root / "threat_labels.csv", [{
        "trace_id": "trace-1", "employee_id": "employee-1", "week": 1,
        "date": "Monday", "scenario_id": "false_recipient_directory",
        "channel": "rag_document", "mechanism": "relevance_manipulation",
        "impact": "disclosure", "schedule_attack": "False",
        "intervention_events": json.dumps([{"event_id": "trace-1:3", "source": "document"}]),
    }])
    if recording == "full":
        _write_csv(root / "agent_prompt.csv", [{
            "trace_id": "trace-1", "event_id": "trace-1:1", "event_index": 1,
            "event_type": "employee_prompt", "text": "Review the work card",
        }])
        _write_csv(root / "agent_tool.csv", [
            {"trace_id": "trace-1", "event_id": "trace-1:2", "event_index": 2,
             "event_type": "agent_tool_result", "action": "result", "tool_name": "retrieve_work_card_documents",
             "call_id": "trace-1:1", "data": json.dumps({"documents": [{"document_id": "directory"}]})},
        ])
        _write_csv(root / "rag.csv", [{
            "trace_id": "trace-1", "event_id": "trace-1:2", "event_index": 2,
            "event_type": "agent_tool_result", "documents": json.dumps([{"document_id": "directory"}]),
        }])
        _write_csv(root / "effect.csv", [{
            "trace_id": "trace-1", "event_id": "trace-1:4", "status": "filed",
            "recipient": "tray-B", "actual_external_effect": "False",
        }])
        for name in ("agent_activity.csv", "skill.csv", "memory.csv"):
            _write_csv(root / name, [])
    for name in ("logon.csv", "email.csv"):
        if not (root / name).exists():
            _write_csv(root / name, [])
    return root


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_builds_nested_person_day_and_keeps_labels_separate(tmp_path):
    result = build_person_day_dataset(_run(tmp_path))
    output = Path(result["output_dir"])
    assert result["person_days"] == 1
    assert result["activities"] == 1
    record = _read_jsonl(output / "person_day.jsonl")[0]
    assert record["person_day_id"] == "employee-1/week_1/Monday"
    assert record["summary"]["tool_event_count"] == 1
    assert len(record["activities"][0]["observations"]["events"]) == 3
    assert "labels" not in record
    assert "labels" not in record["activities"][0]
    with (output / "person_day.csv").open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert "false_recipient_directory" not in row["activities"]
    with (output / "person_day_labels.csv").open(encoding="utf-8", newline="") as handle:
        label = next(csv.DictReader(handle))
    assert label["scenario_ids"] == '["false_recipient_directory"]'


def test_missing_employee_day_is_emitted_as_empty_person_day(tmp_path):
    result = build_person_day_dataset(_run(tmp_path, "employee", missing=True))
    records = _read_jsonl(Path(result["jsonl_file"]))
    assert result["person_days"] == 2
    assert result["complete_person_days"] == 1
    assert result["missing_person_days"] == 1
    missing = next(item for item in records if item["employee_id"] == "employee-2")
    assert missing["status"] == "missing"
    assert missing["activities"] == []


def test_empty_scheduled_day_is_complete_when_no_schedule_is_missing(tmp_path):
    root = _run(tmp_path, "employee")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["events"] = 0
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "employee_day.csv").write_text(
        "trace_id,employee_id,week,date,schedule_index,sim_time,activity\n",
        encoding="utf-8",
    )
    for name in ("final_schedule.csv", "threat_labels.csv"):
        (root / name).write_text("trace_id\n", encoding="utf-8")
    result = build_person_day_dataset(root)
    record = _read_jsonl(Path(result["jsonl_file"]))[0]
    assert record["status"] == "complete"
    assert record["activities"] == []


def test_completed_run_rejects_incomplete_activity_view(tmp_path):
    root = _run(tmp_path)
    (root / "employee_day.csv").write_text("trace_id\n", encoding="utf-8")
    with pytest.raises(ValueError, match="employee_day.csv"):
        build_person_day_dataset(root)


def test_shared_run_output_preserves_source_files_and_large_cells(tmp_path):
    root = _run(tmp_path)
    large = "x" * 150_000
    _write_csv(root / "agent_activity.csv", [{
        "trace_id": "trace-1", "event_id": "trace-1:99", "event_index": 99,
        "event_type": "agent_output", "data": json.dumps({"large": large}),
    }])
    build_person_day_dataset(root, root)
    assert (root / "manifest.json").is_file()
    assert (root / "employee_day.csv").is_file()
    record = _read_jsonl(root / "person_day.jsonl")[0]
    event = next(item for item in record["activities"][0]["observations"]["events"]
                 if item["event_id"] == "trace-1:99")
    assert len(event["data"]["large"]) == len(large)


def test_literal_text_and_session_views_keep_their_trace_assignment(tmp_path):
    root = _run(tmp_path)
    _write_csv(root / "agent_activity.csv", [{
        "trace_id": "trace-1", "event_id": "trace-1:99", "event_index": 99,
        "event_type": "agent_output",
        "data": json.dumps({"numeric": "007", "boolean": "true"}),
    }])
    _write_csv(root / "logon.csv", [{
        "trace_id": "trace-1", "id": "employee-1", "week": "1", "date": "Monday", "sim_timestamp": "10:00",
        "status": "007",
    }])
    _write_csv(root / "email.csv", [{
        "trace_id": "trace-1", "email_from": "employee-1", "week": "1", "date": "Monday", "sim_timestamp": "10:00",
        "content": "true",
    }])
    result = build_person_day_dataset(root)
    record = _read_jsonl(Path(result["jsonl_file"]))[0]
    views = record["activities"][0]["observations"]["views"]
    assert views["logon"][0]["trace_id"] == "trace-1"
    assert views["logon"][0]["status"] == "007"
    assert views["email"][0]["trace_id"] == "trace-1"
    assert views["email"][0]["content"] == "true"
    event = next(item for item in record["activities"][0]["observations"]["events"]
                 if item["event_id"] == "trace-1:99")
    assert event["data"]["numeric"] == "007"
    assert event["data"]["boolean"] == "true"
