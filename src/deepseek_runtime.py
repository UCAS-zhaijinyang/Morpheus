"""DeepSeek Harness model calls for Morpheus.

Daily execution uses text-only turns for employee work and simulated Agent
decisions. Business-tool effects live in the simulator. The planning and
legacy task interfaces below also support durable planner/executor sessions.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass, field, fields
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import indent
from typing import Any, Callable

import config
from agent_registry import AgentRegistry, agent_audit_context
from dotenv import load_dotenv
from trajectory_schema import EventEnvelope, append_trajectory_event, new_event

load_dotenv(getattr(config, "env_path", None), override=False)
load_dotenv(override=False)


class HarnessUnavailableError(RuntimeError):
    """Raised when a real DeepSeek Harness runtime has not been installed."""


_EVENT_INDEX_PATTERN = re.compile(
    r"(?i)\[?\s*event[_ -]?index\s*[:= ]\s*(\d+)\s*\]?"
)


@dataclass
class HarnessRun:
    answer: str
    planner_response: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    planner_session_id: str = ""
    executor_session_id: str = ""
    finish_reasons: list[str | None] = field(default_factory=list)
    agent_profile: dict[str, Any] = field(default_factory=dict)
    semantic_steps: list[dict[str, Any]] = field(default_factory=list)


def _stub_enabled() -> bool:
    configured = getattr(config, "harness_stub_mode", False)
    return bool(configured or os.environ.get("MORPHEUS_HARNESS_STUB", "").lower() in {"1", "true", "yes"})


def _runtime_class():
    try:
        from deepseek_harness import DeepSeekHarness
    except (ImportError, AttributeError) as error:
        raise HarnessUnavailableError(
            "DeepSeek Harness SDK is unavailable or incompatible in this Python environment. "
            "Install the pinned SDK with python -m pip install -r requirements.txt."
        ) from error
    return DeepSeekHarness


def _runtime_config() -> dict[str, Any]:
    base_dir = Path(getattr(config, "base_dir", Path.cwd())).resolve()
    default_home = base_dir / ".dsh"
    dsh_home = os.environ.get(
        "MORPHEUS_DSH_HOME",
        os.environ.get(
            "DSH_HOME",
            getattr(config, "deepseek_harness_home", str(default_home)),
        ),
    )
    if os.environ.get("MORPHEUS_DSH_ISOLATE_HOME", "").lower() in {"1", "true", "yes"}:
        dsh_home = str(
            Path(dsh_home).expanduser()
            / f"worker-{os.getpid()}-{threading.get_ident()}"
        )
    provider = os.environ.get(
        "MORPHEUS_DSH_PROVIDER",
        getattr(config, "deepseek_harness_provider", "deepseek-official"),
    )
    configured_profile = getattr(config, "deepseek_harness_profile", "sdk")
    if provider != "deepseek-official" and "MORPHEUS_DSH_PROFILE" not in os.environ:
        configured_profile = "sdk"
    if getattr(config, "offline_mode", False) and "MORPHEUS_DSH_PROFILE" not in os.environ and provider == "deepseek-official":
        configured_profile = "sdk-minimal"
    profile = os.environ.get("MORPHEUS_DSH_PROFILE", configured_profile)
    model = os.environ.get(
        "MORPHEUS_DSH_MODEL",
        getattr(config, "deepseek_harness_model", "deepseek-v4-flash"),
    )
    reasoning_effort = os.environ.get(
        "MORPHEUS_DSH_REASONING_EFFORT",
        getattr(config, "deepseek_harness_reasoning_effort", "") or "",
    )
    environment = {
        key: value
        for key, value in {
            "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY", ""),
            "DEEPSEEK_BASE_URL": os.environ.get("DEEPSEEK_BASE_URL", getattr(config, "deepseek_harness_base_url", "")),
        }.items()
        if value
    }
    if environment.get("DEEPSEEK_BASE_URL"):
        environment["MORPHEUS_GATEWAY_BASE_URL"] = environment["DEEPSEEK_BASE_URL"]
    configured_patches = getattr(config, "deepseek_harness_patches", ())
    patch_text = os.environ.get("MORPHEUS_DSH_PATCHES", "")
    patches = tuple(
        str((base_dir / item).resolve())
        if not Path(item).expanduser().is_absolute()
        else str(Path(item).expanduser())
        for item in configured_patches
    )
    if patch_text:
        patches += tuple(
            str((base_dir / item).resolve())
            if not Path(item).expanduser().is_absolute()
            else str(Path(item).expanduser())
            for item in patch_text.split(os.pathsep)
            if item
        )
    configured_max_tokens = os.environ.get("MORPHEUS_DSH_MAX_TOKENS")
    if configured_max_tokens:
        try:
            max_tokens = int(configured_max_tokens)
        except ValueError:
            max_tokens = getattr(config, "deepseek_harness_max_tokens", 16384)
    else:
        max_tokens = getattr(config, "deepseek_harness_max_tokens", 16384)
    return {
        "dsh_home": str(Path(dsh_home).expanduser().resolve()),
        "profile": profile,
        "model": model,
        "reasoning_effort": reasoning_effort or None,
        "provider": provider,
        "env": environment,
        "max_tokens": max_tokens,
        "patches": patches,
    }


# SDK 0.2.2rc2 defines the tool registry in the profile. These kernel plugins
# support a text turn with an empty registry. No plugin that registers a tool
# or slash command belongs here. The native executor projects the empty list.
_TEXT_PROFILE = "morpheus-text"
_TEXT_SERVICES = (
    "sdk-app", "sdk-jsonrpc-server", "llm", "system-prompt", "tools", "fs-local",
    "tool-executor-native", "session", "session-projection", "working-directory",
    "agent", "agent-loop",
)
_PROVIDER_PACKAGES = {
    "@deepseek-ai/dsh-llm-deepseek-api-key",
    "@deepseek-ai/dsh-llm-pi-ai",
}


def harness_text_backend() -> str:
    """Return the text backend used for dataset provenance."""

    return "deepseek_harness_stub" if _stub_enabled() else "deepseek_harness"


def harness_text_model(model: str | None = None) -> str:
    """Select an explicit model or inherit the configured Harness model."""

    return (model or "").strip() or _runtime_config()["model"]


def harness_text_provenance(model: str | None = None) -> dict[str, Any]:
    """Public model settings for reproducible Agent traces."""
    runtime = _runtime_config()
    return {
        "agent_provider": runtime["provider"],
        "agent_model": (model or "").strip() or runtime["model"],
        "agent_reasoning_effort": runtime["reasoning_effort"],
    }


def _profile_rows(home: Path, profile: str, patches: tuple[str, ...], env: dict[str, str]):
    """Inspect the effective profile without mounting its plugins or evaluating YAML tags."""

    import yaml
    try:
        from deepseek_harness_runtime import resolve_bundled_launch_args
    except (ImportError, AttributeError) as error:
        raise HarnessUnavailableError(
            "DeepSeek Harness runtime is unavailable. Install the SDK's bundled runtime "
            "with python -m pip install -r requirements.txt."
        ) from error

    home.mkdir(parents=True, exist_ok=True)
    command = [*resolve_bundled_launch_args(), "--profile", profile]
    for patch in patches:
        command.extend(("--patch", patch))
    command.append("--dump-config")
    try:
        result = subprocess.run(
            command, cwd=home, env={**os.environ, **env, "DSH_HOME": str(home)},
            capture_output=True, text=True, check=True, timeout=30,
        )
        document = yaml.compose(result.stdout)
    except (OSError, subprocess.SubprocessError, yaml.YAMLError):
        # Dump output can contain provider credentials. Do not put it in run logs.
        raise HarnessUnavailableError(f"Could not inspect Harness profile {profile!r}") from None
    if not isinstance(document, yaml.SequenceNode):
        raise HarnessUnavailableError(f"Harness profile {profile!r} must contain a plugin list")
    for row in document.value:
        if not isinstance(row, yaml.MappingNode):
            raise HarnessUnavailableError(f"Invalid plugin row in Harness profile {profile!r}")
        yield row, {key.value: value for key, value in row.value}


def _write_text_profile(home: Path, runtime: dict[str, Any], system_prompt: str) -> None:
    import yaml

    directory = home / "profiles" / _TEXT_PROFILE
    directory.mkdir(parents=True)
    manifest = {"name": _TEXT_PROFILE, "private": True, "dsh": {"profile": {"bundles": []}}}
    (directory / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    services = {
        name: {"id": name, "name": "@deepseek-ai/dsh-" + name} for name in _TEXT_SERVICES
    }
    services["sdk-jsonrpc-server"]["inject"] = ["sdkAppStartup", "loader"]
    services["system-prompt"]["config"] = {
        "personaPrefix": system_prompt, "includeRuntimeContext": False, "includeHarnessIdentity": False,
    }
    services["agent-loop"]["config"] = {"agents": []}
    # Keep !!js settings used by native provider profiles. Only copy provider
    # configuration and activation, never deployment children or other plugins.
    entries = yaml.compose(yaml.safe_dump(list(services.values())))
    for row, fields in _profile_rows(Path(runtime["dsh_home"]), runtime["profile"],
                                     runtime["patches"], runtime["env"]):
        name = fields.get("name")
        if isinstance(name, yaml.ScalarNode) and name.value in _PROVIDER_PACKAGES:
            settings = [(key, value) for key, value in row.value
                        if key.value in {"id", "name", "config", "disabled"}]
            entries.value.append(yaml.MappingNode(row.tag, settings))
    # Indent the composed entries under a Cordis insert directive.
    patch = "- insert:\n" + indent(yaml.serialize(entries), "    ")
    (directory / "cordis.patch.yml").write_text(patch, encoding="utf-8")


def _assert_text_profile(home: Path, runtime: dict[str, Any]) -> None:
    """Verify the fresh runtime has only the fixed kernel and known providers."""

    import yaml

    kernel = {"@deepseek-ai/dsh-" + name for name in _TEXT_SERVICES}
    names = set()
    for _, fields in _profile_rows(home, _TEXT_PROFILE, (), runtime["env"]):
        name = fields.get("name")
        if (not isinstance(name, yaml.ScalarNode)
                or name.value not in kernel | _PROVIDER_PACKAGES
                or fields.keys() - {"id", "name", "config", "disabled", "inject"}):
            raise HarnessUnavailableError("Unexpected plugin in the Harness text profile")
        names.add(name.value)
    if not kernel.issubset(names) or not names.intersection(_PROVIDER_PACKAGES):
        raise HarnessUnavailableError("Incomplete kernel or missing provider in the Harness text profile")


def run_text_prompt(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    role: str = "assistant",
    stub_response: str | None = None,
) -> str:
    """Run one isolated text-only model turn with the configured Harness provider."""

    if _stub_enabled():
        return stub_response if stub_response is not None else _stub_answer(role, user_prompt)
    runtime = _runtime_config()
    harness_class = _runtime_class()
    with TemporaryDirectory(prefix="morpheus-text-") as directory:
        home = Path(directory)
        # A Harness home may supply model credentials and proxy settings.
        # Preserve the trusted environment layer independently of its plugins.
        source_env = Path(runtime["dsh_home"]) / ".env"
        if source_env.is_file():
            shutil.copyfile(source_env, home / ".env")
        workspace = home / "workspace"
        workspace.mkdir()
        _write_text_profile(home, runtime, system_prompt)
        _assert_text_profile(home, runtime)
        with harness_class(
            dsh_home=str(home), cwd=str(workspace), profile=_TEXT_PROFILE,
            provider=runtime["provider"], model=(model or "").strip() or runtime["model"],
            reasoning_effort=runtime["reasoning_effort"], max_tokens=runtime["max_tokens"],
            env=runtime["env"],
        ) as harness:
            result = harness.run(user_prompt)
    if result.finish_reason != "completed" or not result.final_response.strip():
        raise RuntimeError(f"Harness text turn failed ({result.finish_reason}): {result.final_response}")
    return result.final_response


def _stub_answer(role: str, prompt: str) -> str:
    task = prompt.split("[TASK]", 1)[-1].strip()
    if role == "human_planner":
        return f"Intent: complete the employee workflow.\nPlan:\n1. Inspect the task context.\n2. Execute the required steps.\n3. Verify the result.\nTask: {task}"
    return f"Completed the delegated workflow and recorded the result.\nTask: {task}"


def _append_events(log_dir: str | None, events: list[dict[str, Any]]) -> None:
    if not log_dir or not events:
        return
    path = Path(log_dir) / "harness_events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def _profile_dict(agent_profile: Any) -> dict[str, Any]:
    if agent_profile is None:
        return {}
    if hasattr(agent_profile, "to_dict"):
        return dict(agent_profile.to_dict())
    if isinstance(agent_profile, dict):
        return dict(agent_profile)
    return {}


_CANONICAL_AUDIT_FIELDS = {item.name for item in fields(EventEnvelope)}


def _merge_sidecar_context(
    base: dict[str, Any], extra: dict[str, Any]
) -> dict[str, Any]:
    """Merge optional trajectory metadata without erasing existing values."""

    merged = dict(base)
    for key, value in extra.items():
        if value is None:
            continue
        if key == "metadata" and isinstance(value, dict):
            metadata = dict(merged.get("metadata") or {})
            metadata.update(value)
            merged[key] = metadata
        else:
            merged[key] = value
    return merged


def _legacy_audit_fields(audit_context: dict[str, Any]) -> dict[str, Any]:
    """Keep pre-schema fields while protecting canonical event fields."""

    return {
        key: value
        for key, value in audit_context.items()
        if key not in _CANONICAL_AUDIT_FIELDS and value is not None
    }


def _stable_event_id(
    trace_id: str | None,
    task_id: str | None,
    session_id: str | None,
    kind: str,
    *parts: Any,
) -> str:
    value = "|".join(
        str(item or "") for item in (trace_id, task_id, session_id, kind, *parts)
    )
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"event-{digest}"


def _agent_metadata(
    agent_profile: Any,
    execution_mode: str,
    human_principal: str | None,
    delegation_context: dict[str, Any] | None,
    caller_agent_profile: Any = None,
) -> dict[str, Any]:
    executor = _profile_dict(agent_profile)
    if not executor and execution_mode in {
        "enterprise_agent",
        "horizon_batch",
        "personal_agent",
        "employee_personal",
    }:
        registry = AgentRegistry.load(
            config.agent_registry_path,
            [human_principal] if human_principal else (),
        )
        resolve_mode = (
            "enterprise_agent"
            if execution_mode == "horizon_batch"
            else execution_mode
        )
        resolved = registry.resolve(human_principal or "", resolve_mode, "task")
        executor = resolved.to_dict() if resolved else {}
    caller = _profile_dict(caller_agent_profile)
    if not caller and human_principal:
        registry = AgentRegistry.load(
            config.agent_registry_path,
            [human_principal],
        )
        resolved = registry.resolve(human_principal, "employee_personal", "task")
        caller = resolved.to_dict() if resolved else {}
    context = delegation_context or {}
    metadata = agent_audit_context(
        caller,
        executor,
        human_principal=human_principal,
        execution_mode=execution_mode,
        delegation_chain=context.get("delegation_chain"),
    )
    metadata.update(
        {
            # Keep the original executor fields for downstream readers that
            # consume the pre-caller schema.
            "agent_id": executor.get("agent_id"),
            "agent_type": executor.get("agent_type"),
            "owner_id": executor.get("owner_id"),
            "authority_scope": executor.get("authority_scope"),
        }
    )
    return metadata


def _notification_callback(
    events: list[dict[str, Any]],
    role: str,
    session_id: str,
    audit_context: dict[str, Any] | None = None,
) -> Callable[[Any], None]:
    previous_event_id: str | None = None

    def append_notification(notification: Any) -> None:
        nonlocal previous_event_id
        payload = getattr(notification, "payload", notification)
        event_payload = payload if isinstance(payload, dict) else {}
        harness_event = event_payload.get("event")
        harness_seq = harness_event.get("seq") if isinstance(harness_event, dict) else None
        event_id = _stable_event_id(
            (audit_context or {}).get("trace_id"),
            (audit_context or {}).get("task_id"),
            session_id,
            "harness_notification",
            harness_seq,
            (harness_event or {}).get("type") if isinstance(harness_event, dict) else "",
        )
        record = {
            "event_type": "harness_notification",
            "event_id": event_id,
            "parent_event_id": previous_event_id,
            "role": role,
            "session_id": session_id,
            "payload": payload,
            **_legacy_audit_fields(audit_context or {}),
        }
        # Canonical fields are written explicitly after legacy fields so an
        # old audit key cannot overwrite the sidecar correlation IDs.
        for key, value in (audit_context or {}).items():
            if key in _CANONICAL_AUDIT_FIELDS and key not in {
                "event_id",
                "parent_event_id",
                "recorded_at",
                "session_id",
            } and value is not None:
                record[key] = value
        record["trace_id"] = (audit_context or {}).get("trace_id")
        record["task_id"] = (audit_context or {}).get("task_id")
        record["session_id"] = session_id
        events.append(record)
        previous_event_id = event_id

    return append_notification


def _safe_summary(value: Any, limit: int = 800) -> str:
    """Create a bounded, redacted summary for semantic audit records."""

    if value in (None, ""):
        return ""
    if isinstance(value, str):
        summary = value
    else:
        try:
            summary = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            summary = str(value)
    summary = re.sub(
        r"(?i)(api[_ -]?key|token|password|secret|authorization)\s*[:=]\s*[^,\s}\]]+",
        r"\1=[REDACTED]",
        summary,
    )
    summary = " ".join(summary.split())
    if len(summary) > limit:
        return summary[: limit - 3] + "..."
    return summary


def _event_data(payload: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}, {}
    event = payload.get("event")
    if not isinstance(event, dict):
        return {}, {}
    data = event.get("data")
    return event, data if isinstance(data, dict) else {}


def _extract_event_index(value: Any) -> int | None:
    text = _safe_summary(value, limit=2000)
    explicit_matches = re.findall(r"(?i)\[\s*event[_ -]?index\s*=\s*(\d+)\s*\]", text)
    if explicit_matches:
        return int(explicit_matches[-1])
    matches = _EVENT_INDEX_PATTERN.findall(text)
    return int(matches[-1]) if matches else None


def _semantic_steps(
    events: list[dict[str, Any]],
    *,
    task_id: str,
    audit_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Normalize Harness notifications into one row per semantic Agent step."""

    grouped: dict[tuple[str, Any, Any], dict[str, Any]] = {}
    tool_names: dict[str, str] = {}
    current_event_index: dict[str, int] = {}
    for notification in events:
        event, data = _event_data(notification.get("payload"))
        event_type = event.get("type")
        if event_type not in {
            "step/start",
            "assistant/message",
            "todo/write",
            "tool/call",
            "tool/result",
            "step/end",
        }:
            continue
        session_id = str(notification.get("session_id", ""))
        turn = data.get("turn")
        step_number = data.get("step")
        group_key = (session_id, turn, step_number)
        group = grouped.setdefault(
            group_key,
            {
                "session_id": session_id,
                "agent_role": notification.get("role", ""),
                "source_seqs": [],
                "tool_names": [],
                "inputs": [],
                "observations": [],
                "has_tool_call": False,
                "has_tool_result": False,
                "has_tool": False,
                "has_plan": False,
                "has_message": False,
                "failed": False,
                "ended": False,
                "event_index": None,
            },
        )
        marker_event_index = _extract_event_index(data)
        if marker_event_index is None:
            marker_event_index = _extract_event_index(event)
        if marker_event_index is not None:
            current_event_index[session_id] = marker_event_index
            group["event_index"] = marker_event_index
        elif session_id in current_event_index:
            group["event_index"] = current_event_index[session_id]
        if event.get("seq") is not None:
            group["source_seqs"].append(event.get("seq"))
        if event_type == "tool/call":
            call_id = str(data.get("callId") or "")
            name = str(data.get("name") or "")
            if call_id and name:
                tool_names[call_id] = name
            group["has_tool"] = True
            group["has_tool_call"] = True
            if name:
                group["tool_names"].append(name)
            group["inputs"].append(data.get("arguments") or data.get("label"))
        elif event_type == "tool/result":
            group["has_tool"] = True
            group["has_tool_result"] = True
        tool_call = data.get("toolCall") if isinstance(data.get("toolCall"), dict) else {}
        message = data.get("message") if isinstance(data.get("message"), dict) else {}
        source = message.get("source") if isinstance(message.get("source"), dict) else {}
        call_id = str(
            data.get("callId")
            or tool_call.get("callId")
            or message.get("toolCallId")
            or source.get("callId")
            or ""
        )
        if event_type == "tool/result":
            tool_name = str(
                data.get("name")
                or tool_call.get("name")
                or tool_names.get(call_id, "")
            )
            if tool_name:
                group["tool_names"].append(tool_name)
            observation_value = data.get("detail") or message or data.get("status")
            group["observations"].append(observation_value)
            if message.get("isError") is True or str(data.get("status", "")).lower() in {
                "failed",
                "error",
            }:
                group["failed"] = True
        elif event_type == "assistant/message":
            group["has_message"] = True
            group["observations"].append(message)
        elif event_type == "todo/write":
            group["has_plan"] = True
            group["inputs"].append(data.get("todos"))
        elif event_type == "step/end":
            group["ended"] = True

    steps: list[dict[str, Any]] = []
    parent_event_id: str | None = None
    for (session_id, turn, step_number), group in grouped.items():
        if group["has_tool_call"]:
            semantic_action = "tool_execute"
            trajectory_action = "executor_agent_action"
            phase = "execution"
        elif group["has_plan"]:
            semantic_action = "plan_update"
            trajectory_action = "employee_agent_plan"
            phase = "planning"
        elif group["has_tool_result"]:
            semantic_action = "tool_execute"
            trajectory_action = "tool_result"
            phase = "execution"
        else:
            semantic_action = "agent_decision"
            trajectory_action = (
                "employee_agent_plan"
                if group["agent_role"] == "human_planner"
                else "agent_decision"
            )
            phase = "planning" if group["agent_role"] == "human_planner" else "execution"
        input_summary = _safe_summary(
            " | ".join(_safe_summary(item) for item in group["inputs"] if item)
        )
        observation_summary = _safe_summary(
            " | ".join(_safe_summary(item) for item in group["observations"] if item)
        )
        tool_name = ",".join(dict.fromkeys(group["tool_names"]))
        tool_call = {"summary": input_summary} if group["has_tool_call"] and input_summary else {}
        tool_result = {
            "summary": observation_summary
        } if group["has_tool_result"] and observation_summary else {}
        event_id = _stable_event_id(
            audit_context.get("trace_id"),
            task_id,
            session_id,
            "agent_step",
            turn,
            step_number,
            trajectory_action,
        )
        event = new_event(
            "agent_step",
            audit_context,
            event_id=event_id,
            task_id=task_id,
            parent_event_id=parent_event_id,
            correlation_id=audit_context.get("handoff_id"),
            session_id=session_id,
            operation=semantic_action,
            tool_name=tool_name or None
            if group["has_tool_call"] or group["has_tool_result"]
            else None,
            tool_call=tool_call,
            tool_result=tool_result,
        )
        event.update(
            {
                "record_type": "agent_step",
                "step_id": f"{session_id}:turn-{turn}:step-{step_number}",
                "agent_role": group["agent_role"],
                "phase": phase,
                "semantic_action": semantic_action,
                "trajectory_action": trajectory_action,
                "tool_result_action": (
                    "tool_result" if group["has_tool_result"] else ""
                ),
                "actual_tool_call": group["has_tool_call"],
                "actual_tool_result": group["has_tool_result"],
                "employee_agent_plan": (
                    observation_summary
                    if trajectory_action == "employee_agent_plan"
                    else ""
                ),
                "executor_agent_action": (
                    input_summary
                    if trajectory_action == "executor_agent_action"
                    else ""
                ),
                "input_summary": input_summary,
                "observation_summary": observation_summary,
                "status": "failed" if group["failed"] else ("completed" if group["ended"] else "observed"),
                "source_event_type": "harness_step",
                "source_seq": group["source_seqs"][0] if group["source_seqs"] else None,
                "source_time": None,
                "event_index": group.get("event_index"),
            }
        )
        steps.append(event)
        parent_event_id = event["event_id"]
    return steps


