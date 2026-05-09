# GPU=8 Calendar Switch Detailed Appendix (Spec Full Sweep)

Date: 2026-05-09  
Source full sweep: `results/calendar_study_spec_full_20260508_rerun`  
Aggregated JSON: `results/calendar_study_spec_full_20260508_rerun/report.json`  
Filter: `gpus = 8`  
Metric: `p95(calendar) / p95(packet_switch_baseline)`

## 核心回答（按你要的口径）

- **各激励下最优调度粒度**：在本次全量重跑的 8-GPU 成功样本里，最优点主要集中在 `chunk` 粒度（个别为 `operator`）。
- **与基线分组交换比对**：整体仍以接近持平为主；仅 `allgather@32MB` 出现了明确小幅收益（ratio `0.98779`），其余大多在 `1.000x` 附近。
- **8-GPU 可用样本规模**：`443` 条 matched ratio（calendar 成功且有 baseline）。

## 每个激励（operator × message size）最优配置与基线对比

- `allgather`
  - `1MB`: best=`chunk+bvn`, calendar/base=`11089/9457`, ratio=`1.172571`
  - `32MB`: best=`chunk+bvn`, calendar/base=`104119/105406`, ratio=`0.987790`
  - `256MB`: best=`chunk+bvn`, calendar/base=`789241/789194`, ratio=`1.000060`
- `allreduce_ring`
  - `1MB`: best=`chunk+bvn`, calendar/base=`9651/9418`, ratio=`1.024740`
  - `32MB`: best=`chunk+bvn`, calendar/base=`200458/199983`, ratio=`1.002375`
  - `256MB`: best=`chunk+solstice`, calendar/base=`1571329/1570737`, ratio=`1.000377`
- `allreduce_tree`
  - `1MB`: best=`chunk+bvn`, calendar/base=`9651/9418`, ratio=`1.024740`
  - `32MB`: best=`chunk+bvn`, calendar/base=`200458/199983`, ratio=`1.002375`
  - `256MB`: best=`chunk+solstice`, calendar/base=`1571329/1570737`, ratio=`1.000377`
- `alltoall_ep`
  - `1MB`: best=`chunk+bvn`, calendar/base=`8075/8075`, ratio=`1.000000`
  - `32MB`: best=`chunk+bvn`, calendar/base=`102867/102867`, ratio=`1.000000`
  - `256MB`: best=`chunk+bvn`, calendar/base=`787959/787959`, ratio=`1.000000`
- `compute_overlap`
  - `1MB`: best=`operator+bvn`, calendar/base=`11590/10324`, ratio=`1.122627`
  - `32MB`: best=`chunk+bvn`, calendar/base=`205669/202928`, ratio=`1.013507`
  - `256MB`: best=`chunk+bvn`, calendar/base=`1574285/1573682`, ratio=`1.000383`
- `moe_combine`
  - `1MB`: best=`chunk+bvn`, calendar/base=`8075/8075`, ratio=`1.000000`
  - `32MB`: best=`chunk+bvn`, calendar/base=`102867/102867`, ratio=`1.000000`
  - `256MB`: best=`chunk+bvn`, calendar/base=`787959/787959`, ratio=`1.000000`
- `moe_dispatch`
  - `1MB`: best=`chunk+bvn`, calendar/base=`8075/8075`, ratio=`1.000000`
  - `32MB`: best=`chunk+bvn`, calendar/base=`102867/102867`, ratio=`1.000000`
  - `256MB`: best=`chunk+bvn`, calendar/base=`787959/787959`, ratio=`1.000000`
- `moe_pipeline`
  - `1MB`: best=`chunk+bvn`, calendar/base=`6545/6545`, ratio=`1.000000`
  - `32MB`: best=`chunk+bvn`, calendar/base=`101361/101361`, ratio=`1.000000`
  - `256MB`: best=`chunk+bvn`, calendar/base=`786437/786437`, ratio=`1.000000`
- `reduce_scatter`
  - `1MB`: best=`chunk+bvn`, calendar/base=`6789/6448`, ratio=`1.052885`
  - `32MB`: best=`chunk+bvn`, calendar/base=`102257/101694`, ratio=`1.005536`
  - `256MB`: best=`operator+bvn`, calendar/base=`787129/787050`, ratio=`1.000100`
- `rs_ag_fused`
  - `1MB`: best=`operator+bvn`, calendar/base=`7174/6386`, ratio=`1.123395`
  - `32MB`: best=`chunk+bvn`, calendar/base=`104069/102667`, ratio=`1.013656`
  - `256MB`: best=`chunk+bvn`, calendar/base=`788505/788023`, ratio=`1.000612`

## 每类激励的“建议粒度”（基于 8-GPU 三个消息点）

按每个粒度在三个消息点取“最佳算法后再平均 ratio”：
- `allgather`: 推荐 `chunk`（与 `packet/slot` 同值，优于 `operator/phase`）
- `allreduce_ring`: 推荐 `chunk`（与 `packet/slot` 同值）
- `allreduce_tree`: 推荐 `chunk`（与 `packet/slot` 同值）
- `alltoall_ep`: 五个粒度等价（均 `1.000000`）
- `compute_overlap`: 推荐 `chunk`（与 `packet/slot` 同值）
- `moe_dispatch`: 五个粒度等价（均 `1.000000`）
- `moe_combine`: 五个粒度等价（均 `1.000000`）
- `moe_pipeline`: 五个粒度等价（均 `1.000000`）
- `reduce_scatter`: 推荐 `chunk`（与 `packet/slot` 同值）
- `rs_ag_fused`: 推荐 `operator`（与 `chunk` 差距极小）

## 8-GPU 结论边界

- 本附录只针对 full-sweep 中 **8-GPU 且成功匹配 baseline** 的样本。
- 结论不能直接外推到 16-GPU；16-GPU 在本轮仍有大量 timeout，需要单独 closure 后再下最终结论。
