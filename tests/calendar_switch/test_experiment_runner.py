import json
import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_SINGLE = REPO_ROOT / "scripts/run_single_experiment.sh"
RUN_STUDY = REPO_ROOT / "scripts/run_calendar_study.sh"


def run_script(
    *args: str, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{REPO_ROOT / 'venv/bin'}:{env['PATH']}"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_run_single_creates_dry_run_artifacts(tmp_path):
    output_dir = tmp_path / "single"

    result = run_script(
        str(RUN_SINGLE),
        "--dry-run",
        "--mode",
        "calendar_switch",
        "--granularity",
        "phase",
        "--algorithm",
        "bvn",
        "--gpus",
        "4",
        "--operator",
        "allreduce_ring",
        "--msg-bytes",
        "1048576",
        "--output-dir",
        str(output_dir),
        "--slot-ns",
        "2000",
        "--frame-slots",
        "512",
    )

    assert "Dry-run mode" in result.stdout

    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["mode"] == "calendar_switch"
    assert metadata["granularity"] == "phase"
    assert metadata["algorithm"] == "bvn"
    assert metadata["gpus"] == 4
    assert metadata["operator"] == "allreduce_ring"
    assert metadata["msg_bytes"] == 1048576
    assert metadata["slot_ns"] == 2000
    assert metadata["frame_slots"] == 512
    assert metadata["timestamp"]

    workload = json.loads((output_dir / "workload.json").read_text(encoding="utf-8"))
    assert workload["operator"] == "allreduce_ring"
    assert workload["num_gpus"] == 4
    assert workload["msg_bytes"] == 1048576

    conf = (output_dir / "SimAI.conf").read_text(encoding="utf-8")
    assert "ENABLE_CALENDAR_SWITCH 1" in conf
    assert "CALENDAR_SLOT_NS 2000" in conf
    assert "CALENDAR_FRAME_SLOTS 512" in conf
    assert "CALENDAR_GRANULARITY_MODE phase" in conf
    assert "CALENDAR_ALGORITHM bvn" in conf
    assert f"CALENDAR_TRACE_FILE {output_dir}/calendar_trace.csv" in conf


def test_run_single_dry_run_skips_existing_simulator(tmp_path):
    bin_dir = REPO_ROOT / "bin"
    simulator = bin_dir / "SimAI_simulator"
    created_fake_simulator = not simulator.exists()
    marker = tmp_path / "simulator_was_invoked"
    output_dir = tmp_path / "single"

    if created_fake_simulator:
        bin_dir.mkdir(exist_ok=True)
        simulator.write_text(
            "#!/usr/bin/env bash\n"
            "touch \"${SIMAI_FAKE_MARKER}\"\n"
            "echo 'fake simulator should not run' >&2\n"
            "exit 42\n",
            encoding="utf-8",
        )
        simulator.chmod(0o755)

    try:
        result = run_script(
            str(RUN_SINGLE),
            "--dry-run",
            "--output-dir",
            str(output_dir),
            extra_env={"SIMAI_FAKE_MARKER": str(marker)},
        )
    finally:
        if created_fake_simulator:
            simulator.unlink(missing_ok=True)
            try:
                bin_dir.rmdir()
            except OSError:
                pass

    assert "Dry-run mode" in result.stdout
    assert not marker.exists()
    assert not (output_dir / "stdout.log").exists()


def test_run_calendar_study_dry_run_writes_expected_jobs(tmp_path):
    results_dir = tmp_path / "study"

    result = run_script(
        str(RUN_STUDY),
        "--dry-run",
        "--parallel",
        "3",
        "--results-dir",
        str(results_dir),
    )

    jobs_file = results_dir / "jobs.txt"
    jobs = jobs_file.read_text(encoding="utf-8").splitlines()

    assert "Total runs: 864" in result.stdout
    assert "[DRY-RUN] Would execute 864 runs with parallelism 3" in result.stdout
    assert len(jobs) == 864

    baseline_jobs = [job for job in jobs if "--mode packet_switch" in job]
    calendar_jobs = [job for job in jobs if "--mode calendar_switch" in job]
    assert len(baseline_jobs) == 54
    assert len(calendar_jobs) == 810

    assert any(
        "--mode packet_switch" in job
        and "--operator allreduce_ring" in job
        and "--gpus 8" in job
        and "--msg-bytes 1048576" in job
        for job in jobs
    )
    assert any(
        "--mode calendar_switch" in job
        and "--granularity slot" in job
        and "--algorithm round_robin" in job
        and "--operator reduce_scatter" in job
        and "--gpus 16" in job
        and "--msg-bytes 268435456" in job
        for job in jobs
    )


def test_runner_scripts_are_executable():
    for script in [RUN_SINGLE, RUN_STUDY]:
        mode = script.stat().st_mode
        assert mode & stat.S_IXUSR, f"{script} is not user-executable"
