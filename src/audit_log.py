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
    "organization_id",
    "project_id",
    "department",
    "department_head",
    "planning_protocol",
    "purpose",
    "task_purpose",
    "intent_id",
    "runtime_id",
    "handoff_id",
    "human_intent",
    "agent_intent",
    "source_ids",
    "resource_ids",
    "recipient",
    "trace_id",
    "event_id",
    "parent_event_id",
    "scenario_id",
    "attack_id",
    "attack_stage",
    "threat_phase",
    "trajectory_action",
    "tool_result_action",
    "employee_agent_plan",
    "executor_agent_action",
    "actual_tool_call",
    "actual_tool_result",
]


def write_agent_behavior_csv(
    log_dir: str | Path,
    execution_mode: str,
    rows: list[dict[str, Any]],
) -> None:
    """Write one high-level-action CSV for one routed Agent family."""

    path = Path(log_dir) / f"{execution_mode}_behavior.csv"
    path.parent.mkdir(parents=True, exist_ok=True)

    def csv_value(value: Any) -> Any:
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, ensure_ascii=False, default=str)
        return value

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=AGENT_BEHAVIOR_FIELDS)
        writer.writeheader()
        writer.writerows(
            {
                field: csv_value(row.get(field, ""))
                for field in AGENT_BEHAVIOR_FIELDS
            }
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


def _handoff_value(
    handoff: dict[str, Any],
    key: str,
    default: Any = None,
) -> Any:
    """Read new top-level handoff fields and legacy metadata fallbacks."""

    value = handoff.get(key)
    if value is not None:
        return value
    metadata = handoff.get("metadata")
    if isinstance(metadata, dict) and metadata.get(key) is not None:
        return metadata[key]
    return default


def _step_row(
    step: dict[str, Any],
    *,
    execution_mode: str,
    handoff: dict[str, Any],
    task_id: str,
    member_id: str,
) -> dict[str, Any]:
    """Project a canonical or reconstructed step into the legacy CSV shape."""

    return {
        "member_id": member_id,
        "execution_mode": execution_mode,
        "agent_id": step.get("executor_agent_id")
        or step.get("agent_id")
        or _handoff_value(handoff, "executor_agent_id")
        or _handoff_value(handoff, "agent_id"),
        "agent_type": step.get("executor_agent_type")
        or step.get("agent_type")
        or _handoff_value(handoff, "executor_agent_type")
        or _handoff_value(handoff, "agent_type"),
        "agent_role": step.get("agent_role"),
        "phase": step.get("phase"),
        "semantic_action": step.get("semantic_action"),
        "tool_name": step.get("tool_name"),
        "input_summary": step.get("input_summary"),
        "observation_summary": step.get("observation_summary"),
        "status": step.get("status"),
        "task_id": step.get("task_id") or task_id,
        "session_id": step.get("session_id"),
        "source_event_type": step.get("source_event_type"),
        "source_seq": step.get("source_seq"),
        "event_index": step.get("event_index"),
        "human_principal": step.get("human_principal") or member_id,
        "organization_id": step.get("organization_id") or _handoff_value(handoff, "organization_id"),
        "project_id": step.get("project_id") or _handoff_value(handoff, "project_id"),
        "department": step.get("department") or _handoff_value(handoff, "department"),
        "department_head": step.get("department_head") or _handoff_value(handoff, "department_head"),
        "planning_protocol": step.get("planning_protocol") or _handoff_value(handoff, "planning_protocol"),
        "purpose": step.get("purpose") or _handoff_value(handoff, "purpose"),
        "task_purpose": step.get("task_purpose") or _handoff_value(handoff, "task_purpose"),
        "intent_id": step.get("intent_id") or _handoff_value(handoff, "intent_id"),
        "runtime_id": step.get("runtime_id") or _handoff_value(handoff, "runtime_id"),
        "handoff_id": step.get("handoff_id") or _handoff_value(handoff, "handoff_id"),
        "human_intent": step.get("human_intent") or _handoff_value(handoff, "human_intent", {}),
        "agent_intent": step.get("agent_intent") or _handoff_value(handoff, "agent_intent", {}),
        "source_ids": step.get("source_ids") or _handoff_value(handoff, "source_ids", []),
        "resource_ids": step.get("resource_ids") or _handoff_value(handoff, "resource_ids", []),
        "recipient": step.get("recipient") or _handoff_value(handoff, "recipient", []),
        "trace_id": step.get("trace_id") or _handoff_value(handoff, "trace_id"),
        "event_id": step.get("event_id"),
        "parent_event_id": step.get("parent_event_id"),
        "scenario_id": step.get("scenario_id") or _handoff_value(handoff, "scenario_id"),
        "attack_id": step.get("attack_id") or _handoff_value(handoff, "attack_id"),
        "attack_stage": step.get("attack_stage") or _handoff_value(handoff, "attack_stage"),
        "threat_phase": step.get("threat_phase") or _handoff_value(handoff, "threat_phase"),
        "trajectory_action": step.get("trajectory_action"),
        "tool_result_action": step.get("tool_result_action", ""),
        "employee_agent_plan": step.get("employee_agent_plan", ""),
        "executor_agent_action": step.get("executor_agent_action", ""),
        "actual_tool_call": step.get("actual_tool_call", False),
        "actual_tool_result": step.get("actual_tool_result", False),
    }


def rebuild_agent_behavior_csv(log_dir: str | Path) -> dict[str, int]:
    """Reconstruct both Agent CSVs from ``harness_events.jsonl``.

    The parser is intentionally offline. It groups one turn/step's planning
    messages, tool calls, and tool results into one high-level action row.
    """

    from deepseek_runtime import _semantic_steps

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
        "organization_id",
        "project_id",
        "department",
        "department_head",
        "planning_protocol",
        "purpose",
        "task_purpose",
        "intent_id",
        "runtime_id",
        "handoff_id",
        "human_intent",
        "agent_intent",
        "source_ids",
        "resource_ids",
        "recipient",
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
        "trace_id",
        "scenario_id",
        "attack_id",
        "attack_stage",
        "threat_phase",
    )

    for handoff_index, handoff in enumerate(handoffs):
        execution_mode = _handoff_value(handoff, "execution_mode")
        if execution_mode not in rows_by_mode:
            continue
        session_ids = {
            session_id
            for session_id in (
                _handoff_value(handoff, "planner_session_id"),
                _handoff_value(handoff, "executor_session_id"),
                handoff.get("session_id"),
            )
            if session_id
        }
        notifications = [
            record
            for record in records
            if record.get("event_type") == "harness_notification"
            and record.get("session_id") in session_ids
        ]
        member_id = str(_handoff_value(handoff, "human_principal") or "")
        task_id = str(
            _handoff_value(handoff, "task_id")
            or f"{member_id}-{execution_mode}-handoff-{handoff_index}"
        )
        audit_context = {
            field: _handoff_value(handoff, field)
            for field in audit_fields
            if _handoff_value(handoff, field) is not None
        }
        if notifications:
            steps = _semantic_steps(
                notifications,
                task_id=task_id,
                audit_context=audit_context,
            )
        else:
            # New runs persist canonical sidecar steps.  Use them only when
            # raw notifications are unavailable so rebuilding never doubles
            # the rows.  This also lets old readers consume a migrated log.
            steps = [
                record
                for record in records
                if record.get("event_type") == "agent_step"
                and record.get("task_id") == task_id
                and record.get("source_event_type") != "session_completed"
                and (
                    record.get("session_id") in session_ids
                    or not session_ids
                )
            ]
        for step in steps:
            rows_by_mode[execution_mode].append(
                _step_row(
                    step,
                    execution_mode=execution_mode,
                    handoff=handoff,
                    task_id=task_id,
                    member_id=member_id,
                )
            )

    counts = {}
    for execution_mode, rows in rows_by_mode.items():
        write_agent_behavior_csv(log_path, execution_mode, rows)
        counts[execution_mode] = len(rows)
    return counts
