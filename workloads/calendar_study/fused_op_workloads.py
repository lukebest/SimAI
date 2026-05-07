"""
Generate fused operator workloads for the calendar switch study.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

try:
    from .generate_workloads import generate_collective_workload
    from .moe_traffic_generator import generate_moe_demand_matrix
except ImportError:
    from generate_workloads import generate_collective_workload
    from moe_traffic_generator import generate_moe_demand_matrix


def _sum_phase_demands(phases: list[dict]) -> list[list[float]]:
    matrices = [np.asarray(phase["demand_matrix"], dtype=float) for phase in phases]
    return np.sum(matrices, axis=0).tolist()


def generate_rs_ag_fused(num_gpus: int, msg_bytes: int) -> dict:
    reduce_scatter = generate_collective_workload(
        "reduce_scatter", num_gpus, msg_bytes
    )
    allgather = generate_collective_workload("allgather", num_gpus, msg_bytes)
    phases = [
        {
            "index": 0,
            "name": "reduce_scatter",
            "demand_matrix": _sum_phase_demands(reduce_scatter["phases"]),
        },
        {
            "index": 1,
            "name": "allgather",
            "demand_matrix": _sum_phase_demands(allgather["phases"]),
        },
    ]

    return {
        "operator": "rs_ag_fused",
        "num_gpus": num_gpus,
        "msg_bytes": msg_bytes,
        "num_phases": 2,
        "phases": phases,
    }


def generate_moe_pipeline(
    num_gpus: int,
    num_experts: int,
    tokens_per_gpu: int,
    token_size: int,
    distribution: str = "uniform",
    compute_ns: int = 100000,
) -> dict:
    dispatch_demand = generate_moe_demand_matrix(
        num_gpus,
        num_experts,
        tokens_per_gpu,
        token_size,
        distribution=distribution,
    )
    combine_demand = dispatch_demand.T.copy()
    phases = [
        {
            "index": 0,
            "name": "dispatch",
            "demand_matrix": dispatch_demand.tolist(),
        },
        {
            "index": 1,
            "name": "expert_compute",
            "demand_matrix": np.zeros((num_gpus, num_gpus), dtype=float).tolist(),
            "compute_ns": compute_ns,
        },
        {
            "index": 2,
            "name": "combine",
            "demand_matrix": combine_demand.tolist(),
        },
    ]

    return {
        "operator": "moe_pipeline",
        "num_gpus": num_gpus,
        "msg_bytes": int(dispatch_demand.sum()),
        "num_phases": 3,
        "phases": phases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate fused calendar-study workload JSON files."
    )
    parser.add_argument("--type", choices=["rs_ag", "moe_pipeline"], required=True)
    parser.add_argument("--num-gpus", type=int, default=8)
    parser.add_argument("--msg-bytes", type=int, default=33554432)
    parser.add_argument("--num-experts", type=int, default=64)
    parser.add_argument("--tokens-per-gpu", type=int, default=512)
    parser.add_argument("--token-size", type=int, default=4096)
    parser.add_argument("--distribution", default="uniform")
    parser.add_argument("--compute-ns", type=int, default=100000)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.type == "rs_ag":
        workload = generate_rs_ag_fused(args.num_gpus, args.msg_bytes)
    else:
        workload = generate_moe_pipeline(
            args.num_gpus,
            args.num_experts,
            args.tokens_per_gpu,
            args.token_size,
            args.distribution,
            args.compute_ns,
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(workload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
