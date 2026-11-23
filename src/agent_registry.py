"""Agent identities and auditable delegation metadata for Morpheus."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


_AUDIT_LOCK = threading.Lock()
EMPLOYEE_AGENT_TYPE = "employee"
PERSONAL_AGENT_TYPE = "personal"
ENTERPRISE_AGENT_TYPE = "enterprise"
LEGACY_PERSONAL_AGENT_ID = "personal-agent"


def employee_agent_id(member_id: str) -> str:
    return f"employee-agent-{member_id}"


def personal_agent_id(member_id: str) -> str:
    return f"personal-agent-{member_id}"


_ENTERPRISE_AGENT_SPEC = {
    "agent_id": "enterprise-workflow-agent",
    "name": "Enterprise Workflow Agent",
    "role": "enterprise workflow orchestration",
    "description": "Plans, delegates, executes, and verifies task-scoped enterprise workflows.",
    "capabilities": (
        "plan",
        "handoff",
        "tool_execute",
        "verify",
        "draft_email",
        "retrieve",
        "summarize",
    ),
    "allowed_tools": ("email", "calendar", "repository", "file", "search"),
    "authority_scope": "task-scoped-delegated",
    "memory_scope": "organization-audited",
}


@dataclass(frozen=True)
class AgentProfile:
    """A non-human execution identity used by an employee."""

    agent_id: str
    name: str
    agent_type: str
    owner_id: str | None
    role: str
    department_scope: str
    description: str
    capabilities: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    authority_scope: str
    memory_scope: str
    human_approval_required: bool = True
    version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _tuple_values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _profile_from_dict(raw: dict[str, Any]) -> AgentProfile:
    return AgentProfile(
        agent_id=str(raw.get("agent_id", "")),
        name=str(raw.get("name", raw.get("agent_id", ""))),
        agent_type=str(raw.get("agent_type", "enterprise")),
        owner_id=raw.get("owner_id"),
        role=str(raw.get("role", "agent execution")),
        department_scope=str(raw.get("department_scope", "organization")),
        description=str(raw.get("description", "")),
        capabilities=_tuple_values(raw.get("capabilities")),
        allowed_tools=_tuple_values(raw.get("allowed_tools")),
        authority_scope=str(raw.get("authority_scope", "task-scoped-delegated")),
        memory_scope=str(raw.get("memory_scope", "task-scoped")),
        human_approval_required=bool(raw.get("human_approval_required", True)),
        version=str(raw.get("version", "1.0")),
    )


def default_agent_profiles(member_ids: Iterable[str] = ()) -> list[AgentProfile]:
    """Build per-employee identities and one shared Enterprise Agent."""

    member_ids = tuple(dict.fromkeys(str(member_id) for member_id in member_ids if member_id))
    profiles = []
    for member_id in member_ids:
        profiles.extend(
            [
                AgentProfile(
                    agent_id=employee_agent_id(member_id),
                    name=f"Employee Agent {member_id}",
                    agent_type=EMPLOYEE_AGENT_TYPE,
                    owner_id=member_id,
                    role="employee intent and behavior controller",
                    department_scope="employee-private",
                    description="Reads the employee schedule, routes intent, and records delegated behavior.",
                    capabilities=("schedule_read", "intent_route", "direct_behavior", "delegate"),
                    allowed_tools=("calendar", "email", "file", "search"),
                    authority_scope="employee-principal-scoped",
                    memory_scope="employee-private",
                    human_approval_required=False,
                ),
                AgentProfile(
                    agent_id=personal_agent_id(member_id),
                    name=f"Personal Agent {member_id}",
                    agent_type=PERSONAL_AGENT_TYPE,
                    owner_id=member_id,
                    role="personal browsing assistant",
                    department_scope="employee-private",
                    description="Handles employee-scoped browsing and preference tasks under Employee Agent delegation.",
                    capabilities=("browse", "summarize", "personal_search"),
                    allowed_tools=("search",),
                    authority_scope="employee-principal-scoped",
                    memory_scope="principal-private",
                    human_approval_required=False,
                ),
            ]
        )
    spec = _ENTERPRISE_AGENT_SPEC
    profiles.append(
        AgentProfile(
            agent_id=spec["agent_id"],
            name=spec["name"],
            agent_type=ENTERPRISE_AGENT_TYPE,
            owner_id=None,
            role=spec["role"],
            department_scope="organization",
            description=spec["description"],
            capabilities=tuple(spec["capabilities"]),
            allowed_tools=tuple(spec["allowed_tools"]),
            authority_scope=spec["authority_scope"],
            memory_scope=spec["memory_scope"],
            human_approval_required=True,
        )
    )
    return profiles


def _strip_json_fence(text: str) -> str:
    value = str(text or "").strip()
    for fence in ("```jsonc", "```json", "```"):
        value = value.replace(fence, "")
    return value.strip()


def generate_agent_registry(
    path: str | Path,
    *,
    company_type: str,
    goal: str,
    business_context: Any,
    member_ids: Iterable[str] = (),
    max_attempt: int = 5,
) -> list[dict[str, Any]]:
    """Generate enterprise Agent profiles from the organization definition.

    The prompt follows the employee-profile generation contract.  The model
    supplies domain-specific responsibilities and capabilities, while the
    registry preserves stable IDs, the fixed schema, and safe fallback values.
    """

    import json5

    from foundation_model import run_llm

    member_ids = tuple(dict.fromkeys(str(member_id) for member_id in member_ids if member_id))
    defaults = [
        profile
        for profile in default_agent_profiles()
        if profile.agent_type == ENTERPRISE_AGENT_TYPE
    ]
    business_json = json.dumps(business_context, ensure_ascii=False, indent=2, default=str)
    schema_example = json.dumps(
        {
            "name": "Enterprise Workflow Agent",
            "agent_id": "enterprise-workflow-agent",
            "agent_type": "enterprise",
            "owner_id": None,
            "role": "workflow orchestration",
            "department_scope": "organization",
            "description": "Coordinates a domain-specific enterprise workflow.",
            "capabilities": ["plan", "handoff", "tool_execute", "verify"],
            "allowed_tools": ["calendar", "repository", "file"],
            "authority_scope": "task-scoped-delegated",
            "memory_scope": "organization-audited",
            "human_approval_required": True,
            "version": "1.0",
        },
        ensure_ascii=False,
        indent=2,
    )
    system_prompt = f"""You are a JSON-generator assistant.
