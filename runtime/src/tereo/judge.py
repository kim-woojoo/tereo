from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

from tereo.measure import bootstrap_mean_improvement, improvement_value, metric_change, percent_distance
from tereo.receipt import (
    ci_bounds,
    evidence_block,
    format_interval,
    format_metric_value,
    format_percent,
    format_probability,
    format_ratio,
    metric_block,
    output_preview,
    run_block,
)


def now_stamp() -> str: return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
def law(gain: Optional[float], noise: Optional[float]) -> bool: return gain is not None and gain > 0 and (noise is None or gain > noise)
def signal_to_noise(signal: Optional[float], noise: Optional[float]) -> Optional[float]:
    return None if signal is None else float("inf") if noise in (None, 0) and signal > 0 else 0.0 if noise in (None, 0) else signal / noise


def compare_metric(
    baseline_metric: Optional[float],
    current_metric: Optional[float],
    direction: Optional[str],
    metric_name: str,
    metric_unit: Optional[str],
) -> Tuple[str, str]:
    details = metric_change(baseline_metric, current_metric, direction)
    if details["status"] is None:
        return ("review", "No comparable metric was found.")
    before = format_metric_value(baseline_metric, metric_unit)
    after = format_metric_value(current_metric, metric_unit)
    delta = format_metric_value(details["absolute_change"], metric_unit)
    pct = "" if details["improvement_percent"] is None else f", {abs(details['improvement_percent']):.2f}%"
    if details["status"] == "better":
        return ("keep", f"{metric_name} improved from {before} to {after} ({delta}{pct}).")
    if details["status"] == "flat":
        return ("review", "Metric stayed flat.")
    return ("discard", f"{metric_name} moved from {before} to {after} ({delta}{pct}) in the wrong direction.")


def derive_verdict(
    baseline: Dict[str, Any],
    current: Dict[str, Any],
    direction: Optional[str],
    metric_name: str,
    metric_unit: Optional[str],
) -> Tuple[str, str]:
    if baseline.get("timed_out", False) and not current.get("timed_out", False):
        return ("keep", "The change removed a timeout.")
    if current.get("timed_out", False) and not baseline.get("timed_out", False):
        return ("discard", "The check timed out.")
    if current.get("timed_out", False) and baseline.get("timed_out", False):
        return ("discard", "The check still times out.")
    if baseline.get("exit_code") != 0 and current.get("exit_code") == 0:
        return ("keep", "The change fixed a failing check.")
    if baseline.get("exit_code") == 0 and current.get("exit_code") != 0:
        return ("discard", "The change broke a previously passing check.")
    if current.get("exit_code") != 0:
        return ("discard", "The check still fails.")
    return compare_metric(baseline.get("metric"), current.get("metric"), direction, metric_name, metric_unit)


def validate_repeat(count: int, command_name: str) -> int:
    if count < 1:
        raise SystemExit(f"`tereo {command_name}` requires --repeat >= 1.")
    return count


