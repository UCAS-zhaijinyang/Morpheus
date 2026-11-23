# ========= Copyright (c) 2026 TTFISH. Licensed under the MIT License. =========
# See the LICENSE file in the project root for the full license text.
#
# SPDX-License-Identifier: MIT
# ==============================================================================
from dotenv import load_dotenv

import config
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm
from foundation_model import run_llm
from agent_registry import AgentRegistry, agent_audit_context, append_agent_audit_event
from schedule_constraints import enforce_daily_schedule_limit

env_path = config.env_path
load_dotenv()

days = tuple(config.work_days)


def export_weekly_schedule_to_daily(
    init_schedule_dir: str,
    week_id: int,
    employee_id: str,
    id_role_map: dict,
    profile_list: list,
):
    week_dir = os.path.join(init_schedule_dir, f"week_{week_id}")
    if not os.path.exists(week_dir):
        os.makedirs(week_dir)

    # load the json file
    week_file = os.path.join(
        config.meeting_log_dir, f"meeting_schedule_week_{week_id}.json"
    )
    with open(week_file, "r") as f:
        data = json.load(f)

    for employee in data:
        if employee["id"] == employee_id:
            # load the json file
            weekly_goal = employee["detailed_goals"]

    for member_profile in profile_list:
        if member_profile["id"] == employee_id:
            profile_detail = member_profile
            break

    employee_agent = AgentRegistry.load(
        config.agent_registry_path,
        [employee_id],
        persist=False,
    ).resolve(employee_id, "employee_personal", "schedule")
    employee_agent_profile = employee_agent.to_dict()

    for attempt in range(config.max_attempt):
        # generate the daily plan
        output = generate_daily_plan_with_gpt(
            week_id=week_id,
            profile_detail=profile_detail,
            id_role_map=id_role_map,
            weekly_goal=weekly_goal,
            employee_agent_profile=employee_agent_profile,
        )

        if "```json" in output:
            output = output.replace("```json", "").replace("```", "").strip()

        # check if the output is valid JSON
        try:
            daily_week_schedule = json.loads(output)
            break
        except Exception as e:
            print("[WARN] Error parsing JSON:", e, "Retrying...")
            if attempt == config.max_attempt - 1:
                print("[Error] Max attempts reached. Exiting.")
                print(f"### Errored JSON ### : {output}")
                raise e

    daily_week_schedule = enforce_daily_schedule_limit(
        daily_week_schedule,
        config.daily_schedule_max_entries,
    )

    # save the JSON to init_schedule/

    for day in days:
        if day in daily_week_schedule and daily_week_schedule[day]:
            # save the json to init_schedule/
            day_file = os.path.join(
                week_dir, f"{employee_id}_week_{week_id}_{day}.json"
            )
            with open(day_file, "w") as fd:
                json.dump(daily_week_schedule[day], fd, indent=4)

    append_agent_audit_event(
        week_dir,
        {
            "event_type": "schedule_generated",
            "member_id": employee_id,
            "week": week_id,
            "agent": employee_agent_profile,
            **agent_audit_context(
                employee_agent_profile,
                employee_agent_profile,
                human_principal=employee_id,
                execution_mode="employee_personal",
            ),
            "schedule_entry_point": "employee_agent",
        },
    )


