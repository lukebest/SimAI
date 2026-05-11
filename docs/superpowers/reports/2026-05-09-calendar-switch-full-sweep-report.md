# Calendar Switch Full Sweep Report (GPU=8 BvN-Production, Quick, 400Gbps)

Date: 2026-05-11 (post-fix rerun)  
Spec (revised): `docs/superpowers/specs/2026-05-07-calendar-switch-perf-study-design.md`  
Raw run root: `results/calendar_study_gpu8_bvn_prod_quick_400g_fix_20260511`  
Raw aggregated JSON: `results/calendar_study_gpu8_bvn_prod_quick_400g_fix_20260511/report.json`

## 1) Scope and Setup

This run follows the production-readout policy under quick profile:
- GPU count fixed to `8`
- Packet topology: `topologies/Spectrum-X_8g_8port_packet_no_nvswitch_400g`
- Calendar topology: `topologies/Spectrum-X_8g_8port_calendar_no_nvswitch_400g`
- Deterministic operators run `bvn` + `round_robin` (RR is control-only)
- Dynamic operators run only `chunk/packet/slot + round_robin`
- Message sizes limited to `1MB` and `32MB` (`time-profile=quick`)

Scan matrix:
- baseline: `10 operators x 2 sizes = 20`
- calendar deterministic: `6 x 5 granularities x 2 algorithms x 2 sizes = 120`
- calendar dynamic: `4 x 3 granularities x 1 algorithm x 2 sizes = 24`
- total: `164`

## 2) Coverage and Completion

Run coverage:
- Total runs: `164`
- Baseline runs: `20`
- Calendar runs: `144`
- Matched calendar-vs-baseline ratios: `80`
- Skipped calendar runs due to empty E2E: `64`

Executive metrics:
- Best p95 ratio: `0.962122`
- Mean p95 ratio (matched runs): `1.228636`
- Missing baseline matches: `0`

Deterministic algorithm comparison (matched samples):
- `bvn`: `60` samples, mean ratio `1.000234`
- `round_robin` (control): `20` samples, mean ratio `1.913842`

## 3) Best Observed Configurations (Per Operator)

Best p95-ratio points per operator (matched runs):
- `allgather`: `chunk + bvn`, `32MB`, ratio `0.962122` (`660689 / 686700`)  
  (post-fix validation shows `operator + bvn` reaches the same ratio/E2E for `1MB` and `32MB`)
- `allreduce_ring`: `operator + bvn`, `1MB`, ratio `0.964499` (`48523 / 50309`)
- `allreduce_tree`: `operator + bvn`, `1MB`, ratio `0.964499` (`48523 / 50309`)
- `compute_overlap`: `operator + bvn`, `1MB`, ratio `0.983355`
- `reduce_scatter`: `operator + bvn`, `1MB`, ratio `0.968941`
- `rs_ag_fused`: `chunk + bvn`, `32MB`, ratio `0.993695`

No matched points in this run for:
- `alltoall_ep`
- `moe_dispatch`
- `moe_combine`
- `moe_pipeline`

Interpretation:
- Deterministic operators are consistently improved/near parity when read out with `bvn`.
- RR remains useful as control evidence, but its quality is clearly below `bvn`.
- Dynamic MoE-family is still coverage-limited in this configuration.

## 4) Empty-E2E Pattern (Calendar, GPU=8)

Calendar run completeness by operator (`matched / total`, skipped = empty E2E):
- `allgather`: `20/20` matched (skipped `0`)
- `allreduce_ring`: `10/20` matched (skipped `10`)
- `allreduce_tree`: `10/20` matched (skipped `10`)
- `alltoall_ep`: `0/6` matched (skipped `6`)
- `compute_overlap`: `15/20` matched (skipped `5`)
- `moe_dispatch`: `0/6` matched (skipped `6`)
- `moe_combine`: `0/6` matched (skipped `6`)
- `moe_pipeline`: `0/6` matched (skipped `6`)
- `reduce_scatter`: `10/20` matched (skipped `10`)
- `rs_ag_fused`: `15/20` matched (skipped `5`)

## 5) Recommendation Snapshot

Given this production-readout matrix:
- **Deterministic operators:** use `bvn` as production candidate; it is strongly better than RR-control in matched evidence.
- **RR policy:** keep as regression/control lane only, not as main conclusion source.
- **Dynamic operators:** continue as separate closure track; current run is insufficient for production recommendation there.

## 6) Next Actions

- Keep `gpu8_bvn_prod` as deterministic production evaluation matrix.
- For dynamic operators, prioritize empty-E2E reduction before comparing fine-grained scheduling quality.
- After dynamic closure, run targeted `256MB` only on shortlisted candidates for final sign-off.

