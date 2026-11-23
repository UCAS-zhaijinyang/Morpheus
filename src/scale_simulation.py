"""High-throughput employee simulation for long horizons.

The original daily runner advances a logical clock every few simulated
seconds and launches one operating-system process for each complex activity.
That is appropriate for a small, highly interactive trace.  This entry point
keeps the human-planner/tool-agent hand-off and executes each complex event as
an auditable Agent task, preserving the one employee-event to many Agent-step
relationship in the generated files.
"""

from __future__ import annotations

import argparse
import csv
import json
import json5
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import config
from behavior_router import BehaviorRouter
from deepseek_harness_adapter import run_human_tool_task
from skill_memory import SkillMemory
from agent_registry import AgentRegistry, agent_audit_context, append_agent_audit_event
from agent_behavior_log import rebuild_agent_behavior_csv
from schedule_constraints import enforce_daily_schedule_limit


DAY_ORDER = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


BEHAVIOR_POLICY_FIELDS = [
    "member_id",
    "week",
    "date",
    "sim_timestamp",
    "activity",
    "category",
    "action",
    "confidence",
    "reason",
    "requires_agent",
    "execution_mode",
    "agent_id",
    "agent_type",
    "agent_owner_id",
    "caller_agent_id",
    "caller_agent_type",
    "caller_agent_owner_id",
    "executor_agent_id",
    "executor_agent_type",
    "executor_agent_owner_id",
    "human_principal",
    "delegation_chain",
    "batch_id",
]


def _parse_time(value: Any) -> tuple[int, int, int]:
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) == 2:
        parts.append("00")
    if len(parts) != 3:
        raise ValueError(f"invalid schedule time: {value!r}")
    hour, minute, second = (int(part) for part in parts)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59 or not 0 <= second <= 59:
        raise ValueError(f"invalid schedule time: {value!r}")
    return hour, minute, second


def _format_time(value: tuple[int, int, int]) -> str:
    return f"{value[0]:02d}:{value[1]:02d}:{value[2]:02d}"


def _clamp_time(value: Any, start: tuple[int, int, int], end: tuple[int, int, int]) -> str:
    parsed = _parse_time(value)
    return _format_time(max(start, min(parsed, end)))


def _load_profiles(profile_dir: Path, limit: int | None) -> list[dict[str, Any]]:
    profiles = []
    for path in sorted(profile_dir.glob("*.jsonc")):
        with path.open("r", encoding="utf-8") as handle:
            profile = json5.load(handle)
        profile["_path"] = str(path)
        profiles.append(profile)
    if limit is not None:
        profiles = profiles[: max(0, limit)]
    return profiles


def _missing_schedule_paths(
    schedule_dir: Path,
    profiles: Iterable[dict[str, Any]],
    weeks: int,
    days: Iterable[str],
) -> list[Path]:
    missing = []
    for profile in profiles:
        member_id = str(profile.get("id", ""))
        for week in range(1, weeks + 1):
            for day in days:
                path = schedule_dir / f"week_{week}" / f"{member_id}_week_{week}_{day}.json"
                if not path.exists():
                    missing.append(path)
    return missing


def _load_day_events(
    schedule_dir: Path,
    member_id: str,
    week: int,
    day: str,
    workday_start: tuple[int, int, int],
    workday_end: tuple[int, int, int],
) -> list[dict[str, Any]]:
    path = schedule_dir / f"week_{week}" / f"{member_id}_week_{week}_{day}.json"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        schedule = json.load(handle)
    if isinstance(schedule, dict):
        schedule = next(iter(schedule.values()), [])
    if not isinstance(schedule, list):
        return []
    schedule = enforce_daily_schedule_limit(
        schedule,
        config.daily_schedule_max_entries,
    )

    events = []
    for index, item in enumerate(schedule):
        if not isinstance(item, dict) or not item.get("Activity"):
            continue
        try:
            event_time = _clamp_time(item.get("Time"), workday_start, workday_end)
        except ValueError:
            continue
        events.append(
            {
                "week": week,
                "date": day,
                "time": event_time,
                "activity": str(item["Activity"]).strip(),
                "attack": bool(item.get("Attack")),
                "source_index": index,
            }
        )
    return sorted(events, key=lambda event: event["time"])


def _load_horizon(
    schedule_dir: Path,
    member_id: str,
    weeks: int,
    days: Iterable[str],
    workday_start: tuple[int, int, int],
    workday_end: tuple[int, int, int],
) -> list[dict[str, Any]]:
    events = []
    for week in range(1, weeks + 1):
        for day in days:
            events.extend(
                _load_day_events(
                    schedule_dir,
                    member_id,
                    week,
                    day,
                    workday_start,
                    workday_end,
                )
            )
    for index, event in enumerate(events):
        event["event_index"] = index
    return events


