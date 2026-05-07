"""
Generate collective operator workloads for the calendar switch study.

Each workload is represented as phase-level demand matrices. Matrix entry
D[i][j] is the byte demand from GPU i to GPU j during that phase.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


OPERATOR_CONFIGS = {
    "allreduce_ring": {"algorithm": "ring", "phases_formula": "N-1"},
    "allgather": {"algorithm": "ring", "phases_formula": "N-1"},
    "reduce_scatter": {"algorithm": "ring", "phases_formula": "N-1"},
    "allreduce_tree": {"algorithm": "tree", "phases_formula": "2"},
}


def _validate_collective_inputs(operator: str, num_gpus: int, msg_bytes: int) -> None:
    if operator not in OPERATOR_CONFIGS:
        raise ValueError(f"Unknown operator: {operator}")
    if num_gpus <= 1:
        raise ValueError("num_gpus must be greater than 1")
    if msg_bytes <= 0:
        raise ValueError("msg_bytes must be positive")


def _zero_matrix(num_gpus: int) -> list[list[float]]:
    return [[0.0 for _ in range(num_gpus)] for _ in range(num_gpus)]


def _ring_phase_demand(
    num_gpus: int, chunk_bytes: float, phase_idx: int
) -> list[list[float]]:
    del phase_idx
    demand = _zero_matrix(num_gpus)
    for src in range(num_gpus):
        dst = (src + 1) % num_gpus
        demand[src][dst] = float(chunk_bytes)
    return demand


def _tree_reduce_demand(num_gpus: int, msg_bytes: int) -> list[list[float]]:
    demand = _zero_matrix(num_gpus)
    for child in range(1, num_gpus):
        parent = (child - 1) // 2
        demand[child][parent] = float(msg_bytes)
    return demand


def _tree_broadcast_demand(num_gpus: int, msg_bytes: int) -> list[list[float]]:
    reduce_demand = _tree_reduce_demand(num_gpus, msg_bytes)
    return [
        [reduce_demand[dst][src] for dst in range(num_gpus)]
        for src in range(num_gpus)
    ]


def generate_collective_workload(
    operator: str, num_gpus: int, msg_bytes: int
) -> dict:
    _validate_collective_inputs(operator, num_gpus, msg_bytes)
    config = OPERATOR_CONFIGS[operator]
    num_phases = num_gpus - 1 if config["phases_formula"] == "N-1" else 2

    phases = []
    if config["algorithm"] == "ring":
        chunk_bytes = msg_bytes / num_gpus
        for phase_idx in range(num_phases):
            phases.append(
                {
                    "index": phase_idx,
                    "demand_matrix": _ring_phase_demand(
                        num_gpus, chunk_bytes, phase_idx
                    ),
                }
            )
    else:
        phases = [
            {
                "index": 0,
                "name": "reduce",
                "demand_matrix": _tree_reduce_demand(num_gpus, msg_bytes),
            },
            {
                "index": 1,
                "name": "broadcast",
                "demand_matrix": _tree_broadcast_demand(num_gpus, msg_bytes),
            },
        ]

    return {
        "operator": operator,
        "num_gpus": num_gpus,
        "msg_bytes": msg_bytes,
        "num_phases": num_phases,
        "phases": phases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a collective calendar-study workload JSON file."
    )
    parser.add_argument("--operator", required=True, choices=sorted(OPERATOR_CONFIGS))
    parser.add_argument("--num-gpus", type=int, required=True)
    parser.add_argument("--msg-bytes", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    workload = generate_collective_workload(
        args.operator, args.num_gpus, args.msg_bytes
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(workload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