def _completion_step(
    *,
    task_id: str,
    session_id: str,
    agent_role: str,
    semantic_action: str,
    summary: str,
    audit_context: dict[str, Any],
    parent_event_id: str | None = None,
) -> dict[str, Any]:
    trajectory_action = (
        "employee_agent_plan"
        if agent_role == "human_planner"
        else "execution_summary"
    )
    event = new_event(
        "agent_step",
        audit_context,
        event_id=_stable_event_id(
            audit_context.get("trace_id"),
            task_id,
            session_id,
            "session_completed",
            semantic_action,
        ),
        parent_event_id=parent_event_id,
        task_id=task_id,
        session_id=session_id,
        operation=semantic_action,
        tool_call={},
        # A model summary is intentionally kept out of tool_result.  Only a
        # concrete Harness tool/result notification can populate that field.
        tool_result={},
        metadata={"summary": _safe_summary(summary)},
    )
    event.update(
        {
            "record_type": "agent_step",
            "step_id": f"{session_id}:completed",
            "agent_role": agent_role,
            "phase": "completion",
            "semantic_action": semantic_action,
            "trajectory_action": trajectory_action,
            "actual_tool_call": False,
            "actual_tool_result": False,
            "tool_name": "",
            "input_summary": "",
            "observation_summary": _safe_summary(summary),
            "employee_agent_plan": (
                _safe_summary(summary)
                if trajectory_action == "employee_agent_plan"
                else ""
            ),
            "executor_agent_action": "",
            "status": "completed",
            "session_id": session_id,
            "source_event_type": "session_completed",
            "source_seq": None,
            "source_time": None,
        }
    )
    return event


