from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from tereo.constants import AUTO_MEASURE_MAX_REPEAT, AUTO_MEASURE_REPEAT, TIMEOUT_EXIT_CODE
from tereo.judge import (
    build_receipt,
    derive_control_confidence,
    derive_control_verdict,
    derive_experiment_confidence,
    validate_repeat,
)
from tereo.measure import (
    build_run_record,
    extract_metric,
    extract_named_metric,
    merge_summaries,
    metric_change,
    run_check,
    run_check_series,
    summarize_control_runs,
    summarize_measurement_runs,
)
from tereo.receipt import (
    build_log_text,
    build_pr_comment_text,
    build_report_text,
    evidence_block,
    format_change_summary,
    format_interval,
    public_verdict,
    result_block,
    sample_summary,
)
from tereo.receipt import (
    append_result_row,
    ensure_workspace,
    list_receipts,
    load_state as raw_load_state,
    proof_lock,
    read_receipt,
    results_path,
    save_receipt,
    save_state as raw_save_state,
    workspace_lock,
    workspace_root,
)

PRESETS: Dict[str, Dict[str, Any]] = {
    "pytest": {
        "check": "pytest -q",
        "summary": "Python repo with stable tests.",
    },
    "npm-test": {
        "check": "npm test -- --runInBand",
        "summary": "Node repo with a real test command.",
    },
    "smoke": {
        "check": "./smoke-test.sh",
        "summary": "Shell or mixed repo with a simple pass/fail smoke test.",
    },
    "latency": {
        "check": "./bench.sh",
        "metric_pattern": r"latency_ms: ([0-9.]+)",
        "direction": "lower",
        "metric_name": "latency",
        "metric_unit": "ms",
        "summary": "Metric benchmark that prints lines like `latency_ms: 12.3`.",
    },
}

CHECK_SHAPE_HINT = "good check: show one gain and catch the core breakage that would make that gain false."
DEFAULT_PROOF = "default"
AUTO_PROOF_ENV = "TEREO_PROOF"
CODEX_THREAD_ENV = "CODEX_THREAD_ID"


class TereoArgumentParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        text = super().format_help()
        lines = []
        for line in text.splitlines():
            if "==SUPPRESS==" in line:
                continue
            if self.prog == "tereo" and line.strip().startswith("{demo,prove,init,baseline,try,control,show,log,report,comment,doctor}"):
                lines.append("  {demo,prove,show,log}")
                continue
            if self.prog == "tereo" and line.startswith("    ") and line.strip().split()[0] in {"init", "baseline", "try", "control", "report", "comment", "doctor"}:
                continue
            lines.append(line)
        return "\n".join(lines).rstrip() + "\n"


