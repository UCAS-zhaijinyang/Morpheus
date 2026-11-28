"""Hierarchical organization planning on top of DeepSeek Harness."""

from __future__ import annotations

import csv
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import config
from deepseek_runtime import run_human_tool_task
from hierarchical_planning import (
    build_hierarchy,
    department_task_prompt,
    load_role_department_map,
    manager_task_prompt,
    write_planning_json,
)


def _load_profiles(member_dir: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    profiles: list[dict[str, Any]] = []
    profile_by_id: dict[str, dict[str, Any]] = {}
    for filename in sorted(os.listdir(member_dir)):
        if not filename.endswith(".jsonc"):
            continue
        with open(os.path.join(member_dir, filename), "r", encoding="utf-8") as handle:
            profile = json.load(handle)
        profiles.append(profile)
        profile_by_id[profile["id"]] = profile
    return profiles, profile_by_id


def _participant_context(member_ids: list[str], profile_by_id: dict[str, dict[str, Any]]) -> str:
    rows = []
    for member_id in member_ids:
        profile = profile_by_id[member_id]
        rows.append(
            " | ".join(
                [
                    f"id={profile.get('id', member_id)}",
                    f"name={profile.get('name', '')}",
                    f"role={profile.get('role', '')}",
                    f"responsibilities={profile.get('description', '')}",
                ]
            )
        )
    return "\n".join(rows)


def _run_meeting_stage(
    prompt: str,
    *,
    participants: str,
    log_dir: str,
    stage_name: str,
) -> str:
    stage_dir = os.path.join(log_dir, stage_name)
    os.makedirs(stage_dir, exist_ok=True)
    result = run_human_tool_task(
        prompt,
        output_dir=stage_dir,
        log_dir=stage_dir,
        role_context=participants,
        session_prefix=f"morpheus-meeting-{stage_name}",
    )
    with open(
        os.path.join(stage_dir, f"{stage_name}_meeting_detailed_actions.log"),
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write("[human_planner]\n")
        handle.write(result.planner_response)
        handle.write("\n\n[tool_agent]\n")
        handle.write(result.answer)
        handle.write("\n")
    return result.answer


def _run_department_stage(job):
    department, council_result, period, goal, profile_by_id, log_dir, index = job
    member_ids = [member["id"] for member in department["members"]]
    result = _run_meeting_stage(
        department_task_prompt(department, council_result, period, goal),
        participants=_participant_context(member_ids, profile_by_id),
        log_dir=log_dir,
        stage_name=f"department_{index}",
    )
    return department["department"], result


def run_hierarchical_weekly_plan(
    member_dir: str,
    process_task_logging=None,
    load_member_profile=None,
):
    """Run the department-head stage followed by department-level meetings.

    The optional callback parameters remain accepted for callers from the old
    entry point.  Stage execution is owned by DeepSeek Harness so all meeting
    and task trajectories share the same runtime and event format.
    """

    del process_task_logging, load_member_profile
    profiles, profile_by_id = _load_profiles(member_dir)
    hierarchy = build_hierarchy(
        profiles,
        load_role_department_map(config.company_config_path),
    )
    log_dir = config.meeting_log_dir
    os.makedirs(log_dir, exist_ok=True)

    leader_ids = [item["leader_id"] for item in hierarchy.get("departments", [])]
    council_result = _run_meeting_stage(
        manager_task_prompt(hierarchy, config.period, config.goal),
        participants=_participant_context(leader_ids, profile_by_id),
        log_dir=log_dir,
        stage_name="head_council",
    )

    department_results: dict[str, str] = {}
    jobs = [
        (
            department,
            council_result,
            config.period,
            config.goal,
            profile_by_id,
            log_dir,
            index,
        )
        for index, department in enumerate(hierarchy.get("departments", []), start=1)
    ]
    with ThreadPoolExecutor(
        max_workers=config.scale_worker_count,
        thread_name_prefix="morpheus-department",
    ) as executor:
        futures = [executor.submit(_run_department_stage, job) for job in jobs]
        for future in as_completed(futures):
            department, result = future.result()
            department_results[department] = result

    bundle = {
        "planning_protocol": "department_head_council_then_department_meetings",
        "harness": "deepseek-harness",
        "hierarchy": hierarchy,
        "head_council": council_result,
        "department_meetings": department_results,
    }
    with open(os.path.join(log_dir, "hierarchy.json"), "w", encoding="utf-8") as handle:
        json.dump(hierarchy, handle, indent=2, ensure_ascii=False)
    with open(os.path.join(log_dir, "hierarchical_meeting_minutes.json"), "w", encoding="utf-8") as handle:
        json.dump(bundle, handle, indent=2, ensure_ascii=False)
    with open(os.path.join(log_dir, "meeting_response.csv"), "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["stage", "department", "minutes"])
        writer.writerow(["head_council", "all_departments", council_result])
        for department, result in department_results.items():
            writer.writerow(["department_meeting", department, result])
    write_planning_json(Path(log_dir) / "meeting_result.log", bundle)
    return bundle
