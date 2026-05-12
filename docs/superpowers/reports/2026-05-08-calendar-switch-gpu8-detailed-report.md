# GPU=8 Detailed Report (BvN Production, Quick, 400Gbps, Dynamic-Fix Rerun)

Date: 2026-05-12  
Run root: `results/calendar_study_gpu8_bvn_prod_quick_400g_dynamicfix_20260512`  
Aggregated JSON: `results/calendar_study_gpu8_bvn_prod_quick_400g_dynamicfix_20260512/report.json`  
Metric: `p95(calendar) / p95(packet_switch_baseline)`

## 核心结论

- 本轮按 production-readout + dynamic-timeout-fix 规则扫描（总计 `152` 组）：
  - baseline: `20`
  - calendar: `132`
  - matched ratio: `80`
  - skipped (empty E2E): `40`
- dynamic lane 采用：`RR + static_operator + 128KB + uniform gate-trace`（关闭动态重调度）
- 全局最优比值：`0.962122`（`allgather@32MB`, `chunk+bvn`）
- matched 样本平均比值：`1.229878`
- deterministic 算法对比（matched）：
  - `bvn`: `60` 样本，均值 `1.000234`
  - `round_robin`（control）: `20` 样本，均值 `1.918810`
- `missing_baselines = 12`：来自 dynamic `128KB` 样本在 baseline 侧暂无对应 size

## 每个算子最优点（1MB/32MB）

- `allgather`
  - `32MB`: `chunk+bvn`, `660689/686700`, ratio=`0.962122`
  - 修复后对照：`operator+bvn` 在 `1MB` 和 `32MB` 与 `chunk+bvn` 完全一致（startup 偏置已消除）
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

动态算子（`alltoall_ep`, `moe_dispatch`, `moe_combine`, `moe_pipeline`）本轮依旧无 matched ratio 点，但 empty-E2E 已消除（见完成率）。

## allreduce_ring 专项结论

- `bvn`：`10/10` matched（两种 size × 五种 granularity）
- `round_robin`：`0/10` matched（全部 empty E2E）
- 结论：在 400Gbps + static policy 下，`allreduce_ring` 的生产候选应固定为 `bvn`，RR 仅用于对照。

## 按算子完成率（calendar）

（说明：使用 matched/total，未匹配部分主要是 empty E2E）

- `allgather`: `20/20`（skipped `0`）
- `allreduce_ring`: `10/20`（skipped `10`）
- `allreduce_tree`: `10/20`（skipped `10`）
- `alltoall_ep`: `3/3`（skipped `0`）
- `compute_overlap`: `15/20`（skipped `5`）
- `moe_dispatch`: `3/3`（skipped `0`）
- `moe_combine`: `3/3`（skipped `0`）
- `moe_pipeline`: `3/3`（skipped `0`）
- `reduce_scatter`: `10/20`（skipped `10`）
- `rs_ag_fused`: `15/20`（skipped `5`）

## 建议

- deterministic 正式结论以 `bvn` 为主，`round_robin` 只保留 control 角色。
- allgather 的 granularity 选择不再受“首次静态表装载时机”偏置影响，operator/chunk 均可。
- dynamic 的 empty-E2E 已通过 static-RR 方案收敛；下一步先补 baseline `128KB`，再做 ratio 对比。
- 若要补全最终报告，建议先完成 dynamic ratio 闭环，再针对入围点补跑大消息量验证。
