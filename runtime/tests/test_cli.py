from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

from tereo import cli


@contextmanager
def pushd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class MetricChangeTests(unittest.TestCase):
    def test_lower_is_better_percent_is_positive_when_value_drops(self) -> None:
        details = cli.metric_change(10.0, 8.0, "lower")
        self.assertEqual(details["status"], "better")
        self.assertAlmostEqual(details["absolute_change"], 2.0)
        self.assertAlmostEqual(details["improvement_percent"], 20.0)

    def test_higher_is_better_percent_is_negative_when_value_drops(self) -> None:
        details = cli.metric_change(100.0, 90.0, "higher")
        self.assertEqual(details["status"], "worse")
        self.assertAlmostEqual(details["absolute_change"], 10.0)
        self.assertAlmostEqual(details["improvement_percent"], -10.0)


class RuntimeFlowTests(unittest.TestCase):
    def cli_env(self, thread_id: str | None = None, extra: dict[str, str] | None = None) -> dict[str, str]:
        repo_root = Path(__file__).resolve().parents[2]
        env = os.environ.copy()
        pythonpath = str(repo_root / "runtime" / "src")
        if env.get("PYTHONPATH"):
            env["PYTHONPATH"] = pythonpath + os.pathsep + env["PYTHONPATH"]
        else:
            env["PYTHONPATH"] = pythonpath
        if thread_id is not None:
            env["CODEX_THREAD_ID"] = thread_id
        if extra:
            env.update(extra)
        return env

    def run_cli_subprocess(
        self,
        workspace: Path,
        argv: list[str],
        *,
        thread_id: str | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "tereo", *argv],
            cwd=workspace,
            env=self.cli_env(thread_id=thread_id, extra=extra_env),
            text=True,
            capture_output=True,
            check=False,
        )

    def run_main(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = cli.main(argv)
        return exit_code, buffer.getvalue()

    def write_metric_stream_script(self, workspace: Path) -> Path:
        script = workspace / "metric_stream.py"
        script.write_text(
            "\n".join(
                [
                    "from pathlib import Path",
                    "import sys",
                    "",
                    "data_path = Path(sys.argv[1])",
                    "values = data_path.read_text().splitlines()",
                    "if not values:",
                    "    raise SystemExit('no values left')",
                    "value = values[0]",
                    "remaining = values[1:]",
                    "data_path.write_text(''.join(line + '\\n' for line in remaining))",
                    "print(f'latency_ms: {value}')",
                ]
            )
            + "\n"
        )
        return script

    def test_report_and_results_show_before_after_improvement(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            with pushd(workspace):
                init_code, init_output = self.run_main(
                    [
                        "init",
                        "--check",
                        'python3 -c "print(\'latency_ms: 10\')"',
                        "--metric-pattern",
                        r"latency_ms: ([0-9.]+)",
                        "--direction",
                        "lower",
                        "--metric-name",
                        "latency",
                        "--metric-unit",
                        "ms",
                    ]
                )
                self.assertEqual(init_code, 0)
                self.assertIn("metric: latency", init_output)

                baseline_code, _ = self.run_main(
                    [
                        "baseline",
                        "--promise",
                        "Current latency is the baseline",
                    ]
                )
                self.assertEqual(baseline_code, 0)

                try_code, try_output = self.run_main(
                    [
                        "try",
                        "--check",
                        'python3 -c "print(\'latency_ms: 8\')"',
                        "--promise",
                        "Cache hits lower latency",
                        "--scope",
                        "src/cache.py",
                    ]
                )
                self.assertEqual(try_code, 0)
                self.assertIn("scorecard: latency: 10.000000 ms -> 8.000000 ms; 2.000000 ms better (20.00%)", try_output)
                self.assertIn("verdict: keep", try_output)
                self.assertIn("next: for this proof: keep this receipt as the new local baseline", try_output)

                _, show_output = self.run_main(["show"])
                self.assertIn("KEEP", show_output)
                self.assertIn("latency: 10.000000 ms -> 8.000000 ms (-20.00%)", show_output)
                self.assertIn("promise: Cache hits lower latency", show_output)

                _, report_output = self.run_main(["report"])
                self.assertIn("Current", report_output)
                self.assertIn("- baseline: latency: 8.000000 ms", report_output)
                self.assertIn("- score: latency: 10.000000 ms -> 8.000000 ms (-20.00%)", report_output)
                self.assertIn("Frontier", report_output)
                self.assertIn("- net: latency: 10.000000 ms -> 8.000000 ms; 2.000000 ms better (20.00%)", report_output)
                self.assertIn("Receipt Log", report_output)

                results_file = workspace / ".tereo" / "results.tsv"
                self.assertTrue(results_file.exists())
                with results_file.open() as handle:
                    rows = list(csv.DictReader(handle, delimiter="\t"))

                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0]["kind"], "baseline")
                self.assertEqual(rows[1]["kind"], "try")
                self.assertEqual(rows[1]["verdict"], "keep")
                self.assertEqual(rows[1]["current_metric"], "8.0")
                self.assertEqual(rows[1]["improvement_percent"], "20.0")

    def test_prove_creates_baseline_then_compares_and_log_lists_history(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            with pushd(workspace):
                self.run_main(
                    [
                        "init",
                        "--check",
                        'python3 -c "print(\'latency_ms: 10\')"',
                        "--metric-pattern",
                        r"latency_ms: ([0-9.]+)",
                        "--direction",
                        "lower",
                        "--metric-name",
                        "latency",
                        "--metric-unit",
                        "ms",
                    ]
                )

                baseline_code, baseline_output = self.run_main(["prove", "--promise", "Current latency is the baseline"])
                self.assertEqual(baseline_code, 0)
                self.assertIn("verdict: hold", baseline_output)
                self.assertIn("evidence: 3 runs", baseline_output)
                self.assertIn("next: make one small change, keep the same check", baseline_output)

                try_code, try_output = self.run_main(
                    [
                        "prove",
                        "--check",
                        'python3 -c "print(\'latency_ms: 8\')"',
                        "--promise",
                        "Cache hits lower latency",
                        "--scope",
                        "src/cache.py",
                    ]
                )
                self.assertEqual(try_code, 0)
                self.assertIn("verdict: keep", try_output)
                self.assertIn("win_probability=", try_output)
                self.assertIn("next: for this proof: keep this receipt as the new local baseline", try_output)

                _, log_output = self.run_main(["log", "--last", "2"])
                self.assertIn("Receipt Log", log_output)
                self.assertIn("| hold | latency: 10.000000 ms | Current latency is the baseline", log_output)
                self.assertIn("| keep | latency: 10.000000 ms -> 8.000000 ms; 2.000000 ms better (20.00%) | Cache hits lower latency", log_output)

    def test_prove_auto_seeds_named_metric_protocol_on_first_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            with pushd(workspace):
                baseline_code, baseline_output = self.run_main(
                    [
                        "prove",
                        "--check",
                        'python3 -c "print(\'TEREO_METRIC latency 10 lower ms\')"',
                        "--promise",
                        "Current latency is the baseline",
                    ]
                )
                self.assertEqual(baseline_code, 0)
                self.assertIn("verdict: hold", baseline_output)
                self.assertIn("latency: 10.000000 ms", baseline_output)
                self.assertIn("evidence: 3 runs", baseline_output)

                state = cli.load_state(workspace)
                proof = state["proofs"][state["active_proof"]]
                self.assertEqual(proof["metric_name"], "latency")
                self.assertEqual(proof["metric_direction"], "lower")
                self.assertEqual(proof["metric_unit"], "ms")

                try_code, try_output = self.run_main(
                    [
                        "prove",
                        "--check",
                        'python3 -c "print(\'TEREO_METRIC latency 8 lower ms\')"',
                        "--promise",
                        "Cache hits lower latency",
                    ]
                )
                self.assertEqual(try_code, 0)
                self.assertIn("verdict: keep", try_output)
                self.assertIn("latency: 10.000000 ms -> 8.000000 ms", try_output)

    def test_prove_auto_seeds_known_metric_preset_on_first_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            with pushd(workspace):
                baseline_code, baseline_output = self.run_main(
                    [
                        "prove",
                        "--check",
                        'python3 -c "print(\'latency_ms: 10\')"',
                        "--promise",
                        "Current latency is the baseline",
                    ]
                )
                self.assertEqual(baseline_code, 0)
                self.assertIn("verdict: hold", baseline_output)
                self.assertIn("latency: 10.000000 ms", baseline_output)
                self.assertIn("evidence: 3 runs", baseline_output)

                state = cli.load_state(workspace)
                proof = state["proofs"][state["active_proof"]]
                self.assertEqual(proof["metric_name"], "latency")
                self.assertEqual(proof["metric_direction"], "lower")
                self.assertEqual(proof["metric_unit"], "ms")

                try_code, try_output = self.run_main(
                    [
                        "prove",
                        "--check",
                        'python3 -c "print(\'latency_ms: 8\')"',
                        "--promise",
                        "Cache hits lower latency",
                    ]
                )
                self.assertEqual(try_code, 0)
                self.assertIn("verdict: keep", try_output)
                self.assertIn("latency: 10.000000 ms -> 8.000000 ms", try_output)

    def test_missing_metric_note_points_to_named_metric_or_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            with pushd(workspace):
                baseline_code, _ = self.run_main(
                    [
                        "prove",
                        "--check",
                        'python3 -c "print(\'ready\')"',
                        "--promise",
                        "Current output is the baseline",
                    ]
                )
                self.assertEqual(baseline_code, 0)

                try_code, try_output = self.run_main(
                    [
                        "prove",
                        "--check",
                        'python3 -c "print(\'ready\')"',
                        "--promise",
                        "Still no comparable metric",
                    ]
                )
                self.assertEqual(try_code, 0)
                self.assertIn("No comparable metric was found. Print `TEREO_METRIC name value direction [unit]` or pass `--metric-pattern`.", try_output)

    def test_prove_keeps_baselines_separate_when_check_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            with pushd(workspace):
                self.run_main(
                    [
                        "init",
                        "--check",
                        'python3 -c "print(\'latency_ms: 10\')"',
                        "--metric-pattern",
                        r"latency_ms: ([0-9.]+)",
                        "--direction",
                        "lower",
                        "--metric-name",
                        "latency",
                        "--metric-unit",
                        "ms",
                    ]
                )

                original_code, original_output = self.run_main(
                    [
                        "prove",
                        "--proof",
                        "original",
                        "--promise",
                        "Current latency is the original baseline",
                    ]
                )
                self.assertEqual(original_code, 0)
                self.assertIn("verdict: hold", original_output)
                self.assertIn("latency: 10.000000 ms", original_output)
                state = cli.load_state(workspace)
                original_proof = state["active_proof"]
                original_baseline = state["baseline_receipt"]

                switched_code, switched_output = self.run_main(
                    [
                        "prove",
                        "--proof",
                        "separate",
                        "--check",
                        'python3 -c "print(\'latency_ms: 30\')"',
                        "--promise",
                        "Current latency is a separate baseline",
                    ]
                )
                self.assertEqual(switched_code, 0)
                self.assertIn("verdict: hold", switched_output)
                self.assertIn("latency: 30.000000 ms", switched_output)
                self.assertNotIn("10.000000 ms -> 30.000000 ms", switched_output)
                state = cli.load_state(workspace)
                switched_proof = state["active_proof"]
                switched_baseline = state["baseline_receipt"]
                self.assertNotEqual(original_proof, switched_proof)
                self.assertNotEqual(original_baseline, switched_baseline)

                back_code, back_output = self.run_main(
                    [
                        "prove",
                        "--proof",
                        "original",
                        "--check",
                        'python3 -c "print(\'latency_ms: 8\')"',
                        "--promise",
                        "Cache hits lower latency for the original baseline",
                    ]
                )
                self.assertEqual(back_code, 0)
                self.assertIn("verdict: keep", back_output)
                self.assertIn("latency: 10.000000 ms -> 8.000000 ms", back_output)
                self.assertNotIn("latency: 30.000000 ms -> 8.000000 ms", back_output)

                state = cli.load_state(workspace)
                self.assertEqual(state["active_proof"], "original")
                self.assertEqual(state["proofs"]["separate"]["baseline_receipt"], switched_baseline)
                latest_receipt = cli.read_receipt(workspace, state["latest_receipt"])
                self.assertEqual(latest_receipt["baseline"]["id"], original_baseline)
                self.assertEqual(latest_receipt["proof"]["key"], "original")

                _, log_output = self.run_main(["log", "--proof", "original", "--last", "5"])
                self.assertIn("Current latency is the original baseline", log_output)
                self.assertIn("Cache hits lower latency for the original baseline", log_output)
                self.assertNotIn("Current latency is a separate baseline", log_output)

    def test_parallel_proofs_do_not_clobber_each_other(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            slow = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "tereo",
                    "prove",
                    "--check",
                    'python3 -c "import time; time.sleep(0.3); print(\'latency_ms: 10\')"',
                    "--metric-pattern",
                    r"latency_ms: ([0-9.]+)",
                    "--direction",
                    "lower",
                    "--metric-name",
                    "latency",
                    "--metric-unit",
                    "ms",
                    "--promise",
                    "Alpha baseline",
                ],
                cwd=workspace,
                env=self.cli_env(thread_id="alpha"),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            time.sleep(0.05)
            fast = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "tereo",
                    "prove",
                    "--check",
                    'python3 -c "print(\'latency_ms: 20\')"',
                    "--metric-pattern",
                    r"latency_ms: ([0-9.]+)",
                    "--direction",
                    "lower",
                    "--metric-name",
                    "latency",
                    "--metric-unit",
                    "ms",
                    "--promise",
                    "Beta baseline",
                ],
                cwd=workspace,
                env=self.cli_env(thread_id="beta"),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            slow_stdout, slow_stderr = slow.communicate()
            fast_stdout, fast_stderr = fast.communicate()
            self.assertEqual(slow.returncode, 0, slow_stderr)
            self.assertEqual(fast.returncode, 0, fast_stderr)
            self.assertIn("verdict: hold", slow_stdout)
            self.assertIn("verdict: hold", fast_stdout)

            state = cli.load_state(workspace)
            alpha_key = "thread:alpha"
            beta_key = "thread:beta"
            self.assertIn(alpha_key, state["proofs"])
            self.assertIn(beta_key, state["proofs"])
            self.assertNotEqual(state["proofs"][alpha_key]["baseline_receipt"], state["proofs"][beta_key]["baseline_receipt"])

    def test_same_proof_parallel_runs_serialize_into_baseline_then_try(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            env = self.cli_env(thread_id="shared")
            baseline_proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "tereo",
                    "prove",
                    "--check",
                    'python3 -c "import time; time.sleep(0.3); print(\'latency_ms: 10\')"',
                    "--metric-pattern",
                    r"latency_ms: ([0-9.]+)",
                    "--direction",
                    "lower",
                    "--metric-name",
                    "latency",
                    "--metric-unit",
                    "ms",
                    "--promise",
                    "Shared baseline",
                ],
                cwd=workspace,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            time.sleep(0.05)
            try_proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "tereo",
                    "prove",
                    "--check",
                    'python3 -c "print(\'latency_ms: 8\')"',
                    "--metric-pattern",
                    r"latency_ms: ([0-9.]+)",
                    "--direction",
                    "lower",
                    "--metric-name",
                    "latency",
                    "--metric-unit",
                    "ms",
                    "--promise",
                    "Shared improvement",
                ],
                cwd=workspace,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            baseline_stdout, baseline_stderr = baseline_proc.communicate()
            try_stdout, try_stderr = try_proc.communicate()
            self.assertEqual(baseline_proc.returncode, 0, baseline_stderr)
            self.assertEqual(try_proc.returncode, 0, try_stderr)
            self.assertIn("verdict: hold", baseline_stdout)
            self.assertIn("verdict: keep", try_stdout)
            self.assertIn("latency: 10.000000 ms -> 8.000000 ms", try_stdout)

            state = cli.load_state(workspace)
            proof_key = "thread:shared"
            latest = cli.read_receipt(workspace, state["proofs"][proof_key]["latest_receipt"])
            self.assertEqual(latest["kind"], "try")
            self.assertEqual(latest["baseline"]["id"], state["proofs"][proof_key]["initial_baseline_receipt"])

    def test_show_and_log_follow_thread_lane_without_manual_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            alpha = self.run_cli_subprocess(
                workspace,
                [
                    "prove",
                    "--check",
                    'python3 -c "print(\'latency_ms: 10\')"',
                    "--metric-pattern",
                    r"latency_ms: ([0-9.]+)",
                    "--direction",
                    "lower",
                    "--metric-name",
                    "latency",
                    "--metric-unit",
                    "ms",
                    "--promise",
                    "Alpha baseline",
                ],
                thread_id="alpha-view",
            )
            beta = self.run_cli_subprocess(
                workspace,
                [
                    "prove",
                    "--check",
                    'python3 -c "print(\'latency_ms: 20\')"',
                    "--metric-pattern",
                    r"latency_ms: ([0-9.]+)",
                    "--direction",
                    "lower",
                    "--metric-name",
                    "latency",
                    "--metric-unit",
                    "ms",
                    "--promise",
                    "Beta baseline",
                ],
                thread_id="beta-view",
            )
            self.assertEqual(alpha.returncode, 0, alpha.stderr)
            self.assertEqual(beta.returncode, 0, beta.stderr)

            alpha_show = self.run_cli_subprocess(workspace, ["show"], thread_id="alpha-view")
            alpha_log = self.run_cli_subprocess(workspace, ["log", "--last", "5"], thread_id="alpha-view")
            beta_show = self.run_cli_subprocess(workspace, ["show"], thread_id="beta-view")

            self.assertIn("promise: Alpha baseline", alpha_show.stdout)
            self.assertNotIn("Beta baseline", alpha_show.stdout)
            self.assertIn("Alpha baseline", alpha_log.stdout)
            self.assertNotIn("Beta baseline", alpha_log.stdout)
            self.assertIn("promise: Beta baseline", beta_show.stdout)

    def test_prove_auto_doubt_turns_weak_signal_into_hold(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            script = self.write_metric_stream_script(workspace)
            baseline_values = workspace / "baseline_values.txt"
            try_values = workspace / "try_values.txt"
            baseline_values.write_text("10.0\n10.0\n10.0\n")
            try_values.write_text("9.95\n10.05\n10.0\n9.98\n10.02\n")

            with pushd(workspace):
                self.run_main(
                    [
                        "init",
                        "--check",
                        f"python3 {script.name} {baseline_values.name}",
                        "--metric-pattern",
                        r"latency_ms: ([0-9.]+)",
                        "--direction",
                        "lower",
                        "--metric-name",
                        "latency",
                        "--metric-unit",
                        "ms",
                    ]
                )

                baseline_code, baseline_output = self.run_main(["prove", "--promise", "Current latency is the baseline"])
                self.assertEqual(baseline_code, 0)
                self.assertIn("evidence: 3 runs", baseline_output)

                try_code, try_output = self.run_main(
                    [
                        "prove",
                        "--check",
                        f"python3 {script.name} {try_values.name}",
                        "--promise",
                        "Tiny cache tweak lowers latency",
                    ]
                )
                self.assertEqual(try_code, 0)
                self.assertIn("verdict: hold", try_output)
                self.assertIn("next: for this proof: shrink the scope, stabilize the check, or add --repeat / `tereo control --repeat 5`", try_output)

                state = cli.load_state(workspace)
                latest_receipt = cli.read_receipt(workspace, state["latest_receipt"])
                self.assertEqual(latest_receipt["result"]["verdict"], "review")
                self.assertEqual(latest_receipt["evidence"]["repeat"], 5)
                self.assertEqual(latest_receipt["evidence"]["confidence"], "low")

    def test_demo_runs_throwaway_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            with pushd(workspace):
                code, output = self.run_main(["demo"])
                self.assertEqual(code, 0)
                self.assertIn("demo workspace:", output)
                self.assertIn("this demo uses a throwaway check", output)
                self.assertIn("verdict: keep", output)
                self.assertIn("Receipt Log", output)

    def test_init_preset_pytest_sets_default_check(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            with pushd(workspace):
                init_code, init_output = self.run_main(["init", "--preset", "pytest"])
                self.assertEqual(init_code, 0)
                self.assertIn("preset: pytest", init_output)
                self.assertIn("default check: pytest -q", init_output)
                self.assertIn("good check: show one gain and catch the core breakage that would make that gain false.", init_output)

                state = cli.load_state(workspace)
                self.assertEqual(state["default_check"], "pytest -q")

    def test_doctor_suggests_presets_from_repo_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            (workspace / "tests").mkdir()
            (workspace / "package.json").write_text("{}\n")
            (workspace / "smoke-test.sh").write_text("#!/bin/sh\nexit 0\n")
            (workspace / "bench.sh").write_text("#!/bin/sh\necho latency_ms: 10\n")

            with pushd(workspace):
                code, output = self.run_main(["doctor"])
                self.assertEqual(code, 0)
                self.assertIn("suggested first checks:", output)
                self.assertIn("good check: show one gain and catch the core breakage that would make that gain false.", output)
                self.assertIn("try: tereo init --preset pytest", output)
                self.assertIn("try: tereo init --preset npm-test", output)
                self.assertIn("try: tereo init --preset smoke", output)
                self.assertIn("try: tereo init --preset latency", output)

    def test_doctor_detects_runtime_tests_layout_as_python_preset(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            (workspace / "runtime" / "tests").mkdir(parents=True)

            with pushd(workspace):
                code, output = self.run_main(["doctor"])
                self.assertEqual(code, 0)
                self.assertIn("try: tereo init --preset pytest", output)

    def test_control_rerun_marks_small_drift_stable_and_large_drift_as_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            with pushd(workspace):
                self.run_main(
                    [
                        "init",
                        "--check",
                        'python3 -c "print(\'latency_ms: 10\')"',
                        "--metric-pattern",
                        r"latency_ms: ([0-9.]+)",
                        "--direction",
                        "lower",
                        "--metric-name",
                        "latency",
                        "--metric-unit",
                        "ms",
                    ]
                )
                self.run_main(["baseline", "--promise", "Current latency is the baseline"])

                stable_code, stable_output = self.run_main(
                    [
                        "control",
                        "--check",
                        'python3 -c "print(\'latency_ms: 10.05\')"',
                        "--max-drift-percent",
                        "1.0",
                        "--repeat",
                        "3",
                    ]
                )
                self.assertEqual(stable_code, 0)
                self.assertIn("verdict: hold", stable_output)
                self.assertIn("confidence:", stable_output)

                drift_code, drift_output = self.run_main(
                    [
                        "control",
                        "--check",
                        'python3 -c "print(\'latency_ms: 12\')"',
                        "--max-drift-percent",
                        "1.0",
                        "--repeat",
                        "3",
                    ]
                )
                self.assertEqual(drift_code, 0)
                self.assertIn("verdict: drop", drift_output)
                self.assertIn("confidence: low", drift_output)

    def test_timeout_baseline_and_recovery_try_work(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            with pushd(workspace):
                self.run_main(
                    [
                        "init",
                        "--check",
                        'python3 -c "import time; time.sleep(0.2)"',
                        "--timeout-seconds",
                        "0.05",
                    ]
                )

                baseline_code, baseline_output = self.run_main(
                    [
                        "baseline",
                        "--promise",
                        "Current check times out",
                    ]
                )
                self.assertEqual(baseline_code, cli.TIMEOUT_EXIT_CODE)
                self.assertIn("Baseline saved", baseline_output)

                try_code, try_output = self.run_main(
                    [
                        "try",
                        "--check",
                        'python3 -c "print(\'ok\')"',
                        "--timeout-seconds",
                        "0.2",
                        "--promise",
                        "The check should finish quickly",
                    ]
                )
                self.assertEqual(try_code, 0)
                self.assertIn("verdict: keep", try_output)
                self.assertIn("removed a timeout", try_output)

    def test_report_shows_measurement_confidence_after_control(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            with pushd(workspace):
                self.run_main(
                    [
                        "init",
                        "--check",
                        'python3 -c "print(\'latency_ms: 10\')"',
                        "--metric-pattern",
                        r"latency_ms: ([0-9.]+)",
                        "--direction",
                        "lower",
                        "--metric-name",
                        "latency",
                        "--metric-unit",
                        "ms",
                    ]
                )
                self.run_main(["baseline", "--promise", "Current latency is the baseline"])
                self.run_main(
                    [
                        "try",
                        "--check",
                        'python3 -c "print(\'latency_ms: 8\')"',
                        "--promise",
                        "Cache hits lower latency",
                    ]
                )
                self.run_main(
                    [
                        "control",
                        "--check",
                        'python3 -c "print(\'latency_ms: 8.02\')"',
                        "--repeat",
                        "3",
                        "--max-drift-percent",
                        "1.0",
                    ]
                )

                _, report_output = self.run_main(["report"])
                self.assertIn("Confidence", report_output)
                self.assertIn("- confidence: `high`", report_output)
                self.assertIn("- signal_to_noise: `80.00x`", report_output)
                self.assertIn("- control:", report_output)

                _, comment_output = self.run_main(["comment"])
                self.assertIn("## TEREO", comment_output)
                self.assertIn("`KEEP` · `HIGH`", comment_output)
                self.assertIn("`latency: 10.000000 ms -> 8.000000 ms (-20.00%)`", comment_output)
                self.assertIn("Cache hits lower latency", comment_output)
                self.assertIn("baseline: `latency: 8.000000 ms`", comment_output)
                self.assertIn("net: `latency: 10.000000 ms -> 8.000000 ms; 2.000000 ms better (20.00%)`", comment_output)
                self.assertIn("> keep only if gain > noise", comment_output)

    def test_repeated_baseline_and_try_emit_bootstrap_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            script = self.write_metric_stream_script(workspace)
            baseline_values = workspace / "baseline_values.txt"
            try_values = workspace / "try_values.txt"
            baseline_values.write_text("10.0\n10.2\n9.8\n10.1\n9.9\n")
            try_values.write_text("8.1\n7.9\n8.0\n8.2\n7.8\n")

            with pushd(workspace):
                self.run_main(
                    [
                        "init",
                        "--check",
                        f"python3 {script.name} {baseline_values.name}",
                        "--metric-pattern",
                        r"latency_ms: ([0-9.]+)",
                        "--direction",
                        "lower",
                        "--metric-name",
                        "latency",
                        "--metric-unit",
                        "ms",
                    ]
                )

                baseline_code, baseline_output = self.run_main(
                    [
                        "baseline",
                        "--promise",
                        "Current latency is the repeated baseline",
                        "--repeat",
                        "5",
                    ]
                )
                self.assertEqual(baseline_code, 0)
                self.assertIn("evidence: 5 runs", baseline_output)

                try_code, try_output = self.run_main(
                    [
                        "try",
                        "--check",
                        f"python3 {script.name} {try_values.name}",
                        "--promise",
                        "Cache hits lower repeated latency",
                        "--repeat",
                        "5",
                    ]
                )
                self.assertEqual(try_code, 0)
                self.assertIn("evidence: win_probability=", try_output)
                self.assertIn("confidence=high", try_output)

                state = cli.load_state(workspace)
                latest_receipt = cli.read_receipt(workspace, state["latest_receipt"])
                self.assertEqual(latest_receipt["evidence"]["repeat"], 5)
                self.assertEqual(len(latest_receipt["evidence"]["samples"]), 5)
                self.assertEqual(latest_receipt["evidence"]["confidence"], "high")
                self.assertGreater(latest_receipt["evidence"]["win"], 0.99)
                self.assertGreater(latest_receipt["evidence"]["gain_ci"][0], 0.0)
                self.assertGreater(latest_receipt["evidence"]["ratio"], 1.0)

                _, report_output = self.run_main(["report"])
                self.assertIn("Confidence", report_output)
                self.assertIn("- win_probability: `100.0%`", report_output)
                self.assertIn("- noise:", report_output)

                results_file = workspace / ".tereo" / "results.tsv"
                with results_file.open() as handle:
                    rows = list(csv.DictReader(handle, delimiter="\t"))
                self.assertEqual(rows[-1]["repeat_count"], "5")
                self.assertNotEqual(rows[-1]["win_probability"], "")
                self.assertNotEqual(rows[-1]["metric_ci_low"], "")


if __name__ == "__main__":
    unittest.main()