def _run_session(
    harness: Any,
    prompt: str,
    role: str,
    session_id: str,
    events: list[dict[str, Any]],
    audit_context: dict[str, Any] | None = None,
) -> tuple[str, str | None]:
    result = harness.run(
        prompt,
        session_id=session_id,
        on_notification=_notification_callback(events, role, session_id, audit_context),
    )
    return result.final_response, result.finish_reason


def run_prompt(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0,
    role: str = "assistant",
    log_dir: str | None = None,
    session_id: str | None = None,
) -> str:
    """Run one model prompt through the Harness runtime.

    ``temperature`` remains in the public signature for compatibility with
    the existing structured-generation callers.  Sampling is controlled by
    the selected Harness provider and the prompt carries the requested mode.
    """

    prompt = (
        f"[MORPHEUS ROLE]\n{role}\n"
        f"[SAMPLING MODE]\n{temperature}\n"
        f"[SYSTEM]\n{system_prompt}\n"
        f"[USER]\n{user_prompt}"
    )
    if _stub_enabled():
        answer = _stub_answer(role, prompt)
        _append_events(log_dir, [{"event_type": "harness_stub", "role": role, "answer": answer}])
        return answer

    DeepSeekHarness = _runtime_class()
    runtime = _runtime_config()
    runtime_cwd = (
        Path(log_dir).resolve()
        if log_dir
        else Path(runtime["dsh_home"]) / "structured_workspace"
    )
    runtime_cwd.mkdir(parents=True, exist_ok=True)
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
    events: list[dict[str, Any]] = []
    effective_session = session_id or f"morpheus-{role}-{uuid.uuid4().hex}"
    with DeepSeekHarness(
        dsh_home=runtime["dsh_home"],
        cwd=str(runtime_cwd),
        profile=runtime["profile"],
        patches=runtime["patches"],
        provider=runtime["provider"],
        model=runtime["model"],
        reasoning_effort=runtime["reasoning_effort"],
        max_tokens=runtime["max_tokens"],
        env=runtime["env"],
    ) as harness:
        answer, finish_reason = _run_session(harness, prompt, role, effective_session, events)
    _append_events(
        log_dir,
        events + [{"event_type": "harness_turn", "role": role, "session_id": effective_session, "finish_reason": finish_reason}],
    )
    return answer


