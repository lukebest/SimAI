#!/usr/bin/env python3
"""Run full-factor LLM inference TPS experiments for SimAI + Vidur."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import itertools
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - startup guard
    raise SystemExit(
        "Missing dependency 'PyYAML'. Run with the project venv or install via "
        "`pip install pyyaml`."
    ) from exc


@dataclass
class RunSpec:
    backend: str
    network_level_id: str
    network_label: str
    error_rate_per_link: float
    network_arg_overrides: Dict[str, Any]
    memory_level_id: str
    memory_label: str
    memory_bandwidth_gbps: float
    repeat: int

    @property
    def run_id(self) -> str:
        return (
            f"{self.backend}__{self.network_level_id}__"
            f"{self.memory_level_id}__r{self.repeat}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TPS full-factor experiments.")
    parser.add_argument(
        "--config",
        default="/home/luke/SimAI/experiments/llm_inference_tps_matrix.yaml",
        help="Path to experiment YAML config.",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Limit the number of runs (0 means all).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip runs already present as success in manifest.",
    )
    return parser.parse_args()


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_run_specs(cfg: Dict[str, Any]) -> List[RunSpec]:
    repeats = int(cfg["repeats"])
    backends = list(cfg["backends"])
    net_levels = list(cfg["network_determinism_levels"])
    mem_levels = list(cfg["memory_bandwidth_levels"])

    specs: List[RunSpec] = []
    for backend, net, mem, repeat in itertools.product(
        backends, net_levels, mem_levels, range(1, repeats + 1)
    ):
        specs.append(
            RunSpec(
                backend=backend,
                network_level_id=net["id"],
                network_label=net["label"],
                error_rate_per_link=float(net["error_rate_per_link"]),
                network_arg_overrides=dict(net.get("arg_overrides", {})),
                memory_level_id=mem["id"],
                memory_label=mem["label"],
                memory_bandwidth_gbps=float(mem["bandwidth_gbps"]),
                repeat=repeat,
            )
        )
    return specs


def write_ns3_config(base_config: Path, out_path: Path, error_rate: float) -> None:
    text = base_config.read_text(encoding="utf-8")
    replaced = False
    lines: List[str] = []
    for raw in text.splitlines():
        if raw.strip().startswith("ERROR_RATE_PER_LINK "):
            lines.append(f"ERROR_RATE_PER_LINK {error_rate:.8f}")
            replaced = True
        else:
            lines.append(raw)
    if not replaced:
        lines.append(f"ERROR_RATE_PER_LINK {error_rate:.8f}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def bool_to_cli(key: str, value: bool) -> List[str]:
    return [f"--{key}" if value else f"--no-{key}"]


def flatten_args(arg_map: Dict[str, Any]) -> List[str]:
    result: List[str] = []
    for key, value in arg_map.items():
        if isinstance(value, bool):
            result.extend(bool_to_cli(key, value))
        else:
            result.extend([f"--{key}", str(value)])
    return result


def find_latest_subdir(parent: Path) -> Path | None:
    if not parent.exists():
        return None
    dirs = [p for p in parent.iterdir() if p.is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


def ensure_manifest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "run_id",
                "backend",
                "network_level_id",
                "network_label",
                "error_rate_per_link",
                "memory_level_id",
                "memory_label",
                "memory_bandwidth_gbps",
                "repeat",
                "status",
                "return_code",
                "duration_s",
                "generated_config",
                "metrics_output_root",
                "metrics_output_dir",
                "request_metrics_csv",
                "command",
            ],
        )
        writer.writeheader()


def load_successful_run_ids(manifest: Path) -> set[str]:
    if not manifest.exists():
        return set()
    run_ids: set[str] = set()
    with manifest.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status") == "success":
                run_ids.add(row["run_id"])
    return run_ids


def append_manifest_row(path: Path, row: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writerow(row)


def run_experiment(cfg: Dict[str, Any], spec: RunSpec, dry_run: bool) -> Dict[str, Any]:
    simai_root = Path(cfg["simai_root"]).resolve()
    # Keep venv interpreter path as configured; resolving symlinks can silently
    # switch back to system python and lose venv packages.
    vidur_python = Path(cfg["vidur_python"]).expanduser()
    vidur_workdir = Path(cfg["vidur_workdir"]).resolve()

    out_cfg_dir = Path(cfg["output"]["generated_configs_dir"]).resolve()
    metrics_root = Path(cfg["output"]["root"]).resolve() / "vidur_runs" / spec.run_id
    generated_cfg = out_cfg_dir / f"{spec.run_id}.conf"

    base_cfg = Path(cfg["simai"]["base_config"]).resolve()
    write_ns3_config(base_cfg, generated_cfg, spec.error_rate_per_link)

    common_args = dict(cfg["common_args"])
    common_args.update(spec.network_arg_overrides)
    common_args["metrics_config_output_dir"] = str(metrics_root)
    common_args["random_forrest_execution_time_predictor_config_backend"] = spec.backend
    common_args["random_forrest_execution_time_predictor_config_simai_dir"] = str(simai_root)
    common_args["random_forrest_execution_time_predictor_config_simai_simulation_topo"] = str(
        Path(cfg["simai"]["topo"]).resolve()
    )
    common_args["random_forrest_execution_time_predictor_config_simai_simulation_config"] = str(
        generated_cfg
    )
    # Keep these aligned so "memory medium bandwidth" is reflected consistently.
    mem_bw_int = int(round(spec.memory_bandwidth_gbps))
    common_args["replica_config_pd_p2p_comm_bandwidth"] = mem_bw_int
    common_args["replica_config_nvlink_bandwidth"] = mem_bw_int
    common_args["replica_config_rdma_bandwidth"] = mem_bw_int
    common_args["replica_config_pd_p2p_comm_dtype"] = "float32"

    command = [
        str(vidur_python),
        "-m",
        str(cfg["vidur_module"]),
        *flatten_args(common_args),
    ]
    command_str = " ".join(command)
    if dry_run:
        return {
            "status": "dry_run",
            "return_code": 0,
            "duration_s": 0.0,
            "generated_config": str(generated_cfg),
            "metrics_output_root": str(metrics_root),
            "metrics_output_dir": "",
            "request_metrics_csv": "",
            "command": command_str,
        }

    started = time.time()
    preflight = subprocess.run(
        [str(vidur_python), "-c", "import networkx"],
        text=True,
        capture_output=True,
    )
    if preflight.returncode != 0:
        return {
            "status": "failed",
            "return_code": preflight.returncode,
            "duration_s": 0.0,
            "generated_config": str(generated_cfg),
            "metrics_output_root": str(metrics_root),
            "metrics_output_dir": "",
            "request_metrics_csv": "",
            "command": command_str,
        }

    proc = subprocess.run(
        command,
        cwd=str(vidur_workdir),
        text=True,
        capture_output=True,
    )
    duration = time.time() - started

    latest = find_latest_subdir(metrics_root)
    request_metrics = (
        latest / "request_metrics.csv" if latest and (latest / "request_metrics.csv").exists() else None
    )
    status = "success" if proc.returncode == 0 and request_metrics else "failed"

    if status == "failed":
        log_file = metrics_root.parent / f"{spec.run_id}.stderr.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text(
            f"STDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}\n", encoding="utf-8"
        )

    return {
        "status": status,
        "return_code": proc.returncode,
        "duration_s": round(duration, 3),
        "generated_config": str(generated_cfg),
        "metrics_output_root": str(metrics_root),
        "metrics_output_dir": str(latest) if latest else "",
        "request_metrics_csv": str(request_metrics) if request_metrics else "",
        "command": command_str,
    }


def main() -> int:
    args = parse_args()
    cfg = load_config(Path(args.config))

    manifest = Path(cfg["output"]["runs_manifest"]).resolve()
    ensure_manifest(manifest)
    success_run_ids = load_successful_run_ids(manifest) if args.skip_existing else set()

    specs = build_run_specs(cfg)
    if args.max_runs > 0:
        specs = specs[: args.max_runs]

    for idx, spec in enumerate(specs, start=1):
        if spec.run_id in success_run_ids:
            print(f"[{idx}/{len(specs)}] skip existing success run: {spec.run_id}")
            continue

        print(
            f"[{idx}/{len(specs)}] run={spec.run_id} "
            f"backend={spec.backend} net={spec.network_label} mem={spec.memory_label}"
        )
        result = run_experiment(cfg, spec, dry_run=args.dry_run)
        row = {
            "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
            "run_id": spec.run_id,
            "backend": spec.backend,
            "network_level_id": spec.network_level_id,
            "network_label": spec.network_label,
            "error_rate_per_link": spec.error_rate_per_link,
            "memory_level_id": spec.memory_level_id,
            "memory_label": spec.memory_label,
            "memory_bandwidth_gbps": spec.memory_bandwidth_gbps,
            "repeat": spec.repeat,
            **result,
        }
        append_manifest_row(manifest, row)
        print(
            f"  -> status={row['status']} return_code={row['return_code']} "
            f"metrics={row['request_metrics_csv']}"
        )

    print(f"Manifest written to: {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
