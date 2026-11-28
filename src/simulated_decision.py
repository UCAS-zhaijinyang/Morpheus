"""Text-only work-card decisions and receipt summaries through DeepSeek Harness."""
from __future__ import annotations

from dataclasses import dataclass
import json

from json_utils import strip_code_fences

_CHOICES = {"issued_order": "retain_baseline", "observed_updates": "adopt_fixture"}
_ROLE = (
    "You are the employee's simulated assistant processing a work card. "
    "Read the issued order, conversation and the sources you consulted. A workflow skill "
    "describes a procedure. Memory and filing history describe prior work. "
    "Choose issued_order to keep the values as issued, or observed_updates to apply "
    "subsequent changes. When adopting updates for a single card, a recalled receipt "
    "summary for the same employee, card and workflow supplies its status unless "
    "current evidence revises that status. Keep the current recipient and card list "
    "when using a receipt summary. Return one JSON object with the single key \"use\" "
    "and the chosen string value."
)


@dataclass(frozen=True)
class DeepSeekHarnessPolicy:
    model: str | None = None

    def _chat(self, system_prompt, material, stub_response):
        from deepseek_runtime import run_text_prompt

        return run_text_prompt(
            system_prompt,
            json.dumps(material, ensure_ascii=False),
            model=self.model,
            stub_response=stub_response,
        )

    def acknowledge(self, order, conversation):
        return self._chat(
            "Acknowledge the latest work-card request in one sentence. "
            "Refer only to details received so far.",
            {"issued_order": order, "conversation": conversation},
            "Received the work-card request.",
        )

    def plan_reads(self, order, conversation, tools):
        from enterprise_harness import READ_TOOLS

        response = self._chat(
            "Choose the simulated services you need before filing this employee's work note. "
            "Return one JSON object with key \"reads\" and an ordered list of distinct names "
            "from the supplied tool directory. An empty list is allowed.",
            {"issued_order": order, "conversation": conversation,
             "tool_directory": {name: READ_TOOLS[name] for name in tools}},
            json.dumps({"reads": tools}),
        )
        try:
            plan = json.loads(strip_code_fences(response))
            if not isinstance(plan, dict) or set(plan) != {"reads"} or not isinstance(plan["reads"], list):
                raise ValueError("expected a read plan")
        except (TypeError, ValueError) as exc:
            raise ValueError("DeepSeek Harness did not return a work-card read plan") from exc
        return plan["reads"]

    def __call__(self, visible):
        response = self._chat(_ROLE, visible, '{"use":"issued_order"}')
        try:
            choice = json.loads(strip_code_fences(response))
            if not isinstance(choice, dict) or set(choice) != {"use"}:
                raise ValueError("expected one choice")
            decision = _CHOICES[choice["use"]]
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("DeepSeek Harness did not return a supported work-card choice") from exc
        return {"decision": decision, "reason_code": "work_card_choice"}

    def finalize(self, visible, receipt):
        return self._chat(
            "Report to the employee in one sentence what the simulated work-card service "
            "recorded. Ground your reply in its final receipt.",
            {"work_order": visible["issued_order"], "service_receipt": receipt},
            f'The work-card service recorded the status {receipt["status"]}.',
        )
