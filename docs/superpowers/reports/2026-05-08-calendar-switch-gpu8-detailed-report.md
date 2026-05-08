# GPU=8 Calendar Switch Detailed Report

**Date:** 2026-05-08  
**Primary sweep:** `results/calendar_study_full_20260507_timeout`  
**Follow-up conflict sweep:** `results/gpu8_conflict_sweep_20260508`  
**Follow-up summary CSV:** `results/gpu8_conflict_sweep_20260508/summary.csv`  
**Filter:** `gpus = 8`  
**Metric:** `p95(calendar) / p95(packet_switch_baseline)`

## 核心结论（先答问题）

- **各激励下最优调度粒度：无唯一最优。** 当前 GPU=8 结果里所有粒度均与 baseline 持平，属于并列最优。
- **与基线分组交换比对：仍全部持平。** 在补充的“冲突增强 + slot_ns 敏感性”实验中，`48/48` 个 calendar 配置也全部 `ratio=1.000`。
- **原因定位进展：已确认 schedule 下发链路有效，但尚未形成可见的 e2e 差异。** `calendar_trace.csv` 出现大量 `reschedule` 事件，说明不再是“完全 no-op”。

## 原始 GPU=8 全量筛选结果（保持不变）

- 样本：`450`（全部有效）
- 优于 baseline：`0`
- 持平 baseline：`450`
- 劣于 baseline：`0`

## 补充实验：冲突增强与 slot 灵敏度（GPU=8）

### 实验设计

- 算法固定：`solstice`
- 激励：`allgather`、`alltoall_ep`、`moe_dispatch`、`moe_combine`
- 粒度：`operator`、`phase`、`chunk`、`slot`
- `slot_ns`：`1000`、`5000`、`20000`
- 共 `48` 个 calendar 点 + `4` 个 baseline 点

### 结果摘要

- `allgather`：最佳 `ratio=1.000`（所有粒度/slot_ns 均 `1.000`）
- `alltoall_ep`：最佳 `ratio=1.000`（所有粒度/slot_ns 均 `1.000`）
- `moe_dispatch`：最佳 `ratio=1.000`（所有粒度/slot_ns 均 `1.000`）
- `moe_combine`：最佳 `ratio=1.000`（所有粒度/slot_ns 均 `1.000`）

## 代码级验证证据

- 已修复首流强制下发表与粒度触发阈值逻辑，避免“从不触发 schedule”。
- 在 `allgather/phase` 场景中，`calendar_trace.csv` 记录到持续重调度，且 `schedule_entries` 显著大于 1（最高接近 900）。
- 尽管如此，e2e 仍与 baseline 持平，说明当前 GPU=8 单交换机映射下，calendar gating 对端到端时延尚未形成可观测优势。

## 当前结论的边界

- 本结论是 **GPU=8 + 单交换机 + 当前 SimAI workload 映射 + 当前流量形态** 下的结果。
- 不应直接外推到更大规模、多跳拓扑或更强热点/突发输入。

## 下一步建议

- 引入真实/可控热点 MoE gate trace（非均匀、时变）再做 GPU=8 对比。
- 增加非 e2e 指标（blocked 次数、每端口队列占用、每 slot admission）来判断 calendar 是否改善瞬时拥塞。
- 在 16 GPU 和多跳路径上复验粒度收益，再更新“最优粒度”结论。
