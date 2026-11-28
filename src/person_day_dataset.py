"""Assemble separated run CSV views into employee-day records.

The daily runner keeps one nested JSONL record per activity and publishes
separate CSV projections for analysis.  This module joins those projections by
``trace_id`` and emits one row per employee, week, and date.  Observations and
ground-truth threat labels are written to separate tables so a detector can
consume the former without receiving the latter.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from contextlib import ExitStack
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable


OBSERVATION_TABLES = (
    "employee_day.csv",
    "final_schedule.csv",
    "agent_prompt.csv",
    "agent_activity.csv",
    "agent_tool.csv",
    "rag.csv",
    "skill.csv",
    "memory.csv",
    "effect.csv",
    "logon.csv",
    "email.csv",
)
LABEL_TABLE = "threat_labels.csv"

PERSON_DAY_FIELDS = (
    "person_day_id",
    "source_run_id",
    "employee_id",
    "week",
    "date",
    "recording",
    "status",
    "activity_count",
    "trace_ids",
    "activities",
    "sim_times",
    "prompt_count",
    "agent_activity_count",
    "tool_event_count",
    "rag_event_count",
    "skill_event_count",
    "memory_event_count",
    "effect_count",
    "event_count",
    "recipients",
    "effect_statuses",
    "actual_external_effects",
)

LABEL_FIELDS = (
    "person_day_id",
    "source_run_id",
    "employee_id",
    "week",
    "date",
    "scenario_ids",
    "channels",
    "mechanisms",
    "impacts",
    "schedule_attack_count",
    "intervention_count",
    "labels",
)

_EVENT_TABLES = {
    "agent_prompt.csv": "agent_prompt",
    "agent_activity.csv": "agent_activity",
    "agent_tool.csv": "agent_tool",
    "rag.csv": "rag",
    "skill.csv": "skill",
    "memory.csv": "memory",
    "effect.csv": "effect",
}


def _decode(value: Any, field: str = "") -> Any:
    """Decode only columns whose CSV contract contains structured JSON."""

    structural = {
        "fields", "data", "arguments", "original_result", "documents",
        "original_documents", "skill", "original_skill", "records",
        "original_records", "receipt", "before", "after", "intervention_events",
    }
    if not isinstance(value, str) or not value or field not in structural:
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return str(value)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    # Full Agent observations can carry a document set or long model output
    # in one quoted cell, exceeding Python's default 128 KiB parser ceiling.
    import sys
    csv.field_size_limit(sys.maxsize)
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            {key: _decode(value, key) for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def _manifest(root: Path) -> dict[str, Any]:
    path = root / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"missing run manifest: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"invalid run manifest {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"run manifest must be an object: {path}")
    return value


def _person_key(row: dict[str, Any]) -> tuple[str, int, str]:
    return (str(row.get("employee_id") or ""), _int(row.get("week")), str(row.get("date") or ""))


def _trace_key(row: dict[str, Any]) -> str:
    return str(row.get("trace_id") or "")


def _event_key(row: dict[str, Any]) -> str:
    return str(row.get("event_id") or "")


def _expected_days(manifest: dict[str, Any]) -> list[tuple[str, int, str]]:
    employees = [str(item) for item in manifest.get("employees", [])]
    calendar = manifest.get("calendar", [])
    expected = []
    for day in calendar:
        if not isinstance(day, dict) or not day.get("date"):
            raise ValueError("manifest calendar entries must contain date")
        week = _int(day.get("week"))
        for employee in employees:
            expected.append((employee, week, str(day["date"])))
    return expected


def _load_views(root: Path, manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    views = {name: _read_csv(root / name) for name in (*OBSERVATION_TABLES, LABEL_TABLE)}
    required = manifest.get("events")
    if manifest.get("status") == "completed" and required is not None:
        actual = len(views["employee_day.csv"])
        if actual != _int(required):
            raise ValueError(
                f"{root}: employee_day.csv has {actual} rows, manifest expects {required}"
            )
    if not (root / "employee_day.csv").is_file():
        raise FileNotFoundError(f"missing separated activity view: {root / 'employee_day.csv'}")
    return views


def _index_views(views: dict[str, list[dict[str, Any]]]) -> tuple[
    dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]],
    dict[str, dict[str, Any]], dict[str, dict[str, list[dict[str, Any]]]]
]:
    activities: dict[str, dict[str, Any]] = {}
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    labels: dict[str, dict[str, Any]] = {}
    signature_index: dict[tuple[str, str, str, str], list[str]] = defaultdict(list)
    for row in views["employee_day.csv"]:
        trace = _trace_key(row)
        if not trace:
            raise ValueError("employee_day.csv contains a row without trace_id")
        if trace in activities:
            raise ValueError(f"duplicate activity trace_id in employee_day.csv: {trace}")
        activities[trace] = row
        by_day["\x1f".join(map(str, _person_key(row)))].append(row)
        signature = (
            str(row.get("employee_id") or ""), str(row.get("week") or ""),
            str(row.get("date") or ""), str(row.get("sim_time") or ""),
        )
        signature_index[signature].append(trace)
    for row in views[LABEL_TABLE]:
        trace = _trace_key(row)
        if trace:
            labels[trace] = row
    indexed: dict[str, dict[str, list[dict[str, Any]]]] = {
        name: defaultdict(list) for name in views
    }
    for filename, rows in views.items():
        for row in rows:
            trace = _trace_key(row)
            if not trace and filename in {"logon.csv", "email.csv"}:
                signature = (
                    str(row.get("employee_id") or row.get("id") or row.get("email_from") or ""),
                    str(row.get("week") or ""), str(row.get("date") or ""),
                    str(row.get("sim_time") or row.get("sim_timestamp") or ""),
                )
                candidates = signature_index.get(signature, [])
                if len(candidates) == 1:
                    trace = candidates[0]
                    row = {**row, "trace_id": trace}
            if trace:
                indexed[filename][trace].append(row)
    return activities, by_day, labels, indexed


def _event_views(
    indexed_views: dict[str, dict[str, list[dict[str, Any]]]], trace_id: str
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    table_names = (*_EVENT_TABLES.items(), ("logon.csv", "logon"), ("email.csv", "email"))
    result: dict[str, list[dict[str, Any]]] = {view_name: [] for _, view_name in table_names}
    events: dict[str, dict[str, Any]] = {}
    for filename, view_name in table_names:
        for row in indexed_views.get(filename, {}).get(trace_id, []):
            result[view_name].append(row)
            event_id = _event_key(row)
            if not event_id:
                continue
            event = events.setdefault(event_id, {"event_id": event_id, "sources": []})
            if view_name not in event["sources"]:
                event["sources"].append(view_name)
            for key, value in row.items():
                if key not in event or event[key] in (None, ""):
                    event[key] = value
    return result, sorted(events.values(), key=lambda item: _int(item.get("event_index")))


def _activity_record(
    activity: dict[str, Any],
    schedule: dict[str, Any],
    label: dict[str, Any] | None,
    indexed_views: dict[str, dict[str, list[dict[str, Any]]]],
    recording: str,
) -> dict[str, Any]:
    trace_id = _trace_key(activity)
    event_views, events = _event_views(indexed_views, trace_id)
    return {
        "trace_id": trace_id,
        "schedule_index": _int(activity.get("schedule_index")),
        "sim_time": activity.get("sim_time", ""),
        "activity": activity.get("activity", ""),
        "schedule": schedule,
        "observations": {
            "employee_day": activity,
            "final_schedule": indexed_views.get("final_schedule.csv", {}).get(trace_id, []),
            "events": events,
            "views": event_views,
        },
        "labels": label or {},
        "recording": recording,
    }


def _summary(person_day: dict[str, Any]) -> dict[str, Any]:
    activities = person_day["activities"]
    values = lambda key: [item[key] for item in activities if item.get(key) not in (None, "")]
    events = [event for item in activities for event in item["observations"]["events"]]
    view_count = lambda view: len({
        _event_key(row) or f"{item['trace_id']}:{index}"
        for item in activities
        for index, row in enumerate(item["observations"]["views"][view])
    })
    effects = [
        row for item in activities for row in item["observations"]["views"]["effect"]
    ]
    recipients = []
    statuses = []
    external = []
    for row in effects:
        if row.get("recipient") not in (None, ""):
            recipients.append(row["recipient"])
        if row.get("status") not in (None, ""):
            statuses.append(row["status"])
        if row.get("actual_external_effect") not in (None, ""):
            external.append(row["actual_external_effect"])
    return {
        "activity_count": len(activities),
        "trace_ids": values("trace_id"),
        "activities": values("activity"),
        "sim_times": values("sim_time"),
        "prompt_count": view_count("agent_prompt"),
        "agent_activity_count": view_count("agent_activity"),
        "tool_event_count": view_count("agent_tool"),
        "rag_event_count": view_count("rag"),
        "skill_event_count": view_count("skill"),
        "memory_event_count": view_count("memory"),
        "effect_count": view_count("effect"),
        "recipients": recipients,
        "effect_statuses": statuses,
        "actual_external_effects": external,
        "event_count": len(events),
    }


def _label_summary(activities: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [item["labels"] for item in activities if item["labels"]]
    scenario_ids = sorted({str(row.get("scenario_id")) for row in labels if row.get("scenario_id")})
    channels = sorted({str(row.get("channel")) for row in labels if row.get("channel")})
    mechanisms = sorted({str(row.get("mechanism")) for row in labels if row.get("mechanism")})
    impacts = sorted({str(row.get("impact")) for row in labels if row.get("impact")})
    attack_count = sum(str(row.get("schedule_attack", "")).lower() == "true" for row in labels)
    interventions = []
    for row in labels:
        value = row.get("intervention_events")
        if isinstance(value, list):
            interventions.extend(value)
    return {
        "scenario_ids": scenario_ids,
        "channels": channels,
        "mechanisms": mechanisms,
        "impacts": impacts,
        "schedule_attack_count": attack_count,
        "intervention_count": len({
            _event_key(event) or json.dumps(event, sort_keys=True, ensure_ascii=False)
            for event in interventions if isinstance(event, dict)
        }),
        "labels": labels,
    }


def build_person_day_dataset(
    run_dir: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build one nested and one flat record for every employee-day in a run."""

    root = Path(run_dir)
    manifest = _manifest(root)
    views = _load_views(root, manifest)
    from person_day_inputs import validate_run_views

    day_statuses = validate_run_views(root, manifest, views)
    recording = str(manifest.get("recording") or "full")
    activities, by_day, labels, indexed_views = _index_views(views)
    schedule_rows = {
        _trace_key(row): row for row in views["final_schedule.csv"] if _trace_key(row)
    }
    expected = _expected_days(manifest)
    if not expected:
        # Older manifests may omit the calendar even though the separated
        # activity view is complete.  Recover the observed person-days rather
        # than silently dropping every row.
        expected = sorted(
            {_person_key(row) for row in activities.values()},
            key=lambda item: (item[1], item[2], item[0]),
        )
        day_statuses.update({key: "complete" for key in expected})
    person_days: list[dict[str, Any]] = []
    for employee_id, week, date in expected:
        key = "\x1f".join((employee_id, str(week), date))
        rows = sorted(by_day.get(key, []), key=lambda row: _int(row.get("schedule_index")))
        day_activities = [
            _activity_record(
                row, schedule_rows.get(_trace_key(row), {}), labels.get(_trace_key(row)),
                indexed_views, recording,
            )
            for row in rows
        ]
        person_day_id = f"{employee_id}/week_{week}/{date}"
        person_days.append({
            "schema_version": "morpheus.person_day.v1",
            "person_day_id": person_day_id,
            "source_run_id": manifest.get("run_id", root.name),
            "employee_id": employee_id,
            "week": week,
            "date": date,
            "recording": recording,
            "status": day_statuses.get((employee_id, week, date), "missing"),
            "summary": _summary({"activities": day_activities}),
            "labels": _label_summary(day_activities),
            "activities": day_activities,
        })

    destination = Path(output_dir) if output_dir is not None else root / "person_day_dataset"
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "run_id": manifest.get("run_id", root.name),
        "recording": recording,
        "person_days": len(person_days),
        "complete_person_days": sum(item["status"] == "complete" for item in person_days),
        "missing_person_days": sum(item["status"] == "missing" for item in person_days),
        "unknown_person_days": sum(item["status"] == "unknown" for item in person_days),
        "activities": sum(item["summary"]["activity_count"] for item in person_days),
        "output_dir": str(destination),
        "observation_file": str(destination / "person_day.csv"),
        "label_file": str(destination / "person_day_labels.csv"),
        "jsonl_file": str(destination / "person_day.jsonl"),
    }
    destination.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".person-day-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        person_csv = stage / "person_day.csv"
        label_csv = stage / "person_day_labels.csv"
        jsonl = stage / "person_day.jsonl"
        with ExitStack() as stack:
            person_handle = stack.enter_context(person_csv.open("w", encoding="utf-8", newline=""))
            label_handle = stack.enter_context(label_csv.open("w", encoding="utf-8", newline=""))
            json_handle = stack.enter_context(jsonl.open("w", encoding="utf-8"))
            person_writer = csv.DictWriter(person_handle, fieldnames=PERSON_DAY_FIELDS)
            label_writer = csv.DictWriter(label_handle, fieldnames=LABEL_FIELDS)
            person_writer.writeheader()
            label_writer.writeheader()
            for item in person_days:
                summary = item["summary"]
                person_writer.writerow({
                    "person_day_id": item["person_day_id"],
                    "source_run_id": item["source_run_id"],
                    "employee_id": item["employee_id"], "week": item["week"], "date": item["date"],
                    "recording": item["recording"], "status": item["status"], **{
                        field: _cell(summary.get(field, "")) for field in PERSON_DAY_FIELDS
                        if field in summary
                    },
                })
                labels = item["labels"]
                label_writer.writerow({
                    "person_day_id": item["person_day_id"], "source_run_id": item["source_run_id"],
                    "employee_id": item["employee_id"], "week": item["week"], "date": item["date"],
                    **{field: _cell(labels.get(field, "")) for field in LABEL_FIELDS if field not in {
                        "person_day_id", "source_run_id", "employee_id", "week", "date"
                    }},
                })
            # The labels are deliberately omitted from the public nested
            # observation file.  They are available in person_day_labels.csv.
            for item in person_days:
                public = {key: value for key, value in item.items() if key != "labels"}
                public["activities"] = [
                    {key: value for key, value in activity.items() if key != "labels"}
                    for activity in item["activities"]
                ]
                json_handle.write(
                    json.dumps(public, ensure_ascii=False, separators=(",", ":")) + "\n"
                )
        stage_manifest = stage / "person_day_manifest.json"
        stage_manifest.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        for source in (person_csv, label_csv, jsonl, stage_manifest):
            source.replace(destination / source.name)
    return result


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="completed run directory containing separated CSVs")
    parser.add_argument("--output-dir", type=Path, help="person-day dataset directory")
    args = parser.parse_args(argv)
    print(json.dumps(build_person_day_dataset(args.run_dir, args.output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
