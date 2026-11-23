# ========= Copyright (c) 2026 TTFISH. Licensed under the MIT License. =========
# See the LICENSE file in the project root for the full license text.
#
# SPDX-License-Identifier: MIT
# ==============================================================================
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from foundation_model import run_llm

from dotenv import load_dotenv
env_path = config.env_path
load_dotenv()

def summarize_weekly_schedule(meeting_log_dir:str, id_list, id_role_map:dict, week_id:int):
    """
    Summarize the weekly schedule from the meeting minutes.
    """

    mintues_path = os.path.join(meeting_log_dir, "meeting_response.csv")
    json_path = os.path.join(meeting_log_dir, f"meeting_schedule_week_{week_id}.json")

    for attempt in range(config.max_attempt):

        # read the meeting minutes from output/meeting_response.csv
        with open(os.path.join(mintues_path), "r") as f:
            meeting_minutes = f.read()
        
        system_prompt = f"""You are a scheduler for a {config.company_type} of {config.employee_number} employees.
The company has {config.employee_number} employees with detailed role mapping as follows: {id_role_map}

The goal of the company is {config.goal} in {config.period} weeks.
I will provide meeting minutes discussing each employee's goals.
Summarize goals for **week {week_id}** for all {config.employee_number} members.
Return ONLY a JSON array with objects containing keys "week", "id", and "detailed_goals".
Employee ids: {id_list}

Example:
[
  {{"week": 1, "id": "dev-1", "detailed_goals": ["Goal A", "Goal B"]}},
  {{"week": 1, "id": "des-1", "detailed_goals": ["Goal C"]}}
]"""
        # Keep prompt within local model context limits.
        max_minutes_chars = 6000
        if len(meeting_minutes) > max_minutes_chars:
            meeting_minutes = meeting_minutes[:max_minutes_chars] + "\n...[truncated]"
        user_prompt = f"""meeting minutes: {meeting_minutes}"""
        llm_output = run_llm(system_prompt, user_prompt)
        json_str = llm_output

        # remove the prefix "```json" and suffix "```"
        if "```json" in json_str:
            json_str = json_str.replace("```json", "").replace("```", "").strip()

        try:
            data = json.loads(json_str)
            if len(data) != len(id_list):
                print("[WARN] Wrong schedule number for the employees. Retrying...")
                continue
            else:
                break
        except Exception as e:
            print("[WARN] Error parsing JSON:", e, "Retrying...")
            if attempt == config.max_attempt - 1:
                print("[Error] Max attempts reached. Exiting.")
                print(f"### Errored JSON ### : {json_str}")
                raise e

    # save the JSON to output/meeting_schedule.json
    with open(os.path.join(json_path), "w") as f:
        json.dump(data, f, indent=4)


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
