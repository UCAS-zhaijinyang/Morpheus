# ========= Copyright (c) 2026 TTFISH. Licensed under the MIT License. =========
# See the LICENSE file in the project root for the full license text.
#
# SPDX-License-Identifier: MIT
# ===============================================================================
"""Standalone browsing task entry point for DeepSeek Harness."""

from __future__ import annotations

import sys

import config
from deepseek_harness_adapter import run_human_tool_task
from deepseek_search import DeepSeekSearchError, format_search_context, search_web
from task import HarnessTask


def construct_harness(question: str):
    """Return a Harness task payload for compatibility with old callers."""

    return HarnessTask(question=question, output_dir=config.execution_log_dir)


construct_society = construct_harness


def main() -> None:
    task = sys.argv[1] if len(sys.argv) > 1 else (
        "Browse the permitted workspace resources and summarize one relevant item."
    )
    try:
        search_context = format_search_context(search_web(task))
    except DeepSeekSearchError as error:
        search_context = f"DeepSeek Search was unavailable: {error}"
    task = f"""{task}

DeepSeek Search results to ground the browsing summary:
{search_context}
"""
    result = run_human_tool_task(
        task,
        output_dir=config.execution_log_dir,
        log_dir=config.execution_log_dir,
        session_prefix="morpheus-browse",
    )
    print(f"Answer: {result.answer}")


if __name__ == "__main__":
    main()
