"""Validate separated CSV views before person-day aggregation.

The validator keeps the aggregation step honest. It checks that activity rows
cover the run manifest, that all event views point at known traces, and that
each required per-activity table has one row for every activity. The returned
mapping distinguishes a complete person-day from a missing or indeterminate
one without requiring the original nested JSONL to be read.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from csv_exports import EMPLOYEE_TABLES, FULL_TABLES


_KEYED_TABLES = ("final_schedule.csv", "threat_labels.csv")


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _activity_key(row: Mapping[str, Any]) -> tuple[str, int | None, str]:
    return (
        str(row.get("employee_id") or ""),
        _as_int(row.get("week")),
        str(row.get("date") or ""),
    )


def _trace(row: Mapping[str, Any]) -> str:
    return str(row.get("trace_id") or "")


def _required_tables(root: Path, manifest: Mapping[str, Any]) -> list[str]:
    recording = str(manifest.get("recording") or "")
    if recording not in {"employee", "full"}:
        raise ValueError(f"unsupported recording level: {recording!r}")
    tables = list(EMPLOYEE_TABLES)
    if recording == "full":
        tables.extend(FULL_TABLES)
    return tables


def _expected_days(manifest: Mapping[str, Any]) -> list[tuple[str, int, str]]:
    employees = [str(item) for item in manifest.get("employees", [])]
    calendar = manifest.get("calendar", [])
    expected: list[tuple[str, int, str]] = []
    for entry in calendar:
        if not isinstance(entry, Mapping) or not entry.get("date"):
            raise ValueError("manifest calendar entries must contain date")
        week = _as_int(entry.get("week"))
        if week is None:
            raise ValueError("manifest calendar entries must contain an integer week")
        expected.extend((employee, week, str(entry["date"])) for employee in employees)
    return expected


def _missing_days(manifest: Mapping[str, Any]) -> set[tuple[str, int, str]]:
    values = manifest.get("missing_employee_days", [])
    result: set[tuple[str, int, str]] = set()
    if isinstance(values, list):
        for entry in values:
            if not isinstance(entry, Mapping):
                continue
            week = _as_int(entry.get("week"))
            date = entry.get("date")
            employee = entry.get("employee_id")
            if week is not None and employee and date:
                result.add((str(employee), week, str(date)))
    return result


def _table_trace_check(
    table: str,
    rows: list[Mapping[str, Any]],
    activities: Mapping[str, Mapping[str, Any]],
) -> None:
    for row in rows:
        trace = _trace(row)
        if not trace:
            # Empty login and email views contain only a header. Any actual row
            # may be assigned by the aggregator from its employee/day/time
            # coordinates when the legacy event writer did not emit trace_id.
            if table in {"logon.csv", "email.csv"}:
                continue
            raise ValueError(f"{table} contains a row without trace_id")
        if trace not in activities:
            raise ValueError(f"{table} references unknown trace_id: {trace}")


def _check_coordinates(
    table: str,
    row: Mapping[str, Any],
    activity: Mapping[str, Any],
) -> None:
    """Check coordinates that a flat view actually carries."""

    coordinate_pairs = (
        (("employee_id", "id", "email_from"), "employee_id"),
        (("week",), "week"),
        (("date",), "date"),
        (("schedule_index", "index"), "schedule_index"),
        (("sim_time", "sim_timestamp"), "sim_time"),
    )
    for names, activity_name in coordinate_pairs:
        value = next((row[name] for name in names if row.get(name) not in (None, "")), None)
        expected = activity.get(activity_name)
        if value in (None, "") or expected in (None, ""):
            continue
        if activity_name in {"week", "schedule_index"}:
            if _as_int(value) != _as_int(expected):
                raise ValueError(f"{table} coordinate {activity_name} disagrees with trace_id")
        elif str(value) != str(expected):
            raise ValueError(f"{table} coordinate {activity_name} disagrees with trace_id")


def validate_run_views(
    root: str | Path,
    manifest: Mapping[str, Any],
    views: Mapping[str, list[Mapping[str, Any]]],
) -> dict[tuple[str, int, str], str]:
    """Validate separated views and return person-day completeness statuses."""

    root_path = Path(root)
    required = _required_tables(root_path, manifest)
    missing_files = [name for name in required if not (root_path / name).is_file()]
    if missing_files:
        raise FileNotFoundError(
            f"{root_path}: missing separated CSV views: {', '.join(sorted(missing_files))}"
        )
    for name in required:
        if name not in views:
            raise ValueError(f"views is missing required table: {name}")

    activity_rows = list(views["employee_day.csv"])
    expected_events = manifest.get("events")
    if expected_events is not None and len(activity_rows) != int(expected_events):
        raise ValueError(
            f"employee_day.csv has {len(activity_rows)} rows, manifest expects {expected_events}"
        )

    activities: dict[str, Mapping[str, Any]] = {}
    by_day: defaultdict[tuple[str, int | None, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in activity_rows:
        trace = _trace(row)
        if not trace:
            raise ValueError("employee_day.csv contains a row without trace_id")
        if trace in activities:
            raise ValueError(f"duplicate activity trace_id: {trace}")
        activities[trace] = row
        key = _activity_key(row)
        if not key[0] or key[1] is None or not key[2]:
            raise ValueError(f"employee_day.csv contains an incomplete person-day key: {row}")
        if row.get("schedule_index") in (None, ""):
            raise ValueError(f"employee_day.csv contains an activity without schedule_index: {trace}")
        by_day[key].append(row)

    for key, rows in by_day.items():
        indexes = [_as_int(row.get("schedule_index")) for row in rows]
        if any(index is None or index < 0 for index in indexes) or len(set(indexes)) != len(indexes):
            raise ValueError(f"duplicate or invalid schedule_index for person-day {key}")

    for table in required:
        if table == "employee_day.csv":
            continue
        _table_trace_check(table, list(views[table]), activities)
        for row in views[table]:
            trace = _trace(row)
            if trace:
                _check_coordinates(table, row, activities[trace])

    expected_counts = manifest.get("csv_exports")
    if isinstance(expected_counts, Mapping):
        for table in required:
            expected_count = expected_counts.get(table)
            if expected_count is not None and len(views[table]) != int(expected_count):
                raise ValueError(
                    f"{table} has {len(views[table])} rows, manifest expects {expected_count}"
                )

    expected = _expected_days(manifest)
    if len(set(expected)) != len(expected):
        raise ValueError("manifest calendar contains duplicate employee-days")
    expected_set = set(expected)
    actual_set = set(by_day)
    unexpected = actual_set - expected_set
    if unexpected:
        raise ValueError(f"activity view contains employee-days outside manifest: {sorted(unexpected)}")

    # Per-activity alignment is required for the schedule and threat label
    # projections, and for effects in a full recording.
    for table in _KEYED_TABLES + (("effect.csv",) if manifest.get("recording") == "full" else ()):
        counts = Counter(_trace(row) for row in views[table])
        bad = [trace for trace in activities if counts[trace] != 1]
        if bad:
            raise ValueError(f"{table} must contain one row per activity, invalid traces: {bad}")

    missing_explicit = _missing_days(manifest)
    missing_budget = int(manifest.get("missing_days") or 0)
    if len(missing_explicit) > missing_budget:
        raise ValueError("manifest missing_employee_days exceeds missing_days")
    statuses: dict[tuple[str, int, str], str] = {}
    unresolved: list[tuple[str, int, str]] = []
    for key in expected:
        employee, week, date = key
        if key in by_day:
            statuses[key] = "complete"
            continue
        if key in missing_explicit:
            statuses[key] = "missing"
            continue
        path = root_path / employee / f"week_{week}" / f"{date}.jsonl"
        if path.is_file():
            statuses[key] = "complete"
        else:
            unresolved.append(key)
    remaining_budget = missing_budget - len(missing_explicit)
    if remaining_budget > len(unresolved):
        raise ValueError("manifest missing_days exceeds unresolved person-days")
    if remaining_budget == 0:
        inferred_status = "complete"
    elif remaining_budget == len(unresolved):
        inferred_status = "missing"
    else:
        inferred_status = "unknown"
    for key in unresolved:
        statuses[key] = inferred_status
    return statuses


__all__ = ["validate_run_views"]
