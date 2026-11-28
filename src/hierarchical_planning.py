"""Small, deterministic helpers for the organizational planning harness.

Department heads agree on shared objectives and dependencies. Each department
uses those decisions to assign goals to its members.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from collections import OrderedDict
from typing import Any, Iterable


LEADER_HINTS = (
    "lead",
    "manager",
    "head",
    "director",
    "chief",
    "principal",
    "supervisor",
    "producer",
    "coordinator",
    "负责人",
    "主管",
    "经理",
    "总监",
)


def write_planning_json(path: Path, value: Any) -> None:
    """Publish complete planning artifacts for concurrent schedule readers."""
    handle = NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    temp = Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def _normalise(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def load_role_department_map(company_config_path: str) -> dict[str, str]:
    """Map a generated role abbreviation to its department path.

    Company profiles already contain a nested role tree.  Reading that tree
    avoids adding a new required field to every employee JSONC file.
    """

    if not os.path.exists(company_config_path):
        return {}
    with open(company_config_path, "r", encoding="utf-8") as handle:
        company = json.load(handle)

    role_map: dict[str, str] = {}

    def visit(node: Any, path: list[str]) -> None:
        if isinstance(node, dict):
            roles = node.get("roles")
            if isinstance(roles, list):
                department = " / ".join(
                    part for part in path if part not in {"roles", "core_development_team"}
                ) or "general"
                for role in roles:
                    if isinstance(role, dict) and role.get("abbr"):
                        role_map[str(role["abbr"])] = department
            for key, value in node.items():
                visit(value, path + [str(key)])
        elif isinstance(node, list):
            for value in node:
                visit(value, path)

    visit(company, [])
    return role_map


def _department_for_profile(profile: dict[str, Any], role_map: dict[str, str]) -> str:
    department = _normalise(profile.get("department"))
    if department:
        return department
    member_id = _normalise(profile.get("id"))
    prefix = member_id.split("-", 1)[0]
    if prefix in role_map:
        return role_map[prefix]
    role = _normalise(profile.get("role"))
    return role.split(" ", 1)[0].lower() or "general"


def _leader_rank(member: dict[str, Any]) -> tuple[int, str]:
    role = _normalise(member.get("role")).lower()
    return (0 if any(hint in role for hint in LEADER_HINTS) else 1, member["id"])


def build_hierarchy(
    profiles: Iterable[dict[str, Any]], role_map: dict[str, str] | None = None
) -> dict[str, Any]:
    """Build a stable, JSON-serialisable department/leader/member hierarchy."""

    role_map = role_map or {}
    departments: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for profile in sorted(profiles, key=lambda item: str(item.get("id", ""))):
        member = {
            "id": _normalise(profile.get("id")),
            "name": _normalise(profile.get("name")),
            "role": _normalise(profile.get("role")),
        }
        department = _department_for_profile(profile, role_map)
        departments.setdefault(department, []).append(member)

    result: list[dict[str, Any]] = []
    for name, members in departments.items():
        members = sorted(members, key=_leader_rank)
        leader = members[0]
        result.append(
            {
                "department": name,
                "leader_id": leader["id"],
                "leader_role": leader["role"],
                "members": members,
            }
        )
    return {"departments": result}


def hierarchy_text(hierarchy: dict[str, Any]) -> str:
    lines = []
    for department in hierarchy.get("departments", []):
        members = ", ".join(
            f"{member['id']} ({member['role']})" for member in department["members"]
        )
        lines.append(
            f"{department['department']}: leader={department['leader_id']}; members={members}"
        )
    return "\n".join(lines)


def manager_task_prompt(hierarchy: dict[str, Any], period: int, goal: str) -> str:
    """Prompt for the first, information-sharing stage."""

    return f"""You are the department-head council in a simulated organization.
This is stage 1 of a hierarchical planning harness.  Only department heads
participate here.  Agree on department-level objectives, dependencies,
capacity constraints, and hand-off requirements for the next {period} weeks.
Do not assign individual daily tasks yet.  Return concise directives for every
department so a second-stage department meeting can turn them into member
goals.

Organization:
{hierarchy_text(hierarchy)}

Organization goal: {goal}
"""


def department_task_prompt(
    department: dict[str, Any], manager_result: str, period: int, goal: str
) -> str:
    """Prompt for the second, department-level stage."""

    return f"""You are a department planning meeting in a simulated organization.
The department head has already participated in the head council.  Convert the
directive below into detailed, feasible goals for every listed member for the
next {period} weeks.  Respect role boundaries, dependencies, and the stated
organization goal.  Return the employee identifiers in every assignment so a
downstream scheduler can produce individual daily plans.

Department: {department['department']}
Department head: {department['leader_id']}
Members: {department['members']}

Head-council directives:
{manager_result}

Organization goal: {goal}
"""
