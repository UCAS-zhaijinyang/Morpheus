# Morpheus-Harness

Morpheus-Harness generates auditable enterprise work trajectories. Department heads coordinate goals and dependencies, departments assign weekly goals, and employee daily schedules drive one unified employee-to-Agent execution chain. The chain uses a DeepSeek Harness decision backend with simulated retrieval, workflow skills, private Agent memory, business tools, and JSONL audit records.

## Repository structure

```text
Morpheus-Harness/
├── src/
│   ├── harness_runner.py              # unified schedule-driven execution entry point
│   ├── employee_agent_runtime.py      # employee → Agent activity simulation
│   ├── enterprise_harness.py          # tools, skills, memory, and enterprise state
│   ├── enterprise_retrieval.py        # embedded RAG connector
│   ├── rag_service.py                 # optional HTTP RAG service
│   ├── deepseek_runtime.py            # DeepSeek Harness SDK bridge
│   ├── audit_log.py                   # auditable event persistence
│   ├── csv_exports.py                  # Chimera-style flat CSV projections
│   ├── person_day_dataset.py           # separated CSV → person-day dataset
│   ├── trajectory_recording.py        # employee/full recording projections
│   ├── scenario_catalog.py            # 15-scenario catalog loader and validator
│   ├── department_goal_coordination.py
│   ├── weekly_goal_distribution.py
│   └── daily_schedule_generation.py
├── threat_scenarios/                  # declarative internal-threat scenarios
├── config/                            # default Harness and enterprise fixtures
├── scripts/                           # run_daily.sh, run_horizon.sh, run_scenarios.sh
├── tests/
└── docs/
    ├── paper/                          # manuscript and experiment drafts
    ├── internal_threat_modeling_matrix.md
    └── internal_threat_injection_references.txt
```

The command line has one schedule executor and one recording selector. `employee` keeps employee activity only, while `full` keeps the complete employee-to-Agent trace.

## Installation

Use Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The Harness provider reads `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `MORPHEUS_DSH_PROVIDER`, and `MORPHEUS_DSH_MODEL`. A deterministic local policy is available for replay and tests with `--agent-backend symbolic`.

## Planning and schedules

```bash
python src/organization_profile_generation.py
python src/profile_generation.py
python src/department_goal_coordination.py
python src/weekly_goal_distribution.py
python src/daily_schedule_generation.py
```

The planner writes daily files under `init_schedule/week_<n>/`. Each row carries `department`, `department_head`, and `planning_protocol` when those values are available.

## Execution

Both recording levels execute the same schedule-driven chain. The level controls persisted trajectory detail.

```bash
python src/execute_daily_schedule.py --week 1 --date Monday --recording employee
python src/execute_daily_schedule.py --week 1 --date Monday --recording full
python src/execute_horizon.py --weeks 2 --recording full
```

`employee` JSONL records contain only `schema_version`, `recording`, `trace_id`, and the employee activity object. Agent memory is not persisted for an employee recording. `full` JSONL records retain the employee activity, prompt draft, actual employee messages, planning context, scenario metadata, Agent input and output, decisions, tool calls, tool results, retrieval payloads, skills, memory, service state, and causal events. Full runs checkpoint Agent memory at `.state/<employee>/memory.json`, which can be supplied to a later full run with `--previous-run`.

Each activity is written to `<employee>/week_<n>/<day>.jsonl`. The effective schedule snapshot is written atomically to the matching `<day>.schedule.json`, so multiple employees and days never overwrite each other. Input schedule files remain available as the unmodified baseline.

After a run completes, the nested JSONL remains the canonical audit record and the runner also writes flat CSV projections at the run root. Every run contains `employee_day.csv`, `final_schedule.csv`, `logon.csv`, `email.csv`, and `threat_labels.csv`. Full recordings additionally contain `agent_prompt.csv`, `agent_activity.csv`, `agent_tool.csv`, `rag.csv`, `skill.csv`, `memory.csv`, and `effect.csv`. The login and email views are created with headers and remain empty when the simulated day has no such events. Existing runs can be projected without rerunning the model.

```bash
PYTHONPATH=src python -c \
  "from csv_exports import export_run_csvs; export_run_csvs('/path/to/run', 'full')"
```

The runner then assembles those separated views into `person_day_dataset/`. `person_day.jsonl` stores one complete nested record for each employee-week-day, `person_day.csv` stores one flat observation row per employee-week-day, and `person_day_labels.csv` stores scenario and intervention ground truth separately. `person_day_manifest.json` records the aggregation counts and output paths. Existing completed runs can be processed without another model call.

```bash
PYTHONPATH=src python src/person_day_dataset.py /path/to/run \
  --output-dir /path/to/person_day_dataset
```

## Attack placement

The active catalog has 15 scenarios.

```bash
python src/scenario_catalog.py
python src/execute_daily_schedule.py --week 1 --date Monday --recording full \
  --employee clia-1 --activity-index 0 --scenario conflicting_record
```

For `employee`, the selected schedule row is replaced by its catalog `employee_activity` text and marked with `Attack` and `AttackScenario` in the effective schedule snapshot. The Agent environment receives no scenario intervention.

For `full`, the selected schedule row remains unchanged. The scenario is applied to the configured downstream surface, which can be a single- or multi-turn employee prompt, retrieved document, tool result, workflow skill, or Agent memory. The resulting trace records the source payload, visible payload, intervention event, Agent decision, service receipt, and memory write when applicable.

Use `--rag-corpus FILE` for an embedded corpus, `--rag-url URL` for the local read-only RAG service, and `--skill-catalog FILE` for another declarative workflow catalog. `scripts/run_scenarios.sh` iterates over the active catalog.

## Threat model artifacts

The 15 scenarios are grouped by consequence and input surface. The consequence labels are disclosure, unauthorized collection, integrity loss, and availability loss. The surfaces are employee prompts, retrieved documents, tool results, workflow skills, and Agent memory. The complete mapping, access assumptions, observable effects, and references are in the [modeling matrix](docs/internal_threat_modeling_matrix.md) and [reference list](docs/internal_threat_injection_references.txt).

Single-turn and multi-turn are Prompt-only fields. RAG uses fact, ranking, and document-rule mechanisms. Tool results use value, result-set, and status mechanisms. Skills use procedure and scope mechanisms. Memory uses write, retrieval, and persistence mechanisms.

## Verification

```bash
python -m pytest -q
python -m compileall -q src tests
for file in scripts/*.sh; do bash -n "$file"; done
```

The current regression suite covers the hierarchical planning path, all 15 catalog entries, RAG behavior, Harness primitives, both recording projections, schedule snapshots, and employee/full attack semantics.
