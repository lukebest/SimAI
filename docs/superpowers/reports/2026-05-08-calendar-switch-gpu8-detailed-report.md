# GPU=8 Detailed Report (Forced Single-Switch, No-NVSwitch)

Date: 2026-05-09  
Run root: `results/calendar_study_gpu8_no_nvswitch_20260509_rerun2`  
Aggregated JSON: `results/calendar_study_gpu8_no_nvswitch_20260509_rerun2/report.json`  
Metric: `p95(calendar) / p95(packet_switch_baseline)`

## 核心结论

- 这是按要求强制拓扑后的 GPU=8 全量 sweep（`480` 组）：
  - baseline: `30/30` 成功
  - calendar: `190` 成功、`260` timeout
  - 有效 matched ratio: `193`
- 全局最优比值：`0.971615`（`allgather@1MB`, `phase+bvn`）
- matched 样本平均比值：`1.087536`
- 总体上 collectives 接近或小幅优于 baseline；MoE/高冲突激励完成率低且多为劣于 baseline。

## 每个激励（operator × message size）最优点

- `allgather`
  - `1MB`: `phase+bvn`, `139896/143983`, ratio=`0.971615`
  - `32MB`: `operator+bvn`, `2468790/2470720`, ratio=`0.999219`
  - `256MB`: `chunk+bvn`, `19032232/19076666`, ratio=`0.997671`
- `allreduce_ring`
  - `1MB`: `chunk+bvn`, `155014/154234`, ratio=`1.005057`
  - `32MB`: `operator+bvn`, `4778558/4778360`, ratio=`1.000041`
- `allreduce_tree`
  - `1MB`: `chunk+bvn`, `155014/154234`, ratio=`1.005057`
  - `32MB`: `operator+bvn`, `4778558/4778360`, ratio=`1.000041`
- `alltoall_ep`
  - `1MB`: `chunk+round_robin`, `139291/126880`, ratio=`1.097817`
- `compute_overlap`
  - `1MB`: `operator+bvn`, `157840/157836`, ratio=`1.000025`
  - `32MB`: `operator+bvn`, `4813528/4813528`, ratio=`1.000000`
- `moe_combine`
  - `1MB`: `phase+round_robin`, `139403/126744`, ratio=`1.099878`
- `moe_dispatch`
  - `1MB`: `operator+round_robin`, `138484/126880`, ratio=`1.091456`
- `moe_pipeline`
  - `1MB`: `packet+round_robin`, `95385/90373`, ratio=`1.055459`
  - `32MB`: `packet+round_robin`, `2403156/2390631`, ratio=`1.005239`
- `reduce_scatter`
  - `1MB`: `chunk+bvn`, `80758/79978`, ratio=`1.009753`
  - `32MB`: `operator+bvn`, `2391374/2391358`, ratio=`1.000007`
  - `256MB`: `operator+bvn`, `19020566/19020566`, ratio=`1.000000`
- `rs_ag_fused`
  - `1MB`: `operator+bvn`, `82585/82581`, ratio=`1.000048`
  - `32MB`: `operator+bvn`, `2408615/2408615`, ratio=`1.000000`
  - `256MB`: `operator+bvn`, `19039739/19039739`, ratio=`1.000000`

注：未出现的 `(operator, size)` 组合是该层在 calendar 路径 timeout，未形成 matched 点。

## 按激励完成率（calendar）

- `allgather`: `45/45` 成功
- `allreduce_ring`: `21/45` 成功（timeout `53.3%`）
- `allreduce_tree`: `21/45` 成功（timeout `53.3%`）
- `alltoall_ep`: `2/45` 成功（timeout `95.6%`）
- `compute_overlap`: `24/45` 成功（timeout `46.7%`）
- `moe_dispatch`: `2/45` 成功（timeout `95.6%`）
- `moe_combine`: `4/45` 成功（timeout `91.1%`）
- `moe_pipeline`: `5/45` 成功（timeout `88.9%`）
- `reduce_scatter`: `33/45` 成功（timeout `26.7%`）
- `rs_ag_fused`: `33/45` 成功（timeout `26.7%`）

## 建议

- Deterministic collectives：优先 `bvn`，粒度以 `operator/chunk/phase` 按消息大小选择。
- MoE 相关激励：先提升完成率（减少 timeout），再讨论粒度最优。
- 对外结论建议把“timeout-heavy strata”明确标注为未收敛区域。
