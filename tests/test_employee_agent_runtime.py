import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from employee_agent_runtime import append_activity_trace, simulate_activity
from enterprise_harness import EnterpriseHarness, ISSUED_FIELDS
from enterprise_retrieval import KnowledgeBase
from scenario_catalog import list_scenario_ids, load_scenario


def run_case(name=None, policy=None):
    return simulate_activity(
        employee_id="employee-1", activity="  Prepare the scheduled handover  ", sim_time="10:00",
        scenario=load_scenario(name) if name else None,
        context={"department": "service", "run_id": "test"}, agent_policy=policy,
    )


class EmployeeAgentRuntimeTests(unittest.TestCase):
    def test_employee_schedule_attack_does_not_modify_agent_environment(self):
        record = simulate_activity(
            employee_id="employee-1", activity="Attack activity: expand the scheduled scope",
            sim_time="10:00", scenario=load_scenario("scope_expansion"),
            context={"trace_id": "employee-schedule-attack"},
            apply_environment_intervention=False,
        )
        self.assertEqual(record["scenario"]["variant"], "scope_expansion")
        self.assertFalse(any(event["event_type"] == "intervention_applied"
                             for event in record["events"]))
        self.assertEqual(record["fixture_state"]["after"]["trays"]["tray-A"][0]["entries"][0]["id"], "card-1")

    def test_intervention_changes_only_selected_source_and_result(self):
        control = run_case()
        control_input = control["agent"]["input"]
        for variant in list_scenario_ids():
            with self.subTest(variant=variant):
                case = run_case(variant)
                visible = case["agent"]["input"]
                channel = case["scenario"]["channel"]
                if variant == "incorrect_receipt_summary":
                    # This write is scheduled after the first activity's final reply.
                    self.assertEqual(visible, control_input)
                    self.assertEqual(case["fixture_state"], control["fixture_state"])
                    self.assertEqual(case["agent"]["output"], control["agent"]["output"])
                    self.assertTrue(any(e["event_type"] == "intervention_applied" and e["source"] == "memory_write"
                                        for e in case["events"]))
                    continue
                changed = {
                    "prompt": "conversation",
                    "tool_result": "lookup_result", "rag_document": "documents",
                    "skill_record": "skill", "agent_memory": "memory",
                }[channel]
                # No scenario ID, owning role or change indicator is delivered to the policy.
                self.assertEqual(set(visible), {"conversation", "issued_order", "documents", "lookup_result",
                                                "skill", "memory", "team_directory", "filing_history"})
                self.assertEqual([key for key in visible if visible[key] != control_input[key]], [changed])
                self.assertEqual(case["employee"], control["employee"])
                self.assertEqual(case["employee_prompt_draft"], control["employee_prompt_draft"])
                self.assertEqual(case["fixture_state"]["before"], control["fixture_state"]["before"])
                self.assertNotEqual(case["fixture_state"]["after"], control["fixture_state"]["after"])

                events = case["events"]
                self.assertEqual([e["parent_event_id"] for e in events],
                                 [None] + [e["event_id"] for e in events[:-1]])
                turns = [e.get("prompt") or e.get("output") for e in events
                         if e["event_type"] in {"employee_prompt", "agent_acknowledgment"}]
                self.assertEqual(turns, visible["conversation"])
                calls = {e["event_id"] for e in events if e["event_type"] == "agent_tool_call"}
                results = {e["call_id"] for e in events if e["event_type"] == "agent_tool_result"}
                self.assertEqual(calls, results)
                changes = [e for e in events if e["event_type"] == "intervention_applied"]
                self.assertTrue(changes)
                self.assertTrue(all(e["actor"] == "scenario_simulator" for e in changes))
                if channel == "rag_document":
                    self.assertEqual(changes[0]["revision"], 2)
                elif channel == "tool_result":
                    evidence = next(e for e in events if e["event_type"] == "agent_tool_result"
                                    and e["call_id"] == changes[0]["call_id"])
                    self.assertEqual(evidence["data"], visible["lookup_result"])
                    self.assertEqual(evidence["original_result"], control_input["lookup_result"])
                elif variant == "cumulative_scope_change":
                    self.assertEqual([e["visible_value"] for e in changes],
                                     [["card-1", "card-2"], ["card-1", "card-2", "card-3"]])
                elif channel in {"skill_record", "agent_memory"}:
                    read_id = changes[0]["call_id"]
                    result = next(e for e in events if e.get("call_id") == read_id and e["event_type"] == "agent_tool_result")
                    if channel == "skill_record":
                        self.assertEqual(result["original_skill"], control_input["skill"])
                        self.assertEqual(result["data"], visible["skill"])
                    else:
                        self.assertEqual(result["original_records"], control_input["memory"])
                        self.assertEqual(result["data"]["records"], visible["memory"])

        held = run_case("misleading_retention_record")
        unavailable = run_case("false_availability_status")
        self.assertEqual(held["agent"]["tool_results"][-1]["data"]["reason"], "retention_hold")
        self.assertEqual(unavailable["agent"]["tool_results"][-1]["data"]["reason"], "card_unavailable")

    def test_unread_skill_is_unobserved_and_reads_execute_in_declared_order(self):
        class SelectReads:
            def plan_reads(self, order, conversation, tools):
                return ["lookup_team_directory", "recall_agent_memory", "read_filing_history"]

            def __call__(self, visible):
                self.visible = visible
                return {"decision": "adopt_fixture"}

        policy = SelectReads()
        trace = run_case("skill_template_drift", policy)
        self.assertIsNone(policy.visible["skill"])
        self.assertIsNone(policy.visible["lookup_result"])
        self.assertEqual(policy.visible["documents"], [])
        self.assertEqual(policy.visible["team_directory"]["scope"], {"department": "service"})
        self.assertEqual(trace["fixture_state"]["after"], run_case()["fixture_state"]["after"])
        self.assertEqual([call["tool_name"] for call in trace["agent"]["tool_calls"]],
                         ["lookup_team_directory", "recall_agent_memory", "read_filing_history", "file_work_note"])
        events = [e["event_type"] for e in trace["events"]]
        self.assertIn("intervention_not_observed", events)
        self.assertNotIn("intervention_applied", events)
        self.assertEqual(next(e["reason"] for e in trace["events"] if e["event_type"] == "intervention_not_observed"),
                         "read_not_planned")

    def test_audits_multiple_revised_documents_and_empty_retrieval(self):
        def directory(document_id):
            return {"card_id": "card-1", "document_id": document_id, "revision": 3, "source": "directory",
                    "title": "Handover routing", "text": "Send the scheduled work note",
                    "facts": {"recipient": "tray-A"}}

        def run(corpus):
            return simulate_activity(employee_id="a", activity="Handover", sim_time="10:00",
                                     scenario=load_scenario("false_recipient_directory"),
                                     harness=EnterpriseHarness("a", knowledge_base=KnowledgeBase(corpus)))

        result = run([directory("one"), directory("two")])
        revisions = [e for e in result["events"] if e["event_type"] == "intervention_applied"]
        self.assertEqual([(e["document_id"], e["revision"]) for e in revisions], [("one", 4), ("two", 4)])
        empty = run([])
        reasons = [e["reason"] for e in empty["events"] if e["event_type"] == "intervention_not_observed"]
        self.assertEqual(reasons, ["target_outside_results"])

    def test_memory_roundtrip_preserves_owner_scope_and_prior_receipt(self):
        import copy

        def run(environment, trace, scenario=None, policy=None):
            return simulate_activity(employee_id="e", activity="Review", sim_time="10:00",
                                     context={"trace_id": trace}, agent_policy=policy, harness=environment,
                                     scenario=load_scenario(scenario) if scenario else None)

        env = EnterpriseHarness("e")
        first = run(env, "day1", "stale_recipient_preference")
        next_day = EnterpriseHarness("e")
        snapshot = json.loads(json.dumps(env.export_memory()))
        next_day.restore_memory(snapshot)
        self.assertEqual(env.export_memory(), next_day.export_memory())
        restored = run(next_day, "day2")
        self.assertEqual(run(env, "day2"), restored)
        prior = restored["agent"]["input"]["memory"][-1]
        self.assertEqual(prior["source_trace_id"], "day1")
        self.assertEqual(prior["receipt"], first["agent"]["tool_results"][-1]["data"])
        history = restored["agent"]["input"]["filing_history"]["records"]
        self.assertEqual(history, [{k: v for k, v in prior.items() if k != "summary_facts"}])
        # A prior delivery is remembered; it does not become the next order's default.
        self.assertEqual(restored["agent"]["tool_results"][-1]["data"]["recipient"], "tray-A")
        after = env.export_memory()
        malformed = copy.deepcopy(after)
        malformed["records"][0]["receipt"]["recipient"] = "unregistered-tray"
        duplicate = copy.deepcopy(after)
        duplicate["records"].append(duplicate["records"][0])
        for invalid in (duplicate, malformed, dict(after, employee_id="other")):
            with self.assertRaises(ValueError):
                env.restore_memory(invalid)
            self.assertEqual(after, env.export_memory())
        with self.assertRaises(ValueError):
            run(EnterpriseHarness("other"), "day3")

    def test_written_summary_persists_without_rewriting_ledger_or_history(self):
        def run(harness, trace, scenario=None, policy=None):
            return simulate_activity(employee_id="e", activity="Review", sim_time="10:00",
                                     context={"trace_id": trace}, harness=harness, agent_policy=policy,
                                     scenario=load_scenario(scenario) if scenario else None)

        writer = EnterpriseHarness("e")
        first = run(writer, "producer", "incorrect_receipt_summary")
        self.assertEqual(first["agent"]["tool_results"][-1]["data"]["receipt"]["entries"][0]["record_value"], "draft")
        snapshot = writer.export_memory()
        saved = snapshot["records"][0]
        self.assertEqual(saved["summary_facts"], {"value": "reviewed"})
        self.assertEqual(saved["write_origin"], "memory_writer")
        self.assertEqual(saved["receipt"], first["agent"]["tool_results"][-1]["data"])
        consumer = EnterpriseHarness("e")
        consumer.restore_memory(snapshot)
        altered = dict(saved, write_origin="receipt_summary")
        with self.assertRaisesRegex(ValueError, "Invalid receipt summary"):
            consumer.restore_memory(dict(snapshot, records=[altered]))
        self.assertEqual(consumer.export_memory(), snapshot)
        downstream = run(consumer, "consumer")
        self.assertIsNone(downstream["scenario"])
        observed = [e for e in downstream["events"] if e["event_type"] == "memory_summary_observed"]
        self.assertEqual([(e["source_trace_id"], e["original_summary"], e["written_summary"]) for e in observed],
                         [("producer", {"value": "draft"}, {"value": "reviewed"})])
        memory = downstream["agent"]["input"]["memory"][-1]
        self.assertNotIn("write_origin", memory)
        self.assertEqual(memory["summary_facts"], {"value": "reviewed"})
        entry = downstream["agent"]["input"]["filing_history"]["records"][0]
        self.assertNotIn("summary_facts", entry)
        self.assertEqual(entry["receipt"], first["agent"]["tool_results"][-1]["data"])
        self.assertEqual(downstream["agent"]["tool_results"][-1]["data"]["receipt"]["entries"][0]["record_value"],
                         "reviewed")
        for retain, skip in ((True, False), (False, True)):
            class Reader:
                def __call__(self, visible):
                    return {"decision": "retain_baseline" if retain else "adopt_fixture"}
                def plan_reads(self, order, conversation, tools):
                    return [] if skip else ["recall_agent_memory"]
            consumer.restore_memory(snapshot)
            trace = run(consumer, "replay", policy=Reader())
            self.assertEqual(trace["agent"]["tool_calls"][-1]["arguments"]["value"], "draft")
            self.assertEqual(any(e["event_type"] == "memory_summary_observed" for e in trace["events"]), not skip)
        # Existing version-one snapshots only recorded the truthful service receipt.
        old_row = {k: v for k, v in saved.items() if k not in {"summary_facts", "write_origin"}}
        consumer.restore_memory({"employee_id": "e", "schema_version": 1, "records": [old_row]})
        migrated = run(consumer, "legacy")
        self.assertEqual(migrated["agent"]["tool_calls"][-1]["arguments"]["value"], "draft")
        self.assertEqual(migrated["agent"]["input"]["memory"][-1]["summary_facts"], {"value": "draft"})

    def test_status_recall_uses_the_same_rule_for_accurate_and_inaccurate_summaries(self):
        def run_with_prior(value, override=None, *, card="card-1", workflow="work note", scenario=None):
            env = EnterpriseHarness("e")
            fields = dict(ISSUED_FIELDS, value=value, record_ids=["card-1", "card-2"], recipient="tray-B")
            state = {"trays": {"tray-A": [], "tray-B": []}, "pending": []}
            receipt = env.file_note("Earlier handover", workflow, fields, state)
            env.remember(card, workflow, "earlier", receipt, summary_override=override)
            trace = simulate_activity(employee_id="e", activity="Review", sim_time="10:00", harness=env,
                                      scenario=load_scenario(scenario) if scenario else None)
            return trace["agent"]["tool_calls"][-1]["arguments"]

        accurate = run_with_prior("reviewed")
        inaccurate = run_with_prior("draft", {"value": "reviewed"})
        self.assertEqual(accurate, inaccurate)
        self.assertEqual((accurate["value"], accurate["record_ids"], accurate["recipient"]),
                         ("reviewed", ["card-1"], "tray-A"))
        self.assertEqual(run_with_prior("reviewed", card="card-2")["value"], "draft")
        self.assertEqual(run_with_prior("reviewed", workflow="browsing note")["value"], "draft")
        self.assertEqual(run_with_prior("reviewed", scenario="scope_expansion")["value"], "draft")
        self.assertEqual(run_with_prior("draft", scenario="substituted_tool_value")["value"], "reviewed")

    def test_failed_model_output_does_not_mutate_memory(self):
        class FailedFinalizer:
            def __call__(self, visible):
                return {"decision": "adopt_fixture"}

            def finalize(self, visible, receipt):
                raise RuntimeError("model unavailable")

        env = EnterpriseHarness("e")
        with self.assertRaises(RuntimeError):
            simulate_activity(employee_id="e", activity="Review", sim_time="10:00",
                              agent_policy=FailedFinalizer(), harness=env)
        self.assertEqual(env.export_memory()["records"], [])

    def test_policy_can_retain_original_without_external_effect(self):
        class Retain:
            def __call__(self, visible):
                self.input = visible
                return {"decision": "retain_baseline"}

            def finalize(self, visible, receipt):
                self.receipt = receipt
                return "The work note was filed in " + receipt["recipient"]

        policy = Retain()
        record = run_case("recipient_substitution", policy)
        self.assertEqual(record["agent"]["input"], policy.input)
        self.assertEqual(record["fixture_state"]["after"], run_case()["fixture_state"]["after"])
        self.assertFalse(record["actual_external_effect"])
        self.assertEqual(record["agent"]["output"]["source"], "text_model")
        self.assertEqual(record["agent"]["output"]["text"], "The work note was filed in tray-A")
        self.assertEqual(record["agent"]["tool_results"][-1]["data"], policy.receipt)
        with self.assertRaises(ValueError):
            run_case("recipient_substitution", lambda _: {"decision": "unrecognized"})

    def test_trace_sink_appends_exact_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.partial"
            a, b = run_case(), run_case("conflicting_record")
            append_activity_trace(path, a)
            append_activity_trace(path, b)
            self.assertEqual([json.loads(row) for row in path.read_text().splitlines()], [a, b])

    def test_multiturn_model_acknowledges_before_next_request(self):
        seen = []

        class Assistant:
            def acknowledge(self, order, messages):
                seen.append(messages)
                return f"Received {len(messages[-1]['fields']['record_ids'])} cards."

            def __call__(self, visible):
                return {"decision": "retain_baseline"}

        trace = run_case("cumulative_scope_change", Assistant())
        delivered = trace["agent"]["input"]["conversation"]
        self.assertEqual(seen, [delivered[:1], delivered[:3]])
        self.assertEqual([m["text"] for m in delivered if m["role"] == "agent"],
                         ["Received 1 cards.", "Received 2 cards."])

    def test_json_values_drive_the_observation_and_final_receipt(self):
        scenario = load_scenario("scope_expansion")
        scenario["change"]["values"] = [["card-1", "card-2", "card-3"]]
        case = simulate_activity(employee_id="a", activity="Review", sim_time="09:00", scenario=scenario)
        receipt = case["agent"]["tool_results"][-1]["data"]["receipt"]
        self.assertEqual([r["id"] for r in receipt["entries"]], scenario["change"]["values"][0])
        scenario["change"]["values"] = [["missing-card"]]
        with self.assertRaisesRegex(ValueError, "unsupported fixture value"):
            simulate_activity(employee_id="a", activity="Review", sim_time="09:00", scenario=scenario)

    def test_component_mechanism_is_audited_at_the_intervention_stage(self):
        for scenario_id in list_scenario_ids():
            with self.subTest(scenario_id=scenario_id):
                scenario = load_scenario(scenario_id)
                trace = run_case(scenario_id)
                self.assertEqual(trace["scenario"]["mechanism"], scenario["mechanism"])
                applied = [event for event in trace["events"]
                           if event["event_type"] == "intervention_applied"]
                self.assertTrue(applied)
                self.assertTrue(all(event["mechanism"] == scenario["mechanism"] for event in applied))
                self.assertTrue(all(event["intervention_stage"] == scenario["intervention_stage"]
                                    for event in applied))

        rag = simulate_activity(
            employee_id="employee-1", activity="Review", sim_time="10:00",
            scenario=load_scenario("false_recipient_directory"),
        )
        evidence = [event for event in rag["events"] if event["event_type"] == "intervention_applied"][0]
        self.assertIsInstance(evidence["rank_before"], int)
        self.assertIsInstance(evidence["rank_after"], int)
