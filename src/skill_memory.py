"""File-backed procedural skill memory for simulated employees.

Skills contain only compact workflow metadata and sanitized step snippets.  No
credentials or tool arguments are persisted.  The store uses a recurrence
threshold so one-off schedule events remain observations instead of becoming
reusable procedures.  It can be used in the existing simulation without
changing the model or adding a training phase.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import fcntl
from datetime import datetime, timezone
from typing import Any


STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "task", "please",
    "you", "your", "into", "then", "have", "will", "are", "today",
}


def _terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_\u4e00-\u9fff]{3,}", str(text).lower())
        if token not in STOPWORDS
    }


def _safe_snippets(answer: str, limit: int = 6) -> list[str]:
    snippets = []
    for line in str(answer or "").splitlines():
        line = re.sub(r"\s+", " ", line).strip(" -*\t")
        line = re.sub(
            r"(?i)(password|api[_ -]?key|token|secret)\s*[:=]\s*\S+",
            r"\1=[REDACTED]",
            line,
        )
        if line and len(line) >= 8:
            snippets.append(line[:240])
        if len(snippets) >= limit:
            break
    return snippets or ["Re-plan the task, execute the required tools, and verify the result."]


class SkillMemory:
    def __init__(self, root_dir: str, min_recurrence: int = 3):
        self.root_dir = os.path.abspath(root_dir)
        self.min_recurrence = max(1, int(min_recurrence))
        os.makedirs(self.root_dir, exist_ok=True)

    def _files(self) -> list[str]:
        return sorted(
            os.path.join(self.root_dir, name)
            for name in os.listdir(self.root_dir)
            if name.startswith("skill_") and name.endswith(".json")
        )

    def retrieve(self, task: str) -> dict[str, Any] | None:
        query = _terms(task)
        if not query:
            return None
        best: tuple[float, dict[str, Any]] | None = None
        for path in self._files():
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    skill = json.load(handle)
            except (OSError, ValueError):
                continue
            score = len(query & set(skill.get("trigger_terms", []))) / max(len(query), 1)
            if score >= 0.25 and (best is None or score > best[0]):
                best = (score, skill)
        if best is None:
            return None
        result = dict(best[1])
        result["retrieval_score"] = round(best[0], 3)
        return result

    @staticmethod
    def context(skill: dict[str, Any] | None) -> str:
        if not skill:
            return "No reusable procedural skill was retrieved."
        steps = "\n".join(f"- {step}" for step in skill.get("steps", []))
        return (
            f"Reusable skill: {skill.get('name', 'unnamed')}\n"
            f"Precondition: {skill.get('precondition', 'similar task context')}\n"
            f"Observed steps:\n{steps}\n"
            "Adapt the skill to the current intent and verify every result."
        )

    def record(
        self,
        task: str,
        answer: str,
        *,
        member_id: str = "",
        event_index: int | str = "",
    ) -> dict[str, Any]:
        """Record one observation under an inter-process exclusive lock."""

        lock_path = os.path.join(self.root_dir, ".skill_memory.lock")
        with open(lock_path, "a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                return self._record(
                    task,
                    answer,
                    member_id=member_id,
                    event_index=event_index,
                )
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def _record(
        self,
        task: str,
        answer: str,
        *,
        member_id: str = "",
        event_index: int | str = "",
    ) -> dict[str, Any]:
        trigger_terms = sorted(_terms(task))[:24]
        digest = hashlib.sha1(" ".join(trigger_terms).encode("utf-8")).hexdigest()[:12]
        path = os.path.join(self.root_dir, f"skill_{digest}.json")
        observation_path = os.path.join(self.root_dir, "observations.json")
        observations: dict[str, Any] = {}
        if os.path.exists(observation_path):
            try:
                with open(observation_path, "r", encoding="utf-8") as handle:
                    observations = json.load(handle)
            except (OSError, ValueError):
                observations = {}
        observation_key = f"{member_id}:{digest}"
        previous_skill: dict[str, Any] = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    previous_skill = json.load(handle)
            except (OSError, ValueError):
                previous_skill = {}
        recurrence_count = max(
            int(observations.get(observation_key, {}).get("recurrence_count", 0)),
            int(previous_skill.get("uses", 0)),
        ) + 1
        observations[observation_key] = {
            "member_id": member_id,
            "trigger_terms": trigger_terms,
            "recurrence_count": recurrence_count,
            "last_event": str(event_index),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        fd, tmp_path = tempfile.mkstemp(
            prefix=".observations_", suffix=".tmp", dir=self.root_dir
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(observations, handle, indent=2, ensure_ascii=False)
            os.replace(tmp_path, observation_path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        if recurrence_count < self.min_recurrence:
            return {
                "name": None,
                "member_id": member_id,
                "trigger_terms": trigger_terms,
                "recurrence_count": recurrence_count,
                "min_recurrence": self.min_recurrence,
                "skill_created": False,
                "skill_available": False,
                "last_event": str(event_index),
            }

        created_at = previous_skill.get("skill_created_at") or datetime.now(timezone.utc).isoformat()
        skill = {
            "name": f"procedural_{digest}",
            "member_id": member_id,
            "trigger_terms": trigger_terms,
            "precondition": "a task with overlapping intent and available tools",
            "steps": _safe_snippets(answer),
            "tool_profile": [
                tool for tool, token in {
                    "mail": "mail",
                    "browser": "browser",
                    "file": "file",
                    "terminal": "terminal",
                    "search": "search",
                }.items() if token in _terms(task) or token in _terms(answer)
            ],
            "uses": recurrence_count,
            "recurrence_count": recurrence_count,
            "min_recurrence": self.min_recurrence,
            "skill_created": True,
            "skill_created_at": created_at,
            "last_event": str(event_index),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        skill_created = not os.path.exists(path)
        fd, tmp_path = tempfile.mkstemp(prefix=".skill_", suffix=".tmp", dir=self.root_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(skill, handle, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        skill["skill_created"] = skill_created
        return skill
