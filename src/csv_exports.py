"""Export flat audit tables from the final daily activity traces of a run."""

from __future__ import annotations

from contextlib import ExitStack
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory


ACTIVITY = ("trace_id", "employee_id", "week", "date", "schedule_index", "sim_time")
EVENT = (*ACTIVITY, "event_index", "event_type", "event_id", "parent_event_id", "actor")
EMPLOYEE_TABLES = {
    "employee_day.csv": (*ACTIVITY, "activity"),
    # Keep Chimera's leading columns for software that reads these files.
    "final_schedule.csv": ("id", "index", "real_timestamp", "sim_timestamp", "name",
                           "container_id", "activity", "trace_id", "week", "date"),
    "logon.csv": ("id", "real_timestamp", "sim_timestamp", "name", "container_id", "status",
                  "trace_id"),
    "email.csv": ("email_from", "real_timestamp", "sim_timestamp", "name", "email_to",
                  "email_cc", "subject", "content", "trace_id"),
    "threat_labels.csv": (*ACTIVITY, "scenario_id", "channel", "mechanism", "impact",
                          "schedule_attack", "intervention_events"),
}
FULL_TABLES = {
    "agent_prompt.csv": (*EVENT, "role", "turn", "text", "fields", "delivered_to"),
    "agent_activity.csv": (*EVENT, "decision", "status", "text", "data"),
    "agent_tool.csv": (*EVENT, "action", "tool_name", "call_id", "arguments", "data", "original_result"),
    "rag.csv": (*EVENT, "call_id", "query", "documents", "original_documents"),
    "skill.csv": (*EVENT, "call_id", "workflow", "skill", "original_skill"),
    "memory.csv": (*EVENT, "call_id", "records", "original_records", "data"),
    "effect.csv": (*ACTIVITY, "event_id", "call_id", "status", "recipient", "receipt",
                   "before", "after", "actual_external_effect"),
}
PROMPTS = {"employee_prompt_drafted", "employee_prompt", "agent_acknowledgment"}
AGENT_ACTIONS = {"agent_acknowledgment", "agent_read_plan", "context_assembled",
                 "agent_decision", "agent_output"}
ENVELOPE = {"trace_id", "event_id", "parent_event_id", "event_type", "actor", "sim_time"}


def _payload(event):
    return {key: value for key, value in event.items() if key not in ENVELOPE}


def _full_rows(record, base):
    """Yield rows in the original event order, linking each tool result to its call."""
    calls = {}
    filing = {}
    for index, event in enumerate(record["events"], start=1):
        kind = event["event_type"]
        row = {**base, "event_index": index, "event_id": event["event_id"], "event_type": kind,
               "parent_event_id": event.get("parent_event_id"), "actor": event.get("actor")}
        if kind in PROMPTS:
            message = event["output"] if kind == "agent_acknowledgment" else event["prompt"]
            yield "agent_prompt.csv", {**row, **message, "delivered_to": event.get("delivered_to")}
        if kind in AGENT_ACTIONS:
            output = event.get("output", {})
            yield "agent_activity.csv", {**row, "decision": event.get("decision"),
                                         "status": output.get("status"), "text": output.get("text"),
                                         "data": _payload(event)}
        if kind == "agent_tool_call":
            call_id = event["event_id"]
            calls[call_id] = event["arguments"]
            yield "agent_tool.csv", {**row, "action": "call", "tool_name": event["tool_name"],
                                     "call_id": call_id, "arguments": calls[call_id]}
        elif kind == "agent_tool_result":
            tool, call_id, data = event["tool_name"], event["call_id"], event["data"]
            args = calls[call_id]
            result = {**row, "call_id": call_id}
            yield "agent_tool.csv", {**result, "action": "result", "tool_name": tool,
                                     "data": data, "original_result": event.get("original_result")}
            if tool == "retrieve_work_card_documents":
                yield "rag.csv", {**result, "query": args.get("query"), "documents": data["documents"],
                                  "original_documents": event.get("original_documents")}
            elif tool == "load_workflow_skill":
                yield "skill.csv", {**result, "workflow": args.get("workflow"), "skill": data,
                                    "original_skill": event.get("original_skill")}
            elif tool == "recall_agent_memory":
                yield "memory.csv", {**result, "records": data["records"],
                                     "original_records": event.get("original_records")}
            elif tool == "file_work_note":
                filing = {"event_id": event["event_id"], "call_id": call_id,
                          "status": data["status"], "recipient": data.get("recipient"), "receipt": data}
        elif kind in {"memory_written", "memory_recalled"}:
            yield "memory.csv", {**row, "call_id": event.get("call_id"), "data": _payload(event)}
    yield "effect.csv", {**base, **filing, **record["fixture_state"],
                         "actual_external_effect": record["actual_external_effect"]}


