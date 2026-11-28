# ========= Copyright (c) 2026 TTFISH. Licensed under the MIT License. =========
# See the LICENSE file in the project root for the full license text.
#
# SPDX-License-Identifier: MIT
# ===============================================================================
"""Compatibility wrapper for structured calls through DeepSeek Harness."""

from __future__ import annotations

from deepseek_runtime import run_prompt, run_text_prompt


def run_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0,
    *,
    role: str = "structured_generator",
) -> str:
    """Run a lightweight model request through the same Harness as tasks."""

    if role == "employee":
        return run_text_prompt(system_prompt, user_prompt, role=role)
    return run_prompt(
        system_prompt,
        user_prompt,
        temperature=temperature,
        role=role,
    )
