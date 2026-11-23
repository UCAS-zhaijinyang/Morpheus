# Morpheus: Auditable Enterprise Behavior Simulation for Agent-Mediated Insider Threats

[![NDSS 2026](https://img.shields.io/badge/NDSS-2026-blue)](https://www.ndss-symposium.org/)
[![Paper](https://img.shields.io/badge/Paper-PDF-red)](https://www.ndss-symposium.org/wp-content/uploads/2026-f375-paper.pdf)
[![Slides](https://img.shields.io/badge/Slides-PDF-orange)](https://www.ndss-symposium.org/wp-content/uploads/F0375-Yu-slides.pdf)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This repository contains the source code for the paper:

> **Morpheus: Auditable Enterprise Behavior Simulation for Agent-Mediated Insider Threats**
> Research prototype derived from the Chimera NDSS 2026 simulator

## Overview

![Morpheus Overview](assets/overview.png)

Morpheus is a multi-agent LLM-driven simulation framework that automatically generates realistic insider threat datasets. It models a virtual organization as a society of LLM agents, where each with a distinct role, personality, and tool access, and orchestrates both normal daily operations and adversarial insider attack behaviors. The collected logs can be served as labeled ground-truth data for insider threat detection research.

## Morpheus-Harness research prototype

The current research direction is being reframed as Organizational Behavior Trajectory Generation (OBTG): an organizational agent harness that generates enterprise-like trajectories under hierarchy, authority, memory, and tool constraints. The ICML 2027 innovation audit, literature trail, method gap, and acceptance gates are tracked in [`docs/research_road_icml2027.html`](docs/research_road_icml2027.html); the earlier iteration is retained in [`docs/research_road.html`](docs/research_road.html). The 100-employee, three-month engineering practice is recorded in [`docs/engineering_roadmap_100x3m.html`](docs/engineering_roadmap_100x3m.html).

The new runtime artifacts are `hierarchy.json`, `behavior_policy.csv`, `harness_events.jsonl`, and per-member `skills/` files. The default offline tool mode remains the safe setting for experiments.

---

## Table of Contents

- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Simulation](#running-the-simulation)
  - [Phase 1: Agent Society Construction](#phase-1-agent-society-construction)
  - [Phase 2: Normal Behavior Simulation](#phase-2-normal-behavior-simulation)
  - [Phase 3: Attack Simulation](#phase-3-attack-simulation)
- [Log Collection](#log-collection)
- [Threat Scenario Format](#threat-scenario-format)
- [DeepSeek Harness runtime](#deepseek-harness-runtime)
- [Cleanup](#cleanup)
- [Citation](#citation)
- [Community Contributions](#community-contributions)

---

## Repository Structure

```
Morpheus/
├── src/           
│   ├── config.py                  
│   ├── foundation_model.py       
│   ├── company_profile_automation.py
│   ├── profile_generation.py
│   ├── meeting_for_weekly_goal_auto.py
│   ├── post_meeting_summary_auto.py
│   ├── daily_plan_generation_auto.py
│   ├── daily_plan_update.py
│   ├── daily_execution_auto.py     # Normal daily simulation entry point
│   ├── daily_execution_auto_attack.py  # Attack-injected simulation entry point
│   ├── attack_schedule.py          
│   ├── daily_attack_schedule.py
│   ├── task.py                    # Employee task entry point
│   ├── deepseek_harness_adapter.py # DeepSeek Harness bridge
│   ├── member_email.py            
│   └── random_browse.py            
├── attacks/                        # Primary threat family definitions
├── config_template/                # Template files for new scenarios
│   ├── env.jsonc                   
│   ├── member.jsonc                
│   └── log.csv                     
├── scripts/                        # Automation shell scripts
│   ├── daily_execution.sh          # Orchestrate multi-day simulation with log capture
│   ├── attack_auto.sh              # Automate attack-day execution
│   └── exit_checker.sh             # Process watchdog for simulation runs
└── requirements.txt                # DeepSeek Harness SDK dependency
```

---

## Prerequisites

- Docker (recommended) or a Python 3.10 environment on Ubuntu 22.04
- [sysdig](https://github.com/draios/sysdig) for system call capture (host machine)
- [tcpdump](https://www.tcpdump.org/) for network capture (host machine)
- [tmux](https://github.com/tmux/tmux) for session management
- A DeepSeek API key for the Harness runtime

---

## Installation

### 1. Launch Docker Container

From the Morpheus repository root:

```bash
sudo docker run --privileged -it \
  --name morpheus \
  -v $(pwd):/data \
  --network host \
  ubuntu:22.04 \
  /bin/bash
```

### 2. Install System Dependencies

```bash
apt update && apt upgrade -y
apt install -y build-essential git vim python3-pip tmux \
               chromium-browser python3-tk iproute2
```

### 3. Set Up Python Environment

```bash
pip install uv
uv venv .venv --python=3.10
source .venv/bin/activate
```

### 4. Install DeepSeek Harness

```bash
uv pip install -r requirements.txt
export DSH_HOME=/absolute/path/to/morpheus/.dsh
```

The Python SDK starts the local `dsh --profile sdk` runtime. Set
`MORPHEUS_DSH_HOME` when the Harness state should live outside `DSH_HOME`.
`MORPHEUS_DSH_MODEL` selects the runtime model. The adapter uses two Harness
sessions for complex work, one for the employee planner and one for the tool
agent, and records notifications in `harness_events.jsonl`.

The former `zips/camel` and `zips/owl` artifacts were removed from the working
tree because the current simulation does not import them.

---

## Configuration

All simulation parameters are controlled via `src/config.py`. Key settings to adjust before running:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `base_dir` | Absolute path to the Morpheus directory inside the container | `"/data/Morpheus"` |
| `scenario_name` | Name for this simulation run (output directory prefix) | `"morpheus_scenario_1"` |
| `company_id` | Identifier for the company JSON config file | `"medical_institution"` |
| `company_type` | Human-readable company type fed to the LLM | `"Medical Institution (Small Community Hospital)"` |
| `goal` | High-level organizational goal for the simulation | `"...complete EHR collection and influenza trend analysis..."` |
| `employee_number` | Number of simulated employees | `5` |
| `period` | Simulation duration in weeks | `2` |
| `base_date` | Start date of the simulation | `"2025-05-02"` |
| `workday_start` / `workday_end` | Logical workday boundary | `10:00` / `19:00` |
| `deepseek_harness_home` | Explicit Harness state directory | `"/data/Morpheus/.dsh"` |
| `deepseek_harness_profile` | Harness tool profile | `"sdk"` |
| `deepseek_harness_model` | Model selected by the Harness provider | `"deepseek-v4-flash"` |
| `loaf_rate` | Fraction of agents that loaf (browse aimlessly) per interval | `0.3` |

Set the DeepSeek API key in the environment used by the Harness runtime:

```bash
export DEEPSEEK_API_KEY=sk-...
export DSH_HOME=/absolute/path/to/morpheus/.dsh
```

---

## Running the Simulation

Activate the virtual environment before each session:

```bash
source /data/Morpheus/.venv/bin/activate
```

### Phase 1: Agent Society Construction

Execute the following steps in order. Each step reads `src/config.py` and writes output to the configured scenario directory.

**Step 1 - Generate company profile** (skip if providing your own):
```bash
python src/company_profile_automation.py
```

**Step 2 - Generate employee profiles:**
```bash
python src/profile_generation.py
```

**Step 3 - Conduct weekly planning meeting:**
```bash
python src/meeting_for_weekly_goal_auto.py
```

**Step 4 - Decompose meeting output into daily schedules:**
```bash
python src/post_meeting_summary_auto.py
```

### Phase 2: Normal Behavior Simulation

> **Warning:** Each simulated workday may consume a significant number of LLM tokens. Monitor your API usage carefully.

```bash
python src/daily_execution_auto.py --date <DAY> --week <WEEK_NUMBER>
# Example:
python src/daily_execution_auto.py --date Friday --week 1
```

For a long-horizon run, use the scale entry point after daily schedules have
been generated. It batches one employee's complete horizon into one auditable
human-planner/tool-agent hand-off, then replays every schedule event into
`trajectory.jsonl`, `behavior_policy.csv`, `final_schedule.csv`, and
`logon.csv`.

```bash
bash scripts/scale_simulation.sh

# Or override the scale parameters explicitly.
python src/scale_simulation.py \
  --weeks 13 \
  --employees 100 \
  --workers 8
```

The scale entry point assumes Monday through Friday workdays and reads
`MORPHEUS_WORKDAY_START` and `MORPHEUS_WORKDAY_END`, which default to `10:00`
and `19:00`. Use `--include-weekends` when the scenario treats all seven days
as working days. The completed run writes `manifest.json` under
`execution_logs/scale_horizon`.

Agent behavior CSVs are reconstructed from the persisted
`harness_events.jsonl`. Each row groups one Harness turn and step, preserving
high-level actions such as `tool_execute` and `agent_decision` without another
model call. Rebuild them after an existing run with:

```bash
python src/scale_simulation.py \
  --output-dir /absolute/path/to/execution_logs/scale_horizon \
  --rebuild-agent-csv
```

To automate multi-day execution with concurrent log collection:

```bash
bash scripts/daily_execution.sh
```

### Phase 3: Attack Simulation

> **Warning:** Each simulated workday may consume a significant number of LLM tokens. Monitor your API usage carefully.

**Step 1 - Select the optimal attack date and inject the attacker into the schedule** (called automatically by `attack_auto.sh`, but can be run manually):

```bash
python src/attack_schedule.py --attacker <AGENT_ID> --attid <ATTACK_ID>
# Example:
python src/attack_schedule.py --attacker clia-1 --attid threat_ai_data_boundary
```

**Step 2 - Run the attack-injected simulation for the selected date:**

```bash
python src/daily_execution_auto_attack.py --attacker <AGENT_ID> --attid <ATTACK_ID>
# Example:
python src/daily_execution_auto_attack.py --attacker clia-1 --attid threat_ai_data_boundary
```

To automate the full attack run:

```bash
bash scripts/attack_auto.sh
```

---

## Log Collection

Sysdig (`.scap`) and tcpdump (`.pcap`) capture is integrated into `scripts/daily_execution.sh` and runs automatically per simulated workday. To collect manually:

**Network capture (pcap):**
```bash
CONTAINER_PID=$(docker inspect -f '{{.State.Pid}}' morpheus)
nsenter -t $CONTAINER_PID -n tcpdump -i any -w /data/Logs/<filename>.pcap
```

**System call capture (scap):**
```bash
CONTAINER_ID=$(docker ps -a | grep morpheus | awk '{print $1}')
sudo sysdig -v -b \
  -p "%evt.rawtime %user.uid %proc.pid %proc.name %syscall.type %evt.dir" \
  -w /data/Logs/<filename>.scap \
  container.id=$CONTAINER_ID
```

Post-processing extracts structured features (logon events, file operations, HTTP traffic, emails) from raw logs to match with CERT dataset format.

---

## Threat Scenario Format

The current experiments use three primary threat families. Their research basis and experiment design are documented in [`docs/threat_scenario_research_2027.html`](docs/threat_scenario_research_2027.html).

- `threat_ai_data_boundary` models an authorized employee using an AI assistant or external AI service to move sensitive information across a data boundary.
- `threat_cross_department_workflow` models legitimate project handoffs, temporary delegation, and approval relationships being combined to aggregate information across departments.
- `threat_skill_memory_contamination` models an obsolete, poisoned, or over-scoped procedural skill being reused by an Agent in a new authorization context.

Legacy `gen_attack_*` and `multi_attack_*` runtime files were removed from the working tree during cleanup. Primary scenarios use the same schedule injection and tool execution entry points, and extend the existing schema with threat-model and provenance fields.

Threat scenarios follow a structured JSON schema. Each step can map to [MITRE ATT&CK](https://attack.mitre.org/) or an AI security taxonomy such as the [OWASP GenAI Security Project](https://genai.owasp.org/llm-top-10/):

```json
{
  "attack_id": "threat_ai_data_boundary",
  "scenario_title": "AI-Mediated Data Boundary Abuse by an Authorized Employee",
  "type": "ai-mediated data boundary abuse",
  "who": { "role": "authorized employee", "origin": "internal" },
  "what": "use an AI workflow to transform sensitive data and disclose the result outside the authorized boundary",
  "when": { "frequency": "single or recurrent", "time_window": "work hours or during a normal task" },
  "where": ["enterprise data repositories", "AI assistant", "email or file sharing"],
  "why": { "motivation": ["convenience", "personal gain"], "details": "..." },
  "threat_model": { "attacker_capability": "...", "security_boundary": "..." },
  "research_questions": ["..."],
  "framework_refs": ["OWASP GenAI Security Project 2025"] ,
  "how": [
    {
      "step": 1,
      "tactic": "Initial Access",
      "technique_id": ["T1199", "T1078"],
      "technique_name": ["Trusted Relationship", "Valid Accounts"],
      "procedure": "...",
      "observable_evidence": [...],
      "detection_data_sources": [...]
    }
  ]
}
```

---

## DeepSeek Harness runtime

All model-backed generation goes through the DeepSeek Harness adapter. Set
`MORPHEUS_DSH_MODEL` to override the configured model and
`MORPHEUS_DSH_PROFILE=sdk` to enable the full Harness tool profile. With
`offline_mode=True`, the adapter selects `sdk-minimal` unless an explicit
profile override is supplied. This keeps the existing offline setting from
enabling web tools while preserving local workspace execution.

---

## Cleanup

The repository keeps source code, current threat definitions, research documents, and the deepseek-v4.1-flash experiment directories. Python caches, pytest caches, Harness temporary files, and obsolete standalone artifacts are excluded from the working tree. Generated scenario and experiment outputs are ignored by Git and should be archived separately when they are needed for analysis.

---

## Citation

If you use Morpheus in your research, cite the current Morpheus prototype and acknowledge the published Chimera predecessor:

```bibtex
@inproceedings{yu2026chimera,
  title     = {Chimera: Harnessing Multi-Agent LLMs for Automatic Insider Threat Simulation},
  author    = {Yu, Jiongchi and Xie, Xiaofei and Hu, Qiang and Ma, Yuhan and Zhao, Ziming},
  booktitle = {Proceedings of the Network and Distributed System Security Symposium (NDSS)},
  year      = {2026}
}
```

---

## Community Contributions

We welcome contributions from the community to extend and improve Morpheus. This includes, but is not limited to:

- Adding support for new applications or services in the simulated environment
- Introducing new insider threat attack scenarios (following the existing JSON schema)
- Improving agent behavior realism or expanding organizational role coverage

Feel free to open an issue or submit a pull request. We appreciate all forms of feedback and collaboration.
