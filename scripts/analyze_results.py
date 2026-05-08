#!/usr/bin/env python3
"""Analyze calendar switch experiment results and emit a JSON report."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ExperimentResult:
    mode: str
    operator: str
    gpus: int
    msg_bytes: int
    granularity: str | None
    algorithm: str
    e2e_times: list[float]
    run_dir: Path


def _metadata_value(metadata: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in metadata:
            return metadata[name]
    return default


def _load_e2e_times(run_dir: Path) -> list[float]:
    times_path = run_dir / "e2e_times.json"
    if not times_path.exists():
        return []

    raw_times = json.loads(times_path.read_text(encoding="utf-8"))
    if isinstance(raw_times, dict):
        raw_times = raw_times.get("e2e_times", raw_times.get("times", []))
    if raw_times is None:
        return []
    return [float(value) for value in raw_times]


def _load_calendar_non_e2e_metrics(run_dir: Path) -> dict[str, float]:
    metrics = {
        "reschedule_events": 0.0,
        "switch_slots_observed": 0.0,
        "switch_attempted": 0.0,
        "switch_allowed": 0.0,
        "switch_blocked": 0.0,
        "switch_block_rate": 0.0,
        "switch_max_q_bytes": 0.0,
        "switch_avg_q_bytes": 0.0,
        "calendar_rows": 0.0,
        "nvswitch_rows": 0.0,
    }

    trace_path = run_dir / "calendar_trace.csv"
    if trace_path.exists():
        with trace_path.open(encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            metrics["reschedule_events"] = float(
                sum(1 for row in reader if row.get("event") == "reschedule")
            )

    switch_path = run_dir / "calendar_trace.csv.switch_metrics.csv"
    if switch_path.exists():
        attempted = 0.0
        allowed = 0.0
        blocked = 0.0
        max_q = 0.0
        weighted_avg_q = 0.0
        slots: set[int] = set()
        with switch_path.open(encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                switch_type = row.get("switch_type", "calendar")
                if switch_type == "nvswitch":
                    metrics["nvswitch_rows"] += 1.0
                else:
                    metrics["calendar_rows"] += 1.0
                slot_idx = int(float(row.get("slot_idx", 0)))
                if "attempted" in row:
                    att = float(row.get("attempted", 0.0))
                    alw = float(row.get("allowed", 0.0))
                    blk = float(row.get("blocked", 0.0))
                    avg_q = float(row.get("avg_q_bytes", 0.0))
                    max_q = max(max_q, float(row.get("max_q_bytes", 0.0)))
                else:
                    # Polling-based format with per-slot deltas.
                    alw = float(row.get("slot_allowed", 0.0))
                    blk = float(row.get("slot_blocked", 0.0))
                    att = alw + blk
                    q0 = float(row.get("egress_bytes_q0", 0.0))
                    non_q0 = float(row.get("egress_bytes_non_q0", row.get("egress_bytes", 0.0)))
                    total_q = q0 + non_q0
                    avg_q = total_q
                    max_q = max(max_q, total_q)
                slots.add(slot_idx)
                attempted += att
                allowed += alw
                blocked += blk
                weighted_avg_q += avg_q * att
        metrics["switch_slots_observed"] = float(len(slots))
        metrics["switch_attempted"] = attempted
        metrics["switch_allowed"] = allowed
        metrics["switch_blocked"] = blocked
        metrics["switch_block_rate"] = (blocked / attempted) if attempted > 0 else 0.0
        metrics["switch_max_q_bytes"] = max_q
        metrics["switch_avg_q_bytes"] = (
            weighted_avg_q / attempted if attempted > 0 else 0.0
        )

    return metrics


def load_experiment_results(results_dir: Path) -> list[ExperimentResult]:
    results = []
    for metadata_path in sorted(results_dir.rglob("metadata.json")):
        run_dir = metadata_path.parent
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        results.append(
            ExperimentResult(
                mode=str(_metadata_value(metadata, "mode", default="")),
                operator=str(_metadata_value(metadata, "operator", default="")),
                gpus=int(_metadata_value(metadata, "gpus", "num_gpus", default=0)),
                msg_bytes=int(_metadata_value(metadata, "msg_bytes", default=0)),
                granularity=_metadata_value(metadata, "granularity", default=None),
                algorithm=str(_metadata_value(metadata, "algorithm", default="")),
                e2e_times=_load_e2e_times(run_dir),
                run_dir=run_dir,
            )
        )
    return results


def compute_e2e_stats(times: list[float]) -> dict[str, float]:
    if not times:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}

    values = np.array(times, dtype=float)
    return {
        "mean": float(np.mean(values)),
        "p50": float(np.percentile(values, 50)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
    }


def _baseline_key(result: ExperimentResult) -> tuple[str, int, int]:
    return (result.operator, result.gpus, result.msg_bytes)


def _is_calendar_result(result: ExperimentResult) -> bool:
    return result.mode != "packet_switch"


def compute_baseline_ratios(results: list[ExperimentResult]) -> list[dict[str, Any]]:
    baselines = {
        _baseline_key(result): result
        for result in results
        if result.mode == "packet_switch"
    }
    ratios = []

    for result in results:
        if not _is_calendar_result(result):
            continue
        if not result.e2e_times:
            continue

        baseline = baselines.get(_baseline_key(result))
        if baseline is not None and not baseline.e2e_times:
            continue

        calendar_stats = compute_e2e_stats(result.e2e_times)
        baseline_stats = compute_e2e_stats(baseline.e2e_times) if baseline else None
        baseline_p95 = baseline_stats["p95"] if baseline_stats else 0.0
        ratio = (
            calendar_stats["p95"] / baseline_p95
            if baseline is not None and baseline_p95 > 0.0
            else None
        )

        ratios.append(
            {
                "operator": result.operator,
                "gpus": result.gpus,
                "msg_bytes": result.msg_bytes,
                "mode": result.mode,
                "granularity": result.granularity,
                "algorithm": result.algorithm,
                "calendar_p95": calendar_stats["p95"],
                "baseline_p95": baseline_p95 if baseline is not None else None,
                "ratio": ratio,
                "baseline_found": baseline is not None,
                "run_dir": str(result.run_dir),
                "non_e2e_metrics": _load_calendar_non_e2e_metrics(result.run_dir),
            }
        )

    return ratios


def _summarize_recommendations(ratios: list[dict[str, Any]]) -> list[str]:
    valid_ratios = [entry for entry in ratios if entry["ratio"] is not None]
    if not valid_ratios:
        return ["Collect matching packet_switch baselines for calendar runs."]

    best = min(valid_ratios, key=lambda entry: entry["ratio"])
    recommendations = [
        (
            "Best observed calendar configuration: "
            f"{best['operator']} {best['gpus']} GPUs "
            f"{best['msg_bytes']} bytes ratio={best['ratio']:.3f}."
        )
    ]
    if any(entry["ratio"] is not None and entry["ratio"] < 1.0 for entry in ratios):
        recommendations.append("Prioritize calendar configurations with p95 below baseline.")
    if any(not entry["baseline_found"] for entry in ratios):
        recommendations.append("Add missing packet_switch baselines before final comparison.")
    return recommendations


def _count_skipped_calendar_runs(results: list[ExperimentResult]) -> dict[str, int]:
    baselines = {
        _baseline_key(result): result
        for result in results
        if result.mode == "packet_switch"
    }
    empty_calendar_runs = 0
    empty_baseline_matches = 0

    for result in results:
        if not _is_calendar_result(result):
            continue
        if not result.e2e_times:
            empty_calendar_runs += 1
            continue
        baseline = baselines.get(_baseline_key(result))
        if baseline is not None and not baseline.e2e_times:
            empty_baseline_matches += 1

    return {
        "skipped_calendar_runs": empty_calendar_runs + empty_baseline_matches,
        "empty_calendar_runs": empty_calendar_runs,
        "empty_baseline_matches": empty_baseline_matches,
    }


def generate_report_data(results: list[ExperimentResult]) -> dict[str, Any]:
    ratios = compute_baseline_ratios(results)
    valid_ratio_values = [entry["ratio"] for entry in ratios if entry["ratio"] is not None]
    skipped_counts = _count_skipped_calendar_runs(results)
    per_operator: dict[str, dict[str, Any]] = {}

    for result in results:
        operator_summary = per_operator.setdefault(
            result.operator,
            {
                "total_runs": 0,
                "baseline_runs": 0,
                "calendar_runs": 0,
                "runs": [],
                "baseline_ratios": [],
                "non_e2e_summary": {
                    "mean_block_rate": 0.0,
                    "max_block_rate": 0.0,
                    "max_queue_bytes": 0.0,
                    "mean_reschedules": 0.0,
                },
            },
        )
        stats = compute_e2e_stats(result.e2e_times)
        operator_summary["total_runs"] += 1
        if result.mode == "packet_switch":
            operator_summary["baseline_runs"] += 1
        else:
            operator_summary["calendar_runs"] += 1
        operator_summary["runs"].append(
            {
                "mode": result.mode,
                "gpus": result.gpus,
                "msg_bytes": result.msg_bytes,
                "granularity": result.granularity,
                "algorithm": result.algorithm,
                "stats": stats,
                "sample_count": len(result.e2e_times),
                "run_dir": str(result.run_dir),
            }
        )

    for ratio in ratios:
        operator_bucket = per_operator.setdefault(
            ratio["operator"],
            {
                "total_runs": 0,
                "baseline_runs": 0,
                "calendar_runs": 0,
                "runs": [],
                "baseline_ratios": [],
                "non_e2e_summary": {
                    "mean_block_rate": 0.0,
                    "max_block_rate": 0.0,
                    "max_queue_bytes": 0.0,
                    "mean_reschedules": 0.0,
                },
            },
        )
        operator_bucket["baseline_ratios"].append(ratio)

    for operator, summary in per_operator.items():
        non_e2e = [
            ratio["non_e2e_metrics"]
            for ratio in summary["baseline_ratios"]
            if ratio.get("non_e2e_metrics")
        ]
        if not non_e2e:
            continue
        block_rates = [item["switch_block_rate"] for item in non_e2e]
        max_q = [item["switch_max_q_bytes"] for item in non_e2e]
        reschedules = [item["reschedule_events"] for item in non_e2e]
        summary["non_e2e_summary"] = {
            "mean_block_rate": float(np.mean(block_rates)),
            "max_block_rate": float(np.max(block_rates)),
            "max_queue_bytes": float(np.max(max_q)),
            "mean_reschedules": float(np.mean(reschedules)),
        }

    return {
        "executive_summary": {
            "total_runs": len(results),
            "baseline_runs": sum(1 for result in results if result.mode == "packet_switch"),
            "calendar_runs": sum(1 for result in results if _is_calendar_result(result)),
            "matched_calendar_runs": len(valid_ratio_values),
            "missing_baselines": sum(1 for entry in ratios if not entry["baseline_found"]),
            "best_p95_ratio": min(valid_ratio_values) if valid_ratio_values else None,
            "mean_p95_ratio": float(np.mean(valid_ratio_values)) if valid_ratio_values else None,
            **skipped_counts,
        },
        "per_operator": per_operator,
        "baseline_ratios": ratios,
        "recommendations": _summarize_recommendations(ratios),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    results = load_experiment_results(args.results_dir)
    report = generate_report_data(results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