def build_receipt(
    *,
    kind: str,
    promise: str,
    scope: List[str],
    run: Dict[str, Any],
    baseline_receipt: Optional[Dict[str, Any]],
    metric_context: Dict[str, Any],
    verdict_override: Optional[str] = None,
    note_override: Optional[str] = None,
) -> Dict[str, Any]:
    baseline_run = run_block(baseline_receipt)
    before = metric_block(baseline_receipt).get("after") if baseline_receipt else None
    after = run.get("metric")

    if kind == "baseline":
        verdict, note = (
            "baseline",
            f"Recorded a timed-out baseline after {run.get('timeout_seconds')} seconds."
            if run.get("timed_out")
            else "Recorded the current state as the baseline.",
        )
    elif verdict_override and note_override:
        verdict, note = verdict_override, note_override
    else:
        verdict, note = derive_verdict(
            {
                "exit_code": baseline_run.get("exit"),
                "metric": before,
                "timed_out": baseline_run.get("timed_out", False),
            },
            {"exit_code": run.get("exit_code"), "metric": after, "timed_out": run.get("timed_out", False)},
            metric_context.get("direction"),
            metric_context.get("name") or "metric",
            metric_context.get("unit"),
        )

    return {
        "id": now_stamp(),
        "kind": kind,
        "promise": promise,
        "scope": scope,
        "baseline": {
            "id": baseline_receipt.get("id") if baseline_receipt else None,
            "exit": baseline_run.get("exit") if baseline_receipt else None,
        },
        "run": {
            "check": run["check"],
            "exit": run["exit_code"],
            "seconds": run["duration_seconds"],
            "timed_out": run.get("timed_out", False),
            "timeout": run.get("timeout_seconds"),
            "preview": output_preview(run.get("output", "")),
        },
        "metric": {
            "name": metric_context.get("name") if before is not None or after is not None else None,
            "unit": metric_context.get("unit"),
            "direction": metric_context.get("direction"),
            "before": before,
            "after": after,
        },
        "evidence": {
            "repeat": run.get("repeat_count"),
            "samples": run.get("metric_samples"),
            "timed_out_count": run.get("timed_out_count"),
            "consistent": run.get("consistent_exit_codes"),
            "successes": run.get("successful_runs"),
        },
        "result": {"verdict": verdict, "note": note},
    }


def derive_control_verdict(
    baseline_receipt: Dict[str, Any],
    current_run: Dict[str, Any],
    metric_context: Dict[str, Any],
    max_drift_percent: float,
) -> Tuple[str, str]:
    base_run = run_block(baseline_receipt)
    base_metric = metric_block(baseline_receipt)
    if base_run.get("timed_out", False) != current_run.get("timed_out", False):
        return ("drift", "Control rerun changed timeout behavior.")
    if current_run.get("timed_out", False) and base_run.get("timed_out", False):
        return ("stable", "Control rerun matched a timed-out baseline.")

    before = base_metric.get("after")
    after = current_run.get("metric")
    direction = metric_context.get("direction")
    if before is None or after is None or not direction:
        if base_run.get("exit") == current_run.get("exit_code"):
            return ("stable", "Control rerun matched the baseline exit status.")
        return ("drift", "Control rerun changed the baseline exit status.")

    change = metric_change(before, after, direction)
    drift_percent = abs(change["improvement_percent"]) if change["improvement_percent"] is not None else None
    name = metric_context.get("name") or base_metric.get("name") or "metric"
    unit = metric_context.get("unit") or base_metric.get("unit")
    summary = (
        f"{name}: {before:.6f}" + (f" {unit}" if unit else "")
        + " -> "
        + f"{after:.6f}" + (f" {unit}" if unit else "")
        + f"; {change['absolute_change']:.6f}" + (f" {unit}" if unit else "")
        + (" better" if change["status"] == "better" else " worse")
        + (f" ({abs(change['improvement_percent']):.2f}%)" if change["improvement_percent"] is not None else "")
    )
    if change["status"] == "flat":
        return ("stable", f"Control rerun matched the baseline. {summary}")
    if drift_percent is None:
        return ("drift", f"Control rerun moved away from the baseline. {summary}")
    if drift_percent <= max_drift_percent:
        return ("stable", f"Control rerun stayed within {max_drift_percent:.2f}% drift. {summary}")
    return ("drift", f"Control rerun exceeded {max_drift_percent:.2f}% drift. {summary}")


