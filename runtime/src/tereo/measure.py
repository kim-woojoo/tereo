from __future__ import annotations

import datetime as dt
import math
import random
import re
import statistics
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from tereo.constants import TIMEOUT_EXIT_CODE

def run_check(command: str, cwd: Path, timeout_seconds: Optional[float] = None) -> Dict[str, Any]:
    started = dt.datetime.now(dt.timezone.utc)
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        stderr = f"{stderr}\nTimed out after {timeout_seconds} seconds."
        exit_code = TIMEOUT_EXIT_CODE

    finished = dt.datetime.now(dt.timezone.utc)
    return {
        "command": command,
        "exit_code": exit_code,
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "stdout": stdout,
        "stderr": stderr,
        "output": stdout + stderr,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
    }


def extract_metric(output: str, pattern: Optional[str]) -> Optional[float]:
    match = None if not pattern else re.search(pattern, output, re.MULTILINE)
    return None if not match else float(match.group(1))


def percent_distance(baseline: Optional[float], current: Optional[float]) -> Optional[float]:
    return None if baseline in (None, 0) or current is None else abs(current - baseline) / abs(baseline) * 100


def percentile(sorted_values: List[float], fraction: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = fraction * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def bootstrap_mean_improvement(
    baseline_samples: List[float],
    current_samples: List[float],
    direction: Optional[str],
    iterations: int = 2000,
) -> Dict[str, Any]:
    if direction not in {"lower", "higher"} or len(baseline_samples) < 2 or len(current_samples) < 2:
        return {}

    rng = random.Random(0)
    improvements: List[float] = []
    wins = 0
    for _ in range(iterations):
        baseline_mean = statistics.mean(rng.choice(baseline_samples) for _ in baseline_samples)
        current_mean = statistics.mean(rng.choice(current_samples) for _ in current_samples)
        improvement = baseline_mean - current_mean if direction == "lower" else current_mean - baseline_mean
        improvements.append(improvement)
        if improvement > 0:
            wins += 1

    improvements.sort()
    return {
        "win_probability": wins / iterations,
        "improvement_ci_low": percentile(improvements, 0.025),
        "improvement_ci_high": percentile(improvements, 0.975),
    }


def metric_change(
    baseline_metric: Optional[float],
    current_metric: Optional[float],
    direction: Optional[str],
) -> Dict[str, Any]:
    if baseline_metric is None or current_metric is None or direction not in {"lower", "higher"}:
        return {"status": None, "absolute_change": None, "improvement_percent": None, "raw_delta": None}

    raw_delta = current_metric - baseline_metric
    better_delta = baseline_metric - current_metric if direction == "lower" else current_metric - baseline_metric
    status = "better" if better_delta > 0 else "worse" if better_delta < 0 else "flat"
    improvement_percent = None if baseline_metric == 0 else (better_delta / abs(baseline_metric)) * 100
    return {
        "status": status,
        "absolute_change": abs(raw_delta),
        "improvement_percent": improvement_percent,
        "raw_delta": raw_delta,
    }


def improvement_value(
    baseline_metric: Optional[float],
    current_metric: Optional[float],
    direction: Optional[str],
) -> Optional[float]:
    if baseline_metric is None or current_metric is None or direction not in {"lower", "higher"}:
        return None
    return baseline_metric - current_metric if direction == "lower" else current_metric - baseline_metric


def build_run_record(metric_context: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "check": result["command"],
        "exit_code": result["exit_code"],
        "duration_seconds": result["duration_seconds"],
        "metric": extract_metric(result["output"], metric_context.get("pattern")),
        "output": result["output"],
        "timed_out": result["timed_out"],
        "timeout_seconds": result.get("timeout_seconds"),
    }


def format_run_summary(run: Dict[str, Any], metric_unit: Optional[str]) -> str:
    metric = run.get("metric")
    metric_text = "(n/a)" if metric is None else f"{metric:.6f}" + (f" {metric_unit}" if metric_unit else "")
    return f"exit={run['exit_code']} duration={run['duration_seconds']:.3f}s timed_out={run.get('timed_out', False)} metric={metric_text}"


def run_check_series(
    command: str,
    cwd: Path,
    metric_context: Dict[str, Any],
    repeat: int,
    timeout_seconds: Optional[float],
) -> List[Dict[str, Any]]:
    return [build_run_record(metric_context, run_check(command, cwd, timeout_seconds=timeout_seconds)) for _ in range(repeat)]


def summarize_metrics(metrics: List[float]) -> Dict[str, Optional[float]]:
    mean = statistics.mean(metrics) if metrics else None
    median = statistics.median(metrics) if metrics else None
    stdev = statistics.stdev(metrics) if len(metrics) > 1 else 0.0 if metrics else None
    sem = None if stdev is None else stdev / math.sqrt(len(metrics))
    margin = None if mean is None or sem is None else 1.96 * sem
    return {
        "mean": mean,
        "median": median,
        "stdev": stdev,
        "sem": sem,
        "low": None if margin is None else mean - margin,
        "high": None if margin is None else mean + margin,
    }


def summarize_measurement_runs(
    runs: List[Dict[str, Any]],
    check: str,
    metric_context: Dict[str, Any],
    timeout_seconds: Optional[float],
) -> Dict[str, Any]:
    exit_codes = [run["exit_code"] for run in runs]
    metrics = [run["metric"] for run in runs if run.get("metric") is not None]
    timed_out_count = sum(1 for run in runs if run.get("timed_out"))
    summary = summarize_metrics(metrics)

    exit_code = 0
    if timed_out_count:
        exit_code = TIMEOUT_EXIT_CODE
    elif any(code != 0 for code in exit_codes):
        exit_code = next(code for code in exit_codes if code != 0)

    return {
        "check": check,
        "exit_codes": exit_codes,
        "exit_code": exit_code,
        "duration_seconds": round(sum(run["duration_seconds"] for run in runs), 3),
        "timed_out": timed_out_count > 0,
        "timeout_seconds": timeout_seconds,
        "metric": summary["mean"],
        "output": "\n".join(f"run {index}: {format_run_summary(run, metric_context.get('unit'))}" for index, run in enumerate(runs, start=1)),
        "repeat_count": len(runs),
        "timed_out_count": timed_out_count,
        "consistent_exit_codes": len(set(exit_codes)) == 1,
        "successful_runs": sum(1 for code in exit_codes if code == 0),
        "metric_samples": metrics,
    }


def summarize_control_runs(
    runs: List[Dict[str, Any]],
    check: str,
    metric_context: Dict[str, Any],
    timeout_seconds: Optional[float],
) -> Dict[str, Any]:
    summary = summarize_measurement_runs(runs, check, metric_context, timeout_seconds)
    metrics = summary.get("metric_samples") or []
    mean_metric = summary.get("metric")
    stdev_metric = statistics.pstdev(metrics) if len(metrics) > 1 else 0.0 if metrics else None
    spread_percent = None if mean_metric in (None, 0) or stdev_metric is None else abs(stdev_metric) / abs(mean_metric) * 100
    summary["spread_percent"] = spread_percent
    return summary


def merge_summaries(
    first: Dict[str, Any],
    second: Dict[str, Any],
    metric_context: Dict[str, Any],
    *,
    control: bool = False,
) -> Dict[str, Any]:
    runs = {
        "check": first["check"],
        "exit_codes": (first.get("exit_codes") or []) + (second.get("exit_codes") or []),
        "duration_seconds": round(first.get("duration_seconds", 0.0) + second.get("duration_seconds", 0.0), 3),
        "timed_out_count": (first.get("timed_out_count") or 0) + (second.get("timed_out_count") or 0),
        "timeout_seconds": first.get("timeout_seconds"),
        "metric_samples": (first.get("metric_samples") or []) + (second.get("metric_samples") or []),
        "output": "\n".join(part for part in [first.get("output", ""), second.get("output", "")] if part),
    }
    summary = summarize_metrics(runs["metric_samples"])
    exit_codes = runs["exit_codes"]
    exit_code = 0
    if runs["timed_out_count"]:
        exit_code = TIMEOUT_EXIT_CODE
    elif any(code != 0 for code in exit_codes):
        exit_code = next(code for code in exit_codes if code != 0)

    merged = {
        "check": runs["check"],
        "exit_codes": exit_codes,
        "exit_code": exit_code,
        "duration_seconds": runs["duration_seconds"],
        "timed_out": runs["timed_out_count"] > 0,
        "timeout_seconds": runs["timeout_seconds"],
        "metric": summary["mean"],
        "output": runs["output"],
        "repeat_count": len(exit_codes),
        "timed_out_count": runs["timed_out_count"],
        "consistent_exit_codes": len(set(exit_codes)) == 1,
        "successful_runs": sum(1 for code in exit_codes if code == 0),
        "metric_samples": runs["metric_samples"],
    }
    if control:
        metrics = merged.get("metric_samples") or []
        mean_metric = merged.get("metric")
        stdev_metric = statistics.pstdev(metrics) if len(metrics) > 1 else 0.0 if metrics else None
        merged["spread_percent"] = None if mean_metric in (None, 0) or stdev_metric is None else abs(stdev_metric) / abs(mean_metric) * 100
    return merged
