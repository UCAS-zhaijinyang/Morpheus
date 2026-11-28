"""The active catalog of finite employee–Agent simulation scenarios."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

CATALOG_DIR = Path(__file__).resolve().parents[1] / "threat_scenarios"

# The values name a simulator channel and an expected business consequence.
METHOD_AXES = {
    "recipient_substitution": ("prompt", "disclosure"),
    "scope_expansion": ("prompt", "unauthorized_collection"),
    "delayed_recipient_change": ("prompt", "disclosure"),
    "cumulative_scope_change": ("prompt", "unauthorized_collection"),
    "conflicting_record": ("rag_document", "integrity_loss"),
    "false_recipient_directory": ("rag_document", "disclosure"),
    "misleading_retention_record": ("rag_document", "availability_loss"),
    "substituted_tool_value": ("tool_result", "integrity_loss"),
    "expanded_result_scope": ("tool_result", "unauthorized_collection"),
    "false_availability_status": ("tool_result", "availability_loss"),
    "skill_template_drift": ("skill_record", "integrity_loss"),
    "skill_retention_mismatch": ("skill_record", "availability_loss"),
    "stale_recipient_preference": ("agent_memory", "disclosure"),
    "misattributed_review_memory": ("agent_memory", "integrity_loss"),
    "incorrect_receipt_summary": ("agent_memory", "integrity_loss"),
}

# A channel names the trust surface that receives the intervention.  The
# mechanism is deliberately scoped to that surface so that the terminology
# used for prompt turns cannot accidentally be reused for a document, tool,
# skill, or memory scenario.
CHANNEL_COMPONENTS = {
    "prompt": "prompt",
    "rag_document": "rag", "tool_result": "tool",
    "skill_record": "skill", "agent_memory": "memory",
}
COMPONENT_MECHANISMS = {
    "prompt": {"authority_scope_substitution", "direct_instruction_override",
                "incremental_commitment", "context_reframing"},
    "rag": {"fact_corruption", "relevance_manipulation", "indirect_instruction"},
    "tool": {"value_substitution", "result_scope_expansion", "status_fabrication"},
    "skill": {"procedure_tampering", "scope_mismatch"},
    "memory": {"write_poisoning", "retrieval_misattribution", "persistent_propagation"},
}
SCENARIO_MECHANISMS = {
    "recipient_substitution": "direct_instruction_override",
    "scope_expansion": "authority_scope_substitution",
    "delayed_recipient_change": "incremental_commitment",
    "cumulative_scope_change": "context_reframing",
    "conflicting_record": "fact_corruption",
    "false_recipient_directory": "relevance_manipulation",
    "misleading_retention_record": "indirect_instruction",
    "substituted_tool_value": "value_substitution",
    "expanded_result_scope": "result_scope_expansion",
    "false_availability_status": "status_fabrication",
    "skill_template_drift": "procedure_tampering",
    "skill_retention_mismatch": "scope_mismatch",
    "stale_recipient_preference": "write_poisoning",
    "misattributed_review_memory": "retrieval_misattribution",
    "incorrect_receipt_summary": "persistent_propagation",
}
INTERACTION_SHAPES = {"single_turn", "multi_turn", "environment_state_transition"}
PROMPT_MODES = {"single_turn", "multi_turn"}
INTERVENTION_STAGES = {
    "employee_request", "document", "tool_result", "skill_read", "memory_read", "memory_write",
}
PROMPT_ATTACK_FAMILIES = {"naive", "context_ignoring", "fake_completion", "combined"}
RAG_ATTACK_GOALS = {"targeted_answer", "denial_of_service", "triggered_denial"}
RAG_POISONING_STAGES = {"corpus_entry", "retrieval_rank", "context_instruction"}
TOOL_RESULT_GOALS = {"direct_harm", "private_data_exfiltration", "state_tampering"}
SKILL_ARTIFACT_LAYERS = {"metadata", "instructions", "scripts", "references", "assets"}
MEMORY_WRITE_CHANNELS = {"seed_record", "cross_task_record", "derived_receipt"}
MEMORY_ATTACK_CLASSES = {"false_precedent", "policy_conformant_fact", "explicit_command"}
MEMORY_SIGNAL_STRENGTHS = {"weak", "strong"}
_COMPONENT_FIELDS = {
    "prompt": {"prompt_mode", "prompt_attack_family"},
    "rag": {"rag_attack_goal", "poisoning_stage"},
    "tool": {"tool_result_attack_goal", "return_field_class"},
    "skill": {"artifact_layer", "skill_mechanism", "skill_provenance", "skill_permission_boundary"},
    "memory": {"memory_write_channel", "attack_class", "signal_strength", "lifecycle_stage"},
}


# Finite ranges understood by the in-memory services. JSON files supply the
# field and its successive values; the simulator never interprets prose as a tool.
_IMPACT_FIELDS = {
    "disclosure": {"recipient"}, "unauthorized_collection": {"record_ids"},
    "integrity_loss": {"value"}, "availability_loss": {"disposition", "available"},
}
_FIELD_VALUES = {
    "recipient": ("tray-A", "tray-B"),
    "value": ("draft", "reviewed"),
    "record_ids": (["card-1"], ["card-1", "card-2"], ["card-1", "card-2", "card-3"]),
    "disposition": ("release", "hold"),
    "available": (True, False),
}

# Each source has its own typed fields. Keeping this separate from the impact
# map prevents a valid value from being placed on the wrong trust surface.
_CHANNEL_FIELDS = {
    "prompt": {"recipient", "record_ids"},
    "rag_document": {"value", "recipient", "disposition"},
    "tool_result": {"value", "record_ids", "disposition", "available"},
    "skill_record": {"value", "disposition"},
    "agent_memory": {"recipient", "value"},
}

CHANNEL_SOURCE_ROLES = {
    "prompt": "request_author",
    "rag_document": "document_contributor",
    "tool_result": "tool_data_contributor",
    "skill_record": "skill_contributor",
    "agent_memory": "memory_writer",
}


def list_scenario_ids() -> tuple[str, ...]:
    """Return the supported IDs, grouped by input channel."""
    return tuple(METHOD_AXES)


def validate_scenario(entry: Mapping[str, Any], scenario_id: str) -> None:
    """Reject unknown routes, invalid service values and ambiguous turn placement."""
    if not isinstance(scenario_id, str) or scenario_id not in METHOD_AXES:
        raise ValueError(f"unknown scenario: {scenario_id!r}")
    if entry.get("schema_version") != 2 or entry.get("variant") != scenario_id:
        raise ValueError(f"{scenario_id}: unexpected schema or variant")
    channel, impact = METHOD_AXES[scenario_id]
    if (entry.get("channel"), entry.get("impact")) != (channel, impact):
        raise ValueError(f"{scenario_id}: unexpected channel or impact")
    component = CHANNEL_COMPONENTS[channel]
    if entry.get("component") != component:
        raise ValueError(f"{scenario_id}: component must be {component!r}")
    for field_name, field_owner in {
        field: owner for owner, fields in _COMPONENT_FIELDS.items() for field in fields
    }.items():
        if field_name in entry and field_owner != component:
            raise ValueError(f"{scenario_id}: {field_name} belongs to {field_owner}")
    mechanism = entry.get("mechanism")
    if not isinstance(mechanism, str) or mechanism not in COMPONENT_MECHANISMS[component]:
        raise ValueError(f"{scenario_id}: unsupported mechanism for {component}")
    if mechanism != SCENARIO_MECHANISMS[scenario_id]:
        raise ValueError(f"{scenario_id}: mechanism does not match the catalog taxonomy")
    shape = entry.get("interaction_shape")
    prompt_mode = entry.get("prompt_mode")
    expected_shape = (prompt_mode if channel == "prompt" else
                      "environment_state_transition")
    if channel == "prompt" and prompt_mode not in PROMPT_MODES:
        raise ValueError(f"{scenario_id}: prompt_mode must be single_turn or multi_turn")
    if channel == "prompt":
        if entry.get("prompt_attack_family") not in PROMPT_ATTACK_FAMILIES:
            raise ValueError(f"{scenario_id}: invalid prompt_attack_family")
    if shape != expected_shape:
        raise ValueError(f"{scenario_id}: interaction_shape must be {expected_shape!r}")
    if channel != "prompt" and "prompt_mode" in entry:
        raise ValueError(f"{scenario_id}: prompt_mode is only valid for prompt channels")
    if channel != "prompt" and "prompt_attack_family" in entry:
        raise ValueError(f"{scenario_id}: prompt_attack_family is only valid for prompt channels")
    if channel != "prompt" and any(field in entry for field in ("conversation_scope", "turn_count")):
        raise ValueError(f"{scenario_id}: prompt conversation fields are only valid for prompt channels")
    if channel == "prompt" and any(field in entry for field in ("conversation_scope", "turn_count")):
        raise ValueError(f"{scenario_id}: use prompt_mode for prompt interaction shape")
    if channel == "rag_document":
        if entry.get("rag_attack_goal") not in RAG_ATTACK_GOALS:
            raise ValueError(f"{scenario_id}: invalid rag_attack_goal")
        if entry.get("poisoning_stage") not in RAG_POISONING_STAGES:
            raise ValueError(f"{scenario_id}: invalid poisoning_stage")
    if channel == "tool_result":
        if entry.get("tool_result_attack_goal") not in TOOL_RESULT_GOALS:
            raise ValueError(f"{scenario_id}: invalid tool_result_attack_goal")
        if not isinstance(entry.get("return_field_class"), str) or not entry["return_field_class"].strip():
            raise ValueError(f"{scenario_id}: return_field_class must be text")
    if channel == "skill_record":
        if entry.get("artifact_layer") not in SKILL_ARTIFACT_LAYERS:
            raise ValueError(f"{scenario_id}: invalid skill artifact_layer")
        for key in ("skill_mechanism", "skill_provenance", "skill_permission_boundary"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(f"{scenario_id}: {key} must be text")
    if channel == "agent_memory":
        if entry.get("memory_write_channel") not in MEMORY_WRITE_CHANNELS:
            raise ValueError(f"{scenario_id}: invalid memory_write_channel")
        if entry.get("attack_class") not in MEMORY_ATTACK_CLASSES:
            raise ValueError(f"{scenario_id}: invalid memory attack_class")
        if entry.get("signal_strength") not in MEMORY_SIGNAL_STRENGTHS:
            raise ValueError(f"{scenario_id}: invalid memory signal_strength")
        if not isinstance(entry.get("lifecycle_stage"), str) or not entry["lifecycle_stage"].strip():
            raise ValueError(f"{scenario_id}: lifecycle_stage must be text")
    if entry.get("intervention_stage") not in INTERVENTION_STAGES:
        raise ValueError(f"{scenario_id}: invalid intervention_stage")
    expected_stage = {
        "prompt": "employee_request",
        "rag_document": "document", "tool_result": "tool_result",
        "skill_record": "skill_read", "agent_memory": "memory_write" if scenario_id in {
            "stale_recipient_preference", "incorrect_receipt_summary"
        } else "memory_read",
    }[channel]
    if entry.get("intervention_stage") != expected_stage:
        raise ValueError(f"{scenario_id}: intervention_stage must be {expected_stage!r}")
    if not isinstance(entry.get("mutation_target"), str) or not entry["mutation_target"].strip():
        raise ValueError(f"{scenario_id}: mutation_target must be non-empty text")
    evidence_fields = entry.get("evidence_fields")
    if (not isinstance(evidence_fields, list) or not evidence_fields or
            not all(isinstance(field, str) and field.strip() for field in evidence_fields)):
        raise ValueError(f"{scenario_id}: evidence_fields must be non-empty text list")
    references = entry.get("references")
    if (not isinstance(references, list) or not references or
            not all(isinstance(reference, str) and reference.strip() for reference in references)):
        raise ValueError(f"{scenario_id}: references must be non-empty text list")
    change = entry.get("change")
    if not isinstance(change, dict) or not isinstance(change.get("field"), str):
        raise ValueError(f"{scenario_id}: missing fixture field")
    field = change["field"]
    if field not in _CHANNEL_FIELDS[channel]:
        raise ValueError(f"{scenario_id}: field {field!r} is not valid for {channel}")
    if field not in _IMPACT_FIELDS[impact]:
        raise ValueError(f"{scenario_id}: invalid field for {impact}")
    if entry.get("source_role", CHANNEL_SOURCE_ROLES[channel]) != CHANNEL_SOURCE_ROLES[channel]:
        raise ValueError(f"{scenario_id}: unexpected source role for {channel}")
    employee_activity = entry.get("employee_activity")
    if (not isinstance(employee_activity, str) or not employee_activity.strip()
            or len(employee_activity) > 1000):
        raise ValueError(f"{scenario_id}: employee_activity must be non-empty text")
    values = change.get("values")
    if not isinstance(values, list) or not values or (channel != "prompt" or entry.get("prompt_mode") != "multi_turn") and len(values) != 1:
        raise ValueError(f"{scenario_id}: invalid number of updates")
    for value in values:
        if not any(type(value) is type(allowed) and value == allowed for allowed in _FIELD_VALUES[field]):
            raise ValueError(f"{scenario_id}: unsupported fixture value for {field}")


def load_scenario(scenario_id: str) -> dict[str, Any]:
    if scenario_id not in METHOD_AXES:
        raise ValueError(f"unknown scenario: {scenario_id!r}")
    path = CATALOG_DIR / f"{scenario_id}.json"
    entry = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entry, dict) or entry.get("attack_id") != scenario_id:
        raise ValueError(f"{path.name}: filename and scenario ID must agree")
    validate_scenario(entry, scenario_id)
    return entry


if __name__ == "__main__":
    print("\n".join(list_scenario_ids()))
