# ========= Copyright (c) 2026 TTFISH. Licensed under the MIT License. =========
# See the LICENSE file in the project root for the full license text.
#
# SPDX-License-Identifier: MIT
# ===============================================================================
"""Weekly planning entry point backed by DeepSeek Harness."""

from __future__ import annotations

import config
from hierarchical_meeting import run_hierarchical_weekly_plan


def WeeklyPlan(member_dir: str):
    """Coordinate the department heads, then assign member goals by department."""

    return run_hierarchical_weekly_plan(member_dir)


if __name__ == "__main__":
    WeeklyPlan(config.profile_output_dir)
