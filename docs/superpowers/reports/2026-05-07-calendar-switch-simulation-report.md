# Calendar-Based Switch Simulation Report

**Date:** 2026-05-07
**Project:** SimAI
**Sweep data:** `results/calendar_study_full_20260507_timeout`
**Machine-readable analysis:** `results/calendar_study_full_20260507_timeout/analysis_report.json`
**Report type:** Full plan-compliant sweep with bounded per-run timeout

## Executive Summary

The full experiment matrix from the spec was executed: **960 runs** = 60 packet-switch baselines plus 900 calendar-switch configurations across 10 operators, 5 granularities, 3 algorithms, 2 GPU counts, and 3 message sizes.

Of those runs, **680 completed**, **280 timed out** under the 180-second per-run guard, and **604 calendar runs** had both valid E2E samples and matching packet-switch baselines. The timeout guard was necessary because several 16-GPU calendar allreduce-style configurations stopped making progress in ns-3 calendar gating.

Best observed valid calendar result: **compute_overlap**, `slot` granularity, `bvn`, 16 GPUs, 33,554,432 bytes, with p95 ratio **0.978** versus baseline. Only **5 / 604** valid calendar comparisons beat packet switching, so the overall result is that calendar switching is not broadly beneficial under the current zero-reconfiguration, single-switch ns-3 implementation.

The strongest pattern is that `slot` granularity is the only granularity class with meaningful wins, while `operator`, `phase`, `chunk`, and `packet` are effectively tied in this current implementation. This indicates the current GranularityController wiring exposes calendar mode mainly through switch gating behavior rather than materially different per-boundary demand recomputation for the SimAI text workload path.

## Sweep Coverage

| Metric | Value |
|---|---:|
| Planned runs | 960 |
| Packet-switch baseline runs | 60 |
| Calendar-switch runs | 900 |
| Successful process exits | 680 |
| Timeout exits | 280 |
| Valid matched calendar comparisons | 604 |
| Empty calendar E2E samples | 296 |
| Missing baselines | 0 |
| Best p95 ratio | 0.978 |
| Mean p95 ratio over valid comparisons | 2.047 |

Timeouts were concentrated at 16 GPUs:

| GPU count | Success | Timeout |
|---:|---:|---:|
| 8 | 480 | 0 |
| 16 | 200 | 280 |

## Best Configuration By Operator

| Operator | Valid comparisons | Calendar wins | Best granularity | Best algorithm | GPU | Message bytes | Best p95 ratio | Mean ratio | Timeouts |
|---|---:|---:|---|---|---:|---:|---:|---:|---:|
| `allgather` | 62 | 1 | `slot` | `round_robin` | 16 | 1048576 | 0.995 | 2.333 | 28 |
| `allreduce_ring` | 62 | 0 | `chunk` | `bvn` | 8 | 1048576 | 1.000 | 2.356 | 28 |
| `allreduce_tree` | 62 | 0 | `chunk` | `bvn` | 8 | 1048576 | 1.000 | 2.356 | 28 |
| `alltoall_ep` | 58 | 0 | `chunk` | `bvn` | 8 | 1048576 | 1.000 | 1.489 | 28 |
| `compute_overlap` | 58 | 3 | `slot` | `bvn` | 16 | 33554432 | 0.978 | 1.907 | 32 |
| `moe_combine` | 58 | 0 | `chunk` | `bvn` | 8 | 1048576 | 1.000 | 1.489 | 28 |
| `moe_dispatch` | 58 | 0 | `chunk` | `bvn` | 8 | 1048576 | 1.000 | 1.489 | 28 |
| `moe_pipeline` | 62 | 0 | `chunk` | `bvn` | 8 | 1048576 | 1.000 | 2.159 | 28 |
| `reduce_scatter` | 62 | 0 | `chunk` | `bvn` | 8 | 1048576 | 1.000 | 2.329 | 28 |
| `rs_ag_fused` | 62 | 1 | `slot` | `solstice` | 16 | 1048576 | 1.000 | 2.443 | 24 |

## Granularity And Algorithm Summary

