"""Execution entry points for one employee–Agent simulation chain.

The recording level controls how much of the chain is persisted. It never
selects a different executor.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import json5

import config
from schedule_constraints import planning_source

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def build_parser(*, horizon=False, require_scenario=False):
    parser = argparse.ArgumentParser(description="Execute previously generated employee schedules.")
    parser.add_argument("--recording", choices=("employee", "full"), default="full",
                        help="amount of simulated behavior persisted (employee or full)")
    parser.add_argument("--profile-dir", type=Path, default=Path(config.profile_output_dir))
    parser.add_argument("--schedule-dir", type=Path, default=Path(config.init_schedule_dir))
    parser.add_argument("--output-dir", type=Path, default=Path(config.execution_log_dir))
    parser.add_argument("--scenario", required=require_scenario, help="catalog ID applied to one scheduled activity")
    parser.add_argument("--employee", help="recipient of the scenario, required for multi-employee runs")
    parser.add_argument("--activity-index", type=int, default=0, help="zero-based index within the selected day")
    parser.add_argument("--agent-backend", choices=("deepseek_harness", "symbolic"),
                        default="deepseek_harness",
                        help="employee-agent decision backend (default: DeepSeek Harness)")
    parser.add_argument("--agent-model", metavar="MODEL",
                        help="optional DeepSeek Harness model override")
    retrieval = parser.add_mutually_exclusive_group()
    retrieval.add_argument("--rag-corpus", type=Path, help="read an enterprise document corpus from JSON")
    retrieval.add_argument("--rag-url", help="retrieve documents from a running local Morpheus-Harness RAG service")
    parser.add_argument("--skill-catalog", type=Path, help="load workflow procedures from this JSON catalog")
    parser.add_argument("--previous-run", type=Path,
                        help="load Agent memory from a completed unified run")
    if horizon:
        parser.add_argument("--weeks", type=positive, default=config.period)
        parser.add_argument("--start-week", type=positive, default=1, help="first week of the execution horizon")
        parser.add_argument("--employees", type=positive, help="limit to the first N profiles by filename")
        parser.add_argument("--workers", type=positive, default=config.scale_worker_count,
                            help="number of employees processed concurrently")
        parser.add_argument("--include-weekends", action="store_true")
        parser.add_argument("--allow-missing-schedules", action="store_true")
        parser.add_argument("--scenario-week", type=positive, help="default is the first week of the horizon")
        parser.add_argument("--scenario-day", choices=DAYS, help="default is the first configured workday")
    else:
        parser.add_argument("--week", type=positive, required=True)
        parser.add_argument("--date", choices=DAYS, required=True)
    return parser


def _profile_list(directory, limit):
    paths = sorted(directory.glob("*.jsonc"))
    if not paths:
        raise ValueError(f"no employee profiles in {directory}")
    if limit and len(paths) < limit:
        raise ValueError(f"requested {limit} employees, found {len(paths)}")
    profiles = []
    for path in paths[:limit]:
        with path.open(encoding="utf-8") as handle:
            profile = json5.load(handle)
        if not isinstance(profile, dict) or profile.get("id") != path.stem:
            raise ValueError(f"profile id must match its filename: {path}")
        profiles.append(profile)
    return profiles


def read_schedule(path, day):
    """Read original event order, exact times, and legacy single-day wrappers."""
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        if day in data:
            data = data[day]
        elif len(data) == 1:
            data = next(iter(data.values()))
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a list of activities for {day}")
    for index, row in enumerate(data):
        if not isinstance(row, dict) or not isinstance(row.get("Activity"), str) or not row["Activity"].strip():
            raise ValueError(f"{path}: invalid Activity at index {index}")
        if not isinstance(row.get("Time"), str) or not row["Time"].strip():
            raise ValueError(f"{path}: invalid Time at index {index}")
    return data


@dataclass
class AgentDay:
    output: Path
    profile: dict
    week: int
    day: str
    rows: list[dict]
    run_id: str
    selected_index: int | None
    scenario: dict | None

    def trace_id(self, index):
        slot = [self.run_id, self.profile["id"], self.week, self.day, index]
        return str(uuid5(NAMESPACE_URL, json.dumps(slot)))


def _record_for_level(record, recording):
    """Persist a detail projection without changing the simulation result."""
    from trajectory_recording import project_trace

    return project_trace(record, recording)


def _agent_day(job, agent_policy, model_context, harness, previous, recording="full"):
    from employee_agent_runtime import append_activity_trace, simulate_activity

    job.output.parent.mkdir(parents=True, exist_ok=True)
    schedule_snapshot = job.output.with_name(f"{job.day}.schedule.json")
    snapshot_partial = schedule_snapshot.with_suffix(".partial.json")
    snapshot_partial.write_text(json.dumps(job.rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    snapshot_partial.replace(schedule_snapshot)
    partial = job.output.with_suffix(".partial.jsonl")
    partial.touch(exist_ok=False)
    try:
        for index, row in enumerate(job.rows):
            context = {
                "run_id": job.run_id, "week": job.week, "date": job.day, "schedule_index": index,
                "trace_id": job.trace_id(index), "previous_activity_trace_id": previous,
                "organization_id": config.company_id, "role": job.profile.get("role", ""),
                "department": job.profile.get("department", ""), **planning_source(row), **model_context,
            }
            record = simulate_activity(
                employee_id=job.profile["id"], activity=row["Activity"], sim_time=row["Time"],
                scenario=job.scenario if index == job.selected_index else None, context=context,
                agent_policy=agent_policy, harness=harness,
                apply_environment_intervention=(recording == "full"),
            )
            append_activity_trace(partial, _record_for_level(record, recording))
            previous = record["trace_id"]
        partial.replace(job.output)
    finally:
        partial.unlink(missing_ok=True)
    return previous


def _employee_agent_days(employee, jobs, agent_policy, model_context, knowledge_base, skills_path,
                         run_dir, prior_dir, recording="full"):
    from enterprise_harness import EnterpriseHarness

    harness = EnterpriseHarness(employee, knowledge_base=knowledge_base, skills_path=skills_path)
    previous = None
    if prior_dir is not None and recording == "full":
        saved_path = prior_dir / ".state" / employee / "memory.json"
        if not saved_path.is_file():
            raise ValueError("previous run has no Agent memory checkpoint")
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        harness.restore_memory(saved)
        if saved["records"]:
            previous = saved["records"][-1]["source_trace_id"]
    count = 0
    for day in jobs:
        previous = _agent_day(day, agent_policy, model_context, harness, previous, recording)
        count += len(day.rows)
    if recording == "full":
        destination = run_dir / ".state" / employee / "memory.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(".partial")
        snapshot = json.dumps(harness.export_memory(), ensure_ascii=False) + "\n"
        partial.write_text(snapshot, encoding="utf-8")
        partial.replace(destination)
    return count


def run_schedules(args, *, horizon=False):
    if (args.employee or args.activity_index != 0) and not args.scenario:
        raise ValueError("--employee and --activity-index select a --scenario placement")
    if args.agent_model is not None and (not args.agent_model.strip() or args.agent_backend == "symbolic"):
        raise ValueError("--agent-model requires a DeepSeek Harness model name and backend")
    recording = args.recording
    previous = None
    if args.previous_run is not None:
        previous = json.loads((args.previous_run / "manifest.json").read_text(encoding="utf-8"))
        if previous.get("status") != "completed":
            raise ValueError("previous run must be completed")
    if args.activity_index < 0:
        raise ValueError("--activity-index must be non-negative")
    profiles = _profile_list(args.profile_dir, args.employees if horizon else None)
    if horizon:
        days = DAYS if args.include_weekends else config.work_days
        if not days or len(set(days)) != len(days) or any(day not in DAYS for day in days):
            raise ValueError(f"invalid workday configuration: {days}")
        days = sorted(days, key=DAYS.index)
        calendar = [(week, day) for week in range(args.start_week, args.start_week + args.weeks) for day in days]
        chosen_date = (args.scenario_week or args.start_week, args.scenario_day or days[0])
    else:
        calendar = [(args.week, args.date)]
        chosen_date = calendar[0]

    if previous:
        if previous.get("organization_id") != config.company_id:
            raise ValueError("previous Agent memory must belong to this organization")
        prior_dates = [(d["week"], DAYS.index(d["date"])) for d in previous["calendar"]]
        if not prior_dates or max(prior_dates) >= (calendar[0][0], DAYS.index(calendar[0][1])):
            raise ValueError("previous Agent run must end before the selected calendar")

    selection = None
    scenario = None
    if args.scenario:
        from scenario_catalog import load_scenario

        scenario = load_scenario(args.scenario)
        if len(profiles) > 1 and not args.employee:
            raise ValueError("choose a target --employee for the scenario")
        employee = args.employee or profiles[0]["id"]
        if employee not in {profile["id"] for profile in profiles}:
            raise ValueError(f"employee {employee!r} is not in the selected profiles")
        if chosen_date not in calendar:
            raise ValueError("scenario date falls outside the execution horizon")
        selection = (employee, *chosen_date)

    run_id = f"run_{uuid4().hex}"
    run_dir = args.output_dir / run_id
    jobs = {profile["id"]: [] for profile in profiles}
    placed = False
    missing_employee_days = []
    for week, day in calendar:
        for profile in profiles:
            employee = profile["id"]
            path = args.schedule_dir / f"week_{week}" / f"{employee}_week_{week}_{day}.json"
            targeted = selection == (employee, week, day)
            if not path.exists():
                if targeted or (horizon and not args.allow_missing_schedules):
                    raise ValueError(f"missing schedule {path}")
                missing_employee_days.append({"employee_id": employee, "week": week, "date": day})
                continue
            rows = read_schedule(path, day)
            if targeted:
                if args.activity_index >= len(rows):
                    raise ValueError(f"{path} has no activity at index {args.activity_index}")
                placed = True
                if recording == "employee":
                    attacked = dict(rows[args.activity_index])
                    # Employee-level attacks are represented by the scheduled
                    # work item itself.  The catalog supplies the concrete
                    # business action so the recorded activity stays free of
                    # downstream Agent/environment terminology.
                    attacked["Activity"] = scenario["employee_activity"]
                    attacked["Attack"] = "True"
                    attacked["AttackScenario"] = scenario["attack_id"]
                    rows[args.activity_index] = attacked
            dest = run_dir / employee / f"week_{week}" / f"{day}.jsonl"
            job = AgentDay(dest, profile, week, day, rows, run_id,
                           args.activity_index if targeted else None, scenario if targeted else None)
            jobs[employee].append(job)

    if selection and not placed:
        raise ValueError("selected scenario was not placed")
    if len(missing_employee_days) == len(calendar) * len(profiles):
        raise ValueError("no schedules found for the selected calendar and employees")
    from deepseek_runtime import harness_text_backend, harness_text_provenance

    agent_policy = None
    model_context = {"agent_backend": None, "agent_model": None, "agent_provider": None,
                     "agent_reasoning_effort": None}
    if args.agent_backend == "symbolic":
        model_context["agent_backend"] = "symbolic"
    else:
        from simulated_decision import DeepSeekHarnessPolicy

        model_context["agent_backend"] = harness_text_backend()
        if model_context["agent_backend"] == "deepseek_harness":
            model_context.update(harness_text_provenance(args.agent_model))
        agent_policy = DeepSeekHarnessPolicy(model_context["agent_model"])
    run_dir.mkdir(parents=True)
    summary = {
        "run_id": run_id, "execution_chain": "employee_agent", "recording": recording,
        "employees": [profile["id"] for profile in profiles],
        "organization_id": config.company_id, "previous_run_id": previous["run_id"] if previous else None,
        "calendar": [{"week": week, "date": day} for week, day in calendar],
        "missing_days": len(missing_employee_days), "missing_employee_days": missing_employee_days,
        "scenario": args.scenario, "placement": None,
        "events": 0, "status": "running",
        **model_context,
    }
    if selection:
        summary["placement"] = {"employee_id": selection[0], "week": selection[1],
                                "date": selection[2], "activity_index": args.activity_index}
    manifest = run_dir / "manifest.json"

    def save():
        partial = manifest.with_suffix(".partial")
        partial.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        partial.replace(manifest)

    save()
    try:
        from enterprise_harness import DEFAULT_SKILLS
        skills_path = (args.skill_catalog or DEFAULT_SKILLS).resolve()
        summary["skill_catalog"] = str(skills_path)
        if recording == "full":
            summary["state_dir"] = str((run_dir / ".state").resolve())
        if args.rag_url is not None:
            from rag_service import LocalRagClient
            knowledge_base = LocalRagClient(args.rag_url)
            summary["retrieval"] = {"backend": "http", "origin": args.rag_url}
        else:
            from enterprise_retrieval import DEFAULT_CORPUS, KnowledgeBase
            corpus = args.rag_corpus or DEFAULT_CORPUS
            knowledge_base = KnowledgeBase.from_file(corpus)
            summary["retrieval"] = {"backend": "embedded", "corpus": str(corpus.resolve()),
                                    "sha256": knowledge_base.digest}
        with ThreadPoolExecutor(max_workers=args.workers if horizon else 1) as pool:
            futures = [pool.submit(_employee_agent_days, employee, days, agent_policy, model_context,
                                   knowledge_base, skills_path, run_dir,
                                   args.previous_run if previous and employee in previous["employees"] else None,
                                   recording)
                       for employee, days in jobs.items()]
            summary["events"] = sum(future.result() for future in futures)
        from csv_exports import export_run_csvs
        from person_day_dataset import build_person_day_dataset

        summary["csv_exports"] = export_run_csvs(run_dir, recording)
        save()
        summary["person_day_dataset"] = build_person_day_dataset(run_dir)
        summary["status"] = "completed"
    except BaseException as error:
        summary["status"] = "failed"
        summary["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        save()
    return run_dir, summary


def main(argv=None, *, horizon=False, require_scenario=False):
    parser = build_parser(horizon=horizon, require_scenario=require_scenario)
    args = parser.parse_args(argv)
    try:
        run_dir, summary = run_schedules(args, horizon=horizon)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        parser.exit(1, f"Simulation failed: {error}\n")
    print(json.dumps({"output": str(run_dir), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
