# Calendar-Based Switch Simulation Report

**Date:** 2026-05-07  
**Project:** SimAI  
**Input data:** `results/example-EndToEnd.csv`, `results/test-EndToEnd.csv`  
**Report type:** Initial EndToEnd CSV analysis against the calendar-switch study plan

## Executive Summary

The available simulation outputs are SimAI EndToEnd CSV summaries, not the full calendar-switch sweep output described in the plan. They do not yet contain `calendar_switch` versus `packet_switch` mode labels, granularity labels (`operator`, `phase`, `chunk`, `packet`, `slot`), scheduling algorithm labels (`solstice`, `bvn`, `round_robin`), slot utilization, or per-run `e2e_times.json`.

Within the available CSVs, the `test-` run improves total time versus `example-` by **139,401 raw time units**, a **1.85% reduction**:

- `example-` total time: `7,545,619`
- `test-` total time: `7,406,218`
- total exposed communication drops from `2,656,839` to `2,528,453`, a **4.83% reduction**
- total compute is unchanged at `4,542,795`
- bubble time drops by **3.18%**

The main communication shift is not uniform:

- `Expose_EP_comm` improves strongly: **-296,150** (**-24.22%**)
- `Expose DP comm` improves: **-19,742** (**-48.95%**)
- `Expose DP_EP comm` regresses: **+82,990** (**+7.78%**)
- `Expose TP comm` regresses: **+104,515** (**+31.99%**)

This suggests the `test-` configuration reduces exposed MoE/EP communication enough to offset worse TP and DP_EP exposure.

## Available Data and Scope

The two files have the same structure:

- first two rows: whole-run summary
- remaining rows: per-layer/operator timing and communication breakdown
- layer rows: `1789` in both files

The CSVs appear to represent analytical EndToEnd outputs rather than the full ns-3 calendar-switch study matrix. Therefore, this report can assess operator hotspots and explain what the calendar-switch study should prioritize, but it cannot yet rank calendar request granularities or scheduling algorithms from measured calendar-switch runs.

## Whole-Run Comparison

`test-` is faster mainly because exposed communication shrinks while compute stays fixed.

- Total time: `7,545,619` -> `7,406,218`
- Delta: `-139,401`
- Relative change: `-1.85%`

Breakdown by high-level exposed communication class:

- DP: `40,332` -> `20,590`, delta `-19,742`
- DP_EP: `1,067,010` -> `1,150,000`, delta `+82,990`
- TP: `326,686` -> `431,201`, delta `+104,515`
- EP: `1,222,811` -> `926,661`, delta `-296,150`
- PP: unchanged at `0`

The net exposed communication reduction is:

- `2,656,839` -> `2,528,453`
- Delta: `-128,386`
- Relative change: `-4.83%`

## Operator Hotspots

The largest exposed communication contributors are MoE-related.

In `example-`:

- `moe_grad_norm2`: `711,340`
- `moe_grad_norm1`: `355,670`
- `grad_param_comm`: `26,888`
- `grad_gather`: `13,444`
- repeated `mlp_moelayer` rows: `3,184` per row

In `test-`:

- `moe_grad_norm2`: `766,667`
- `moe_grad_norm1`: `383,333`
- `grad_param_comm`: `13,727`
- `grad_gather`: `6,863`
- repeated `mlp_moelayer` rows: `2,414` per row

Aggregated by layer name, the largest deltas are:

- `mlp_moelayer`: `1,492,992` -> `1,286,784`, delta `-206,208`
- `moe_grad_norm2`: `711,340` -> `766,667`, delta `+55,327`
- `moe_grad_norm1`: `355,670` -> `383,333`, delta `+27,663`
- `grad_param_comm`: `26,888` -> `13,727`, delta `-13,161`
- `attention_row`: `33,792` -> `43,392`, delta `+9,600`
- `grad_gather`: `13,444` -> `6,863`, delta `-6,581`
- `attention_column`: `16,896` -> `21,696`, delta `+4,800`

The dominant improvement comes from repeated MoE MLP-layer communication. The dominant regressions are MoE gradient norm and TP attention communication.

## Calendar-Switch Implications