| Granularity | Valid comparisons | Wins vs baseline | Mean ratio | Best ratio |
|---|---:|---:|---:|---:|
| `operator` | 106 | 0 | 2.491 | 1.000 |
| `phase` | 106 | 0 | 2.491 | 1.000 |
| `chunk` | 106 | 0 | 2.491 | 1.000 |
| `packet` | 106 | 0 | 2.491 | 1.000 |
| `slot` | 180 | 5 | 1.000 | 0.978 |

| Algorithm | Valid comparisons | Wins vs baseline | Mean ratio | Best ratio |
|---|---:|---:|---:|---:|
| `solstice` | 180 | 2 | 1.000 | 0.978 |
| `bvn` | 180 | 1 | 1.000 | 0.978 |
| `round_robin` | 244 | 2 | 3.591 | 0.978 |

## Interpretation

- **Collectives:** `allreduce_ring`, `allreduce_tree`, and `reduce_scatter` do not show valid calendar wins in this sweep. Several 16-GPU calendar runs timed out, indicating the current calendar gating path can block progress for larger ring-style collective traffic.
- **MoE and EP traffic:** `alltoall_ep`, `moe_dispatch`, and `moe_combine` complete at 8 GPUs and have stable baselines, but their best valid ratios are approximately 1.0. The current SimAI workload path uses generated `ALLTOALL_EP` microbenchmarks plus JSON demand artifacts; it does not yet replay real expert-gating traces into ns-3 packet injection.
- **Fused operators:** `compute_overlap` produced the best observed ratio, 0.978, at slot granularity. `rs_ag_fused` had one near-tie win at 0.9999. These are narrow wins, not enough to claim broad calendar advantage.
- **Granularity:** `slot` is the only granularity class with wins. Other granularities produce identical aggregate behavior in many cases because the current text workload injection exposes one or two communication layers rather than native per-phase/chunk packet-boundary callbacks.
- **Algorithms:** Solstice and BvN have similar mean ratios near 1.0 over valid comparisons. Round-robin has a much worse mean ratio because it includes more completed slow configurations instead of timing out in the same pattern.

## Plan Compliance Notes

Covered by this sweep:

- 10 operator labels from the spec, including `compute_overlap`.
- 5 request granularities: `operator`, `phase`, `chunk`, `packet`, `slot`.
- 3 calendar algorithms: `solstice`, `bvn`, `round_robin`.
- 8-GPU and 16-GPU scales. 16-GPU results include substantial timeout evidence.
- 3 message sizes: 1 MiB, 32 MiB, 256 MiB.
- Packet-switch baselines for every `(operator, GPU count, message size)`.

Remaining limitations:

- E2E is extracted from SimAI stdout `all passes finished at time`, so units are SimAI raw time/cycles rather than independently instrumented packet-level operator microseconds.
- Slot utilization, queue occupancy, PFC/CNP counts, and slot waiting distributions are not yet parsed into the report. The generated run directories retain `stdout.log`, `fct.txt`, `trace.tr`, and `calendar_trace.csv` paths where available for follow-up instrumentation.
- MoE runs use synthetic demand matrices and `ALLTOALL_EP` SimAI microbenchmarks. They are reproducible but not a real DeepSeek-V3 token trace replay.
- Timeout entries are part of the full sweep result. They should be treated as failures/non-convergence for the current calendar switch implementation, not as latency wins or losses.

## Reproduction

The sweep was run with:

```bash
SIM_TIMEOUT_SECONDS=180 scripts/run_calendar_study.sh --parallel 8 --results-dir results/calendar_study_full_20260507_timeout
python3 scripts/analyze_results.py --results-dir results/calendar_study_full_20260507_timeout --output results/calendar_study_full_20260507_timeout/analysis_report.json
```

Important runtime fixes made before the sweep:

- `run_single_experiment.sh` now invokes `SimAI_simulator` with the actual `-t/-w/-n/-c` CLI and writes local trace/FCT/PFC output paths.
- `run_single_experiment.sh` now generates SimAI text workloads in addition to JSON demand artifacts.
- `run_calendar_study.sh` now includes `compute_overlap` and supports bash-native parallel fallback when GNU `parallel` is unavailable.
- `RdmaHw::SendPacketComplete` now returns `0` on the success path, avoiding the previous illegal-instruction crash from falling off a non-void function.