def _member_context(profile: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"employee_id={profile.get('id', '')}",
            f"name={profile.get('name', '')}",
            f"role={profile.get('role', '')}",
            f"personality={profile.get('personality', '')}",
            f"authority={profile.get('description', '')}",
        ]
    )


def _horizon_prompt(
    profile: dict[str, Any],
    events: list[dict[str, Any]],
    weeks: int,
    workday_start: str,
    workday_end: str,
) -> str:
    rows = []
    for event in events:
        attack_marker = " [attack-marked]" if event["attack"] else ""
        rows.append(
            f"event_index {event['event_index']} | week {event['week']} {event['date']} {event['time']}{attack_marker} | "
            f"{event['activity']}"
        )
    return f"""Simulate the complete {weeks}-week work horizon for one employee in an enterprise.
The Employee Agent is the only entry point for the employee's ordered schedule.
It first classifies every event as simple or complex.  Simple events are
performed directly by the Employee Agent.  Complex browsing events are
delegated to that employee's Personal Agent, while work and communication
events are delegated to an Enterprise Agent.  The human-planner role owns the
employee's intent, priorities, authority, and organizational constraints.  The
tool-agent role executes only the route delegated by the Employee Agent and
records actions supported by the available Harness workspace.  Preserve the
employee's role and personality, respect the workday {workday_start}-{workday_end},
and keep the listed event order.  Reuse a procedural skill only after the same
workflow has recurred enough times to establish a reusable procedure.  Keep the
response compact and report the major decisions, tool actions, hand-offs, and
   verification outcomes across the horizon.

Employee context:
{_member_context(profile)}

Ordered scheduled events:
{chr(10).join(rows)}
"""


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_event_artifacts(
    member_dir: Path,
    profile: dict[str, Any],
    events: list[dict[str, Any]],
    decisions: list[Any],
    answer: str,
    batch_id: str,
    model_executed: bool,
    workday_start: str,
    workday_end: str,
    agent_profiles: list[dict[str, Any]],
    execution_records: list[dict[str, Any]] | None = None,
    caller_agent_profile: dict[str, Any] | None = None,
) -> None:
    member_id = str(profile.get("id", ""))
    execution_records = execution_records or []
    batch_agents = {
        record["execution_mode"]: record.get("agent_profile", {})
        for record in execution_records
    }
    trajectory_path = member_dir / "trajectory.jsonl"
    with trajectory_path.open("w", encoding="utf-8") as handle:
        for event, decision, agent_profile in zip(events, decisions, agent_profiles):
            audit_context = agent_audit_context(
                caller_agent_profile,
                agent_profile,
                human_principal=member_id,
                execution_mode=decision.execution_mode,
            )
            handle.write(
                json.dumps(
                    {
                        "member_id": member_id,
                        "batch_id": batch_id,
                        "execution_mode": decision.execution_mode,
                        "batch_execution_mode": "horizon_batch",
                        "agent_id": agent_profile.get("agent_id"),
                        "agent_type": agent_profile.get("agent_type"),
                        "agent_owner_id": agent_profile.get("owner_id"),
                        "authority_scope": agent_profile.get("authority_scope"),
                        "memory_scope": agent_profile.get("memory_scope"),
                        **audit_context,
                        "batch_agent_id": batch_agents.get(decision.execution_mode, {}).get("agent_id"),
                        "batch_agent_type": batch_agents.get(decision.execution_mode, {}).get("agent_type"),
                        "batch_authority_scope": batch_agents.get(decision.execution_mode, {}).get("authority_scope"),
                        "batch_memory_scope": batch_agents.get(decision.execution_mode, {}).get("memory_scope"),
                        "model_executed": model_executed and decision.requires_agent,
                        "event": event,
                        "behavior_decision": decision.__dict__,
                        "horizon_answer_file": "horizon_answer.txt" if model_executed else None,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    behavior_rows = []
    schedule_rows = []
    for event, decision, agent_profile in zip(events, decisions, agent_profiles):
        audit_context = agent_audit_context(
            caller_agent_profile,
            agent_profile,
            human_principal=member_id,
            execution_mode=decision.execution_mode,
        )
        behavior_row = {
            "member_id": member_id,
            "week": event["week"],
            "date": event["date"],
            "sim_timestamp": event["time"],
            "activity": event["activity"],
            "category": decision.category,
            "action": decision.action,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "requires_agent": decision.requires_agent,
            "execution_mode": decision.execution_mode,
            "agent_id": agent_profile.get("agent_id"),
            "agent_type": agent_profile.get("agent_type"),
            "agent_owner_id": agent_profile.get("owner_id"),
            **audit_context,
            "batch_id": batch_id,
        }
        behavior_rows.append(behavior_row)
        schedule_rows.append(
            {
                "member_id": member_id,
                "week": event["week"],
                "date": event["date"],
                "index": event["event_index"],
                "sim_timestamp": event["time"],
                "activity": event["activity"],
                "attack": event["attack"],
                "batch_id": batch_id,
            }
        )
    _write_csv(
        member_dir / "behavior_policy.csv",
        BEHAVIOR_POLICY_FIELDS,
        behavior_rows,
    )

    rebuild_agent_behavior_csv(member_dir)
    _write_csv(
        member_dir / "final_schedule.csv",
        [
            "member_id",
            "week",
            "date",
            "index",
            "sim_timestamp",
            "activity",
            "attack",
            "batch_id",
        ],
        schedule_rows,
    )

    logon_rows = []
    seen_days = set()
    for event in events:
        day_key = (event["week"], event["date"])
        if day_key in seen_days:
            continue
        seen_days.add(day_key)
        logon_rows.extend(
            [
                {
                    "member_id": member_id,
                    "week": event["week"],
                    "date": event["date"],
                    "sim_timestamp": workday_start,
                    "status": "login",
                    "batch_id": batch_id,
                },
                {
                    "member_id": member_id,
                    "week": event["week"],
                    "date": event["date"],
                    "sim_timestamp": workday_end,
                    "status": "logout",
                    "batch_id": batch_id,
                },
            ]
        )
    _write_csv(
        member_dir / "logon.csv",
        ["member_id", "week", "date", "sim_timestamp", "status", "batch_id"],
        logon_rows,
    )

    (member_dir / "horizon_answer.txt").write_text(answer or "", encoding="utf-8")


def _run_member(
    profile: dict[str, Any],
    schedule_dir: Path,
    output_dir: Path,
    weeks: int,
    days: tuple[str, ...],
    workday_start: tuple[int, int, int],
    workday_end: tuple[int, int, int],
) -> dict[str, Any]:
    started = time.perf_counter()
    member_id = str(profile.get("id", ""))
    member_dir = output_dir / member_id
    member_dir.mkdir(parents=True, exist_ok=True)
    events = _load_horizon(
        schedule_dir,
        member_id,
        weeks,
        days,
        workday_start,
        workday_end,
    )
    router = BehaviorRouter(config.loaf_rate)
    decisions = [router.route_activity(event["activity"]) for event in events]
    agent_registry = AgentRegistry.load(
        config.agent_registry_path,
        [member_id],
    )
    employee_agent_profile = agent_registry.resolve(
        member_id, "employee_personal", "schedule"
    ).to_dict()
    agent_profiles = [
        (
            agent.to_dict()
            if (agent := agent_registry.resolve(member_id, decision.execution_mode, decision.action))
            else {}
        )
        for decision in decisions
    ]
    complex_events = [event for event, decision in zip(events, decisions) if decision.requires_agent]
    batch_id = f"{member_id}-horizon-{weeks}w"
    answer = ""
    model_executed = bool(complex_events)
    execution_records: list[dict[str, Any]] = []
    status = "completed"
    error = ""

    try:
        if complex_events:
            skill_memory = SkillMemory(
                str(member_dir / "skills"), config.skill_min_recurrence
            )
            skill_observations = []
            retrieved_skill_names = []
            answer_parts = []
            grouped_events: dict[str, list[dict[str, Any]]] = {}
            for event, decision in zip(events, decisions):
                if decision.requires_agent:
                    grouped_events.setdefault(decision.execution_mode, []).append(event)

            for execution_mode, routed_events in grouped_events.items():
                first_event = routed_events[0]
                batch_agent = agent_registry.resolve(
                    member_id,
                    execution_mode,
                    BehaviorRouter().route_activity(first_event["activity"]).action,
                )
                batch_agent_profile = batch_agent.to_dict()
                agent_task_id = f"{batch_id}-{execution_mode}"
                append_agent_audit_event(
                    member_dir,
                    {
                        "event_type": "horizon_batch_started",
                        "member_id": member_id,
                        "batch_id": batch_id,
                        "task_id": agent_task_id,
                        "agent": batch_agent_profile,
                        "execution_mode": execution_mode,
                        "event_count": len(routed_events),
                        "event_indices": [event["event_index"] for event in routed_events],
                        **agent_audit_context(
                            employee_agent_profile,
                            batch_agent_profile,
                            human_principal=member_id,
                            execution_mode=execution_mode,
                        ),
                    },
                )
                task = _horizon_prompt(
                    profile,
                    routed_events,
                    weeks,
                    _format_time(workday_start),
                    _format_time(workday_end),
                )
                retrieved_skills = [
                    skill_memory.retrieve(event["activity"]) for event in routed_events
                ]
                retrieved_skills = [skill for skill in retrieved_skills if skill]
                retrieved_skill_names.extend(
                    skill.get("name") for skill in retrieved_skills if skill.get("name")
                )
                result = run_human_tool_task(
                    task,
                    output_dir=str(member_dir / "workspace" / execution_mode),
                    log_dir=str(member_dir),
                    collaboration_context="\n\n".join(
                        SkillMemory.context(skill) for skill in retrieved_skills
                    ),
                    role_context=_member_context(profile),
                    session_prefix=f"morpheus-scale-{member_id}-w{weeks}-{execution_mode}",
                    agent_profile=batch_agent_profile,
                    execution_mode=execution_mode,
                    human_principal=member_id,
                    delegation_context={
                        "delegation_chain": [
                            employee_agent_profile["agent_id"],
                            batch_agent_profile["agent_id"],
                        ]
                    },
                    caller_agent_profile=employee_agent_profile,
                    task_id=agent_task_id,
                )
                answer_parts.append(f"[{execution_mode}]\n{result.answer}")
                execution_records.append(
                    {
                        "execution_mode": execution_mode,
                        "task_id": agent_task_id,
                        "agent_profile": batch_agent_profile,
                        "semantic_steps": result.semantic_steps,
                        "answer": result.answer,
                        "planner_session_id": result.planner_session_id,
                        "executor_session_id": result.executor_session_id,
                        "status": "completed",
                    }
                )
                skill_records = [
                    skill_memory.record(
                        event["activity"],
                        result.answer,
                        member_id=member_id,
                        event_index=event["event_index"],
                    )
                    for event in routed_events
                ]
                skill_observations.extend(
                    {
                        "event_index": event["event_index"],
                        "skill_name": skill.get("name"),
                        "recurrence_count": skill.get("recurrence_count", 0),
                        "skill_created": skill.get("skill_created", False),
                        "execution_mode": execution_mode,
                    }
                    for event, skill in zip(routed_events, skill_records)
                )
                append_agent_audit_event(
                    member_dir,
                    {
                        "event_type": "horizon_batch_completed",
                        "member_id": member_id,
                        "batch_id": batch_id,
                        "task_id": agent_task_id,
                        "agent": batch_agent_profile,
                        "execution_mode": execution_mode,
                        "semantic_step_count": len(result.semantic_steps),
                        **agent_audit_context(
                            employee_agent_profile,
                            batch_agent_profile,
                            human_principal=member_id,
                            execution_mode=execution_mode,
                        ),
                    },
                )
            answer = "\n\n".join(answer_parts)
            (member_dir / "skill_provenance.json").write_text(
                json.dumps(
                    {
                        "retrieved": bool(retrieved_skill_names),
                        "retrieved_skill_names": retrieved_skill_names,
                        "observations": skill_observations,
                        "batch_id": batch_id,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        _write_event_artifacts(
            member_dir,
            profile,
            events,
            decisions,
            answer,
            batch_id,
            model_executed,
            _format_time(workday_start),
            _format_time(workday_end),
            agent_profiles,
            execution_records,
            employee_agent_profile,
        )
        for event, decision, agent_profile in zip(events, decisions, agent_profiles):
            if agent_profile:
                append_agent_audit_event(
                    member_dir,
                    {
                        "event_type": "event_routed",
                        "member_id": member_id,
                        "batch_id": batch_id,
                        "event_index": event["event_index"],
                        "activity": event["activity"],
                        "agent": agent_profile,
                        "attack_marked": event["attack"],
                        **agent_audit_context(
                            employee_agent_profile,
                            agent_profile,
                            human_principal=member_id,
                            execution_mode=decision.execution_mode,
                        ),
                    },
                )
    except Exception as exc:
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        (member_dir / "error.txt").write_text(error, encoding="utf-8")

    result = {
        "member_id": member_id,
        "name": profile.get("name", ""),
        "status": status,
        "error": error,
        "event_count": len(events),
        "complex_event_count": len(complex_events),
        "model_batches": len(execution_records),
        "batch_id": batch_id,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    (member_dir / "horizon_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a long-horizon employee simulation.")
    parser.add_argument("--profile-dir", default=config.profile_output_dir)
    parser.add_argument("--schedule-dir", default=config.init_schedule_dir)
    parser.add_argument(
        "--output-dir",
        default=str(Path(config.execution_log_dir) / "scale_horizon"),
    )
    parser.add_argument("--weeks", type=int, default=config.period)
    parser.add_argument("--employees", type=int, default=config.employee_number)
    parser.add_argument("--workers", type=int, default=config.scale_worker_count)
    parser.add_argument(
        "--include-weekends",
        action="store_true",
        help="include Saturday and Sunday in addition to configured work days",
    )
    parser.add_argument(
        "--allow-missing-schedules",
        action="store_true",
        help="allow incomplete schedule trees and emit empty days",
    )
    parser.add_argument(
        "--rebuild-agent-csv",
        action="store_true",
        help="rebuild Agent CSVs from existing harness_events.jsonl files",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    profile_dir = Path(args.profile_dir).expanduser().resolve()
    schedule_dir = Path(args.schedule_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if args.rebuild_agent_csv:
        if not output_dir.exists():
            raise SystemExit(f"output directory does not exist: {output_dir}")
        rebuilt = {}
        for member_dir in sorted(path for path in output_dir.iterdir() if path.is_dir()):
            rebuilt[member_dir.name] = rebuild_agent_behavior_csv(member_dir)
        print(
            json.dumps(
                {"output_dir": str(output_dir), "rebuilt": rebuilt},
                ensure_ascii=False,
            )
        )
        return 0
    requested_employees = args.employees if args.employees > 0 else None
    profiles = _load_profiles(profile_dir, requested_employees)
    if not profiles:
        raise SystemExit(f"no employee profiles found in {profile_dir}")
    if requested_employees is not None and len(profiles) < requested_employees:
        raise SystemExit(
            f"requested {requested_employees} employees but found only {len(profiles)} profiles in {profile_dir}"
        )

    days = DAY_ORDER if args.include_weekends else tuple(config.work_days)
    invalid_days = sorted(set(days) - set(DAY_ORDER))
    if invalid_days:
        raise SystemExit(f"invalid work days: {invalid_days}")
    workday_start = _parse_time(config.workday_start)
    workday_end = _parse_time(config.workday_end)
    if workday_start >= workday_end:
        raise SystemExit("workday start must be earlier than workday end")
    if args.workers < 1:
        raise SystemExit("workers must be positive")

    if not args.allow_missing_schedules:
        missing = _missing_schedule_paths(schedule_dir, profiles, args.weeks, days)
        if missing:
            preview = "\n".join(str(path) for path in missing[:5])
            suffix = f"\n... and {len(missing) - 5} more" if len(missing) > 5 else ""
            raise SystemExit(
                f"missing {len(missing)} schedule files under {schedule_dir}. "
                "Generate the complete horizon first or pass --allow-missing-schedules.\n"
                f"{preview}{suffix}"
            )

    if config.scale_isolate_harness_home:
        os.environ.setdefault("MORPHEUS_DSH_ISOLATE_HOME", "1")

    output_dir.mkdir(parents=True, exist_ok=True)
    AgentRegistry.load(
        config.agent_registry_path,
        [str(profile.get("id", "")) for profile in profiles],
    )
    started = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="morpheus-scale") as pool:
        futures = {
            pool.submit(
                _run_member,
                profile,
                schedule_dir,
                output_dir,
                args.weeks,
                days,
                workday_start,
                workday_end,
            ): profile
            for profile in profiles
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(
                f"[{result['status']}] {result['member_id']} "
                f"events={result['event_count']} "
                f"elapsed={result['elapsed_seconds']:.1f}s"
            )

    results.sort(key=lambda item: item["member_id"])
    elapsed = round(time.perf_counter() - started, 3)
    manifest = {
        "execution_mode": "horizon_batch",
        "employee_count": len(profiles),
        "weeks": args.weeks,
        "work_days": list(days),
        "workday_start": _format_time(workday_start),
        "workday_end": _format_time(workday_end),
        "workers": args.workers,
        "elapsed_seconds": elapsed,
        "completed": sum(item["status"] == "completed" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "events": sum(item["event_count"] for item in results),
        "model_batches": sum(item["model_batches"] for item in results),
        "members": results,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: manifest[key] for key in manifest if key != "members"}, ensure_ascii=False))
    return 0 if manifest["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
