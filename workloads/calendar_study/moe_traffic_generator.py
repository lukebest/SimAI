"""
Generate MoE dispatch demand matrices for calendar switch studies.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def _validate_moe_inputs(
    num_gpus: int,
    num_experts: int,
    tokens_per_gpu: int,
    token_size: int,
    distribution: str,
) -> None:
    if num_gpus <= 0:
        raise ValueError("num_gpus must be positive")
    if num_experts <= 0:
        raise ValueError("num_experts must be positive")
    if tokens_per_gpu <= 0:
        raise ValueError("tokens_per_gpu must be positive")
    if token_size <= 0:
        raise ValueError("token_size must be positive")
    if num_experts < num_gpus:
        raise ValueError("num_experts must be greater than or equal to num_gpus")
    if distribution not in {"uniform", "zipf", "power_law"}:
        raise ValueError(f"Unknown distribution: {distribution}")


def _expert_to_gpu(expert_ids: np.ndarray, num_experts: int, num_gpus: int) -> np.ndarray:
    return np.minimum((expert_ids * num_gpus) // num_experts, num_gpus - 1)


def generate_moe_demand_matrix(
    num_gpus: int,
    num_experts: int,
    tokens_per_gpu: int,
    token_size: int,
    distribution: str = "uniform",
    zipf_s: float = 1.2,
    seed: int = 42,
) -> np.ndarray:
    _validate_moe_inputs(
        num_gpus, num_experts, tokens_per_gpu, token_size, distribution
    )

    rng = np.random.default_rng(seed)
    token_shape = (num_gpus, tokens_per_gpu)
    if distribution == "uniform":
        expert_ids = rng.integers(0, num_experts, size=token_shape)
    elif distribution == "zipf":
        raw = rng.zipf(zipf_s, size=token_shape)
        expert_ids = (raw - 1) % num_experts
    else:
        ranks = np.arange(1, num_experts + 1, dtype=float)
        probabilities = ranks ** (-zipf_s)
        probabilities /= probabilities.sum()
        expert_ids = rng.choice(num_experts, size=token_shape, p=probabilities)

    dst_gpus = _expert_to_gpu(expert_ids, num_experts, num_gpus)
    demand = np.zeros((num_gpus, num_gpus), dtype=float)
    for src_gpu in range(num_gpus):
        counts = np.bincount(dst_gpus[src_gpu], minlength=num_gpus)
        demand[src_gpu] = counts * token_size

    return demand


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a MoE calendar-study demand matrix JSON file."
    )
    parser.add_argument("--num-gpus", type=int, default=8)
    parser.add_argument("--num-experts", type=int, default=64)
    parser.add_argument("--tokens-per-gpu", type=int, default=512)
    parser.add_argument("--token-size", type=int, default=4096)
    parser.add_argument("--distribution", default="uniform")
    parser.add_argument("--zipf-s", type=float, default=1.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    demand = generate_moe_demand_matrix(
        args.num_gpus,
        args.num_experts,
        args.tokens_per_gpu,
        args.token_size,
        args.distribution,
        args.zipf_s,
        args.seed,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(demand.tolist(), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
