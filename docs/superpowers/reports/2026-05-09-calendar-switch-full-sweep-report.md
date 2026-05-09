# Calendar Switch Full Sweep Report (GPU=8, Forced No-NVSwitch)

Date: 2026-05-09  
Spec: `docs/superpowers/specs/2026-05-07-calendar-switch-perf-study-design.md`  
Raw run root: `results/calendar_study_gpu8_no_nvswitch_20260509_rerun2`  
Raw aggregated JSON: `results/calendar_study_gpu8_no_nvswitch_20260509_rerun2/report.json`

## 1) Scope and Setup

This rerun is the user-requested forced-topology sweep:
- GPU count fixed to `8`
- Packet mode topology fixed to `topologies/Spectrum-X_8g_8port_packet_no_nvswitch`
- Calendar mode topology fixed to `topologies/Spectrum-X_8g_8port_calendar_no_nvswitch`
- `NVLS` disabled (`--nvls-enable 0`)
- Full matrix preserved for GPU=8:
  - 10 operators
  - 5 granularities
  - 3 algorithms
  - 3 message sizes
  - plus packet baselines

## 2) Coverage and Completion

Run coverage:
- Total runs: `480`
- Baseline runs: `30` (`success=30`, `timeout=0`)
- Calendar runs: `450` (`success=190`, `timeout=260`)
- Matched calendar-vs-baseline ratios: `193`

Executive metrics from aggregated report:
- Best p95 ratio: `0.971615`
- Mean p95 ratio (matched runs): `1.087536`
- Missing baseline matches: `0`
- Skipped calendar runs due to empty E2E: `257`

## 3) Best Observed Configurations (Per Operator)

Best p95-ratio points per operator (on matched runs):
- `allgather`: `phase + bvn`, `1MB`, ratio `0.971615` (`139896 / 143983`)
- `allreduce_ring`: `operator + bvn`, `32MB`, ratio `1.000041`
- `allreduce_tree`: `operator + bvn`, `32MB`, ratio `1.000041`
- `alltoall_ep`: `chunk + round_robin`, `1MB`, ratio `1.097817`
- `compute_overlap`: `operator + bvn`, `32MB`, ratio `1.000000`
- `moe_combine`: `phase + round_robin`, `1MB`, ratio `1.099878`
- `moe_dispatch`: `operator + round_robin`, `1MB`, ratio `1.091456`
- `moe_pipeline`: `packet + round_robin`, `32MB`, ratio `1.005239`
- `reduce_scatter`: `operator + bvn`, `256MB`, ratio `1.000000`
- `rs_ag_fused`: `operator + bvn`, `256MB`, ratio `1.000000`

Interpretation:
- Deterministic collectives are mostly near parity with packet baseline under this forced single-switch setup.
- `allgather` shows the clearest measured calendar benefit.
- MoE-family operators remain slower than packet in available matched samples.

## 4) Timeout Pattern (Calendar, GPU=8)

Timeout rates by operator:
- `alltoall_ep`: `43/45` timeout (`95.6%`)
- `moe_dispatch`: `43/45` timeout (`95.6%`)
- `moe_combine`: `41/45` timeout (`91.1%`)
- `moe_pipeline`: `40/45` timeout (`88.9%`)
- `allreduce_ring`: `24/45` timeout (`53.3%`)
- `allreduce_tree`: `24/45` timeout (`53.3%`)
- `compute_overlap`: `21/45` timeout (`46.7%`)
- `reduce_scatter`: `12/45` timeout (`26.7%`)
- `rs_ag_fused`: `12/45` timeout (`26.7%`)
- `allgather`: `0/45` timeout

This is the dominant limitation for “full-plan closure”: matrix launched fully, but completion is partial in contention-heavy regimes.

## 5) Recommendation Snapshot (Current Evidence)

Given matched successful runs only:
- **Collectives:** prefer `bvn`; granularity tends to `operator/phase/chunk` depending on message size, with small margins.
- **MoE-family:** no evidence of calendar advantage yet in this forced no-NVSwitch setup; current implementations are timeout-prone.
- **Confidence:** medium for completed collective regions, low for MoE/high-contention regions due to heavy timeout bias.

## 6) Next Actions

To reach stronger spec-level conclusions on GPU=8 no-NVSwitch:
- prioritize closure of timeout-heavy strata (`alltoall_ep`, `moe_dispatch`, `moe_combine`, `moe_pipeline`)
- keep this fixed topology and compare only completed strata when selecting final per-operator granularity
- regenerate this report once timeout-heavy strata are materially reduced

