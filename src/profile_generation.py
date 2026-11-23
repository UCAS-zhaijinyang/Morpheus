# ========= Copyright (c) 2026 TTFISH. Licensed under the MIT License. =========
# See the LICENSE file in the project root for the full license text.
#
# SPDX-License-Identifier: MIT
# ==============================================================================
from dotenv import load_dotenv

import json5
import json
import config
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import tqdm

from foundation_model import run_llm
from agent_registry import generate_agent_registry

env_path = config.env_path
load_dotenv()


def get_member_profile(role, id, ip, existing_profiles):
    for attempt in range(config.max_attempt):
        system_prompt = f"""You are a JSONC-generator assistant.
                                Always output valid JSON with comments (JSONC) and nothing else.
                                Do not wrap your output in markdown or plain-text descriptions.\n\n
                                The jsonc config is used for storing personal information for a large {config.company_type}.
                                The goal of your company is {config.goal}.
                                Each employee should have their individual personalities and characteristics.
                                I will provide you with the role of the employee for the company and you will help me generate the jsonc file for this member of the company.\n\n
                                The exampled jsonc file for one developer in a game company is as follows:\n```jsonc\n{{\n    \"name\": \"Sophie Kim\",\n    \"id\": \"des-1\",\n    \"ip\": \"10.0.0.88\",\n    \"age\": 30,\n    // professional\n    \"role\": \"Designer\",\n    \"description\": \"In charge of the design and shaping the core player experience with UI designs, including gameplay mechanics, level design, and the overall creative vision. provides guidance on visual and UX elements, providing art files.\",\n    // personality\n    \"mbti\": \"INFJ\",\n    \"interests\": \"computer games (CSGo), fishing\",\n    \"personality\": \"Get up late and stay at the corp later than others. Like to work alone\",\n    // company configuration\n    \"application\": {{\n        \"Zendo\": {{\n            \"account_name\": \"des-448291\",\n            \"password\": \"sophieK@design\",\n            \"permissions\": \"designer\"\n        }}\n    }},\n    \"email\": \"des-448291@corp.com\",\n    \"container_id\": \"497e76a108b1\"\n}}\n```"""
        user_prompt = f"""Now, please generate one profile config for: one {role}. Try using different names and personalities for each profile. Existing profiles are: {existing_profiles}.\n\n"""
        llm_output = run_llm(system_prompt, user_prompt)
        output = llm_output

        if "```jsonc" in output:
            output = output.replace("```jsonc", "").replace("```", "").strip()

        try:
            employee_list = json5.loads(output)
            break
        except Exception as e:
            print("[WARN] Error parsing JSONC:", e, "Retrying...")
            if attempt == config.max_attempt - 1:
                print(
                    f"[Error] Max attempts reached. The profile generation for {id} failed."
                )

    # update id and ip
    employee_list["id"] = id
    employee_list["ip"] = f"10.0.0.{ip}"

    return employee_list


def extract_roles(data):
    roles = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "roles" and isinstance(value, list):
                roles.extend(value)
            else:
                roles.extend(extract_roles(value))
    elif isinstance(data, list):
        for item in data:
            roles.extend(extract_roles(item))
    return roles


def _generate_profile(job):
    role, member_id, ip, existing_profiles = job
    return member_id, get_member_profile(role, member_id, ip, existing_profiles)


def _write_profile(member_id: str, profile: dict) -> None:
    with open(f"{config.profile_output_dir}/{member_id}.jsonc", "w") as handle:
        json.dump(profile, handle, indent=4)


if __name__ == "__main__":
    ip_start = 10
    existing_profiles = []

    # load the company config
    with open(config.company_config_path, "r") as f:
        company_config = json.load(f)

    # create the profile output directory
    if not os.path.exists(config.profile_output_dir):
        os.makedirs(config.profile_output_dir)

    # for each roles:
    all_roles = extract_roles(company_config)

    if config.scale_isolate_harness_home:
        os.environ.setdefault("MORPHEUS_DSH_ISOLATE_HOME", "1")

    jobs = []
    for role in all_roles:
        for i in range(role["count"]):
            jobs.append((role["role_name"], f"{role['abbr']}-{i + 1}", ip_start))
            ip_start += 1

    # Keep parallelism for throughput while refreshing the context between
    # batches.  A single snapshot for all workers makes every profile see the
    # same empty company and often produces repeated names and personalities.
    batch_size = max(1, config.scale_worker_count)
    with ThreadPoolExecutor(
        max_workers=config.scale_worker_count,
        thread_name_prefix="morpheus-profile",
    ) as executor:
        for start in range(0, len(jobs), batch_size):
            batch = jobs[start : start + batch_size]
            context = list(existing_profiles)
            batch_jobs = [(*job, context) for job in batch]
            futures = [executor.submit(_generate_profile, job) for job in batch_jobs]
            for future in tqdm.tqdm(
                as_completed(futures), total=len(futures), desc="Generating profiles"
            ):
                member_id, member_profile = future.result()
                existing_profiles.append(member_profile)
                _write_profile(member_id, member_profile)

    generate_agent_registry(
        config.agent_registry_path,
        company_type=config.company_type,
        goal=config.goal,
        business_context=company_config,
        member_ids=[profile["id"] for profile in existing_profiles],
        max_attempt=config.max_attempt,
    )
