import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_results import (  # noqa: E402
    compute_baseline_ratios,
    compute_e2e_stats,
    generate_report_data,
    load_experiment_results,
)


def _write_run(
    tmp_path: Path,
    name: str,
    *,
    mode: str,
    operator: str = "allreduce",
    gpus: int = 8,
    msg_bytes: int = 1048576,
    granularity: str | None = None,
    algorithm: str = "ring",
    e2e_times: list[float] | None = None,
) -> Path:
    run_dir = tmp_path / name
    run_dir.mkdir(parents=True)
    metadata = {
        "mode": mode,
        "operator": operator,
        "gpus": gpus,
        "msg_bytes": msg_bytes,
        "granularity": granularity,
        "algorithm": algorithm,
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    if e2e_times is not None:
        (run_dir / "e2e_times.json").write_text(json.dumps(e2e_times), encoding="utf-8")
    return run_dir


def test_load_experiment_results_reads_metadata_and_e2e_times(tmp_path):
    baseline_dir = _write_run(
        tmp_path,
        "baseline",
        mode="packet_switch",
        e2e_times=[10.0, 12.0, 14.0],
    )
    calendar_dir = _write_run(
        tmp_path,
        "calendar",
        mode="calendar",
        granularity="flow",
        e2e_times=[6.0, 7.0, 8.0],
    )

    results = load_experiment_results(tmp_path)

    assert len(results) == 2
    by_mode = {result.mode: result for result in results}
    assert by_mode["packet_switch"].e2e_times == [10.0, 12.0, 14.0]
    assert by_mode["packet_switch"].run_dir == baseline_dir
    assert by_mode["calendar"].granularity == "flow"
    assert by_mode["calendar"].run_dir == calendar_dir


def test_load_experiment_results_uses_empty_times_when_file_missing(tmp_path):
    _write_run(tmp_path, "calendar", mode="calendar", e2e_times=None)

    results = load_experiment_results(tmp_path)

    assert len(results) == 1
    assert results[0].e2e_times == []


def test_compute_e2e_stats_returns_percentiles():
    stats = compute_e2e_stats([1.0, 2.0, 3.0, 4.0, 5.0])

    assert stats["mean"] == pytest.approx(3.0)
    assert stats["p50"] == pytest.approx(3.0)
    assert stats["p95"] == pytest.approx(4.8)
    assert stats["p99"] == pytest.approx(4.96)


def test_compute_e2e_stats_returns_zeros_for_empty_times():
    assert compute_e2e_stats([]) == {
        "mean": 0.0,
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
    }


def test_compute_baseline_ratios_reports_faster_calendar_ratio(tmp_path):
    _write_run(tmp_path, "baseline", mode="packet_switch", e2e_times=[10.0, 10.0, 10.0])
    _write_run(
        tmp_path,
        "calendar",
        mode="calendar",
        granularity="flow",
        e2e_times=[5.0, 5.0, 5.0],
    )
    results = load_experiment_results(tmp_path)

    ratios = compute_baseline_ratios(results)

    assert len(ratios) == 1
    assert ratios[0]["ratio"] == pytest.approx(0.5)
    assert ratios[0]["ratio"] < 1.0
    assert ratios[0]["baseline_found"] is True


def test_compute_baseline_ratios_marks_missing_baseline(tmp_path):
    _write_run(tmp_path, "calendar", mode="calendar", e2e_times=[5.0, 5.0, 5.0])
    results = load_experiment_results(tmp_path)

    ratios = compute_baseline_ratios(results)

    assert len(ratios) == 1
    assert ratios[0]["ratio"] is None
    assert ratios[0]["baseline_found"] is False


def test_generate_report_data_contains_required_sections(tmp_path):
    _write_run(tmp_path, "baseline", mode="packet_switch", e2e_times=[10.0, 10.0, 10.0])
    _write_run(
        tmp_path,
        "calendar",
        mode="calendar",
        granularity="flow",
        e2e_times=[5.0, 5.0, 5.0],
    )
    results = load_experiment_results(tmp_path)

    report = generate_report_data(results)

    assert set(report) >= {"executive_summary", "per_operator", "recommendations"}
    assert report["executive_summary"]["total_runs"] == 2
    assert report["per_operator"]["allreduce"]["calendar_runs"] == 1
    assert report["recommendations"]


def test_cli_writes_json_report(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    _write_run(results_dir, "baseline", mode="packet_switch", e2e_times=[10.0])
    _write_run(results_dir, "calendar", mode="calendar", e2e_times=[5.0])
    output = tmp_path / "report.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "analyze_results.py"),
            "--results-dir",
            str(results_dir),
            "--output",
            str(output),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["executive_summary"]["total_runs"] == 2
