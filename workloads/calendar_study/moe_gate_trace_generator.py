"""
Generate controllable, time-varying MoE gate traces.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def _build_phase_load(
    num_gpus: int,
    phase: int,
    mode: str,
    hotspot_ratio: float,
    burst_interval: int,
    burst_width: int,
) -> np.ndarray:
    load = np.ones(num_gpus, dtype=float)
    if mode == "uniform":
        return load

    hotspot_gpu = (phase // max(1, burst_interval)) % num_gpus
    in_burst = (phase % max(1, burst_interval)) < max(1, burst_width)
    burst_amp = hotspot_ratio if in_burst else hotspot_ratio * 0.2
    load[hotspot_gpu] += burst_amp
    return load


def generate_gate_trace(
    num_gpus: int,
    num_phases: int,
    mode: str,
    hotspot_ratio: float,
    burst_interval: int,
    burst_width: int,
) -> dict:
    phase_scales = []
    per_phase_src_load = []
    hotspot_gpu_trace = []

    for phase in range(num_phases):
        src_load = _build_phase_load(
            num_gpus=num_gpus,
            phase=phase,
            mode=mode,
            hotspot_ratio=hotspot_ratio,
            burst_interval=burst_interval,
            burst_width=burst_width,
        )
        temporal_scale = 1.0 + 0.35 * np.sin((2.0 * np.pi * phase) / max(1, num_phases))
        src_load = src_load / np.mean(src_load)
        phase_scales.append(float(max(0.05, temporal_scale)))
        per_phase_src_load.append([float(x) for x in src_load.tolist()])
        hotspot_gpu_trace.append(int(np.argmax(src_load)))

    return {
        "mode": mode,
        "num_gpus": num_gpus,
        "num_phases": num_phases,
        "phase_scales": phase_scales,
        "phase_src_load": per_phase_src_load,
        "hotspot_gpu_trace": hotspot_gpu_trace,
        "description": "Controllable MoE gate trace with non-uniform and time-varying load.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate MoE gate trace JSON.")
    parser.add_argument("--num-gpus", type=int, required=True)
    parser.add_argument("--num-phases", type=int, required=True)
    parser.add_argument("--mode", choices=["uniform", "hotspot_burst"], default="hotspot_burst")
    parser.add_argument("--hotspot-ratio", type=float, default=4.0)
    parser.add_argument("--burst-interval", type=int, default=4)
    parser.add_argument("--burst-width", type=int, default=2)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.num_gpus <= 0:
        raise ValueError("num-gpus must be positive")
    if args.num_phases <= 0:
        raise ValueError("num-phases must be positive")
    if args.hotspot_ratio < 0.0:
        raise ValueError("hotspot-ratio must be non-negative")

    trace = generate_gate_trace(
        num_gpus=args.num_gpus,
        num_phases=args.num_phases,
        mode=args.mode,
        hotspot_ratio=args.hotspot_ratio,
        burst_interval=args.burst_interval,
        burst_width=args.burst_width,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(trace, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