The plan asks which calendar request granularity minimizes end-to-end completion time for collective, fused, and MoE operators. The available CSVs do not directly answer that yet, but they identify where calendar scheduling should focus first.

### MoE Dispatch/Combine and EP Traffic

MoE/EP traffic is the largest exposed-communication component in both runs. It is also dynamic because token-to-expert routing can be skewed and data-dependent.

Recommended first calendar granularity candidates:

- `phase/stage`: natural boundary after MoE gating, once the actual expert demand matrix is known
- `chunk/tile`: useful when expert load skew is high and a single phase schedule would over-allocate to stale demand
- `slot`: useful as a stress point, but should be treated as high-control-overhead unless zero-overhead oracle assumptions are retained

The available data supports prioritizing MoE `dispatch`, `combine`, `alltoall_ep`, and fused `moe_pipeline` experiments before broadening the sweep.

### Deterministic Collectives

TP-related communication regresses in `test-`, especially `attention_row` and `attention_column`. These are more predictable than MoE traffic and are better suited to coarser calendar requests.

Recommended first granularity candidates:

- `operator` for simple deterministic collective experiments
- `phase/stage` for ring/tree collectives where each phase has a different active port pairing
- `chunk/tile` for large messages where pipeline fill/drain effects matter

For allreduce/allgather/reduce_scatter, the plan's comparison of `operator -> phase -> chunk -> packet -> slot` remains valid, but the current CSVs only show aggregate exposed communication, not measured calendar completion time.

### Fused Operators

The available EndToEnd format does not mark fused operator boundaries explicitly. Based on the plan, fused operators should be analyzed as high-level phases:

- `RS_AG_FUSED`: reduce_scatter phase plus allgather phase
- `COMPUTE_OVERLAP`: communication phases interleaved with compute
- `MOE_PIPELINE`: dispatch, expert compute, combine

The current data suggests fused MoE should be prioritized, because MoE-layer communication is the largest repeated exposed component.

## What Cannot Be Claimed Yet

The plan's final report requires results that are not present in these CSVs:

- calendar versus packet-switch baseline ratio
- per-operator heatmaps over granularity and algorithm
- Solstice versus BvN versus RoundRobin measured comparison
- p50/p95/p99 E2E distributions from `e2e_times.json`
- slot utilization
- slot waiting time
- queue occupancy
- PFC/CNP event counts
- message-size sensitivity across the planned matrix
- MoE skew sensitivity across uniform, Zipf, and power-law expert distributions

Because those fields are absent, this report should not be interpreted as proof that one calendar granularity or scheduling algorithm is best. It is an initial EndToEnd hotspot report to guide the next full sweep.

## Recommended Next Simulation Sweep

To produce the full plan-compliant report, run the calendar study runner on a reduced but meaningful matrix first:

1. Operators:
   - `allreduce_ring`
   - `allgather`
   - `reduce_scatter`
   - `alltoall_ep`
   - `moe_dispatch`
   - `moe_combine`
   - `rs_ag_fused`
   - `moe_pipeline`

2. GPU scale:
   - start with `8`
   - add `16` after the first matrix is validated

3. Granularity:
   - `operator`
   - `phase`
   - `chunk`
   - `packet`
   - `slot`

4. Algorithms:
   - `solstice`
   - `bvn`
   - `round_robin`

5. Required outputs per run:
   - `metadata.json`
   - `workload.json`
   - `SimAI.conf`
   - `stdout.log`
   - `e2e_times.json`
   - calendar trace with slot admission/wait metrics when available

After this sweep, `scripts/analyze_results.py` can produce the p95 baseline ratios and recommendations required by the plan.

## Current Conclusion

Based on the currently available `example-` versus `test-` EndToEnd CSVs:

- `test-` is the better configuration by total time, improving by **1.85%**
- the gain comes from lower exposed communication, especially EP/MoE-layer communication
- MoE and fused MoE operators should be the first calendar-switch targets
- deterministic collectives still need explicit calendar granularity sweeps before selecting `operator`, `phase`, or `chunk`
- no measured Solstice/BvN/RoundRobin ranking can be claimed until the full calendar-switch sweep produces per-run E2E outputs
