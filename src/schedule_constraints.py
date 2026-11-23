"""Shared constraints for compact, auditable employee schedules."""

from __future__ import annotations

from typing import Any


def _is_attack(entry: dict[str, Any]) -> bool:
    value = entry.get("Attack", False)
    return value is True or str(value).strip().lower() == "true"


def compact_schedule_entries(
    schedule: list[dict[str, Any]],
    max_entries: int = 4,
) -> list[dict[str, Any]]:
    """Merge overflow entries while preserving their order and content."""

    valid_entries = [entry for entry in schedule if isinstance(entry, dict)]
    if max_entries < 1 or len(valid_entries) <= max_entries:
        return valid_entries

    buckets: list[list[dict[str, Any]]] = [[] for _ in range(max_entries)]
    for index, entry in enumerate(valid_entries):
        bucket_index = min(index * max_entries // len(valid_entries), max_entries - 1)
        buckets[bucket_index].append(entry)

    compacted = []
    for bucket in buckets:
        if not bucket:
            continue
        merged = dict(bucket[0])
        activities = [str(item.get("Activity", "")).strip() for item in bucket]
        merged["Activity"] = "; ".join(activity for activity in activities if activity)
        if any(_is_attack(item) for item in bucket):
            merged["Attack"] = True
        compacted.append(merged)
    return compacted


def enforce_daily_schedule_limit(
    schedule: Any,
    max_entries: int = 4,
) -> Any:
    """Apply the daily entry limit to either one day or a whole week."""

    if isinstance(schedule, dict):
        return {
            day: compact_schedule_entries(entries, max_entries)
            if isinstance(entries, list)
            else entries
            for day, entries in schedule.items()
        }
    if isinstance(schedule, list):
        return compact_schedule_entries(schedule, max_entries)
    return schedule