def generate_daily_plan_with_gpt(
    week_id: int,
    profile_detail: dict,
    id_role_map,
    weekly_goal: str,
    employee_agent_profile: dict | None = None,
):
    employee_agent_profile = employee_agent_profile or {
        "agent_id": f"employee-agent-{profile_detail['id']}",
        "agent_type": "employee",
        "owner_id": profile_detail["id"],
    }
    agent_instruction = (
        f"You are the Employee Agent {employee_agent_profile['agent_id']} for this employee. "
        "You are the only entry point that converts the assigned weekly goal into this employee's daily schedule. "
        "Read the goal, apply the employee's role and organizational constraints, and output the schedule. "
        "Do not invoke a Personal Agent or Enterprise Agent while generating the schedule."
    )
    system_prompt = f"""Your name is {profile_detail['name']}. Your personality is {profile_detail['mbti']}, and your age is {profile_detail['age']}.
                You are a {profile_detail['role']} in a {config.company_type}.
                The goal of your company is {config.goal}. \n\n
                I will provide you with your goal plan for this week after you meet with all the members in the company. Divide the work into **3 to 4 principal activity blocks per workday**. Each block may contain multiple related substeps in its Activity text. Do not create a separate schedule entry for every micro-action. \n\n
                There are {config.employee_number} members in your company, and the detailed role distribution can be found as follows: {id_role_map}. \n\n
                You can contact your colleagues if you require external support or data/information from them, or have anything to discuss. Since all contact will be managed through email communication, such activity just needs to specify the people to include in the email with @PEOPLE and then specify the topic.\n\n
                The regular working hours for your company are {config.workday_start} - {config.workday_end} (with lunch time from 12:00-14:00), while you should arrange your work based on your personal preferences and personalities. **You should act based on your characteristics and your own personal preferences to handle your work**.\n\n
                When you are not into working, you can loaf around by browsing websites you are interested in, or doing nothing with yourself. \n\n
                **You should organize your activity timetable into a JSON format for the whole week with the necessary keys including \\\"Time\\\" and \\\"Activity\\\". Every workday should contain at most {config.daily_schedule_max_entries} entries and should target {config.daily_schedule_target_entries} to 4 entries.**\n\n
                The example format for a game company can be found as follows: \n{{\n    \"Monday\": [{{\n      \"Time\": \"{config.workday_start}\",\n      \"Activity\": \"Log in to the OA system, check emails. Install the required dependencies for game development (including git, vim), and implement the code for the login page of the game (e.g., login navigation for users, banner figure, documentation). \"\n    }},\n    {{\n      \"Time\": \"{config.workday_start}\",\n      \"Activity\": \"Meet with @Designer to align on requirements and confirm the UI design for the login page (e.g., banner image selection, location, and the size for the banner), \"\n    }}]\n}}\n\n
                {agent_instruction}\n\n
                The response should be JSON with detailed information inside each Activity field, while keeping the daily entry count compact. **You should only return the JSON file without any other sentences**. \n\n"""
    user_prompt = f"""The detailed goal for the developer for week {week_id} is as follows: {weekly_goal}.\n\n"""

    llm_output = run_llm(system_prompt, user_prompt)
    return llm_output


def _generate_employee_week(args):
    init_schedule_dir, week_id, employee_id, id_role_map, profile_list = args
    export_weekly_schedule_to_daily(
        init_schedule_dir,
        week_id,
        employee_id,
        id_role_map,
        profile_list,
    )
    return week_id, employee_id


if __name__ == "__main__":
    # mkdir of the init_schedule directory
    init_schedule_dir = config.init_schedule_dir
    if not os.path.exists(init_schedule_dir):
        os.makedirs(init_schedule_dir)

    ########################
    # Get the total employee info
    id_role_map = {}
    id_list = []
    profile_list = []

    member_dir = config.profile_output_dir
    for file in os.listdir(member_dir):
        if file.endswith(".jsonc"):
            member_profile_path = os.path.join(member_dir, file)
            with open(member_profile_path, "r") as f:
                member_profile = json.load(f)
            id_role_map[member_profile["id"]] = member_profile[
                "role"
            ]  # add id-role map
            id_list.append(member_profile["id"])
            profile_list.append(member_profile)  # add profile
    ########################

    AgentRegistry.load(
        config.agent_registry_path,
        id_list,
    )

    # for single employee single week
    # week_id = 2
    # employee_id = "cdev-1"
    # export_weekly_schedule_to_daily(init_schedule_dir, week_id, employee_id, id_role_map, profile_list)

    if config.scale_isolate_harness_home:
        os.environ.setdefault("MORPHEUS_DSH_ISOLATE_HOME", "1")
    jobs = [
        (init_schedule_dir, week_id, employee_id, id_role_map, profile_list)
        for week_id in range(1, config.period + 1)
        for employee_id in id_list
    ]
    with ThreadPoolExecutor(
        max_workers=config.scale_worker_count,
        thread_name_prefix="morpheus-plan",
    ) as executor:
        futures = [executor.submit(_generate_employee_week, job) for job in jobs]
        for future in tqdm(
            as_completed(futures), total=len(futures), desc="Generating daily schedules"
        ):
            future.result()

    # post check
    # BASH: for i in init_schedule/*; do ls ${i} | wc -l; done
