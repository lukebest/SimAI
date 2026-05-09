# Calendar Switch Full Sweep Report (Spec-Compliant Rerun)

Date: 2026-05-09  
Spec: `docs/superpowers/specs/2026-05-07-calendar-switch-perf-study-design.md`  
Raw aggregated JSON: `results/calendar_study_spec_full_20260508_rerun/report.json`  
Raw run root: `results/calendar_study_spec_full_20260508_rerun`

## 1) Executive Summary

This report summarizes a full rerun of the spec-defined matrix:
- 10 operators
- 5 granularities (`operator/phase/chunk/packet/slot`)
- 3 calendar algorithms (`solstice/bvn/round_robin`)
- 2 GPU scales (`8/16`)
- 3 message sizes (`1MB/32MB/256MB`)
- plus packet-switch baselines

Observed coverage:
- Total runs: `960` (`900` calendar + `60` baseline)
- Baseline successful: `60/60`
- Calendar successful: `478/900`
- Calendar timeout: `422/900` (empty E2E)
- Matched calendar-vs-baseline ratios available: `478`

Top-line result on matched runs:
- Best observed p95 ratio (`calendar_p95 / baseline_p95`): `0.98779` (calendar win)
- Mean p95 ratio across matched runs: `1.7953` (dominated by 16-GPU hard cases)
- 8-GPU matched mean ratio: `1.2573`
- 16-GPU matched mean ratio: `8.6047` (few successful points, high stress/instability)

## 2) Experiment Matrix and Controls

Implemented exactly per spec dimensions and controls:
- Operators: `allreduce_ring`, `allreduce_tree`, `allgather`, `reduce_scatter`, `alltoall_ep`, `moe_dispatch`, `moe_combine`, `rs_ag_fused`, `compute_overlap`, `moe_pipeline`
- Granularity/algorithm/GPU/message dimensions as above
- Single-switch no-NVSwitch topology was enforced for both calendar and packet modes
- Link and protocol controls inherited from SimAI config path used by the runner

Execution artifacts:
- Job orchestration: `scripts/run_calendar_study.sh`
- Per-run execution: `scripts/run_single_experiment.sh`
- Aggregation: `scripts/analyze_results.py`

## 3) Per-Operator Best Observed Configurations (Matched Runs)

Best p95-ratio points per operator (lower is better):
- `allgather`: `chunk + bvn`, `8 GPU`, `32MB`, ratio `0.98779`
- `allreduce_ring`: `chunk + solstice`, `8 GPU`, `256MB`, ratio `1.00038`
- `allreduce_tree`: `chunk + solstice`, `8 GPU`, `256MB`, ratio `1.00038`
- `alltoall_ep`: `chunk + bvn`, `8 GPU`, `1MB`, ratio `1.00000`
- `compute_overlap`: `chunk + bvn`, `8 GPU`, `256MB`, ratio `1.00038`
- `moe_combine`: `chunk + bvn`, `8 GPU`, `1MB`, ratio `1.00000`
- `moe_dispatch`: `chunk + bvn`, `8 GPU`, `1MB`, ratio `1.00000`
- `moe_pipeline`: `chunk + bvn`, `8 GPU`, `1MB`, ratio `1.00000`
- `reduce_scatter`: `operator + bvn`, `8 GPU`, `256MB`, ratio `1.00010`
- `rs_ag_fused`: `chunk + bvn`, `8 GPU`, `256MB`, ratio `1.00061`

Interpretation:
- For 8-GPU successful points, calendar and packet are mostly parity, with small deltas.
- `allgather` has the only clear measured calendar gain in this full sweep.
- `chunk` granularity appears most frequently in best-observed points for successful 8-GPU cases.

## 4) Timeout / Feasibility Analysis (Critical for Full Matrix)

Calendar timeout concentration by operator and GPU:
- 16-GPU timeout = 100% for: `allgather`, `alltoall_ep`, `moe_dispatch`, `moe_combine`, `moe_pipeline`
- 16-GPU timeout = 84.4% for: `allreduce_ring`, `allreduce_tree`, `compute_overlap`, `reduce_scatter`, `rs_ag_fused`
- 8-GPU timeout mostly 0%; small non-zero only for `allreduce_ring` and `allreduce_tree`

This means:
- The matrix was fully launched and logged, but not fully closed in terms of valid E2E samples.
- Recommendation confidence is high for 8-GPU successful region, low for 16-GPU high-contention region.

## 5) Message Size Sensitivity (From Available Matched Data)

Using matched runs only:
- At `1MB`, multiple operators are near exact parity (`ratio ~= 1.0`)
- At `32MB` and `256MB`, differences remain small for completed 8-GPU runs
- Large 16-GPU points are underrepresented due to timeout, so no strong sensitivity conclusion is claimed for that regime

## 6) MoE Dynamic-Pattern Observations

For completed 8-GPU MoE-family points:
- `alltoall_ep`, `moe_dispatch`, `moe_combine`, `moe_pipeline` are generally near parity in p95 ratio
- Stability under dynamic traffic is still an issue at 16-GPU scale (timeout-heavy)
- Current best practical recommendation remains in 8-GPU region until 16-GPU stall/timeout root causes are further reduced

## 7) Fused Operator Observations

- `rs_ag_fused` and `compute_overlap` (8-GPU successful points) stay near packet baseline
- No strong evidence from this full sweep that operator-level unified scheduling clearly dominates phase/finer modes
- Best observed fused points still lean to `chunk + bvn` at 8 GPU

## 8) Utilization / Queue / Blocking Notes

Non-E2E metrics are present in many calendar runs (from `calendar_trace.csv` and `calendar_trace.csv.switch_metrics.csv`), including:
- block rate
- queue bytes
- reschedule count

However, strict spec-style link-utilization comparability is incomplete for all points because:
- many 16-GPU configurations timed out (no completed E2E)
- utilization decision-rule coverage is therefore partial

## 9) Recommendation (Current Evidence)

Per operator class, using successful matched runs:
- Deterministic collectives (8 GPU): prefer `chunk` granularity, `bvn` or `solstice`; expected gain is modest
- MoE / dynamic family (8 GPU): `chunk + bvn` is currently the most stable best-observed choice
- 16-GPU: do not finalize granularity recommendation yet; timeout rate is too high for spec-level confidence

Confidence levels:
- 8-GPU recommendation confidence: Medium
- 16-GPU recommendation confidence: Low

## 10) Next Closure Steps for Full Spec Completion

To fully satisfy spec intent (not just launch-complete):
- raise completion ratio on 16-GPU calendar runs (reduce timeout-heavy regimes)
- rerun failed strata first: all 16-GPU MoE-family + high-contention collectives
- regenerate this report after closure to produce stable per-operator final recommendations with higher confidence

