"""Canonical, JSON-serializable events for Morpheus trajectories.

The simulator has several existing audit sinks.  ``TrajectoryContext`` carries
the stable causal metadata shared by those sinks, while ``EventEnvelope``
records one observable transition.  The schema is deliberately permissive so
existing schedule and Harness records can be migrated incrementally without
discarding their original fields.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any, Mapping, Sequence
import uuid


_TRAJECTORY_LOCK = threading.Lock()


def _identifier(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _sequence(value: Sequence[Any] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _json_value(value: Any) -> Any:
    """Convert nested dataclass values and tuples into JSON-safe values."""

    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return value


@dataclass
class TrajectoryContext:
    """Causal metadata shared by events belonging to one task trace."""

    trace_id: str = field(default_factory=lambda: _identifier("trace"))
    scenario_id: str | None = None
    attack_id: str | None = None
    attack_stage: str | int | None = None
    threat_phase: str | None = None
    organization_id: str | None = None
    project_id: str | None = None
    department: str | None = None
    department_head: str | None = None
    planning_protocol: str | None = None
    purpose: str | None = None
    task_purpose: str | None = None
    intent_id: str = field(default_factory=lambda: _identifier("intent"))
    human_principal: str | None = None
    human_intent: dict[str, Any] = field(default_factory=dict)
    agent_intent: dict[str, Any] = field(default_factory=dict)
    initiator_agent_id: str | None = None
    caller_agent_id: str | None = None
    executor_agent_id: str | None = None
    runtime_id: str | None = None
    session_id: str | None = None
    handoff_id: str | None = None
    execution_mode: str | None = None
    delegation_scope: dict[str, Any] = field(default_factory=dict)
    approval_scope: dict[str, Any] = field(default_factory=dict)
    approval_id: str | None = None
    approval_expiry: str | None = None
    source_ids: list[str] = field(default_factory=list)
    resource_ids: list[str] = field(default_factory=list)
    recipient: list[str] = field(default_factory=list)
    source_provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source_ids = _sequence(self.source_ids)
        self.resource_ids = _sequence(self.resource_ids)
        self.recipient = _sequence(self.recipient)
        self.human_intent = dict(self.human_intent or {})
        self.agent_intent = dict(self.agent_intent or {})
        self.delegation_scope = dict(self.delegation_scope or {})
        self.approval_scope = dict(self.approval_scope or {})
        self.source_provenance = dict(self.source_provenance or {})
        self.metadata = dict(self.metadata or {})

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "TrajectoryContext":
        """Build a context from an existing audit record."""

        if not value:
            return cls()
        fields = {field_name for field_name in cls.__dataclass_fields__}
        return cls(**{key: value[key] for key in fields if key in value})

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass
class EventEnvelope:
    """One observable event in a provenance-bearing trajectory."""

    event_type: str
    trace_id: str
    event_id: str = field(default_factory=lambda: _identifier("event"))
    parent_event_id: str | None = None
    correlation_id: str | None = None
    task_id: str | None = None
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    scenario_id: str | None = None
    attack_id: str | None = None
    attack_stage: str | int | None = None
    threat_phase: str | None = None
    label: str | None = None

    organization_id: str | None = None
    project_id: str | None = None
    department: str | None = None
    department_head: str | None = None
    planning_protocol: str | None = None
    purpose: str | None = None
    task_purpose: str | None = None
    intent_id: str | None = None

    human_principal: str | None = None
    human_intent: dict[str, Any] = field(default_factory=dict)
    agent_intent: dict[str, Any] = field(default_factory=dict)
    initiator_agent_id: str | None = None
    caller_agent_id: str | None = None
    executor_agent_id: str | None = None
    runtime_id: str | None = None
    session_id: str | None = None
    handoff_id: str | None = None
    execution_mode: str | None = None

    delegation_scope: dict[str, Any] = field(default_factory=dict)
    approval_scope: dict[str, Any] = field(default_factory=dict)
    approval_id: str | None = None
    approval_expiry: str | None = None
    source_ids: list[str] = field(default_factory=list)
    resource_ids: list[str] = field(default_factory=list)
    operation: str | None = None
    recipient: list[str] = field(default_factory=list)
    source_provenance: dict[str, Any] = field(default_factory=dict)

    tool_name: str | None = None
    tool_call: dict[str, Any] = field(default_factory=dict)
    tool_result: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source_ids = _sequence(self.source_ids)
        self.resource_ids = _sequence(self.resource_ids)
        self.recipient = _sequence(self.recipient)
        for field_name in (
            "human_intent",
            "agent_intent",
            "delegation_scope",
            "approval_scope",
            "tool_call",
            "tool_result",
            "source_provenance",
            "metadata",
        ):
            setattr(self, field_name, dict(getattr(self, field_name) or {}))

    @classmethod
    def from_context(
        cls,
        event_type: str,
        context: TrajectoryContext | Mapping[str, Any] | None = None,
        **fields: Any,
    ) -> "EventEnvelope":
        """Create an event while copying all shared context fields."""

        context_value = (
            context
            if isinstance(context, TrajectoryContext)
            else TrajectoryContext.from_dict(context)
        )
        values = context_value.to_dict()
        values.update(fields)
        values["event_type"] = event_type
        values.setdefault("trace_id", context_value.trace_id)
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-ready representation with all schema fields."""

        return _json_value(asdict(self))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


def new_context(**fields: Any) -> TrajectoryContext:
    """Create a trace context with a fresh trace ID unless one is supplied."""

    return TrajectoryContext(**fields)


def new_event(
    event_type: str,
    context: TrajectoryContext | Mapping[str, Any] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Create a JSON-ready event dictionary for an audit sink."""

    return EventEnvelope.from_context(event_type, context, **fields).to_dict()


def append_trajectory_event(log_dir: str | Path, event: Mapping[str, Any]) -> dict[str, Any]:
    """Append any audit record as a canonical trajectory sidecar event.

    Existing audit producers may still emit legacy fields.  They are preserved
    alongside the canonical envelope so the migration does not discard data.
    """

    raw = dict(event)
    event_type = str(raw.get("event_type") or "audit_event")
    envelope_fields = {}
    if raw.get("event_id"):
        envelope_fields["event_id"] = raw["event_id"]
    canonical = new_event(event_type, raw, **envelope_fields)
    canonical.update(raw)
    path = Path(log_dir) / "trajectory.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _TRAJECTORY_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(canonical, ensure_ascii=False, default=str) + "\n")
    return canonical


__all__ = [
    "EventEnvelope",
    "TrajectoryContext",
    "append_trajectory_event",
    "new_context",
    "new_event",
]