def _activity_rows(record, schedule, base, recording):
    employee = record["employee"]
    yield "employee_day.csv", {**base, "activity": employee["activity"]}
    yield "final_schedule.csv", {
        "id": base["employee_id"], "index": base["schedule_index"], "sim_timestamp": base["sim_time"],
        "trace_id": base["trace_id"], "week": base["week"], "date": base["date"],
        "activity": employee["activity"], "name": employee.get("name"),
        "container_id": employee.get("container_id"), "real_timestamp": employee.get("real_timestamp"),
    }
    scenario = record.get("scenario") or {}
    yield "threat_labels.csv", {
        **base, "scenario_id": scenario.get("attack_id") or schedule.get("AttackScenario"),
        "channel": scenario.get("channel"), "mechanism": scenario.get("mechanism"),
        "impact": scenario.get("impact"), "schedule_attack": str(schedule.get("Attack")).lower() == "true",
        "intervention_events": [event for event in record.get("events", [])
                                if event.get("actor") == "scenario_simulator"
                                or event["event_type"] == "memory_summary_observed"],
    }
    if recording == "full":
        yield from _full_rows(record, base)


def _run_rows(root, manifest):
    recording = manifest["recording"]
    dates = ((day["week"], day["date"], employee)
             for day in manifest["calendar"] for employee in manifest["employees"])
    missing = 0
    for week, day, member in dates:
        path = root / member / f"week_{week}" / f"{day}.jsonl"
        if not path.exists():
            missing += 1
            continue
        snapshot = path.with_suffix(".schedule.json")
        schedule = json.loads(snapshot.read_text(encoding="utf-8"))
        if not isinstance(schedule, list):
            raise ValueError(f"{snapshot}: expected a list of activities")
        count = 0
        with path.open(encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                try:
                    record = json.loads(line)
                    if record["recording"] != recording:
                        raise ValueError("recording level differs from manifest")
                    employee = record["employee"]
                    base = {"trace_id": record["trace_id"], "employee_id": employee["employee_id"],
                            "sim_time": employee["sim_time"], "week": week, "date": path.stem,
                            "schedule_index": index}
                    yield from _activity_rows(record, schedule[index], base, recording)
                except (IndexError, KeyError, TypeError, ValueError) as error:
                    raise ValueError(f"{path}:{index + 1}: invalid activity: {error}") from error
                count += 1
        if count != len(schedule):
            raise ValueError(f"{path}: {count} activities differ from {len(schedule)} schedule entries")
    if missing != manifest["missing_days"]:
        raise ValueError(f"{root}: missing {missing} of the daily trajectories in the manifest")


def export_run_csvs(run_dir, recording=None):
    """Rebuild a run's CSVs from JSONL. Return row counts keyed by filename."""
    root = Path(run_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    level = manifest["recording"]
    if level not in ("employee", "full") or (recording is not None and recording != level):
        raise ValueError(f"CSV recording must match the manifest recording level ({level})")
    tables = EMPLOYEE_TABLES if level == "employee" else {**EMPLOYEE_TABLES, **FULL_TABLES}
    counts = dict.fromkeys(tables, 0)
    # A parse or serialization error leaves the previously published tables intact.
    with TemporaryDirectory(prefix=".csv-export-", dir=root) as temporary:
        stage = Path(temporary)
        with ExitStack() as stack:
            writers = {}
            for name, fields in tables.items():
                handle = stack.enter_context((stage / name).open("w", encoding="utf-8", newline=""))
                writers[name] = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
                writers[name].writeheader()
            for name, row in _run_rows(root, manifest):
                writers[name].writerow({
                    key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                    for key, value in row.items()
                })
                counts[name] += 1
        if manifest.get("status") == "completed" and counts["employee_day.csv"] != manifest["events"]:
            raise ValueError(f"{root}: recorded activity count differs from the completed run manifest")
        for name in tables:
            (stage / name).replace(root / name)
    return counts


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="completed run directory containing manifest.json")
    args = parser.parse_args()
    print(json.dumps(export_run_csvs(args.run_dir), ensure_ascii=False, indent=2))
