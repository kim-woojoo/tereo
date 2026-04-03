from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tereo.constants import APP_DIR, PROMISES_DIR, RECEIPTS_DIR, RESULTS_FILE, RESULT_FIELDS, STATE_FILE
from tereo.measure import metric_change, summarize_metrics

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


PUBLIC_VERDICTS = {
    "keep": "keep",
    "discard": "drop",
    "drift": "drop",
    "review": "hold",
    "stable": "hold",
    "baseline": "hold",
}


def part(receipt: Optional[Dict[str, Any]], name: str) -> Dict[str, Any]:
    return {} if not receipt else receipt.get(name, {})


def baseline_block(receipt: Optional[Dict[str, Any]]) -> Dict[str, Any]: return part(receipt, "baseline")
def proof_block(receipt: Optional[Dict[str, Any]]) -> Dict[str, Any]: return part(receipt, "proof")
def run_block(receipt: Optional[Dict[str, Any]]) -> Dict[str, Any]: return part(receipt, "run")
def metric_block(receipt: Optional[Dict[str, Any]]) -> Dict[str, Any]: return part(receipt, "metric")
def evidence_block(receipt: Optional[Dict[str, Any]]) -> Dict[str, Any]: return part(receipt, "evidence")
def result_block(receipt: Optional[Dict[str, Any]]) -> Dict[str, Any]: return part(receipt, "result")
def ci_bounds(evidence: Dict[str, Any], key: str = "ci") -> Tuple[Optional[float], Optional[float]]: return tuple((evidence.get(key) or [None, None])[:2])  # type: ignore[return-value]
def workspace_root(cwd: Path) -> Path: return cwd / APP_DIR
def state_path(cwd: Path) -> Path: return workspace_root(cwd) / STATE_FILE
def results_path(cwd: Path) -> Path: return workspace_root(cwd) / RESULTS_FILE
def locks_root(cwd: Path) -> Path: return workspace_root(cwd) / "locks"
def workspace_lock_path(cwd: Path) -> Path: return locks_root(cwd) / "workspace.lock"
def proof_lock_path(cwd: Path, proof_key: str) -> Path: return locks_root(cwd) / f"{hashlib.sha1(proof_key.encode('utf-8')).hexdigest()}.lock"


def ensure_results_file(cwd: Path) -> Path:
    path = results_path(cwd)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        csv.DictWriter(handle, fieldnames=RESULT_FIELDS, delimiter="\t").writeheader()
    return path


def ensure_workspace(cwd: Path) -> Path:
    root = workspace_root(cwd)
    (root / RECEIPTS_DIR).mkdir(parents=True, exist_ok=True)
    (root / PROMISES_DIR).mkdir(parents=True, exist_ok=True)
    locks_root(cwd).mkdir(parents=True, exist_ok=True)
    ensure_results_file(cwd)
    return root


def load_state(cwd: Path) -> Dict[str, Any]:
    path = state_path(cwd)
    return {} if not path.exists() else json.loads(path.read_text())


def save_state(cwd: Path, state: Dict[str, Any]) -> None:
    ensure_workspace(cwd)
    atomic_write_text(state_path(cwd), json.dumps(state, indent=2) + "\n")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@contextmanager
def file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def workspace_lock(cwd: Path):
    ensure_workspace(cwd)
    with file_lock(workspace_lock_path(cwd)):
        yield


@contextmanager
def proof_lock(cwd: Path, proof_key: str):
    ensure_workspace(cwd)
    with file_lock(proof_lock_path(cwd, proof_key)):
        yield


def format_metric_value(value: Optional[float], unit: Optional[str] = None) -> str: return "(n/a)" if value is None else f"{value:.6f}" + (f" {unit}" if unit else "")
def format_percent(value: Optional[float]) -> str: return "(n/a)" if value is None else f"{value:.2f}%"
def format_ratio(value: Optional[float]) -> str: return "(n/a)" if value is None else "inf" if value == float("inf") else f"{value:.2f}x"
def format_probability(value: Optional[float]) -> str: return "(n/a)" if value is None else f"{value * 100:.1f}%"
def format_interval(low: Optional[float], high: Optional[float], unit: Optional[str] = None) -> str: return "(n/a)" if low is None or high is None else f"{low:.6f}..{high:.6f}" + (f" {unit}" if unit else "")
def output_preview(output: str, limit: int = 40) -> str:
    lines = output.strip().splitlines()
    return "(no output)" if not lines else "\n".join(lines[:limit] + ([] if len(lines) <= limit else ["... (truncated)"]))
