# GPU=8 Detailed Report (BvN Production, Quick, 400Gbps)

Date: 2026-05-11  
Run root: `results/calendar_study_gpu8_bvn_prod_quick_400g_20260511`  
Aggregated JSON: `results/calendar_study_gpu8_bvn_prod_quick_400g_20260511/report.json`  
Metric: `p95(calendar) / p95(packet_switch_baseline)`

## 核心结论

- 本轮按 production-readout 规则扫描（`1MB` + `32MB`，`164` 组）：
  - baseline: `20`
  - calendar: `144`
  - matched ratio: `80`
  - skipped (empty E2E): `64`
- 全局最优比值：`0.962122`（`allgather@32MB`, `chunk+bvn`）
- matched 样本平均比值：`1.234820`
- deterministic 算法对比（matched）：
  - `bvn`: `60` 样本，均值 `1.003472`
  - `round_robin`（control）: `20` 样本，均值 `1.928863`

## 每个算子最优点（1MB/32MB）

- `allgather`
  - `32MB`: `chunk+bvn`, `660689/686700`, ratio=`0.962122`
- `allreduce_ring`
  - `1MB`: `operator+bvn`, `48523/50309`, ratio=`0.964499`
- `allreduce_tree`
  - `1MB`: `operator+bvn`, `48523/50309`, ratio=`0.964499`
- `compute_overlap`
  - `1MB`: `operator+bvn`, ratio=`0.983355`
- `reduce_scatter`
  - `1MB`: `operator+bvn`, `27640/28526`, ratio=`0.968941`
- `rs_ag_fused`
  - `32MB`: `chunk+bvn`, `612757/616645`, ratio=`0.993695`

动态算子（`alltoall_ep`, `moe_dispatch`, `moe_combine`, `moe_pipeline`）本轮无 matched 点。

## allreduce_ring 专项结论

- `bvn`：`10/10` matched（两种 size × 五种 granularity）
- `round_robin`：`0/10` matched（全部 empty E2E）
- 结论：在 400Gbps + static policy 下，`allreduce_ring` 的生产候选应固定为 `bvn`，RR 仅用于对照。

## 按算子完成率（calendar）

（说明：使用 matched/total，未匹配部分主要是 empty E2E）

- `allgather`: `20/20`（skipped `0`）
- `allreduce_ring`: `10/20`（skipped `10`）
- `allreduce_tree`: `10/20`（skipped `10`）
- `alltoall_ep`: `0/6`（skipped `6`）
- `compute_overlap`: `15/20`（skipped `5`）
- `moe_dispatch`: `0/6`（skipped `6`）
- `moe_combine`: `0/6`（skipped `6`）
- `moe_pipeline`: `0/6`（skipped `6`）
- `reduce_scatter`: `10/20`（skipped `10`）
- `rs_ag_fused`: `15/20`（skipped `5`）

## 建议

- deterministic 正式结论以 `bvn` 为主，`round_robin` 只保留 control 角色。
- dynamic 仍是主瓶颈：优先做 empty-E2E 收敛，再开展算法优劣结论。
- 若要补全最终报告，建议只在已收敛候选上补跑 `256MB`，避免恢复全矩阵高成本扫描。
