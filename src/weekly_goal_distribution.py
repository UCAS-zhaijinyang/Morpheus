# ========= Copyright (c) 2026 TTFISH. Licensed under the MIT License. =========
# See the LICENSE file in the project root for the full license text.
#
# SPDX-License-Identifier: MIT
# ==============================================================================
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import config
from foundation_model import run_llm
from hierarchical_planning import write_planning_json
from json_utils import parse_llm_json


def _planning_groups(directory, member_ids):
    """Use the most recent meeting's canonical output, including older flat meetings."""
    result = directory / "meeting_result.log"
    if not result.exists():
        result = directory / "hierarchical_meeting_minutes.json"
    if not result.exists():
        result = directory / "meeting_response.csv"
    minutes = result.read_text(encoding="utf-8")
    try:
        bundle = json.loads(minutes)
    except ValueError:
        bundle = None
    if not isinstance(bundle, dict) or "department_meetings" not in bundle:
        return [({"planning_protocol": "all_hands"}, member_ids, minutes)]

    departments = bundle["hierarchy"]["departments"]
    meetings = bundle["department_meetings"]
    groups = []
    roster = []
    names = []
    for dept in departments:
        name = dept["department"]
        members = [person["id"] for person in dept["members"]]
        text = meetings[name]
        if not members or dept["leader_id"] not in members or not isinstance(text, str) or not text.strip():
            raise ValueError(f"Incomplete meeting or roster for department {name}")
        source = {"planning_protocol": bundle["planning_protocol"], "department": name,
                  "department_head": dept["leader_id"]}
        groups.append((source, members, text))
        roster.extend(members)
        names.append(name)
    if sorted(names) != sorted(meetings) or sorted(roster) != sorted(member_ids):
        raise ValueError("Department meetings and rosters must cover each employee exactly once")
    return groups


def _week_goals(minutes, roles, week_id):
    prompt = (f"Extract the assignments for week {week_id} from these meeting minutes. "
              f"The employees in this meeting and their roles are {roles}. "
              "Return a JSON array with exactly one record per listed employee. Each record "
              "has week (the week number), id (employee ID) and detailed_goals (a list of assigned goals). "
              "For a member with no assignments that week, use an empty list. "
              "Preserve the assigned tasks and dependencies for this week.")
    for attempt in range(config.max_attempt):
        reply = run_llm(prompt, minutes)
        try:
            records = parse_llm_json(reply, expect=list)
            goals = {}
            for record in records:
                member = record["id"]
                items = record["detailed_goals"]
                if (str(record["week"]) != str(week_id) or member not in roles or member in goals
                        or not isinstance(items, list)
                        or not all(isinstance(item, str) and item.strip() for item in items)):
                    raise ValueError("wrong week, employee, or goal list")
                goals[member] = items
            if goals.keys() != roles.keys():
                raise ValueError("missing employee goals")
            return goals
        except (TypeError, KeyError, ValueError) as error:
            if attempt + 1 == config.max_attempt:
                raise ValueError(f"Could not extract assignments for week {week_id}, {list(roles)}") from error


def summarize_weekly_schedule(meeting_log_dir: str, id_list, id_role_map: dict, week_id: int):
    """Extract each department's goals from its own meeting before publishing the week."""
    directory = Path(meeting_log_dir)
    if not id_list or len(set(id_list)) != len(id_list):
        raise ValueError("A nonempty roster of unique employee IDs is required")
    result = {}
    for source, members, minutes in _planning_groups(directory, id_list):
        goals = _week_goals(minutes, {member: id_role_map[member] for member in members}, week_id)
        for member in members:
            result[member] = {"week": week_id, "id": member, "detailed_goals": goals[member], **source}
    write_planning_json(directory / f"meeting_schedule_week_{week_id}.json", [result[i] for i in id_list])


def _summarize_week(job):
    meeting_log_dir, id_list, id_role_map, week_id = job
    summarize_weekly_schedule(meeting_log_dir, id_list, id_role_map, week_id)
    return week_id

if __name__ == "__main__":

    ########################
    # Get the total employee info
    all_roles = set()
    id_role_map = {}
    id_list = []

    member_dir = config.profile_output_dir
    for file in os.listdir(member_dir):
        if file.endswith(".jsonc"):
            member_profile_path = os.path.join(member_dir, file)
            with open(member_profile_path, 'r') as f:
                member_profile = json.load(f)
            all_roles.add(member_profile['role']) # add roles
            id_role_map[member_profile['id']] = member_profile['role'] # add id-role map
            id_list.append(member_profile['id'])
    ########################

    if config.scale_isolate_harness_home:
        os.environ.setdefault("MORPHEUS_DSH_ISOLATE_HOME", "1")
    jobs = [
        (config.meeting_log_dir, id_list, id_role_map, week_id)
        for week_id in range(1, config.period + 1)
    ]
    with ThreadPoolExecutor(
        max_workers=config.scale_worker_count,
        thread_name_prefix="morpheus-summary",
    ) as executor:
        futures = [executor.submit(_summarize_week, job) for job in jobs]
        for future in as_completed(futures):
            print(f"### Summarized schedule for week {future.result()} ###")
