import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from behavior_router import BehaviorRouter
from agent_registry import AgentRegistry, generate_agent_registry
from deepseek_harness_adapter import run_human_tool_task
import config
from hierarchical_planning import build_hierarchy, load_role_department_map
from skill_memory import SkillMemory


class HarnessPrimitiveTests(unittest.TestCase):
    def test_fast_router_separates_session_and_complex_behaviors(self):
        router = BehaviorRouter(0.3, rng=lambda: 0.1)
        logout = router.route_activity("take a break")
        email = router.route_activity("send email to @eng-1")
        loaf = router.route_activity("LoafBrowsing")
        self.assertEqual(logout.action, "logout")
        self.assertEqual(logout.execution_mode, "employee_personal")
        self.assertEqual(logout.agent_type, "employee")
        self.assertEqual(email.action, "email")
        self.assertEqual(email.execution_mode, "enterprise_agent")
        self.assertEqual(loaf.action, "loaf")
        self.assertEqual(loaf.execution_mode, "personal_agent")
        self.assertEqual(router.route_gap(45).action, "loaf")

    def test_agent_registry_separates_personal_and_enterprise_scopes(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = AgentRegistry.load(
                os.path.join(directory, "agents.json"),
                ["employee-1"],
            )
            personal = registry.resolve("employee-1", "personal_agent", "loaf")
            employee = registry.resolve("employee-1", "employee_personal", "login")
            enterprise = registry.resolve("employee-1", "enterprise_agent", "task")
            self.assertEqual(employee.agent_id, "employee-agent-employee-1")
            self.assertEqual(employee.agent_type, "employee")
            self.assertEqual(personal.agent_id, "personal-agent-employee-1")
            self.assertEqual(personal.agent_type, "personal")
            self.assertEqual(personal.owner_id, "employee-1")
            self.assertEqual(enterprise.agent_type, "enterprise")
            self.assertNotEqual(personal.memory_scope, enterprise.memory_scope)

    def test_agent_registry_scopes_personal_and_employee_agents_per_member(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = AgentRegistry.load(
                os.path.join(directory, "agents.json"),
                ["employee-1", "employee-2"],
            )
            self.assertEqual(
                [
                    profile["agent_id"]
                    for profile in registry.as_dicts()
                    if profile["agent_type"] in {"employee", "personal"}
                ],
                [
                    "employee-agent-employee-1",
                    "employee-agent-employee-2",
                    "personal-agent-employee-1",
                    "personal-agent-employee-2",
                ],
            )

    def test_registry_uses_one_shared_enterprise_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = AgentRegistry.load(
                os.path.join(directory, "agents.json"),
            )
            enterprise = [
                profile
                for profile in registry.as_dicts()
                if profile["agent_type"] == "enterprise"
            ]
            personal = [
                profile
                for profile in registry.as_dicts()
                if profile["agent_type"] == "personal"
            ]
            self.assertEqual(len(enterprise), 1)
            self.assertEqual(len(personal), 0)
            self.assertEqual(enterprise[0]["agent_id"], "enterprise-workflow-agent")

    def test_agent_generation_uses_company_context_and_fixed_schema(self):
        generated = {
            "agents": [
                {
                    "name": "Hospital Workflow Agent",
                    "role": "clinical workflow orchestration",
                    "description": "Coordinates hospital data collection tasks.",
                    "capabilities": ["plan", "handoff", "verify"],
                    "allowed_tools": ["calendar", "repository"],
                    "authority_scope": "clinical-project-delegated",
                    "memory_scope": "project-audited",
                },
                {
                    "name": "Hospital Compliance Agent",
                    "role": "privacy review",
                    "description": "Checks minimum-necessary data use.",
                    "capabilities": ["policy_check", "audit"],
                    "allowed_tools": ["directory", "repository"],
                    "authority_scope": "compliance-review-delegated",
                    "memory_scope": "compliance-audited",
                },
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "foundation_model.run_llm",
                return_value=json.dumps(generated),
            ) as run_llm:
                generate_agent_registry(
                    os.path.join(directory, "agents.json"),
                    company_type="Small Community Hospital",
                    goal="Complete EHR collection and influenza analysis",
                    business_context={"roles": ["EHR Data Specialist"]},
                )
            prompt = run_llm.call_args.args[1]
            self.assertIn("Complete EHR collection", prompt)
            with open(os.path.join(directory, "agents.json"), encoding="utf-8") as handle:
                payload = json.load(handle)
            self.assertEqual(len(payload["agents"]), 1)
            self.assertEqual(payload["agents"][0]["agent_id"], "enterprise-workflow-agent")
            self.assertEqual(payload["generation_context"]["company_type"], "Small Community Hospital")

    def test_stub_harness_persists_agent_identity_on_both_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"MORPHEUS_HARNESS_STUB": "1"}, clear=False):
                with patch.object(
                    config,
                    "agent_registry_path",
                    os.path.join(directory, "agents.json"),
                ):
                    result = run_human_tool_task(
                        "Inspect the assigned work item.",
                        output_dir=directory,
                        log_dir=directory,
                        human_principal="employee-1",
                    )
            self.assertEqual(
                [step["semantic_action"] for step in result.semantic_steps],
                ["plan_created", "execution_verified"],
            )
            self.assertTrue(all(step["task_id"] for step in result.semantic_steps))
            with open(
                os.path.join(directory, "harness_events.jsonl"), encoding="utf-8"
            ) as handle:
                events = [json.loads(line) for line in handle]
            self.assertEqual(
                {event["agent_id"] for event in events if "agent_id" in event},
                {"enterprise-workflow-agent"},
            )

    def test_hierarchy_uses_company_role_tree_and_stable_leader(self):
        with tempfile.TemporaryDirectory() as directory:
            company_path = os.path.join(directory, "company.json")
            with open(company_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {"engineering": {"roles": [{"abbr": "eng"}]}, "support": {"roles": [{"abbr": "hr"}]}},
                    handle,
                )
            role_map = load_role_department_map(company_path)
            hierarchy = build_hierarchy(
                [
                    {"id": "eng-2", "name": "B", "role": "Engineer"},
                    {"id": "eng-1", "name": "A", "role": "Lead Engineer"},
                    {"id": "hr-1", "name": "C", "role": "HR"},
                ],
                role_map,
            )
            self.assertEqual(hierarchy["departments"][0]["leader_id"], "eng-1")
            self.assertEqual(len(hierarchy["departments"]), 2)

    def test_skill_memory_retrieves_and_redacts(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = SkillMemory(directory)
            for _ in range(3):
                memory.record(
                    "search the browser and send a mail",
                    "1. Search the browser\n2. password: secret-value\n3. Verify the result",
                    member_id="eng-1",
                )
            skill = memory.retrieve("send a mail and search the browser")
            self.assertIsNotNone(skill)
            self.assertIn("[REDACTED]", " ".join(skill["steps"]))

    def test_skill_memory_waits_for_recurrence_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = SkillMemory(directory, min_recurrence=3)
            first = memory.record("repeat the queue review", "Inspect and verify", member_id="eng-1")
            second = memory.record("repeat the queue review", "Inspect and verify", member_id="eng-1")
            self.assertFalse(first["skill_created"])
            self.assertFalse(second["skill_created"])
            self.assertIsNone(memory.retrieve("repeat the queue review"))
            third = memory.record("repeat the queue review", "Inspect and verify", member_id="eng-1")
            self.assertTrue(third["skill_created"])
            self.assertIsNotNone(memory.retrieve("repeat the queue review"))


if __name__ == "__main__":
    unittest.main()