def run_human_tool_task(
    task: str,
    *,
    output_dir: str,
    log_dir: str | None = None,
    collaboration_context: str = "",
    role_context: str = "",
    temperature: float = 0,
    session_prefix: str = "morpheus-task",
    agent_profile: dict[str, Any] | Any | None = None,
    execution_mode: str = "enterprise_agent",
    human_principal: str | None = None,
    delegation_context: dict[str, Any] | None = None,
    caller_agent_profile: dict[str, Any] | Any | None = None,
    task_id: str | None = None,
    trajectory_context: dict[str, Any] | None = None,
) -> HarnessRun:
    """Run the employee planner-to-tool-agent hand-off."""

    profile = _profile_dict(agent_profile)
    base_audit_context = _agent_metadata(
        profile,
        execution_mode,
        human_principal,
        delegation_context,
        caller_agent_profile,
    )
    effective_task_id = task_id or session_prefix
    trajectory_context = dict(trajectory_context or {})
    trajectory_context.setdefault("trace_id", f"trace-{uuid.uuid4().hex}")
    trajectory_context.setdefault("runtime_id", f"runtime-{uuid.uuid4().hex}")
    trajectory_context.setdefault("handoff_id", f"handoff-{uuid.uuid4().hex}")
    trajectory_context.setdefault("task_purpose", task)
    trajectory_context.setdefault("purpose", trajectory_context["task_purpose"])
    trajectory_context.setdefault("human_principal", human_principal)
    trajectory_context.setdefault("task_id", effective_task_id)
    audit_context = _merge_sidecar_context(base_audit_context, trajectory_context)
    agent_context = json.dumps(
        {
            **base_audit_context,
            "capabilities": profile.get("capabilities", []),
            "allowed_tools": profile.get("allowed_tools", []),
        },
        ensure_ascii=False,
    )

    collaboration = f"Collaboration context:\n{collaboration_context}\n\n" if collaboration_context else ""
    planner_prompt = f"""[MORPHEUS HUMAN-AGENT HAND-OFF]
You are the simulated employee's human-planner role. Own the employee's
intent, priorities, authority boundaries, and organizational constraints.
Produce a concise executable plan for the delegated tool-agent. Do not claim
that a tool was used and do not invent observations.

Employee context:
{role_context}

{collaboration}Agent execution context:
{agent_context}

[TASK]
{task}
"""
    if _stub_enabled():
        planner = _stub_answer("human_planner", planner_prompt)
        executor = _stub_answer("tool_agent", f"[TASK]\n{task}\n[PLAN]\n{planner}")
        planner_session = f"{session_prefix}-planner-stub"
        executor_session = f"{session_prefix}-executor-stub"
        semantic_steps = [
            _completion_step(
                task_id=effective_task_id,
                session_id=planner_session,
                agent_role="human_planner",
                semantic_action="plan_created",
                summary=planner,
                audit_context=audit_context,
            ),
            _completion_step(
                task_id=effective_task_id,
                session_id=executor_session,
                agent_role="tool_agent",
                semantic_action="execution_verified",
                summary=executor,
                audit_context=audit_context,
                parent_event_id=None,
            ),
        ]
        semantic_steps[1]["parent_event_id"] = semantic_steps[0]["event_id"]
        stub_handoff_event = {
            **new_event(
                "human_agent_handoff",
                audit_context,
                event_id=_stable_event_id(
                    audit_context.get("trace_id"),
                    effective_task_id,
                    audit_context.get("handoff_id"),
                    "human_agent_handoff",
                ),
                parent_event_id=semantic_steps[-1]["event_id"],
                task_id=effective_task_id,
                correlation_id=audit_context.get("handoff_id"),
                metadata={"task": task, "mode": "stub"},
            ),
            **_legacy_audit_fields(audit_context),
            "task": task,
            "planner_session_id": planner_session,
            "executor_session_id": executor_session,
            "planner_finish_reason": "completed",
            "executor_finish_reason": "completed",
        }
        _append_events(
            log_dir,
            [
                {
                    **new_event(
                        "harness_stub",
                        audit_context,
                        event_id=_stable_event_id(
                            audit_context.get("trace_id"),
                            effective_task_id,
                            planner_session,
                            "harness_stub",
                            "human_planner",
                        ),
                        session_id=planner_session,
                        task_id=effective_task_id,
                        metadata={"role": "human_planner"},
                    ),
                    **_legacy_audit_fields(audit_context),
                },
                {
                    **new_event(
                        "harness_stub",
                        audit_context,
                        event_id=_stable_event_id(
                            audit_context.get("trace_id"),
                            effective_task_id,
                            executor_session,
                            "harness_stub",
                            "tool_agent",
                        ),
                        session_id=executor_session,
                        task_id=effective_task_id,
                        metadata={"role": "tool_agent"},
                    ),
                    **_legacy_audit_fields(audit_context),
                },
                stub_handoff_event,
                *semantic_steps,
            ],
        )
        if log_dir:
            for event in [*semantic_steps, stub_handoff_event]:
                append_trajectory_event(log_dir, event)
        return HarnessRun(
            answer=executor,
            planner_response=planner,
            planner_session_id=planner_session,
            executor_session_id=executor_session,
            finish_reasons=["completed", "completed"],
            agent_profile=profile,
            semantic_steps=semantic_steps,
        )

    DeepSeekHarness = _runtime_class()
    runtime = _runtime_config()
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
    events: list[dict[str, Any]] = []
    planner_session = f"{session_prefix}-planner-{uuid.uuid4().hex}"
    executor_session = f"{session_prefix}-executor-{uuid.uuid4().hex}"
    with DeepSeekHarness(
        dsh_home=runtime["dsh_home"],
        cwd=str(Path(output_dir).resolve()),
        profile=runtime["profile"],
        patches=runtime["patches"],
        provider=runtime["provider"],
        model=runtime["model"],
        reasoning_effort=runtime["reasoning_effort"],
        max_tokens=runtime["max_tokens"],
        env=runtime["env"],
    ) as harness:
        planner_response, planner_reason = _run_session(
            harness,
            planner_prompt,
            "human_planner",
            planner_session,
            events,
            audit_context,
        )
        executor_prompt = f"""[MORPHEUS TOOL-AGENT EXECUTION]
You are the employee's tool-agent. Execute the human-planner's hand-off in
the current Harness workspace. Use available tools when the task requires
them. Respect the employee's role, organizational authority, and data
boundaries. Report only actions that were actually performed and observations
that were actually obtained.

Employee context:
{role_context}

Human-planner hand-off:
{planner_response}

{collaboration}Agent execution context:
{agent_context}

[TASK]
{task}
"""
        answer, executor_reason = _run_session(
            harness,
            executor_prompt,
            "tool_agent",
            executor_session,
            events,
            audit_context,
        )
    semantic_steps = _semantic_steps(
        events,
        task_id=effective_task_id,
        audit_context=audit_context,
    )
    planner_completion = _completion_step(
        task_id=effective_task_id,
        session_id=planner_session,
        agent_role="human_planner",
        semantic_action="plan_completed",
        summary=planner_response,
        audit_context=audit_context,
        parent_event_id=semantic_steps[-1]["event_id"] if semantic_steps else None,
    )
    executor_completion = _completion_step(
        task_id=effective_task_id,
        session_id=executor_session,
        agent_role="tool_agent",
        semantic_action="execution_verified",
        summary=answer,
        audit_context=audit_context,
        parent_event_id=planner_completion["event_id"],
    )
    semantic_steps.extend([planner_completion, executor_completion])
    handoff_event = {
        **new_event(
            "human_agent_handoff",
            audit_context,
            event_id=_stable_event_id(
                audit_context.get("trace_id"),
                effective_task_id,
                audit_context.get("handoff_id"),
                "human_agent_handoff",
            ),
            parent_event_id=semantic_steps[-1]["event_id"] if semantic_steps else None,
            task_id=effective_task_id,
            correlation_id=audit_context.get("handoff_id"),
            metadata={
                "task": task,
                "planner_finish_reason": planner_reason,
                "executor_finish_reason": executor_reason,
                "output_dir": str(Path(output_dir).resolve()),
            },
        ),
        **_legacy_audit_fields(audit_context),
        "task": task,
        "planner_session_id": planner_session,
        "executor_session_id": executor_session,
        "planner_finish_reason": planner_reason,
        "executor_finish_reason": executor_reason,
        "output_dir": str(Path(output_dir).resolve()),
    }
    _append_events(
        log_dir,
        events + semantic_steps + [handoff_event],
    )
    if log_dir:
        for event in semantic_steps + [handoff_event]:
            append_trajectory_event(log_dir, event)
    return HarnessRun(
        answer=answer,
        planner_response=planner_response,
        events=events,
        planner_session_id=planner_session,
        executor_session_id=executor_session,
        finish_reasons=[planner_reason, executor_reason],
        agent_profile=profile,
        semantic_steps=semantic_steps,
    )
