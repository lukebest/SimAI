# Calendar Switch Full Sweep Report (GPU=8 Mixed, Quick Profile)

Date: 2026-05-09  
Spec (revised): `docs/superpowers/specs/2026-05-07-calendar-switch-perf-study-design.md`  
Raw run root: `results/calendar_study_gpu8_mixed_quick_20260509`  
Raw aggregated JSON: `results/calendar_study_gpu8_mixed_quick_20260509/report.json`

## 1) Scope and Setup

This run follows the revised spec and the quick runtime profile:
- GPU count fixed to `8`
- Packet mode topology: `topologies/Spectrum-X_8g_8port_packet_no_nvswitch`
- Calendar mode topology: `topologies/Spectrum-X_8g_8port_calendar_no_nvswitch`
- Dynamic operators (`alltoall_ep`, `moe_dispatch`, `moe_combine`, `moe_pipeline`) run only `chunk/packet/slot`
- Dynamic operators use `round_robin` only (non-demand-aware path)
- Deterministic operators run `round_robin`, `bvn`, `solstice`
- Message sizes limited to `1MB` and `32MB` (`time-profile=quick`)

Scan matrix:
- baseline: `10 operators x 2 sizes = 20`
- calendar deterministic: `6 x 5 granularities x 3 algorithms x 2 sizes = 180`
- calendar dynamic: `4 x 3 granularities x 1 algorithm x 2 sizes = 24`
- total: `224`

## 2) Coverage and Completion

Run coverage:
- Total runs: `224`
- Baseline runs: `20`
- Calendar runs: `204`
- Matched calendar-vs-baseline ratios: `150`
- Skipped calendar runs due to empty E2E: `54`

Executive metrics:
- Best p95 ratio: `0.971615`
- Mean p95 ratio (matched runs): `1.106545`
- Missing baseline matches: `0`

## 3) Best Observed Configurations (Per Operator)

Best p95-ratio points per operator (matched runs):
- `allgather`: `phase + bvn`, `1MB`, ratio `0.971615` (`139896 / 143983`)
- `allreduce_ring`: `operator + bvn`, `32MB`, ratio `1.000041`
- `allreduce_tree`: `operator + bvn`, `32MB`, ratio `1.000041`
- `alltoall_ep`: `chunk + round_robin`, `1MB`, ratio `1.093955`
- `compute_overlap`: `operator + bvn`, `32MB`, ratio `1.000000`
- `moe_combine`: `chunk + round_robin`, `1MB`, ratio `1.099787`
- `moe_dispatch`: `packet + round_robin`, `1MB`, ratio `1.087792`
- `moe_pipeline`: `packet + round_robin`, `1MB`, ratio `1.071714`
- `reduce_scatter`: `operator + bvn`, `32MB`, ratio `1.000007`
- `rs_ag_fused`: `operator + bvn`, `32MB`, ratio `1.000000`

Interpretation:
- `allgather` remains the only clearly better-than-baseline operator in this profile.
- Several deterministic operators are close to baseline at `32MB` (ratio near `1.0`).
- Dynamic MoE-family now has matched points, but all currently above baseline (`>1.0`).

## 4) Empty-E2E Pattern (Calendar, GPU=8)

Calendar run completeness by operator (`matched / total`, skipped = empty E2E):
- `allgather`: `30/30` matched (skipped `0`)
- `allreduce_ring`: `22/30` matched (skipped `8`)
- `allreduce_tree`: `21/30` matched (skipped `9`)
- `alltoall_ep`: `2/6` matched (skipped `4`)
- `compute_overlap`: `24/30` matched (skipped `6`)
- `moe_combine`: `1/6` matched (skipped `5`)
- `moe_dispatch`: `2/6` matched (skipped `4`)
- `moe_pipeline`: `2/6` matched (skipped `4`)
- `reduce_scatter`: `22/30` matched (skipped `8`)
- `rs_ag_fused`: `24/30` matched (skipped `6`)

## 5) Recommendation Snapshot

Given quick-profile evidence:
- **Deterministic operators:** BvN points are generally strongest and near parity at `32MB`.
- **Dynamic operators:** still lag baseline and have lower completion quality (higher empty-E2E share).
- **Confidence:** medium for `1MB/32MB` behavior; no claim made for `256MB` because it was intentionally excluded in this run.

## 6) Next Actions

To close remaining gaps under current spec:
- prioritize empty-E2E reduction for dynamic operators (`moe_combine`, `moe_dispatch`, `moe_pipeline`, `alltoall_ep`)
- keep quick profile as regression gate, then run targeted full-size (`256MB`) only on shortlisted configurations
- maintain non-fatal batch scheduling behavior to avoid sweep interruption from single-job failure

