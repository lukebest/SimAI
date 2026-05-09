# GPU=8 Detailed Report (Mixed Algorithms, Quick Profile)

Date: 2026-05-09  
Run root: `results/calendar_study_gpu8_mixed_quick_20260509`  
Aggregated JSON: `results/calendar_study_gpu8_mixed_quick_20260509/report.json`  
Metric: `p95(calendar) / p95(packet_switch_baseline)`

## 核心结论

- 本轮按修改后的 spec + quick profile 扫描（仅 `1MB` 和 `32MB`，总计 `224` 组）：
  - baseline: `20`
  - calendar: `204`
  - matched ratio: `150`
  - skipped (empty E2E): `54`
- 全局最优比值：`0.971615`（`allgather@1MB`, `phase+bvn`）
- matched 样本平均比值：`1.106545`
- 相比上一轮 RR-only 结果，本轮在 deterministic 上明显改善：多个算子在 `32MB` 已接近 baseline（ratio 约 `1.0`）。

## 每个算子最优点（1MB/32MB）

- `allgather`
  - `1MB`: `phase+bvn`, `139896/143983`, ratio=`0.971615`
  - `32MB`: `phase+bvn`, `2468790/2470720`, ratio=`0.999219`
- `allreduce_ring`
  - `32MB`: `operator+bvn`, `4778558/4778360`, ratio=`1.000041`
- `allreduce_tree`
  - `32MB`: `operator+bvn`, `4778558/4778360`, ratio=`1.000041`
- `compute_overlap`
  - `32MB`: `operator+bvn`, `4813528/4813528`, ratio=`1.000000`
- `reduce_scatter`
  - `32MB`: `operator+bvn`, `2391374/2391358`, ratio=`1.000007`
- `rs_ag_fused`
  - `32MB`: `operator+bvn`, `2408615/2408615`, ratio=`1.000000`
- `alltoall_ep`
  - `1MB`: `chunk+round_robin`, `138801/126880`, ratio=`1.093955`
- `moe_dispatch`
  - `1MB`: `packet+round_robin`, `138019/126880`, ratio=`1.087792`
- `moe_combine`
  - `1MB`: `chunk+round_robin`, `139541/126880`, ratio=`1.099787`
- `moe_pipeline`
  - `1MB`: `packet+round_robin`, `96854/90373`, ratio=`1.071714`

## 按算子完成率（calendar）

（说明：这里使用 matched/total，未匹配部分主要是 empty E2E）

- `allgather`: `30/30`（skipped `0`）
- `allreduce_ring`: `22/30`（skipped `8`）
- `allreduce_tree`: `21/30`（skipped `9`）
- `alltoall_ep`: `2/6`（skipped `4`）
- `compute_overlap`: `24/30`（skipped `6`）
- `moe_dispatch`: `2/6`（skipped `4`）
- `moe_combine`: `1/6`（skipped `5`）
- `moe_pipeline`: `2/6`（skipped `4`）
- `reduce_scatter`: `22/30`（skipped `8`）
- `rs_ag_fused`: `24/30`（skipped `6`）

## 建议

- 当前 quick 结果支持“deterministic 优先 BvN”的结论：在 `32MB` 大多可达近 baseline。
- dynamic 仍是主瓶颈：优先解决 empty-E2E 问题，再谈粒度/算法微调。
- 若需要对外给出完整结论，建议下一步只对筛选后的少量候选补跑 `256MB`，而不是恢复全矩阵。
