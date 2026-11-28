import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from csv_exports import EMPLOYEE_TABLES, FULL_TABLES
from person_day_inputs import validate_run_views


def _write_table(root: Path, name: str, rows: list[dict]) -> None:
    fields = set(EMPLOYEE_TABLES.get(name, ()) or FULL_TABLES.get(name, ()))
    for row in rows:
        fields.update(row)
    fields = sorted(fields) or ["trace_id"]
    with (root / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _fixture(tmp_path: Path, recording: str = "full"):
    tables = list(EMPLOYEE_TABLES)
    if recording == "full":
        tables.extend(FULL_TABLES)
    rows = {name: [] for name in tables}
    activity = {
        "trace_id": "trace-1", "employee_id": "e1", "week": "1",
        "date": "Monday", "schedule_index": "0", "sim_time": "10:00",
        "activity": "Review card",
    }
    rows["employee_day.csv"] = [activity]
    for name in tables:
        if name == "employee_day.csv":
            pass
        elif name in {"final_schedule.csv", "threat_labels.csv"} or name == "effect.csv":
            rows[name] = [{"trace_id": "trace-1", "employee_id": "e1", "week": "1",
                           "date": "Monday", "schedule_index": "0"}]
        else:
            rows[name] = []
        _write_table(tmp_path, name, rows[name])
    manifest = {
        "recording": recording, "employees": ["e1"],
        "calendar": [{"week": 1, "date": "Monday"}],
        "events": 1, "missing_days": 0, "status": "completed",
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    views = {name: rows[name] for name in tables}
    return manifest, views


def test_validates_complete_person_day(tmp_path):
    manifest, views = _fixture(tmp_path)
    result = validate_run_views(tmp_path, manifest, views)
    assert result == {("e1", 1, "Monday"): "complete"}


def test_rejects_unknown_trace(tmp_path):
    manifest, views = _fixture(tmp_path)
    views["final_schedule.csv"].append({"trace_id": "unknown"})
    with pytest.raises(ValueError, match="unknown trace_id"):
        validate_run_views(tmp_path, manifest, views)


def test_marks_manifest_missing_day(tmp_path):
    manifest, views = _fixture(tmp_path)
    manifest["employees"] = ["e1", "e2"]
    manifest["missing_days"] = 1
    manifest["missing_employee_days"] = [{"employee_id": "e2", "week": 1, "date": "Monday"}]
    result = validate_run_views(tmp_path, manifest, views)
    assert result[("e2", 1, "Monday")] == "missing"


def test_validates_manifest_csv_counts_and_cross_table_coordinates(tmp_path):
    manifest, views = _fixture(tmp_path)
    manifest["csv_exports"] = {name: len(rows) for name, rows in views.items()}
    manifest["csv_exports"]["effect.csv"] = 0
    with pytest.raises(ValueError, match="effect.csv has 1 rows"):
        validate_run_views(tmp_path, manifest, views)
    manifest["csv_exports"]["effect.csv"] = 1
    views["effect.csv"][0]["week"] = 2
    with pytest.raises(ValueError, match="coordinate week"):
        validate_run_views(tmp_path, manifest, views)


def test_infers_legacy_missing_or_unknown_days(tmp_path):
    manifest, views = _fixture(tmp_path, "employee")
    manifest["employees"].extend(["e2", "e3"])
    manifest["missing_days"] = 1
    result = validate_run_views(tmp_path, manifest, views)
    assert result[("e2", 1, "Monday")] == result[("e3", 1, "Monday")] == "unknown"
    existing = tmp_path / "e2/week_1/Monday.jsonl"
    existing.parent.mkdir(parents=True)
    existing.touch()
    result = validate_run_views(tmp_path, manifest, views)
    assert result[("e2", 1, "Monday")] == "complete"
    assert result[("e3", 1, "Monday")] == "missing"
