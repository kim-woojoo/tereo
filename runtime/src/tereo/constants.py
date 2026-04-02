APP_DIR = ".tereo"
STATE_FILE = "state.json"
RECEIPTS_DIR = "receipts"
PROMISES_DIR = "promises"
RESULTS_FILE = "results.tsv"
TIMEOUT_EXIT_CODE = 124
AUTO_MEASURE_REPEAT = 3
AUTO_MEASURE_MAX_REPEAT = 5
RESULT_FIELDS = [
    "id",
    "kind",
    "verdict",
    "confidence",
    "metric_name",
    "direction",
    "baseline_metric",
    "current_metric",
    "absolute_change",
    "improvement_percent",
    "signal_percent",
    "noise_percent",
    "signal_to_noise",
    "drift_percent",
    "spread_percent",
    "sample_count",
    "metric_median",
    "metric_stddev",
    "metric_sem",
    "metric_ci_low",
    "metric_ci_high",
    "win_probability",
    "improvement_ci_low",
    "improvement_ci_high",
    "exit_code",
    "duration_seconds",
    "timed_out",
    "repeat_count",
    "scope",
    "promise",
]