Always output valid JSON and nothing else. Do not wrap the output in markdown.

The JSON stores non-human Agent profiles for a simulated enterprise. Generate
exactly one enterprise Agent profile. Its responsibilities, capabilities,
allowed tools, authority scope, and memory scope must reflect the company
domain, organization goal, business processes, and role responsibilities.
The Agent must cover the planning, communication, data, security, knowledge,
or other functions required by this organization.
Do not generate employee credentials, passwords, API keys, or personal data.
The runtime assigns stable agent_id values and requires every field in this schema.

The fixed JSON field schema is:
{schema_example}

Return one JSON object with an `agents` array."""
    user_prompt = f"""Company type:
{company_type}

Company goal:
{goal}

Business and organizational configuration:
{business_json}

Generate the enterprise Agent profiles now. Keep each profile specific to the
business processes above and make the functions materially different."""

    generated_rows: list[dict[str, Any]] = []
    for attempt in range(max(1, max_attempt)):
        try:
            output = _strip_json_fence(run_llm(system_prompt, user_prompt))
            parsed = json5.loads(output)
            rows = parsed.get("agents", []) if isinstance(parsed, dict) else parsed
            if isinstance(rows, list):
                generated_rows = [row for row in rows if isinstance(row, dict)]
            if generated_rows:
                break
        except Exception as error:
            print(f"[WARN] Agent profile generation failed on attempt {attempt + 1}: {error}")

    profiles: list[dict[str, Any]] = []
    fields = (
        "name",
        "role",
        "description",
        "capabilities",
        "allowed_tools",
        "authority_scope",
        "memory_scope",
        "version",
    )
    for index, fallback in enumerate(defaults):
        profile = fallback.to_dict()
        if index < len(generated_rows):
            generated = generated_rows[index]
            for field in fields:
                value = generated.get(field)
                if value not in (None, "", []):
                    profile[field] = value
            profile["capabilities"] = list(_tuple_values(profile["capabilities"]))
            profile["allowed_tools"] = list(_tuple_values(profile["allowed_tools"]))
        profile["agent_id"] = fallback.agent_id
        profile["agent_type"] = "enterprise"
        profile["owner_id"] = None
        profile["department_scope"] = "organization"
        profile["human_approval_required"] = True
        profiles.append(profile)

    generated_member_profiles = [
        profile
        for profile in default_agent_profiles(member_ids)
        if profile.agent_type != ENTERPRISE_AGENT_TYPE
    ]
    profiles.extend(profile.to_dict() for profile in generated_member_profiles)
    registry_path = Path(path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "agents": profiles,
                "generation_context": {
                    "company_type": company_type,
                    "goal": goal,
                    "enterprise_agent_id": "enterprise-workflow-agent",
                    "employee_count": len(member_ids),
                    "source": "employee-profile-style-generation-prompt",
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return profiles


class AgentRegistry:
    """Resolve employee-used Agents and persist the registry for a run."""

    def __init__(self, profiles: Iterable[AgentProfile]):
        self._profiles = {profile.agent_id: profile for profile in profiles}

    @classmethod
    def load(
        cls,
        path: str | Path,
        member_ids: Iterable[str] = (),
        *,
        persist: bool = True,
    ) -> "AgentRegistry":
        registry_path = Path(path)
        registry_existed = registry_path.exists()
        raw_rows: list[dict[str, Any]] = []
        configured: list[AgentProfile] = []
        if registry_existed:
            try:
                raw = json.loads(registry_path.read_text(encoding="utf-8"))
                rows = raw.get("agents", []) if isinstance(raw, dict) else raw
                if isinstance(rows, list):
                    raw_rows = [item for item in rows if isinstance(item, dict)]
                    configured = [
                        _profile_from_dict(item)
                        for item in raw_rows
                        if isinstance(item, dict) and item.get("agent_id")
                    ]
            except (OSError, ValueError):
                configured = []

        member_ids = tuple(dict.fromkeys(str(member_id) for member_id in member_ids if member_id))
        defaults = default_agent_profiles(member_ids)
        default_ids = {profile.agent_id for profile in defaults}
        merged = {profile.agent_id: profile for profile in defaults}
        for profile in configured:
            if profile.agent_id in default_ids:
                merged[profile.agent_id] = profile
            elif not member_ids and profile.agent_type in {
                EMPLOYEE_AGENT_TYPE,
                PERSONAL_AGENT_TYPE,
            }:
                # A caller without a principal may inspect the shared
                # registry. Preserve already-generated member identities
                # instead of shrinking the registry to the enterprise fleet.
                merged[profile.agent_id] = profile
            elif profile.agent_id == LEGACY_PERSONAL_AGENT_ID:
                # Migrate the old shared personal profile to every employee's
                # personal identity while preserving its configurable fields.
                for member_id in member_ids:
                    migrated = profile.to_dict()
                    migrated.update(
                        {
                            "agent_id": personal_agent_id(member_id),
                            "agent_type": PERSONAL_AGENT_TYPE,
                            "owner_id": member_id,
                            "name": f"Personal Agent {member_id}",
                        }
                    )
                    merged[migrated["agent_id"]] = _profile_from_dict(migrated)
        registry = cls(merged.values())
        enterprise_profiles = [
            profile
            for profile in registry._profiles.values()
            if profile.agent_type == "enterprise"
        ]
        personal_profiles = [
            profile
            for profile in registry._profiles.values()
            if profile.agent_type == PERSONAL_AGENT_TYPE
        ]
        employee_profiles = [
            profile
            for profile in registry._profiles.values()
            if profile.agent_type == EMPLOYEE_AGENT_TYPE
        ]
        schema_complete = all(
            {"name", "role", "version"}.issubset(item)
            for item in raw_rows
            if item.get("agent_id")
        )
        needs_persist = (
            not registry_existed
            or not raw_rows
            or len(enterprise_profiles) != 1
            or (
                bool(member_ids)
                and len(personal_profiles) != len(member_ids)
            )
            or (
                bool(member_ids)
                and len(employee_profiles) != len(member_ids)
            )
            or not schema_complete
            or any(
                item.get("agent_id") == LEGACY_PERSONAL_AGENT_ID
                for item in raw_rows
            )
        )
        if persist and needs_persist:
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            registry_path.write_text(
                json.dumps(
                    {"agents": registry.as_dicts()},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        return registry

    def as_dicts(self) -> list[dict[str, Any]]:
        return [
            profile.to_dict()
            for profile in sorted(self._profiles.values(), key=lambda item: item.agent_id)
        ]

    def get(self, agent_id: str) -> AgentProfile:
        if agent_id not in self._profiles:
            raise KeyError(f"unknown Agent identity: {agent_id}")
        return self._profiles[agent_id]

    def resolve(self, member_id: str, execution_mode: str, action: str = "task") -> AgentProfile | None:
        """Resolve an Agent for a routed behavior.

        Every schedule event is owned by an Employee Agent.  Direct actions
        resolve to that identity, while complex work resolves to a per-employee
        Personal Agent or a shared Enterprise Agent.
        """

        if execution_mode == "employee_personal":
            return self.get(employee_agent_id(member_id))
        if execution_mode == "personal_agent":
            return self.get(personal_agent_id(member_id))
        enterprise_profiles = [
            profile
            for profile in self._profiles.values()
            if profile.agent_type == ENTERPRISE_AGENT_TYPE
        ]
        if action == "email":
            for profile in enterprise_profiles:
                if "draft_email" in profile.capabilities:
                    return profile
        if action in {"task", "horizon_batch"}:
            for profile in enterprise_profiles:
                if "plan" in profile.capabilities and "tool_execute" in profile.capabilities:
                    return profile
        if enterprise_profiles:
            return enterprise_profiles[0]
        raise KeyError("no enterprise Agent identity is configured")

    def append_audit_event(self, log_dir: str | Path, event: dict[str, Any]) -> None:
        path = Path(log_dir) / "agent_audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        with _AUDIT_LOCK:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def agent_audit_context(
    caller_profile: AgentProfile | dict[str, Any] | None,
    executor_profile: AgentProfile | dict[str, Any] | None,
    *,
    human_principal: str | None = None,
    execution_mode: str | None = None,
    delegation_chain: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return the common caller/executor fields used by every audit sink."""

    def as_dict(profile: AgentProfile | dict[str, Any] | None) -> dict[str, Any]:
        if profile is None:
            return {}
        if isinstance(profile, AgentProfile):
            return profile.to_dict()
        return dict(profile)

    caller = as_dict(caller_profile)
    executor = as_dict(executor_profile)
    caller_id = caller.get("agent_id")
    executor_id = executor.get("agent_id")
    chain = list(delegation_chain or ())
    if not chain:
        chain = [item for item in (caller_id, executor_id) if item]
        if caller_id and caller_id == executor_id:
            chain = [caller_id]
    return {
        "caller_agent_id": caller_id,
        "caller_agent_type": caller.get("agent_type"),
        "caller_agent_owner_id": caller.get("owner_id"),
        "executor_agent_id": executor_id,
        "executor_agent_type": executor.get("agent_type"),
        "executor_agent_owner_id": executor.get("owner_id"),
        "execution_mode": execution_mode,
        "human_principal": human_principal,
        "delegation_chain": chain,
    }

def append_agent_audit_event(log_dir: str | Path, event: dict[str, Any]) -> None:
    """Append an audit event when a caller does not need registry resolution."""

    path = Path(log_dir) / "agent_audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    with _AUDIT_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
