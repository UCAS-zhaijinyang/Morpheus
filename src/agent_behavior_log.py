"""Rebuild Agent behavior CSVs from persisted Harness notifications."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


AGENT_BEHAVIOR_FIELDS = [
    "member_id",
    "execution_mode",
    "agent_id",
    "agent_type",
    "agent_role",
    "phase",
    "semantic_action",
    "tool_name",
    "input_summary",
    "observation_summary",
    "status",
    "task_id",
    "session_id",
    "source_event_type",
    "source_seq",
    "event_index",
    "human_principal",
]


def write_agent_behavior_csv(
    log_dir: str | Path,
    execution_mode: str,
    rows: list[dict[str, Any]],
) -> None:
    """Write one high-level-action CSV for one routed Agent family."""

    path = Path(log_dir) / f"{execution_mode}_behavior.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=AGENT_BEHAVIOR_FIELDS)
        writer.writeheader()
        writer.writerows(
            {field: row.get(field, "") for field in AGENT_BEHAVIOR_FIELDS}
            for row in rows
        )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def rebuild_agent_behavior_csv(log_dir: str | Path) -> dict[str, int]:
    """Reconstruct both Agent CSVs from ``harness_events.jsonl``.

    The parser is intentionally offline. It groups one turn/step's planning
    messages, tool calls, and tool results into one high-level action row.
    """

    from deepseek_harness_adapter import _semantic_steps

    log_path = Path(log_dir)
    records = _read_jsonl(log_path / "harness_events.jsonl")
    handoffs = [
        record
        for record in records
        if record.get("event_type") == "human_agent_handoff"
    ]
    rows_by_mode = {"personal_agent": [], "enterprise_agent": []}
    audit_fields = (
        "human_principal",
        "execution_mode",
        "agent_id",
        "agent_type",
        "owner_id",
        "executor_agent_id",
        "executor_agent_type",
        "executor_agent_owner_id",
        "caller_agent_id",
        "caller_agent_type",
        "caller_agent_owner_id",
        "delegation_chain",
    )

    for handoff_index, handoff in enumerate(handoffs):
        execution_mode = handoff.get("execution_mode")
        if execution_mode not in rows_by_mode:
            continue
        session_ids = {
            handoff.get("planner_session_id"),
            handoff.get("executor_session_id"),
        }
        notifications = [
            record
            for record in records
            if record.get("event_type") == "harness_notification"
            and record.get("session_id") in session_ids
        ]
        member_id = str(handoff.get("human_principal") or "")
        task_id = f"{member_id}-{execution_mode}-handoff-{handoff_index}"
        audit_context = {
            field: handoff.get(field)
            for field in audit_fields
            if field in handoff
        }
        steps = _semantic_steps(
            notifications,
            task_id=task_id,
            audit_context=audit_context,
        )
        for step in steps:
            rows_by_mode[execution_mode].append(
                {
                    "member_id": member_id,
                    "execution_mode": execution_mode,
                    "agent_id": handoff.get("executor_agent_id")
                    or handoff.get("agent_id"),
                    "agent_type": handoff.get("executor_agent_type")
                    or handoff.get("agent_type"),
                    "agent_role": step.get("agent_role"),
                    "phase": step.get("phase"),
                    "semantic_action": step.get("semantic_action"),
                    "tool_name": step.get("tool_name"),
                    "input_summary": step.get("input_summary"),
                    "observation_summary": step.get("observation_summary"),
                    "status": step.get("status"),
                    "task_id": task_id,
                    "session_id": step.get("session_id"),
                    "source_event_type": step.get("source_event_type"),
                    "source_seq": step.get("source_seq"),
                    "event_index": step.get("event_index"),
                    "human_principal": member_id,
                }
            )

    counts = {}
    for execution_mode, rows in rows_by_mode.items():
        write_agent_behavior_csv(log_path, execution_mode, rows)
        counts[execution_mode] = len(rows)
    return counts
