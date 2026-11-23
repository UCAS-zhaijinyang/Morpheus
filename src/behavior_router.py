"""Fast intent gating for simulated employee behavior.

The router is deliberately lightweight.  It makes only the state transition
decision at the event boundary; complex work is still delegated to the
existing planner/executor society.  This keeps login/logout cheap while
preserving rich trajectories for mail, browsing, and work tasks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class BehaviorDecision:
    category: str
    action: str
    confidence: float
    reason: str
    requires_agent: bool
    execution_mode: str = "employee_personal"
    agent_type: str | None = None


@dataclass(frozen=True)
class _BehaviorIntent:
    """The action and complexity classification before executor selection."""

    category: str
    action: str
    confidence: float
    reason: str


class BehaviorRouter:
    """A deterministic, testable fast path before agent execution."""

    def __init__(self, loaf_rate: float = 0.3, rng: Callable[[], float] | None = None):
        self.loaf_rate = max(0.0, min(1.0, float(loaf_rate)))
        self.rng = rng

    @staticmethod
    def _classify_activity(text: str) -> _BehaviorIntent:
        """Classify an activity as simple or complex before choosing an executor."""

        if any(token in text for token in ("break", "logout", "log out", "休息", "下班")):
            return _BehaviorIntent("simple", "logout", 0.99, "explicit session boundary")
        if "@" in text or any(
            token in text
            for token in ("send email", "email to", "reply to", "发邮件", "回复邮件")
        ):
            return _BehaviorIntent(
                "complex", "email", 0.96, "communication requires content generation"
            )
        if any(token in text for token in ("loafbrowsing", "browse", "摸鱼", "闲逛")):
            return _BehaviorIntent(
                "complex", "loaf", 0.95, "open-ended browsing requires an agent"
            )
        if any(token in text for token in ("login", "log in", "登入", "登录")) and not any(
            token in text for token in ("check", "review", "open", "task", "and")
        ):
            return _BehaviorIntent("simple", "login", 0.99, "explicit session start")
        return _BehaviorIntent(
            "complex", "task", 0.90, "goal-directed work requires planning and execution"
        )

    @staticmethod
    def _select_agent_route(action: str) -> tuple[str, str]:
        """Select the Agent family only after complexity is known."""

        if action == "loaf":
            return "personal_agent", "personal"
        return "enterprise_agent", "enterprise"

    @classmethod
    def _build_decision(cls, intent: _BehaviorIntent) -> BehaviorDecision:
        if intent.category == "simple":
            return BehaviorDecision(
                intent.category,
                intent.action,
                intent.confidence,
                intent.reason,
                False,
                "employee_personal",
                "employee",
            )
        execution_mode, agent_type = cls._select_agent_route(intent.action)
        return BehaviorDecision(
            intent.category,
            intent.action,
            intent.confidence,
            intent.reason,
            True,
            execution_mode,
            agent_type,
        )

    def route_activity(self, activity: str, logged_in: bool = False) -> BehaviorDecision:
        del logged_in
        text = str(activity or "").strip().lower()
        intent = self._classify_activity(text)
        return self._build_decision(intent)

    def route_gap(self, gap_minutes: float) -> BehaviorDecision:
        """Choose an AFK state transition for a long idle interval."""

        if gap_minutes <= 0:
            return self._build_decision(
                _BehaviorIntent("simple", "stay", 1.0, "no idle interval")
            )
        draw = self.rng() if self.rng is not None else 0.5
        if draw < self.loaf_rate:
            return self._build_decision(
                _BehaviorIntent(
                    "complex", "loaf", self.loaf_rate, "stochastic idle browsing"
                )
            )
        return self._build_decision(
            _BehaviorIntent(
                "simple",
                "logout",
                1.0 - self.loaf_rate,
                "stochastic inactive session",
            )
        )
