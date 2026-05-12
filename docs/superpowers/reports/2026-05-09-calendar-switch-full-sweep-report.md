# Calendar Switch Full Sweep Report (GPU=8 BvN-Production, Quick, 400Gbps, Dynamic-Fix)

Date: 2026-05-12 (spec rerun)  
Spec (revised): `docs/superpowers/specs/2026-05-07-calendar-switch-perf-study-design.md`  
Raw run root: `results/calendar_study_gpu8_bvn_prod_quick_400g_dynamicfix_20260512`  
Raw aggregated JSON: `results/calendar_study_gpu8_bvn_prod_quick_400g_dynamicfix_20260512/report.json`

## 1) Scope and Setup

This run follows the production-readout policy under quick profile:
- GPU count fixed to `8`
- Packet topology: `topologies/Spectrum-X_8g_8port_packet_no_nvswitch_400g`
- Calendar topology: `topologies/Spectrum-X_8g_8port_calendar_no_nvswitch_400g`
- Deterministic operators run `bvn` + `round_robin` (RR is control-only)
- Dynamic operators run only `chunk/packet/slot + round_robin`
- Dynamic operators force static replay (`--calendar-recompute-policy static_operator`, no dynamic recompute)
- Dynamic operator message size is reduced to `128KB` (`131072`) for timeout-closure lane
- Message sizes limited to `1MB` and `32MB` (`time-profile=quick`)

Scan matrix (rerun + dynamic baseline closure):
- baseline: `20 + dynamic-128KB(4) = 24`
- calendar deterministic: `6 x 5 granularities x 2 algorithms x 2 sizes = 120`
- calendar dynamic: `4 x 3 granularities x 1 algorithm x 1 size(128KB) = 12`
- total: `156`

## 2) Coverage and Completion

Run coverage:
- Total runs: `156`
- Baseline runs: `24`
- Calendar runs: `132`
- Matched calendar-vs-baseline ratios: `92`
- Skipped calendar runs due to empty E2E: `40`

Executive metrics:
- Best p95 ratio: `0.962122`
- Mean p95 ratio (matched runs): `1.375195`
- Missing baseline matches: `0`

Deterministic algorithm comparison (matched samples):
- `bvn`: `60` samples, mean ratio `1.000234`
- `round_robin` (control): `20` samples, mean ratio `1.918810`

## 3) Best Observed Configurations (Per Operator)

Best p95-ratio points per operator (matched runs):
- `allgather`: `chunk + bvn`, `32MB`, ratio `0.962122` (`660689 / 686700`)  
  (post-fix validation shows `operator + bvn` reaches the same ratio/E2E for `1MB` and `32MB`)
- `allreduce_ring`: `operator + bvn`, `1MB`, ratio `0.964499` (`48523 / 50309`)
- `allreduce_tree`: `operator + bvn`, `1MB`, ratio `0.964499` (`48523 / 50309`)
- `compute_overlap`: `operator + bvn`, `1MB`, ratio `0.983355`
- `reduce_scatter`: `operator + bvn`, `1MB`, ratio `0.968941`
- `rs_ag_fused`: `chunk + bvn`, `32MB`, ratio `0.993695`
- `alltoall_ep`: `chunk + round_robin`, `128KB`, ratio `2.551855` (`55314 / 21676`)
- `moe_dispatch`: `packet + round_robin`, `128KB`, ratio `2.557297` (`55322 / 21633`)
- `moe_combine`: `chunk + round_robin`, `128KB`, ratio `2.563485` (`55320 / 21580`)
- `moe_pipeline`: `packet + round_robin`, `128KB`, ratio `1.702739` (`17780 / 10442`)

Interpretation:
- Deterministic operators are consistently improved/near parity when read out with `bvn`.
- RR remains useful as control evidence, but its quality is clearly below `bvn`.
- Dynamic operators now complete and ratio is closed at `128KB`, but all observed ratios are above baseline (current dynamic lane remains slower than packet-switch).

## 4) Empty-E2E Pattern (Calendar, GPU=8)

Calendar run completeness by operator (`matched / total`, skipped = empty E2E):
- `allgather`: `20/20` matched (skipped `0`)
- `allreduce_ring`: `10/20` matched (skipped `10`)
- `allreduce_tree`: `10/20` matched (skipped `10`)
- `alltoall_ep`: `3/3` matched (skipped `0`)
- `compute_overlap`: `15/20` matched (skipped `5`)
- `moe_dispatch`: `3/3` matched (skipped `0`)
- `moe_combine`: `3/3` matched (skipped `0`)
- `moe_pipeline`: `3/3` matched (skipped `0`)
- `reduce_scatter`: `10/20` matched (skipped `10`)
- `rs_ag_fused`: `15/20` matched (skipped `5`)

## 5) Recommendation Snapshot

Given this production-readout matrix:
- **Deterministic operators:** use `bvn` as production candidate; it is strongly better than RR-control in matched evidence.
- **RR policy:** keep as regression/control lane only, not as main conclusion source.
- **Dynamic operators:** empty-E2E issue and baseline matching are both closed under static-RR `128KB` lane, but performance is still behind baseline (needs dedicated optimization).

## 6) Next Actions

- Keep `gpu8_bvn_prod` as deterministic production evaluation matrix.
- Keep dynamic closure lane at `RR + static_operator + 128KB` to maintain completion.
- Start dynamic improvement loop from this stable lane (optimize slot/frame/replay policy against `128KB` baseline).
- After dynamic ratio improves, run targeted larger-size revalidation on shortlisted candidates.

