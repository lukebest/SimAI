# GPU=8 Calendar Switch Detailed Report

**Date:** 2026-05-08  
**Primary sweep:** `results/calendar_study_full_20260507_timeout`  
**Follow-up conflict sweep:** `results/gpu8_conflict_sweep_20260508`  
**Follow-up summary CSV:** `results/gpu8_conflict_sweep_20260508/summary.csv`  
**Hotspot trace + switch-type metrics:** `results/debug_nvswitch_metrics/analysis.json`  
**Filter:** `gpus = 8`  
**Metric:** `p95(calendar) / p95(packet_switch_baseline)`

## 核心结论（先答问题）

- **各激励下最优调度粒度：无唯一最优。** 当前 GPU=8 结果里所有粒度均与 baseline 持平，属于并列最优。
- **与基线分组交换比对：仍全部持平。** 在补充的“冲突增强 + slot_ns 敏感性”实验中，`48/48` 个 calendar 配置也全部 `ratio=1.000`。
- **原因定位进展：已确认 schedule 下发链路有效，且非 e2e 指标已能区分 `calendar`/`nvswitch` 路径。** 这解释了早期 `switch_*` 指标接近 0 的观测偏差。

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

## 新增：switch_type 拆分后的非 e2e 证据（关键）

### 改动点

- 指标采集从仅 `CalendarSwitchNode` 扩展到 `CalendarSwitchNode + NVSwitchNode`。
- `calendar_trace.csv.switch_metrics.csv` 新增 `switch_type` 字段（`calendar` / `nvswitch`）。
- 队列统计口径从仅 MMU `egress_bytes` 扩展到端口队列字节（覆盖 `q0 + non_q0`）。

### 观测结果（`moe_dispatch`, GPU=8, hotspot trace）

- 对照目录：
  - `results/debug_nvswitch_metrics/nvls_on`
  - `results/debug_nvswitch_metrics/nvls_off`
  - baseline: `results/debug_nvswitch_metrics/baseline`
- `analysis.json` 观测到：
  - `calendar_rows = 2016`
  - `nvswitch_rows = 167`
  - `switch_allowed = 317723`
  - `switch_blocked = 0`
  - `switch_max_q_bytes = 54432`
- 含义：
  - 之前 `switch_allowed/switch_blocked/egress_bytes` 接近 0，主要是统计点未覆盖 `nvswitch` 主路径；
  - 加入 `switch_type` 拆分后，`nvswitch` 路径已有明显非零活动指标；
  - 但 calendar 对 e2e 的增益在本组实验仍未体现（`ratio = 1.000`）。

## 当前结论的边界

- 本结论是 **GPU=8 + 单交换机 + 当前 SimAI workload 映射 + 当前流量形态** 下的结果。
- 不应直接外推到更大规模、多跳拓扑或更强热点/突发输入。

## 下一步建议

- 基于 `switch_type` 指标继续放大冲突（更强热点、更高 burst、更多 phase）观察 `switch_block_rate` 是否抬升。
- 增加 `calendar` 与 `nvswitch` 分别统计的对比图（rows/allowed/queue），用于判定主路径归属与拥塞位置。
- 在 16 GPU 和多跳路径上复验粒度收益，再更新“最优粒度”结论。
