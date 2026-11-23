# ========= Copyright (c) 2026 TTFISH. Licensed under the MIT License. =========
# See the LICENSE file in the project root for the full license text.
#
# SPDX-License-Identifier: MIT
# ===============================================================================
"""Weekly planning entry point backed by DeepSeek Harness."""

from __future__ import annotations

import config
from hierarchical_meeting import run_flat_weekly_plan, run_hierarchical_weekly_plan


def WeeklyPlan(member_dir: str):
    """Generate the weekly plan using hierarchical planning by default."""

    if getattr(config, "hierarchical_planning", True):
        return run_hierarchical_weekly_plan(member_dir)
    return run_flat_weekly_plan(member_dir)


if __name__ == "__main__":
    WeeklyPlan(config.profile_output_dir)
