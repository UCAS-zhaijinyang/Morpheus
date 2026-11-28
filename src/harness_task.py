# ========= Copyright (c) 2026 TTFISH. Licensed under the MIT License. =========
# See the LICENSE file in the project root for the full license text.
#
# SPDX-License-Identifier: MIT
# ===============================================================================
"""Employee task execution through the DeepSeek Harness."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass

from deepseek_runtime import HarnessRun, run_human_tool_task
import config
from agent_registry import AgentRegistry, agent_audit_context, append_agent_audit_event
from audit_log import rebuild_agent_behavior_csv
from trajectory_schema import TrajectoryContext, new_event


@dataclass(frozen=True)
class HarnessTask:
    """Description of one employee-to-Agent Harness task."""

    question: str
    output_dir: str
    temperature: float = 0
    collaboration_context: str = ""


def construct_harness(
    question: str,
    output_dir: str,
    temperature: float = 0,
    collaboration_context: str = "",
) -> HarnessTask:
    """Describe a human-planner and tool-agent Harness execution."""

    return HarnessTask(
        question=question,
        output_dir=output_dir,
        temperature=temperature,
        collaboration_context=collaboration_context,
    )


def _member_context(member_id: str) -> str:
    profile_path = os.path.join(config.profile_output_dir, f"{member_id}.jsonc")
    if not os.path.exists(profile_path):
        return f"employee_id={member_id}"
    try:
        with open(profile_path, "r", encoding="utf-8") as handle:
            profile = json.load(handle)
    except (OSError, ValueError):
        return f"employee_id={member_id}"
    fields = (
        f"employee_id={profile.get('id', member_id)}",
        f"name={profile.get('name', '')}",
        f"role={profile.get('role', '')}",
        f"personality={profile.get('personality', '')}",
        f"authority={profile.get('description', '')}",
    )
    return "\n".join(fields)


def _write_detailed_log(log_path: str, result: HarnessRun) -> None:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write("[human_planner]\n")
        handle.write(result.planner_response)
        handle.write("\n\n[tool_agent]\n")
        handle.write(result.answer)
        handle.write("\n")


def _agent_dict(agent_profile) -> dict:
    if agent_profile is None:
        return {}
    if hasattr(agent_profile, "to_dict"):
        return agent_profile.to_dict()
    return dict(agent_profile)


def _resolve_agent(member_id: str, execution_mode: str, action: str) -> dict:
    registry = AgentRegistry.load(
        config.agent_registry_path,
        [member_id],
    )
    return _agent_dict(registry.resolve(member_id, execution_mode, action))


def run_task(
    week: int,
    date: str,
    task: str,
    member_id: str,
    log_dir: str,
    event_index: int,
    output_dir: str,
    temperature: float = 0,
    agent_profile=None,
    execution_mode: str = "enterprise_agent",
    delegation_context: dict | None = None,
    caller_agent_profile=None,
    trajectory_context: dict | None = None,
) -> str:
    """Execute a complex employee activity with the Harness hand-off."""

    profile = _agent_dict(agent_profile) or _resolve_agent(member_id, execution_mode, "task")
    caller = _agent_dict(caller_agent_profile) or _resolve_agent(
        member_id, "employee_personal", "task"
    )
    delegation_context = delegation_context or {
        "delegation_chain": [
            item for item in (caller.get("agent_id"), profile.get("agent_id")) if item
        ]
    }
    task_id = f"{member_id}-w{week}-{date}-event-{event_index}"
    context = TrajectoryContext.from_dict(trajectory_context)
    context.runtime_id = context.runtime_id or f"runtime-{uuid.uuid4().hex}"
    context.handoff_id = context.handoff_id or f"handoff-{uuid.uuid4().hex}"
    context.human_principal = member_id
    context.task_purpose = context.task_purpose or task
    context.purpose = context.purpose or context.task_purpose
    context.caller_agent_id = caller.get("agent_id")
    context.executor_agent_id = profile.get("agent_id")
    context.initiator_agent_id = context.initiator_agent_id or caller.get("agent_id")
    context.agent_intent = {
        "execution_mode": execution_mode,
        "agent_id": profile.get("agent_id"),
        **context.agent_intent,
    }
    audit_context = agent_audit_context(
        caller,
        profile,
        human_principal=member_id,
        execution_mode=execution_mode,
        delegation_chain=delegation_context.get("delegation_chain"),
    )
    started_event = new_event(
        "task_started",
        context,
        task_id=task_id,
        operation="task_start",
        metadata={
            "member_id": member_id,
            "week": week,
            "date": date,
            "event_index": event_index,
            "agent": profile,
        },
    )
    append_agent_audit_event(log_dir, {**started_event, **audit_context})
    result = run_human_tool_task(
        task,
        output_dir=output_dir,
        log_dir=log_dir,
        role_context=_member_context(member_id),
        temperature=temperature,
        session_prefix=f"morpheus-{member_id}-w{week}-{event_index}",
        agent_profile=profile,
        execution_mode=execution_mode,
        human_principal=member_id,
        delegation_context=delegation_context,
        caller_agent_profile=caller,
        task_id=task_id,
        trajectory_context=context.to_dict(),
    )

    detailed_log = os.path.join(
        log_dir, f"{member_id}_week_{week}_{date}_executio_task_{event_index}.log"
    )
    _write_detailed_log(detailed_log, result)
    rebuild_agent_behavior_csv(log_dir)
    event_path = os.path.join(log_dir, "harness_events.jsonl")
    os.makedirs(log_dir, exist_ok=True)
    with open(event_path, "a", encoding="utf-8") as event_file:
        completed_event = new_event(
            "task_completed",
            context,
            task_id=task_id,
            parent_event_id=started_event["event_id"],
            session_id=result.executor_session_id,
            operation="task_complete",
            tool_result={},
            metadata={
                "member_id": member_id,
                "week": week,
                "date": date,
                "event_index": event_index,
                "human_agent_handoff": True,
                "planner_session_id": result.planner_session_id,
                "executor_session_id": result.executor_session_id,
                "model_observation": result.answer,
                "agent": profile,
            },
        )
        event_file.write(json.dumps(completed_event, ensure_ascii=False) + "\n")
    append_agent_audit_event(log_dir, {**completed_event, **audit_context})
    return result.answer


if __name__ == "__main__":
    print(
        run_task(
            1,
            "Monday",
            "Inspect the assigned work item and report the next action.",
            "employee-1",
            config.execution_log_dir,
            0,
            config.execution_log_dir,
        )
    )