def derive_control_confidence(
    initial_baseline_receipt: Optional[Dict[str, Any]],
    current_baseline_receipt: Dict[str, Any],
    control_summary: Dict[str, Any],
    verdict: str,
    max_drift_percent: float,
) -> Dict[str, Any]:
    current_metric = metric_block(current_baseline_receipt)
    drift = percent_distance(current_metric.get("after"), control_summary.get("metric"))
    spread = control_summary.get("spread_percent")
    noise = max([value for value in [drift, spread] if value is not None], default=None)

    signal = None
    direction = current_metric.get("direction")
    if initial_baseline_receipt and direction:
        gain = metric_change(
            metric_block(initial_baseline_receipt).get("after"),
            current_metric.get("after"),
            direction,
        )
        if gain.get("improvement_percent") is not None:
            signal = abs(gain["improvement_percent"])

    ratio = signal_to_noise(signal, noise)

    if control_summary.get("timed_out_count", 0) > 0 or not control_summary.get("consistent_exit_codes", True):
        confidence, reason = "low", "Control runs were not stable enough to trust."
    elif signal is None:
        confidence = "high" if verdict == "stable" and (noise is None or noise <= max_drift_percent / 2) else "medium" if verdict == "stable" else "low"
        reason = "Confidence is based on control stability only."
    else:
        confidence = "high" if verdict == "stable" and law(signal, noise) and (ratio == float("inf") or (ratio is not None and ratio >= 3)) else "medium" if verdict == "stable" and law(signal, noise) else "low"
        reason = "Confidence is based on signal size versus measured control noise."

    return {
        "confidence": confidence,
        "note": f"{reason} signal={format_percent(signal)}, noise={format_percent(noise)}, signal_to_noise={format_ratio(ratio)}.",
        "drift": drift,
        "spread": spread,
        "noise": noise,
        "signal": signal,
        "ratio": ratio,
    }


def derive_experiment_confidence(
    baseline_receipt: Dict[str, Any],
    current_receipt: Dict[str, Any],
    metric_context: Dict[str, Any],
) -> Dict[str, Any]:
    before_metric = metric_block(baseline_receipt)
    after_metric = metric_block(current_receipt)
    before_evidence = evidence_block(baseline_receipt)
    after_evidence = evidence_block(current_receipt)
    direction = metric_context.get("direction")
    before_samples = before_evidence.get("samples") or []
    after_samples = after_evidence.get("samples") or []
    if direction not in {"lower", "higher"} or len(before_samples) < 2 or len(after_samples) < 2:
        return {}

    bootstrap = bootstrap_mean_improvement(before_samples, after_samples, direction)
    if not bootstrap:
        return {}

    point_gain = improvement_value(before_metric.get("after"), after_metric.get("after"), direction)
    signal_change = metric_change(before_metric.get("after"), after_metric.get("after"), direction)
    signal = abs(signal_change["improvement_percent"]) if signal_change.get("improvement_percent") is not None else None
    gain_low = bootstrap.get("improvement_ci_low")
    gain_high = bootstrap.get("improvement_ci_high")
    win = bootstrap.get("win_probability")
    interval_excludes_zero = gain_low is not None and gain_high is not None and (gain_low > 0 or gain_high < 0)

    noise = None
    if point_gain is not None and before_metric.get("after") not in (None, 0):
        half_width = max(abs(point_gain - (gain_low or point_gain)), abs((gain_high or point_gain) - point_gain))
        noise = abs(half_width) / abs(before_metric.get("after")) * 100

    ratio = signal_to_noise(signal, noise)

    if not law(point_gain, None):
        confidence, reason = "low", "Repeated checks do not show a positive mean improvement."
    elif interval_excludes_zero and win is not None and win >= 0.99 and law(signal, noise):
        confidence, reason = "high", "Repeated checks strongly support a real improvement."
    elif interval_excludes_zero and win is not None and win >= 0.95 and law(signal, noise):
        confidence, reason = "medium", "Repeated checks support a likely improvement, but some noise remains."
    else:
        confidence, reason = "low", "Repeated checks are suggestive, but not strong enough yet."

    return {
        "confidence": confidence,
        "note": (
            f"{reason} win_probability={format_probability(win)}, "
            f"improvement_95ci={format_interval(gain_low, gain_high, after_metric.get('unit'))}, "
            f"signal={format_percent(signal)}, noise={format_percent(noise)}, signal_to_noise={format_ratio(ratio)}."
        ),
        "signal": signal,
        "noise": noise,
        "ratio": ratio,
        "win": win,
        "gain_ci": [gain_low, gain_high],
    }
