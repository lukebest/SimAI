#!/usr/bin/env python3
"""Aggregate system TPS and per-stream TPS from TPS matrix manifest."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate TPS metrics.")
    parser.add_argument(
        "--manifest",
        default="/home/luke/SimAI/results/tps_matrix/runs_manifest.csv",
        help="Path to run manifest CSV.",
    )
    parser.add_argument(
        "--summary-out",
        default="/home/luke/SimAI/results/tps_matrix/tps_summary.csv",
        help="Output summary CSV path.",
    )
    parser.add_argument(
        "--effects-out",
        default="/home/luke/SimAI/results/tps_matrix/tps_effects.csv",
        help="Output effects CSV path.",
    )
    return parser.parse_args()


def safe_div(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return float("nan")
    return numerator / denominator


def summarize_run(row: pd.Series) -> Dict[str, float]:
    metrics_file = Path(row["request_metrics_csv"])
    if not metrics_file.exists():
        raise FileNotFoundError(f"request_metrics.csv not found: {metrics_file}")

    df = pd.read_csv(metrics_file)
    for needed in [
        "arrived_at",
        "completed_at",
        "decode_time",
        "request_num_decode_tokens",
    ]:
        if needed not in df.columns:
            raise KeyError(f"Missing column {needed} in {metrics_file}")

    decode_tokens_sum = float(df["request_num_decode_tokens"].sum())
    window_start = float(df["arrived_at"].min())
    window_end = float(df["completed_at"].max())
    window_duration = window_end - window_start

    # Requested metric definitions:
    # - System TPS: sum(decode_tokens) / (max(completed_at) - min(arrived_at))
    # - Per-stream TPS (request-level): decode_tokens / decode_time
    per_request_tps = np.where(
        df["decode_time"] > 0,
        df["request_num_decode_tokens"] / df["decode_time"],
        np.nan,
    )
    per_request_tps = pd.Series(per_request_tps).replace([np.inf, -np.inf], np.nan).dropna()

    return {
        "decode_tokens_sum": decode_tokens_sum,
        "window_start": window_start,
        "window_end": window_end,
        "window_duration": window_duration,
        "system_tps": safe_div(decode_tokens_sum, window_duration),
        "single_stream_tps_mean": float(per_request_tps.mean()) if len(per_request_tps) else float("nan"),
        "single_stream_tps_p50": float(per_request_tps.quantile(0.50)) if len(per_request_tps) else float("nan"),
        "single_stream_tps_p95": float(per_request_tps.quantile(0.95)) if len(per_request_tps) else float("nan"),
        "single_stream_tps_p99": float(per_request_tps.quantile(0.99)) if len(per_request_tps) else float("nan"),
        "request_count": int(len(df)),
    }


def build_effect_rows(summary: pd.DataFrame) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    metrics = ["system_tps", "single_stream_tps_mean"]

    for backend, bdf in summary.groupby("backend"):
        # Main effect: network determinism
        by_net = bdf.groupby(["network_level_id", "network_label"], as_index=False)[metrics].mean()
        for _, rec in by_net.iterrows():
            for metric in metrics:
                rows.append(
                    {
                        "backend": backend,
                        "effect_type": "main_effect",
                        "factor": "network_determinism",
                        "level_a": rec["network_level_id"],
                        "level_b": "",
                        "metric": metric,
                        "value": rec[metric],
                    }
                )

        # Main effect: memory bandwidth
        by_mem = bdf.groupby(["memory_level_id", "memory_label"], as_index=False)[metrics].mean()
        for _, rec in by_mem.iterrows():
            for metric in metrics:
                rows.append(
                    {
                        "backend": backend,
                        "effect_type": "main_effect",
                        "factor": "memory_bandwidth",
                        "level_a": rec["memory_level_id"],
                        "level_b": "",
                        "metric": metric,
                        "value": rec[metric],
                    }
                )

        # Interaction surface (network x memory)
        inter = bdf.groupby(["network_level_id", "memory_level_id"], as_index=False)[metrics].mean()
        for _, rec in inter.iterrows():
            for metric in metrics:
                rows.append(
                    {
                        "backend": backend,
                        "effect_type": "interaction",
                        "factor": "network_x_memory",
                        "level_a": rec["network_level_id"],
                        "level_b": rec["memory_level_id"],
                        "metric": metric,
                        "value": rec[metric],
                    }
                )

    return rows


def main() -> int:
    args = parse_args()
    manifest = pd.read_csv(args.manifest)
    runs = manifest[manifest["status"] == "success"].copy()
    if runs.empty:
        raise RuntimeError("No successful runs found in manifest.")

    records: List[Dict[str, object]] = []
    for _, row in runs.iterrows():
        try:
            metrics = summarize_run(row)
        except Exception as exc:
            print(f"Skip run_id={row['run_id']} due to error: {exc}")
            continue

        payload = row.to_dict()
        payload.update(metrics)
        records.append(payload)

    summary = pd.DataFrame(records)
    summary_path = Path(args.summary_out)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_path, index=False)

    effects_rows = build_effect_rows(summary)
    effects = pd.DataFrame(effects_rows)
    effects_path = Path(args.effects_out)
    effects_path.parent.mkdir(parents=True, exist_ok=True)
    effects.to_csv(effects_path, index=False)

    print(f"Summary written: {summary_path}")
    print(f"Effects written: {effects_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