def build_proof_state(
    key: str,
    check: str,
    metric_context: Dict[str, Any],
    timeout_seconds: Optional[float],
    existing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    proof = dict(existing or {})
    proof["key"] = key
    proof["check"] = check
    persist_metric_context(proof, metric_context)
    persist_timeout_seconds(proof, timeout_seconds)
    return proof


def proof_metric_context(proof: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pattern": proof.get("metric_pattern"),
        "direction": proof.get("metric_direction"),
        "name": proof.get("metric_name"),
        "unit": proof.get("metric_unit"),
    }


def sync_active_state(state: Dict[str, Any]) -> Dict[str, Any]:
    proofs = state.get("proofs") or {}
    active_key = state.get("active_proof")
    active = proofs.get(active_key)
    if not active:
        return state

    state["default_check"] = active.get("check")
    state["metric_pattern"] = active.get("metric_pattern")
    state["metric_direction"] = active.get("metric_direction")
    state["metric_name"] = active.get("metric_name")
    state["metric_unit"] = active.get("metric_unit")
    state["timeout_seconds"] = active.get("timeout_seconds")
    state["baseline_receipt"] = active.get("baseline_receipt")
    state["initial_baseline_receipt"] = active.get("initial_baseline_receipt")
    state["latest_control_receipt"] = active.get("latest_control_receipt")
    state["latest_receipt"] = active.get("latest_receipt")
    return state


def active_proof_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return ((state.get("proofs") or {}).get(state.get("active_proof")) or {})


def selected_proof_state(state: Dict[str, Any], key: Optional[str]) -> Dict[str, Any]:
    proofs = state.get("proofs") or {}
    key = key or auto_proof_key()
    if key and key in proofs:
        return proofs[key]
    return active_proof_state(state)


def auto_proof_key() -> Optional[str]:
    if os.getenv(AUTO_PROOF_ENV):
        return os.getenv(AUTO_PROOF_ENV)
    if os.getenv(CODEX_THREAD_ENV):
        return f"thread:{os.environ[CODEX_THREAD_ENV]}"
    return None


def requested_proof_key(args: argparse.Namespace, state: Dict[str, Any]) -> str:
    return getattr(args, "proof", None) or auto_proof_key() or state.get("active_proof") or DEFAULT_PROOF


def normalize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(state or {})
    proofs = {key: dict(value) for key, value in (normalized.get("proofs") or {}).items()}

    legacy_check = normalized.get("default_check")
    if legacy_check:
        legacy_metric_context = {
            "pattern": normalized.get("metric_pattern"),
            "direction": normalized.get("metric_direction"),
            "name": normalized.get("metric_name"),
            "unit": normalized.get("metric_unit"),
        }
        key = normalized.get("active_proof") or auto_proof_key() or DEFAULT_PROOF
        legacy = build_proof_state(key, legacy_check, legacy_metric_context, normalized.get("timeout_seconds"), proofs.get(key))
        for field in ("baseline_receipt", "initial_baseline_receipt", "latest_control_receipt", "latest_receipt"):
            if field in normalized:
                legacy[field] = normalized.get(field)
        proofs[key] = legacy
        normalized.setdefault("active_proof", key)

    if proofs:
        normalized["proofs"] = proofs
        if normalized.get("active_proof") not in proofs:
            normalized["active_proof"] = next(iter(proofs))
        sync_active_state(normalized)
    return normalized


def load_state(cwd: Path) -> Dict[str, Any]:
    return normalize_state(raw_load_state(cwd))


def save_state(cwd: Path, state: Dict[str, Any]) -> None:
    raw_save_state(cwd, normalize_state(state))


def resolve_metric_context(args: argparse.Namespace, state: Dict[str, Any], proof: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    proof = proof or {}
    return {
        "pattern": getattr(args, "metric_pattern", None) or proof.get("metric_pattern") or state.get("metric_pattern"),
        "direction": getattr(args, "direction", None) or proof.get("metric_direction") or state.get("metric_direction"),
        "name": getattr(args, "metric_name", None) or proof.get("metric_name") or state.get("metric_name") or "metric",
        "unit": getattr(args, "metric_unit", None) or proof.get("metric_unit") or state.get("metric_unit"),
    }


def persist_metric_context(state: Dict[str, Any], metric_context: Dict[str, Any]) -> None:
    for key, state_key in [("pattern", "metric_pattern"), ("direction", "metric_direction"), ("name", "metric_name"), ("unit", "metric_unit")]:
        if metric_context.get(key):
            state[state_key] = metric_context[key]


def resolve_timeout_seconds(args: argparse.Namespace, state: Dict[str, Any], proof: Optional[Dict[str, Any]] = None) -> Optional[float]:
    if getattr(args, "timeout_seconds", None) is not None:
        return getattr(args, "timeout_seconds", None)
    return (proof or {}).get("timeout_seconds") if (proof or {}).get("timeout_seconds") is not None else state.get("timeout_seconds")


def persist_timeout_seconds(state: Dict[str, Any], timeout_seconds: Optional[float]) -> None:
    if timeout_seconds is not None:
        state["timeout_seconds"] = timeout_seconds


def resolve_proof_context(
    args: argparse.Namespace,
    state: Dict[str, Any],
    key: Optional[str] = None,
) -> tuple[str, Dict[str, Any], Optional[float], Dict[str, Any]]:
    key = key or requested_proof_key(args, state)
    seed = (state.get("proofs") or {}).get(key) or {}
    check = args.check or seed.get("check") or state.get("default_check")
    if not check:
        raise SystemExit("No check command provided. Use --check, `tereo init --preset ...`, or run `tereo doctor` first.")
    metric_context = resolve_metric_context(args, state, seed)
    timeout_seconds = resolve_timeout_seconds(args, state, seed)
    proof = build_proof_state(key, check, metric_context, timeout_seconds, seed)
    return check, metric_context, timeout_seconds, proof


def init_preset(args: argparse.Namespace) -> Dict[str, Any]:
    return PRESETS.get(getattr(args, "preset", None), {})


def detect_presets(cwd: Path) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if any(
        path.exists()
        for path in [
            cwd / "tests",
            cwd / "test",
            cwd / "runtime" / "tests",
            cwd / "pytest.ini",
            cwd / "pyproject.toml",
            cwd / "tox.ini",
        ]
    ):
        found.append(("pytest", "Python tests or test layout detected."))
    if (cwd / "package.json").exists():
        found.append(("npm-test", "package.json detected."))
    if (cwd / "smoke-test.sh").exists():
        found.append(("smoke", "smoke-test.sh detected."))
    if (cwd / "bench.sh").exists():
        found.append(("latency", "bench.sh detected."))
    return found


def auto_seed_metric_context(metric_context: Dict[str, Any], output: str) -> Optional[Dict[str, Any]]:
    if metric_context.get("pattern"):
        return None

    named = extract_named_metric(output)
    if named:
        return {
            "pattern": named["pattern"],
            "direction": named["direction"],
            "name": named["name"],
            "unit": named["unit"],
        }

    matches: list[Dict[str, Any]] = []
    for preset in PRESETS.values():
        pattern = preset.get("metric_pattern")
        direction = preset.get("direction")
        if not pattern or not direction:
            continue
        if extract_metric(output, pattern) is None:
            continue
        candidate = {
            "pattern": pattern,
            "direction": direction,
            "name": preset.get("metric_name"),
            "unit": preset.get("metric_unit"),
        }
        if candidate not in matches:
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def merge_metric_context(metric_context: Dict[str, Any], seeded: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pattern": metric_context.get("pattern") or seeded.get("pattern"),
        "direction": metric_context.get("direction") or seeded.get("direction"),
        "name": seeded.get("name") if metric_context.get("name") in {None, "", "metric"} else metric_context.get("name"),
        "unit": metric_context.get("unit") or seeded.get("unit"),
    }


def build_run(
    *,
    check: str,
    cwd: Path,
    metric_context: Dict[str, Any],
    timeout_seconds: Optional[float],
    repeat: int,
    control: bool = False,
) -> Dict[str, Any]:
    runs = run_check_series(check, cwd, metric_context, repeat=repeat, timeout_seconds=timeout_seconds)
    if control:
        return summarize_control_runs(runs, check, metric_context, timeout_seconds)
    return summarize_measurement_runs(runs, check, metric_context, timeout_seconds)


def build_first_baseline_run(
    *,
    args: argparse.Namespace,
    proof: Dict[str, Any],
    check: str,
    cwd: Path,
    metric_context: Dict[str, Any],
    timeout_seconds: Optional[float],
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    first_result = run_check(check, cwd, timeout_seconds=timeout_seconds)
    seeded = auto_seed_metric_context(metric_context, first_result["output"])
    if seeded:
        metric_context = merge_metric_context(metric_context, seeded)
        persist_metric_context(proof, metric_context)

    repeat = auto_repeat_target("baseline", args, metric_context, None)
    runs = [build_run_record(metric_context, first_result)]
    if repeat > 1:
        runs.extend(run_check_series(check, cwd, metric_context, repeat=repeat - 1, timeout_seconds=timeout_seconds))
    run = summarize_measurement_runs(runs, check, metric_context, timeout_seconds)
    return run, metric_context, proof


def auto_repeat_target(
    kind: str,
    args: argparse.Namespace,
    metric_context: Dict[str, Any],
    baseline_receipt: Optional[Dict[str, Any]],
) -> int:
    requested = getattr(args, "repeat", None)
    if requested is not None:
        return validate_repeat(requested, kind)
    if kind == "control":
        return AUTO_MEASURE_MAX_REPEAT
    if kind == "baseline":
        return AUTO_MEASURE_REPEAT if metric_context.get("pattern") and metric_context.get("direction") else 1
    if kind == "try":
        baseline_repeat = evidence_block(baseline_receipt).get("repeat") if baseline_receipt else None
        if metric_context.get("pattern") and metric_context.get("direction") and (baseline_repeat or 0) >= 2:
            return max(AUTO_MEASURE_REPEAT, int(baseline_repeat))
    return 1


def build_receipt_for_run(
    *,
    kind: str,
    args: argparse.Namespace,
    proof: Dict[str, Any],
    run: Dict[str, Any],
    baselines: Dict[str, Optional[Dict[str, Any]]],
    metric_context: Dict[str, Any],
) -> Dict[str, Any]:
    verdict_override = note_override = None
    if kind == "control":
        verdict_override, note_override = derive_control_verdict(
            baselines["baseline"],
            run,
            metric_context,
            args.max_drift_percent,
        )

    receipt = build_receipt(
        kind=kind,
        promise=args.promise,
        scope=args.scope,
        proof=proof,
        run=run,
        baseline_receipt=baselines["baseline"],
        metric_context=metric_context,
        verdict_override=verdict_override,
        note_override=note_override,
    )
    if kind == "try":
        receipt["evidence"].update(derive_experiment_confidence(baselines["baseline"], receipt, metric_context))
        if result_block(receipt).get("verdict") == "keep" and evidence_block(receipt).get("confidence") == "low":
            receipt["result"] = {
                "verdict": "review",
                "note": "The signal is positive, but repeated checks are still too close to noise.",
            }
    elif kind == "control":
        receipt["evidence"].update(
            derive_control_confidence(
                baselines["initial"],
                baselines["baseline"],
                run,
                result_block(receipt).get("verdict"),
                args.max_drift_percent,
            )
        )
    return receipt


def should_retry_try(kind: str, args: argparse.Namespace, receipt: Dict[str, Any], baseline_receipt: Optional[Dict[str, Any]], repeat: int) -> bool:
    if kind != "try" or getattr(args, "repeat", None) is not None:
        return False
    if not baseline_receipt or repeat >= AUTO_MEASURE_MAX_REPEAT:
        return False
    evidence = evidence_block(receipt)
    if result_block(receipt).get("verdict") not in {"keep", "review"}:
        return False
    if (evidence_block(baseline_receipt).get("repeat") or 0) < 2:
        return False
    return evidence.get("confidence") in {"low", "medium"}


def execute_run_locked(kind: str, args: argparse.Namespace, proof_key: str) -> tuple[int, Dict[str, Any], Path]:
    cwd = Path.cwd()
    state = load_state(cwd)
    check, metric_context, timeout_seconds, proof = resolve_proof_context(args, state, proof_key)
    baselines = load_baselines(cwd, proof, kind)
    if kind == "baseline" and not metric_context.get("pattern"):
        run, metric_context, proof = build_first_baseline_run(
            args=args,
            proof=proof,
            check=check,
            cwd=cwd,
            metric_context=metric_context,
            timeout_seconds=timeout_seconds,
        )
    else:
        repeat = auto_repeat_target(kind, args, metric_context, baselines["baseline"])
        run = build_run(
            check=check,
            cwd=cwd,
            metric_context=metric_context,
            timeout_seconds=timeout_seconds,
            repeat=repeat,
            control=kind == "control",
        )
    repeat = run.get("repeat_count", 1)
    receipt = build_receipt_for_run(kind=kind, args=args, proof=proof, run=run, baselines=baselines, metric_context=metric_context)
    if should_retry_try(kind, args, receipt, baselines["baseline"], repeat):
        extra_run = build_run(
            check=check,
            cwd=cwd,
            metric_context=metric_context,
            timeout_seconds=timeout_seconds,
            repeat=AUTO_MEASURE_MAX_REPEAT - repeat,
            control=False,
        )
        run = merge_summaries(run, extra_run, metric_context, control=False)
        receipt = build_receipt_for_run(kind=kind, args=args, proof=proof, run=run, baselines=baselines, metric_context=metric_context)

    with workspace_lock(cwd):
        latest_state = load_state(cwd)
        md_path = save_receipt(cwd, receipt)
        append_result_row(cwd, receipt)
        update_state_for_run(latest_state, kind, proof, receipt)
        save_state(cwd, latest_state)
    return 0 if run["exit_code"] == 0 else run["exit_code"], receipt, md_path


def execute_run(kind: str, args: argparse.Namespace) -> tuple[int, Dict[str, Any], Path]:
    cwd = Path.cwd()
    proof_key = requested_proof_key(args, load_state(cwd))
    with proof_lock(cwd, proof_key):
        return execute_run_locked(kind, args, proof_key)


def load_baselines(cwd: Path, proof: Dict[str, Any], kind: str) -> Dict[str, Optional[Dict[str, Any]]]:
    if kind == "baseline":
        return {"baseline": None, "initial": None}
    baseline_id = proof.get("baseline_receipt")
    if not baseline_id:
        raise SystemExit("No baseline found. Run `tereo prove` first.")
    return {
        "baseline": read_receipt(cwd, baseline_id),
        "initial": read_receipt(cwd, proof["initial_baseline_receipt"]) if kind == "control" and proof.get("initial_baseline_receipt") else None,
    }


def update_state_for_run(
    state: Dict[str, Any],
    kind: str,
    proof: Dict[str, Any],
    receipt: Dict[str, Any],
) -> None:
    proofs = state.setdefault("proofs", {})
    current = build_proof_state(proof["key"], proof["check"], proof_metric_context(proof), proof.get("timeout_seconds"), proofs.get(proof["key"]))
    current["latest_receipt"] = receipt["id"]
    if kind == "baseline":
        current["baseline_receipt"] = receipt["id"]
        current["latest_control_receipt"] = None
        if not current.get("initial_baseline_receipt"):
            current["initial_baseline_receipt"] = receipt["id"]
    elif kind == "try":
        if result_block(receipt).get("verdict") == "keep":
            current["baseline_receipt"] = receipt["id"]
            current["latest_control_receipt"] = None
    elif kind == "control":
        current["latest_control_receipt"] = receipt["id"]
    proofs[proof["key"]] = current
    state["active_proof"] = proof["key"]
    sync_active_state(state)


def print_run_result(kind: str, receipt: Dict[str, Any], md_path: Path) -> None:
    names = {"baseline": "Baseline", "try": "Receipt", "control": "Control receipt"}
    evidence = evidence_block(receipt)
    summary = sample_summary(evidence)
    result = result_block(receipt)
    print(f"{names[kind]} saved to {md_path}")
    if kind == "baseline":
        print(f"verdict: {public_verdict(result.get('verdict'))}")
        print(f"scorecard: {format_change_summary(receipt)}")
        print(f"note: {result.get('note')}")
        if evidence.get("repeat", 0) > 1:
            print(
                f"evidence: {evidence.get('repeat')} runs, "
                f"mean_95ci={format_interval(*(summary.get('ci') or [None, None]), receipt.get('metric', {}).get('unit'))}"
            )
        return

    print(f"scorecard: {format_change_summary(receipt)}")
    print(f"verdict: {public_verdict(result.get('verdict'))}")
    if kind == "try" and evidence.get("win") is not None:
        print(
            "evidence: "
            f"win_probability={evidence['win'] * 100:.1f}%, "
            f"improvement_95ci={format_interval(*(evidence.get('gain_ci') or [None, None]), receipt.get('metric', {}).get('unit'))}, "
            f"confidence={evidence.get('confidence')}"
        )
    if kind == "control":
        print(f"confidence: {evidence.get('confidence')}")
    print(f"note: {result.get('note')}")
    next_step = next_step_hint(kind, receipt)
    if next_step:
        print(f"next: {next_step}")


def next_step_hint(kind: str, receipt: Dict[str, Any]) -> Optional[str]:
    verdict = public_verdict(result_block(receipt).get("verdict"))
    if kind == "baseline":
        return None
    if kind == "control":
        if verdict == "drop":
            return "for this loop: shrink the check before trusting it again"
        if verdict == "hold":
            return "for this loop: the baseline still looks noisy; shrink the check or rerun control"
        return None
    if verdict == "keep":
        return "for this proof: keep this receipt as the new local baseline"
    if verdict == "hold":
        return "for this proof: shrink the scope, stabilize the check, or add --repeat / `tereo control --repeat 5`"
    if verdict == "drop":
        return "for this proof: discard this patch or change the promise before trying again"
    return None


def tereo(kind: str, args: argparse.Namespace) -> int:
    exit_code, receipt, md_path = execute_run(kind, args)
    print_run_result(kind, receipt, md_path)
    return exit_code


def cmd_init(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    ensure_workspace(cwd)
    state = load_state(cwd)
    preset = init_preset(args)
    key = requested_proof_key(args, state)
    seed = (state.get("proofs") or {}).get(key) or {}
    check = args.check or preset.get("check") or seed.get("check") or state.get("default_check")
    metric_context = {
        "pattern": args.metric_pattern if args.metric_pattern is not None else preset.get("metric_pattern") or seed.get("metric_pattern") or state.get("metric_pattern"),
        "direction": args.direction if args.direction is not None else preset.get("direction") or seed.get("metric_direction") or state.get("metric_direction"),
        "name": args.metric_name if args.metric_name is not None else preset.get("metric_name") or seed.get("metric_name") or state.get("metric_name"),
        "unit": args.metric_unit if args.metric_unit is not None else preset.get("metric_unit") or seed.get("metric_unit") or state.get("metric_unit"),
    }
    timeout_seconds = resolve_timeout_seconds(args, state, seed)
    if check:
        proofs = state.setdefault("proofs", {})
        proofs[key] = build_proof_state(key, check, metric_context, timeout_seconds, seed)
        state["active_proof"] = key
        sync_active_state(state)
    else:
        persist_metric_context(state, metric_context)
        persist_timeout_seconds(state, timeout_seconds)
    save_state(cwd, state)
    print(f"Initialized {workspace_root(cwd)}")
    print(f"preset: {args.preset or '(none)'}")
    print(f"default check: {state.get('default_check', '(none)')}")
    print(f"metric: {state.get('metric_name', '(none)')}")
    print(f"timeout_seconds: {state.get('timeout_seconds', '(none)')}")
    if preset.get("summary"):
        print(f"preset_note: {preset['summary']}")
    print(CHECK_SHAPE_HINT)
    return 0


def cmd_baseline(args: argparse.Namespace) -> int:
    return tereo("baseline", args)


def cmd_try(args: argparse.Namespace) -> int:
    return tereo("try", args)


def cmd_prove(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    proof_key = requested_proof_key(args, load_state(cwd))
    with proof_lock(cwd, proof_key):
        state = load_state(cwd)
        _, _, _, proof = resolve_proof_context(args, state, proof_key)
        kind = "try" if proof.get("baseline_receipt") else "baseline"
        exit_code, receipt, md_path = execute_run_locked(kind, args, proof_key)
    print_run_result(kind, receipt, md_path)
    if kind == "baseline":
        print("next: make one small change, keep the same check, then run `tereo prove` again.")
    return exit_code


def cmd_demo(_: argparse.Namespace) -> int:
    previous = Path.cwd()
    demo_dir = Path(tempfile.mkdtemp(prefix="tereo-demo-"))
    try:
        os.chdir(demo_dir)
        print(f"demo workspace: {demo_dir}")
        print("this demo uses a throwaway check so you can feel the loop first.")
        print()

        init_code = cmd_init(
            argparse.Namespace(
                check='python3 -c "print(\'latency_ms: 10\')"',
                preset=None,
                metric_pattern=r"latency_ms: ([0-9.]+)",
                direction="lower",
                metric_name="latency",
                metric_unit="ms",
                timeout_seconds=None,
            )
        )
        if init_code != 0:
            return init_code

        print()
        baseline_code = cmd_prove(
            argparse.Namespace(
                check=None,
                promise="Current latency is the baseline",
                scope=[],
                metric_pattern=None,
                direction=None,
                metric_name=None,
                metric_unit=None,
                timeout_seconds=None,
                repeat=3,
            )
        )
        if baseline_code != 0:
            return baseline_code

        print()
        try_code = cmd_prove(
            argparse.Namespace(
                check='python3 -c "print(\'latency_ms: 8\')"',
                promise="Cache hits lower latency",
                scope=["src/cache.py"],
                metric_pattern=None,
                direction=None,
                metric_name=None,
                metric_unit=None,
                timeout_seconds=None,
                repeat=3,
            )
        )
        if try_code != 0:
            return try_code

        print()
        cmd_show(argparse.Namespace())
        print()
        cmd_log(argparse.Namespace(last=5))
        return 0
    finally:
        os.chdir(previous)


def cmd_show(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    state = load_state(cwd)
    proof = selected_proof_state(state, requested_proof_key(args, state))
    receipt_id = proof.get("latest_receipt") or state.get("latest_receipt")
    if not receipt_id:
        raise SystemExit("No receipt found yet. Run `tereo prove` first.")
    print((workspace_root(cwd) / "receipts" / f"{receipt_id}.md").read_text().rstrip())
    return 0


def cmd_control(args: argparse.Namespace) -> int:
    return tereo("control", args)


def cmd_report(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    state = load_state(cwd)
    proof = selected_proof_state(state, requested_proof_key(args, state))
    receipts = list_receipts(cwd, proof=proof or None)
    if not receipts:
        raise SystemExit("No receipts found yet. Run `tereo prove` first.")
    baseline = read_receipt(cwd, proof["baseline_receipt"]) if proof.get("baseline_receipt") else None
    initial_baseline = read_receipt(cwd, proof["initial_baseline_receipt"]) if proof.get("initial_baseline_receipt") else None
    latest_control = read_receipt(cwd, proof["latest_control_receipt"]) if proof.get("latest_control_receipt") else None
    print(build_report_text(receipts, baseline, initial_baseline, latest_control, args.last))
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    state = load_state(cwd)
    receipts = list_receipts(cwd, proof=selected_proof_state(state, requested_proof_key(args, state)) or None)
    if not receipts:
        raise SystemExit("No receipts found yet. Run `tereo prove` first.")
    print(build_log_text(receipts, args.last))
    return 0


def cmd_comment(_: argparse.Namespace) -> int:
    cwd = Path.cwd()
    state = load_state(cwd)
    proof = selected_proof_state(state, requested_proof_key(_, state))
    receipts = list_receipts(cwd, proof=proof or None)
    if not receipts:
        raise SystemExit("No receipts found yet. Run `tereo prove` first.")
    baseline = read_receipt(cwd, proof["baseline_receipt"]) if proof.get("baseline_receipt") else None
    initial_baseline = read_receipt(cwd, proof["initial_baseline_receipt"]) if proof.get("initial_baseline_receipt") else None
    latest_control = read_receipt(cwd, proof["latest_control_receipt"]) if proof.get("latest_control_receipt") else None
    print(build_pr_comment_text(receipts, baseline, initial_baseline, latest_control))
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    cwd = Path.cwd()
    state = load_state(cwd)
    print(f"cwd: {cwd}")
    print(f"workspace: {workspace_root(cwd)}")
    print(f"default_check: {state.get('default_check', '(none)')}")
    print(f"baseline_receipt: {state.get('baseline_receipt', '(none)')}")
    print(f"initial_baseline_receipt: {state.get('initial_baseline_receipt', '(none)')}")
    print(f"latest_control_receipt: {state.get('latest_control_receipt', '(none)')}")
    print(f"timeout_seconds: {state.get('timeout_seconds', '(none)')}")
    print(f"results: {results_path(cwd)}")
    print("tools:")
    for tool in ["python", "python3", "pytest", "node", "npm", "uv", "cargo", "go"]:
        print(f"  {tool}: {shutil.which(tool) or '(missing)'}")
    suggestions = detect_presets(cwd)
    print("suggested first checks:")
    print(f"  {CHECK_SHAPE_HINT}")
    if suggestions:
        for name, reason in suggestions:
            preset = PRESETS[name]
            print(f"  {name}: {preset['check']} ({reason})")
            print(f"    try: tereo init --preset {name}")
    else:
        print("  (no obvious preset detected)")
        print("  try one of: pytest -q | npm test -- --runInBand | ./smoke-test.sh | ./bench.sh")
    return 0


def add_shared_arguments(parser: argparse.ArgumentParser, promise_required: bool = True) -> None:
    parser.add_argument("--check", help="Shell command used as the fixed check. It should show one gain and catch the core breakage that would make that gain false.")
    parser.add_argument("--proof", help=argparse.SUPPRESS)
    parser.add_argument("--promise", required=promise_required, default="Control rerun of the current baseline" if not promise_required else None, help="Small promise for this run.")
    parser.add_argument("--scope", action="append", default=[], help="Path in scope for the change. Repeat for multiple paths.")
    parser.add_argument("--metric-pattern", help="Regex with one capture group for a numeric metric in command output.")
    parser.add_argument("--direction", choices=["lower", "higher"], help="Whether a lower or higher metric is better.")
    parser.add_argument("--metric-name", help="Human-readable metric name shown in receipts and reports.")
    parser.add_argument("--metric-unit", help="Optional metric unit such as ms, MB, or score.")
    parser.add_argument("--timeout-seconds", type=float, help="Hard timeout for the check command.")


def build_parser() -> argparse.ArgumentParser:
    parser = TereoArgumentParser(
        prog="tereo",
        usage="tereo [-h] {demo,prove,show,log} ...",
        description="TEREO runtime. Promise -> Check -> Receipt.",
        epilog=(
            "Public surface:\n"
            "  tereo demo\n"
            "  tereo prove\n"
            "  tereo show\n"
            "  tereo log\n\n"
            "Advanced commands still work, but they stay behind the front door."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("demo", help="Run the throwaway TEREO demo loop.").set_defaults(func=cmd_demo)

    prove_parser = subparsers.add_parser("prove", help="Run one promise against one fixed check and write one receipt.")
    add_shared_arguments(prove_parser)
    prove_parser.add_argument("--repeat", type=int, help="How many times to rerun the check before summarizing it. If omitted, TEREO may measure more automatically.")
    prove_parser.set_defaults(func=cmd_prove)

    init_parser = subparsers.add_parser("init", help=argparse.SUPPRESS, description="Create the local .tereo workspace.")
    init_parser.add_argument("--check", help="Default shell command used as the fixed check. It should show one gain and catch the core breakage that would make that gain false.")
    init_parser.add_argument("--proof", help=argparse.SUPPRESS)
    init_parser.add_argument("--preset", choices=sorted(PRESETS), help="Starter check preset for common repo shapes.")
    init_parser.add_argument("--metric-pattern", help="Default regex with one capture group for a numeric metric.")
    init_parser.add_argument("--direction", choices=["lower", "higher"], help="Default optimization direction.")
    init_parser.add_argument("--metric-name", help="Default metric name shown in receipts and reports.")
    init_parser.add_argument("--metric-unit", help="Default metric unit such as ms or MB.")
    init_parser.add_argument("--timeout-seconds", type=float, help="Default hard timeout for the check command.")
    init_parser.set_defaults(func=cmd_init)

    baseline_parser = subparsers.add_parser("baseline", help=argparse.SUPPRESS, description="Run the current code and record a baseline.")
    add_shared_arguments(baseline_parser)
    baseline_parser.add_argument("--repeat", type=int, help="How many times to rerun the baseline check before summarizing it.")
    baseline_parser.set_defaults(func=cmd_baseline)

    try_parser = subparsers.add_parser("try", help=argparse.SUPPRESS, description="Run the current code after a change and write a receipt.")
    add_shared_arguments(try_parser)
    try_parser.add_argument("--repeat", type=int, help="How many times to rerun the changed check before summarizing it.")
    try_parser.set_defaults(func=cmd_try)

    control_parser = subparsers.add_parser("control", help=argparse.SUPPRESS, description="Rerun the baseline to check drift and flakiness.")
    add_shared_arguments(control_parser, promise_required=False)
    control_parser.add_argument("--max-drift-percent", type=float, default=1.0, help="Maximum drift percent allowed before the control run is marked as drift.")
    control_parser.add_argument("--repeat", type=int, default=5, help="How many times to rerun the current baseline when measuring control stability.")
    control_parser.set_defaults(func=cmd_control)

    show_parser = subparsers.add_parser("show", help="Show the latest receipt.")
    show_parser.add_argument("--proof", help=argparse.SUPPRESS)
    show_parser.set_defaults(func=cmd_show)
    log_parser = subparsers.add_parser("log", help="Show a short receipt history.")
    log_parser.add_argument("--proof", help=argparse.SUPPRESS)
    log_parser.add_argument("--last", type=int, default=5, help="How many recent receipts to show.")
    log_parser.set_defaults(func=cmd_log)
    report_parser = subparsers.add_parser("report", help=argparse.SUPPRESS, description="Show a compact numeric summary and recent history.")
    report_parser.add_argument("--proof", help=argparse.SUPPRESS)
    report_parser.add_argument("--last", type=int, default=5, help="How many recent receipts to show.")
    report_parser.set_defaults(func=cmd_report)
    comment_parser = subparsers.add_parser("comment", help=argparse.SUPPRESS, description="Render a short PR comment from the latest receipt.")
    comment_parser.add_argument("--proof", help=argparse.SUPPRESS)
    comment_parser.set_defaults(func=cmd_comment)
    subparsers.add_parser("doctor", help=argparse.SUPPRESS, description="Inspect workspace setup and common tools.").set_defaults(func=cmd_doctor)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