def public_verdict(value: Optional[str]) -> str: return PUBLIC_VERDICTS.get(value or "", value or "hold")
def format_noise_band(value: Optional[float]) -> str: return "(n/a)" if value is None else f"±{abs(value):.2f}%"
def format_delta_percent(before: Optional[float], after: Optional[float]) -> str:
    if before in (None, 0) or after is None:
        return "(n/a)"
    return f"{((after - before) / abs(before)) * 100:.2f}%"


def bullet(label: str, value: Any) -> str: return f"- {label}: {value}"
def bullets(*items: Tuple[str, Any]) -> List[str]: return [bullet(label, value) for label, value in items if value is not None]
def section(title: str, *items: Tuple[str, Any]) -> List[str]:
    body = bullets(*items)
    return [] if not body else ["", title, *body]


def blank(value: Any) -> Any: return "" if value is None else value


def change_block(receipt: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    metric = metric_block(receipt)
    return metric_change(metric.get("before"), metric.get("after"), metric.get("direction"))


def sample_summary(evidence: Dict[str, Any]) -> Dict[str, Any]:
    samples = evidence.get("samples") or []
    summary = summarize_metrics(samples)
    return {
        "count": len(samples),
        "median": summary["median"],
        "stdev": summary["stdev"],
        "sem": summary["sem"],
        "ci": [summary["low"], summary["high"]],
    }


def receipt_parts(receipt: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    run = run_block(receipt)
    metric = metric_block(receipt)
    evidence = evidence_block(receipt)
    return run, metric, evidence, sample_summary(evidence), change_block(receipt), result_block(receipt)


def repeated_items(metric: Dict[str, Any], evidence: Dict[str, Any], summary: Dict[str, Any]) -> List[Tuple[str, Any]]:
    if not evidence.get("repeat"):
        return []
    ci_low, ci_high = tuple(summary["ci"])
    return [
        ("repeat_count", f"`{evidence.get('repeat')}`"),
        ("sample_count", f"`{summary.get('count')}`"),
        ("mean_95ci", f"`{format_interval(ci_low, ci_high, metric.get('unit'))}`"),
        ("metric_median", f"`{format_metric_value(summary.get('median'), metric.get('unit'))}`"),
        ("metric_stddev", f"`{format_metric_value(summary.get('stdev'), metric.get('unit'))}`"),
    ]


def confidence_items(evidence: Dict[str, Any], note_label: str = "note") -> List[Tuple[str, Any]]:
    if evidence.get("confidence") is None:
        return []
    return [
        ("confidence", f"`{evidence.get('confidence')}`"),
        ("drift_percent", f"`{format_percent(evidence.get('drift'))}`"),
        ("spread_percent", f"`{format_percent(evidence.get('spread'))}`"),
        ("signal_percent", f"`{format_percent(evidence.get('signal'))}`"),
        ("noise_percent", f"`{format_percent(evidence.get('noise'))}`"),
        ("signal_to_noise", f"`{format_ratio(evidence.get('ratio'))}`"),
        (note_label, evidence.get("note")),
    ]


def bootstrap_items(metric: Dict[str, Any], evidence: Dict[str, Any]) -> List[Tuple[str, Any]]:
    if evidence.get("win") is None:
        return []
    gain_low, gain_high = ci_bounds(evidence, "gain_ci")
    return [
        ("win_probability", f"`{format_probability(evidence.get('win'))}`"),
        ("improvement_95ci", f"`{format_interval(gain_low, gain_high, metric.get('unit'))}`"),
    ]


def format_change_summary(receipt: Dict[str, Any]) -> str:
    run = run_block(receipt)
    metric = metric_block(receipt)
    change = change_block(receipt)
    name = metric.get("name") or "metric"
    unit = metric.get("unit")
    before = metric.get("before")
    after = metric.get("after")
    if after is None:
        return f"check exit: {run.get('exit')}" if receipt.get("kind") == "baseline" else f"check exit: {baseline_block(receipt).get('exit')} -> {run.get('exit')}"
    if before is None or receipt.get("kind") == "baseline":
        return f"{name}: {format_metric_value(after, unit)}"
    if change.get("status") == "flat":
        return f"{name}: {format_metric_value(before, unit)} -> {format_metric_value(after, unit)}; flat"
    tail = "" if change.get("improvement_percent") is None else f" ({abs(change['improvement_percent']):.2f}%)"
    direction = "better" if change.get("status") == "better" else "worse"
    return f"{name}: {format_metric_value(before, unit)} -> {format_metric_value(after, unit)}; {format_metric_value(change.get('absolute_change'), unit)} {direction}{tail}"


def format_headline(receipt: Dict[str, Any]) -> str:
    metric = metric_block(receipt)
    before = metric.get("before")
    after = metric.get("after")
    name = metric.get("name") or "metric"
    unit = metric.get("unit")
    if before is None or after is None:
        return format_change_summary(receipt)
    return f"{name}: {format_metric_value(before, unit)} -> {format_metric_value(after, unit)} ({format_delta_percent(before, after)})"


def format_baseline_snapshot(receipt: Dict[str, Any]) -> str:
    metric = metric_block(receipt)
    return f"{metric.get('name') or 'metric'}: {format_metric_value(metric.get('after'), metric.get('unit'))}" if metric.get("after") is not None else f"check exit: {run_block(receipt).get('exit')}"


def format_transition_summary(baseline_receipt: Dict[str, Any], current_receipt: Dict[str, Any]) -> str:
    before = metric_block(baseline_receipt)
    after = metric_block(current_receipt)
    metric = {
        "name": after.get("name") or before.get("name"),
        "unit": after.get("unit") or before.get("unit"),
        "direction": after.get("direction") or before.get("direction"),
        "before": before.get("after"),
        "after": after.get("after"),
    }
    return format_change_summary(
        {
            "kind": "transition",
            "baseline": {"exit": run_block(baseline_receipt).get("exit")},
            "run": {"exit": run_block(current_receipt).get("exit")},
            "metric": metric,
        }
    )


def make_receipt_markdown(receipt: Dict[str, Any]) -> str:
    run, metric, evidence, summary, _, result = receipt_parts(receipt)
    verdict = public_verdict(result.get("verdict")).upper()
    lines = [
        "# Receipt",
        "",
        verdict,
        "",
        format_headline(receipt),
        "",
        f"noise: {format_noise_band(evidence.get('noise'))}",
        f"confidence: {evidence.get('confidence') or '(n/a)'}",
        f"promise: {receipt['promise']}",
    ]
    if receipt.get("scope"):
        lines.append(f"scope: {', '.join(receipt['scope'])}")
    if result.get("note"):
        lines.extend(["", f"why: {result['note']}"])

    evidence_items = [
        ("repeats", f"`{evidence.get('repeat')}`" if evidence.get("repeat") else None),
        ("win_probability", f"`{format_probability(evidence.get('win'))}`" if evidence.get("win") is not None else None),
        ("improvement_95ci", f"`{format_interval(*ci_bounds(evidence, 'gain_ci'), metric.get('unit'))}`" if evidence.get("gain_ci") else None),
        ("signal_to_noise", f"`{format_ratio(evidence.get('ratio'))}`" if evidence.get("ratio") is not None else None),
    ]
    evidence_lines = bullets(*[(label, value) for label, value in evidence_items if value is not None])
    if evidence_lines:
        lines.extend(["", "## Evidence", *evidence_lines])

    lines.extend(["", "## Trace", *bullets(("check", f"`{run.get('check')}`"), ("receipt_id", f"`{receipt['id']}`"))])
    return "\n".join(lines).strip()


def latest_receipt_path(cwd: Path, receipt_id: str) -> Path:
    return workspace_root(cwd) / RECEIPTS_DIR / f"{receipt_id}.json"


def save_receipt(cwd: Path, receipt: Dict[str, Any]) -> Path:
    root = ensure_workspace(cwd)
    json_path = root / RECEIPTS_DIR / f"{receipt['id']}.json"
    md_path = root / RECEIPTS_DIR / f"{receipt['id']}.md"
    atomic_write_text(json_path, json.dumps(receipt, indent=2) + "\n")
    atomic_write_text(md_path, make_receipt_markdown(receipt).rstrip() + "\n")
    return md_path


def append_result_row(cwd: Path, receipt: Dict[str, Any]) -> None:
    run, metric, evidence, summary, change, result = receipt_parts(receipt)
    ci_low, ci_high = tuple(summary["ci"])
    gain_low, gain_high = ci_bounds(evidence, "gain_ci")
    row = {
        "id": receipt["id"],
        "kind": receipt["kind"],
        "verdict": result.get("verdict"),
        "timed_out": run.get("timed_out", False),
        "scope": ";".join(receipt.get("scope") or []),
        "promise": receipt["promise"],
        **{  # Keep None out of the TSV without losing zeros or False.
            key: blank(value)
            for key, value in {
                "confidence": evidence.get("confidence"),
                "metric_name": metric.get("name"),
                "direction": metric.get("direction"),
                "baseline_metric": metric.get("before"),
                "current_metric": metric.get("after"),
                "absolute_change": change.get("absolute_change"),
                "improvement_percent": change.get("improvement_percent"),
                "signal_percent": evidence.get("signal"),
                "noise_percent": evidence.get("noise"),
                "signal_to_noise": evidence.get("ratio"),
                "drift_percent": evidence.get("drift"),
                "spread_percent": evidence.get("spread"),
                "sample_count": summary.get("count"),
                "metric_median": summary.get("median"),
                "metric_stddev": summary.get("stdev"),
                "metric_sem": summary.get("sem"),
                "metric_ci_low": ci_low,
                "metric_ci_high": ci_high,
                "win_probability": evidence.get("win"),
                "improvement_ci_low": gain_low,
                "improvement_ci_high": gain_high,
                "exit_code": run.get("exit"),
                "duration_seconds": run.get("seconds"),
                "repeat_count": evidence.get("repeat"),
            }.items()
        },
    }
    with ensure_results_file(cwd).open("a", newline="") as handle:
        csv.DictWriter(handle, fieldnames=RESULT_FIELDS, delimiter="\t").writerow(row)


def read_receipt(cwd: Path, receipt_id: str) -> Dict[str, Any]:
    return json.loads(latest_receipt_path(cwd, receipt_id).read_text())


def receipt_matches_proof(receipt: Dict[str, Any], proof: Dict[str, Any]) -> bool:
    current = proof_block(receipt)
    if current.get("key"):
        return current.get("key") == proof.get("key")

    metric = metric_block(receipt)
    return (
        run_block(receipt).get("check") == proof.get("check")
        and (metric.get("name") or "metric") == (proof.get("metric_name") or "metric")
        and metric.get("direction") == proof.get("metric_direction")
        and metric.get("unit") == proof.get("metric_unit")
    )


def list_receipts(cwd: Path, proof: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    root = workspace_root(cwd) / RECEIPTS_DIR
    receipts = [] if not root.exists() else [json.loads(path.read_text()) for path in sorted(root.glob("*.json"))]
    return receipts if not proof else [receipt for receipt in receipts if receipt_matches_proof(receipt, proof)]


def build_report_text(
    receipts: List[Dict[str, Any]],
    baseline: Optional[Dict[str, Any]],
    initial_baseline: Optional[Dict[str, Any]],
    latest_control: Optional[Dict[str, Any]],
    last: int,
) -> str:
    latest = receipts[-1]
    subject = latest
    if latest.get("kind") == "control":
        for candidate in reversed(receipts[:-1]):
            if candidate.get("kind") == "try":
                subject = candidate
                break

    lines = ["TEREO Proofboard"]
    if baseline:
        lines.extend(
            [
                "",
                "Current",
                *bullets(
                    ("baseline", format_baseline_snapshot(baseline)),
                    ("verdict", f"`{public_verdict(result_block(subject).get('verdict'))}`"),
                    ("promise", subject["promise"]),
                    ("score", format_headline(subject)),
                ),
            ]
        )

    if initial_baseline and baseline:
        lines.extend(
            [
                "",
                "Frontier",
                *bullets(
                    ("first", format_baseline_snapshot(initial_baseline)),
                    ("current", format_baseline_snapshot(baseline)),
                    ("net", format_transition_summary(initial_baseline, baseline)),
                ),
            ]
        )

    confidence_source = latest_control or subject
    confidence = evidence_block(confidence_source) if confidence_source else {}
    confidence_lines = bullets(
        ("confidence", f"`{confidence.get('confidence')}`" if confidence.get("confidence") is not None else None),
        ("noise", f"`{format_noise_band(confidence.get('noise'))}`" if confidence.get("noise") is not None else None),
        ("signal_to_noise", f"`{format_ratio(confidence.get('ratio'))}`" if confidence.get("ratio") is not None else None),
        ("win_probability", f"`{format_probability(confidence.get('win'))}`" if confidence.get("win") is not None else None),
    )
    if confidence_lines:
        if latest_control:
            confidence_lines.append(bullet("control", f"`{latest_control['id']}`"))
        lines.extend(["", "Confidence", *confidence_lines])

    recent = max(1, min(last, len(receipts)))
    lines.extend(["", f"Receipt Log ({recent})"])
    lines.extend(
        f"- {receipt['id']} | {public_verdict(result_block(receipt).get('verdict'))} | {format_change_summary(receipt)} | {receipt['promise']}"
        for receipt in receipts[-recent:]
    )
    return "\n".join(lines)


def build_log_text(receipts: List[Dict[str, Any]], last: int) -> str:
    recent = max(1, min(last, len(receipts)))
    lines = ["Receipt Log", ""]
    lines.extend(
        f"- {receipt['id']} | {public_verdict(result_block(receipt).get('verdict'))} | {format_change_summary(receipt)} | {receipt['promise']}"
        for receipt in receipts[-recent:]
    )
    return "\n".join(lines)


def build_pr_comment_text(
    receipts: List[Dict[str, Any]],
    baseline: Optional[Dict[str, Any]],
    initial_baseline: Optional[Dict[str, Any]],
    latest_control: Optional[Dict[str, Any]],
) -> str:
    latest = receipts[-1]
    subject = latest
    if latest.get("kind") == "control":
        for candidate in reversed(receipts[:-1]):
            if candidate.get("kind") == "try":
                subject = candidate
                break

    latest_result = result_block(subject)
    latest_evidence = evidence_block(subject)
    confidence = None
    if latest_control:
        control = evidence_block(latest_control)
        confidence = control.get("confidence")
    elif latest_evidence.get("confidence") is not None:
        confidence = latest_evidence.get("confidence")

    sticker = f"`{public_verdict(latest_result.get('verdict')).upper()}`"
    if confidence:
        sticker = f"{sticker} · `{str(confidence).upper()}`"

    lines = [
        "## TEREO",
        "",
        sticker,
        "",
        f"`{format_headline(subject)}`",
        subject.get("promise") or "",
    ]

    if baseline:
        lines.append(f"baseline: `{format_baseline_snapshot(baseline)}`")

    if initial_baseline and baseline and initial_baseline.get("id") != baseline.get("id"):
        lines.append(f"net: `{format_transition_summary(initial_baseline, baseline)}`")

    if latest_evidence.get("win") is not None:
        lines.append(f"win: `{format_probability(latest_evidence.get('win'))}`")

    lines.extend(
        [
            "",
            "> keep only if gain > noise",
        ]
    )
    return "\n".join(lines)
