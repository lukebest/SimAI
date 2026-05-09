# Calendar-Based Switch Performance Study for LLM Operators

**Date:** 2026-05-07
**Project:** SimAI (astra-sim-alibabacloud + ns-3-alibabacloud)
**Scope:** Demand-aware calendar switch performance benchmarking across LLM collective, fused, and MoE operators at multiple scheduling granularities

---

## 1. Problem Statement

LLM training and inference workloads generate structured, often predictable communication patterns through collective operations (allreduce, allgather, reduce_scatter) and expert-parallel MoE dispatch/combine. Calendar-based (circuit-switched) networks can exploit this structure by pre-scheduling switch configurations to match traffic demand, potentially reducing contention and tail latency compared to packet-switched fabrics.

The central question: **at what scheduling granularity should a demand-aware calendar switch operate to minimize end-to-end operator completion time?** Coarser granularity (operator-level) has lower scheduling overhead but may waste bandwidth on non-uniform phases. Finer granularity (packet/slot) adapts better but may not amortize the scheduling cost.

Complicating this: deterministic operators (allreduce, allgather, reduce_scatter) have fully predictable traffic matrices, while MoE dispatch/combine have dynamic, gating-dependent traffic patterns that are only known after the expert selection decision.

## 2. Goals

1. Implement a configurable demand-aware calendar switch in ns-3 that supports multiple scheduling algorithms and granularity modes.
2. Benchmark all major LLM operator classes under calendar scheduling.
3. Determine the optimal scheduling granularity for each operator class by measuring E2E completion time.
4. Compare calendar switch performance against a packet-switched RDMA/QBB baseline.
5. Produce reproducible experiment infrastructure and a quantitative analysis report.

## 3. Non-Goals

- Large-scale (>16 GPU) evaluation (future work).
- Non-zero reconfiguration overhead modeling (start with zero overhead to isolate granularity impact).
- Calendar-aware redesign of collective algorithms themselves.
- Replacement of the existing RDMA/QBB simulation stack.
- End-to-end model training trace closure.

## 4. System Architecture

Three-layer design with clean separation of concerns:

```
AstraSim Layer                Calendar Scheduler Library        ns-3 Layer
+--------------------+       +-------------------------+       +---------------------+
| Workload Generator |       | DemandCollector         |       | CalendarSwitchNode  |
| Collective Engine  |------>| ScheduleAlgorithms      |------>| EgressGating        |
| GranularityCtrl    |       |   - Solstice            |       | (extends SwitchNode)|
+--------------------+       |   - BvN                 |       +---------------------+
                             |   - RoundRobin          |       | Baseline SwitchNode |
                             | ScheduleTable           |       | (unchanged)         |
                             +-------------------------+       +---------------------+
```

### 4.1 CalendarScheduler Library

A pure C++ library with no ns-3 dependencies. Inputs: an NxN demand matrix D where D[i][j] = bytes from port i to port j. Outputs: a schedule S = [(P_k, w_k)] where P_k is a permutation matrix and w_k is the number of slots allocated to that permutation.

Three algorithm implementations:

- **Solstice**: Greedy iterative matching. At each step, extract a maximum-weight matching from the residual demand matrix, allocate slots proportional to the matching weight, subtract. Repeat until demand is exhausted.
- **Birkhoff-von Neumann (BvN)**: Normalize D to a doubly-stochastic matrix, decompose into a convex combination of permutation matrices using the BvN theorem, quantize the weights to integer slot counts.
- **Round-Robin**: Cycle through N rotations of a circular shift pattern, each rotation gets equal slot allocation. Demand-agnostic but provides a lower bound on scheduling intelligence.

All three produce the same output type: `vector<pair<PermutationMatrix, uint32_t>>`.

### 4.2 CalendarSwitchNode

A new C++ class extending `SwitchNode` (in ns-3). Does NOT modify the existing `SwitchNode` -- the experiment selects between them via configuration.

Runtime behavior:
- Maintains a `current_schedule` (sequence of permutation matrices with durations).
- A `slot_timer` fires every `calendar_slot_ns` nanoseconds, advancing the slot counter.
- On egress dequeue: check if the packet's `(ingress_port, egress_port)` pair is permitted by the current permutation. If permitted, dequeue and forward. If not, hold the packet in the queue until a future slot permits it.
- When the schedule is exhausted (all permutations have been served), either loop or wait for a new schedule from the GranularityController.

### 4.3 GranularityController

Sits between AstraSim's collective execution and the CalendarScheduler. Configured with one of five granularity modes:

| Mode | Trigger | Demand Scope |
|------|---------|--------------|
| `operator` | Before operator's first flow | Full operator traffic matrix |
| `phase` | Before each ring step / tree phase / MoE stage | Traffic for this phase only |
| `chunk` | Before each data chunk within a phase | Traffic for this chunk |
| `packet` | Per-packet (degenerates to per-flow arbitration) | Single packet src->dst |
| `slot` | Per time quantum | Current queue state |

Implementation hooks into AstraSim's flow model generation. For operators using `MockNcclGroup`, the controller reads `flowTag.tag_id` to identify operators, `current_flow_id` for phases, and `child_flow_id` for chunks.

### 4.4 Demand Collection for Different Operator Types

**Deterministic operators** (allreduce, allgather, reduce_scatter):
- Traffic pattern is fully determined by the collective algorithm (ring, tree, halving-doubling) and message size.
- At `operator` granularity: analyze the algorithm to produce the full demand matrix before any packet is sent.
- At `phase` granularity: produce a demand matrix for each communication step of the algorithm.
- Lower granularities subdivide phase demand by chunk size.

**MoE dispatch/combine**:
- Traffic depends on the expert gating decision (which tokens go to which experts).
- At `operator` granularity: use a uniform demand estimate (each GPU sends equal traffic to all others). This models the worst case of scheduling without demand knowledge.
- At `phase` granularity: the gating decision is available, so the demand matrix reflects the actual token-to-expert mapping. This is the natural scheduling point for MoE.
- At `chunk/packet/slot` granularity: subdivide the known MoE demand further.

**Fused operators**:
- **ReduceScatter + AllGather**: Two-phase operator. Each phase gets its own schedule at phase-level granularity. At operator-level, a combined schedule covers both phases.
- **Compute-communication overlap**: Communication phases are scheduled; compute phases represent gaps where the switch can serve other traffic or idle.
- **MoE pipeline (dispatch + expert_compute + combine)**: Three phases. Dispatch and combine are communication phases with potentially different demand matrices. Expert compute is a non-network gap.

## 5. Configuration

Config entries added to `SimAI.conf` parsing in `common.h`:

```
ENABLE_CALENDAR_SWITCH      0|1
CALENDAR_SLOT_NS            <nanoseconds per slot>
CALENDAR_FRAME_SLOTS        <slots per frame>
CALENDAR_GRANULARITY_MODE   operator|phase|chunk|packet|slot
CALENDAR_ALGORITHM          solstice|bvn|round_robin
CALENDAR_TRACE_ENABLE       0|1
CALENDAR_TRACE_FILE         <path to slot admission trace>
```

Defaults preserve baseline behavior (`ENABLE_CALENDAR_SWITCH=0`).

## 6. Operator Set

| Operator | Category | Multi-phase? | Demand Predictability |
|----------|----------|-------------|----------------------|
| `ALLREDUCE` (ring) | Collective | Yes (N-1 ring steps) | Deterministic |
| `ALLREDUCE` (tree) | Collective | Yes (reduce + broadcast) | Deterministic |
| `ALLGATHER` | Collective | Yes (N-1 ring steps) | Deterministic |
| `REDUCE_SCATTER` | Collective | Yes (N-1 ring steps) | Deterministic |
| `ALLTOALL_EP` | MoE | Yes (N-1 send phases) | Dynamic (gating-dependent) |
| `MOE_DISPATCH` | MoE | Depends on implementation | Dynamic |
| `MOE_COMBINE` | MoE | Depends on implementation | Dynamic |
| `RS_AG_FUSED` | Fused | Yes (RS phase + AG phase) | Deterministic |
| `COMPUTE_OVERLAP` | Fused | Yes (compute + comm interleave) | Deterministic |
| `MOE_PIPELINE` | Fused | Yes (dispatch + compute + combine) | Dynamic (dispatch/combine) |

> **Spec update (2026-05-09, revised 2026-05-09b):**
> - Experiments are constrained to **GPU=8 only**.
> - For operators marked **Dynamic** in this table, calendar scheduling only evaluates `chunk` / `packet` / `slot` granularities.
> - `operator` and `phase` granularities are **not evaluated** for Dynamic operators.
> - **Dynamic** operators: no demand-aware scheduling; calendar uses **Round-Robin only**.
> - **Deterministic** operators: calendar runs all three algorithms **Round-Robin**, **BvN**, and **Solstice** (demand-aware where the implementation applies).

## 7. Granularity Semantics Per Operator

### 7.1 Ring AllReduce (N GPUs, message M)

- **operator**: One schedule covers all N-1 ring steps. Demand matrix: each GPU sends M/(N) to its right neighbor at each step, but aggregated over all steps = each GPU sends/receives M*(N-1)/N total.
- **phase**: N-1 separate schedules, one per ring step. Each step's demand: GPU_i sends M/N to GPU_(i+1 mod N).
- **chunk**: Within each ring step, M/N is split into C chunks. C schedules per step.
- **packet**: Per-packet, M/N/packet_size schedules per step.
- **slot**: Time-quantum scheduling, independent of ring steps.

### 7.2 MoE Dispatch (N GPUs, E experts, T tokens per GPU)

- **operator**: _Not evaluated in this spec revision (Dynamic operator pruning rule)_.
- **phase**: _Not evaluated in this spec revision (Dynamic operator pruning rule)_.
- **chunk**: Divide each GPU's outbound tokens into chunks of C tokens, schedule per chunk.
- **packet**: Per-packet.
- **slot**: Time-quantum.

### 7.3 RS+AG Fused

- **operator**: One schedule covering both RS and AG phases. Demand = sum of RS demand + AG demand.
- **phase**: Separate schedule for RS phase and AG phase.
- Finer granularities subdivide within each phase.

## 8. Experiment Design

### 8.1 Fixed Controls

For all A/B comparisons (calendar vs baseline):
- Topology: single switch, N fully-connected ports
- Link bandwidth: 100 Gbps
- Link latency: 1 us
- Packet payload: 1000 bytes
- ECN/PFC settings: match SimAI defaults
- Workload definition: identical operator and message size

### 8.2 Experiment Matrix

Dimensions:
- Operator type: 10 operators (see Section 6)
- Granularity:
  - Deterministic operators: 5 levels (`operator`, `phase`, `chunk`, `packet`, `slot`)
  - Dynamic operators: 3 levels (`chunk`, `packet`, `slot`)
- Algorithm:
  - Deterministic: 3 (`round_robin`, `bvn`, `solstice`)
  - Dynamic: 1 (`round_robin` only; no demand-aware)
- GPU count: 1 (`8`)
- Message size: from real traces (Llama-70B gradient sizes for collectives, DeepSeek-V3 MoE token distributions)
- Switch mode: 2 (calendar, packet-switch baseline)

Pruning rules:
- Single-phase operators at `phase` granularity collapse to `operator` (report as such, skip separate run).
- Baseline runs ignore granularity and algorithm (1 run per operator/GPU/size combo).
- Dynamic operators do not run `operator` or `phase` granularity.
- Dynamic calendar runs use `round_robin` only and do not use demand-aware schedule construction.
- Deterministic calendar runs use `round_robin`, `bvn`, and `solstice` as specified per run.

Estimated run count (GPU=8, 3 message sizes):  
`calendar = (6 deterministic x 5 granularities x 3 algorithms x 3 sizes) + (4 dynamic x 3 granularities x 1 algorithm x 3 sizes) = 270 + 36 = 306`  
`baseline = 10 operators x 1 GPU-count x 3 message sizes = 30`  
Total `336` runs.

### 8.3 Workload Sources

- **Collective operators**: Use AICB (`aicb/workload_generator/SimAI_training_workload_generator.py`) to extract gradient sizes from Llama-70B model config. The allreduce message size for gradient synchronization in Llama-70B with TP=8 is approximately 32MB for the largest layers.
- **MoE operators**: Use DeepSeek-V3 style config (256 experts, top-k=6, shared experts). Token-to-expert distributions: uniform (baseline), zipf (skewed), and empirically measured from DeepSeek-V3 traces if available.
- **Fused operators**: Construct from combinations of the above, with realistic inter-phase timing from AICB profiles.

## 9. Metrics

### 9.1 Primary

**Operator E2E completion time**: Time from first packet of the operator entering the network to the last packet's delivery confirmation. Report p50, p95, p99, mean.

### 9.2 Secondary

- **Flow completion time (FCT)**: Per-flow (src, dst, size) completion time distribution.
- **Link utilization**: Fraction of time each port carries payload data (not idle or blocked).
- **Slot utilization**: (Calendar mode) Fraction of calendar slots that carry at least one packet. Measures schedule efficiency.
- **Slot waiting time**: (Calendar mode) Distribution of time packets wait in queue for their permitted slot.
- **Scheduling overhead**: Wall time for demand collection + schedule computation. Instrumented but expected near-zero for small N.
- **Queue occupancy**: Peak and mean queue depth at the switch.
- **PFC/CNP events**: Count of flow control events, if any.

### 9.3 Decision Rule

Per operator class, the best granularity is the one that minimizes p95 E2E time without link utilization dropping below 50% of the baseline. If lower latency comes with major utilization collapse, report as explicit trade-off.

## 10. Baseline Comparison

For each (operator, message_size, gpu_count), the baseline is the same workload on unmodified packet-switched `SwitchNode` with RDMA/QBB. Results are reported as:

- Absolute E2E time (calendar and baseline)
- Ratio: `calendar_e2e / baseline_e2e` (values < 1.0 = calendar wins)
- Utilization comparison

## 11. File Layout

```
SimAI/
├── calendar_scheduler/                    # Standalone scheduler library
│   ├── include/
│   │   ├── calendar_scheduler.h           # DemandMatrix, Schedule, Permutation types
│   │   ├── solstice_scheduler.h
│   │   ├── bvn_scheduler.h
│   │   └── round_robin_scheduler.h
│   ├── src/
│   │   ├── solstice_scheduler.cc
│   │   ├── bvn_scheduler.cc
│   │   └── round_robin_scheduler.cc
│   └── CMakeLists.txt
│
├── ns-3-alibabacloud/simulation/src/point-to-point/model/
│   ├── calendar-switch-node.h             # NEW
│   ├── calendar-switch-node.cc            # NEW
│   └── (switch-node.h/.cc unchanged)
│
├── astra-sim-alibabacloud/astra-sim/network_frontend/ns3/
│   ├── common.h                           # MODIFY: calendar config knobs
│   ├── entry.h                            # MODIFY: wire GranularityController
│   └── granularity_controller.h           # NEW
│
├── workloads/calendar_study/
│   ├── generate_workloads.py              # AICB-based trace extraction
│   ├── moe_traffic_generator.py           # MoE with skew control
│   └── fused_op_workloads.py
│
├── scripts/
│   ├── run_calendar_study.sh              # Master experiment runner
│   ├── run_single_experiment.sh           # Single config run
│   └── analyze_results.py                 # Metrics + figures
│
├── tests/calendar_switch/
│   ├── test_scheduler_algorithms.py
│   ├── test_granularity_controller.py
│   ├── test_calendar_switch_node.py
│   ├── test_workload_generation.py
│   └── test_baseline_parity.py
│
└── docs/superpowers/specs/
    └── 2026-05-07-calendar-switch-perf-study-design.md
```

## 12. Validation Plan

1. **Baseline parity**: With `ENABLE_CALENDAR_SWITCH=0`, simulation results must match unmodified SwitchNode behavior exactly (bit-identical packet traces).

2. **Scheduler correctness**: Unit tests verify that each algorithm's output schedule (a) covers the full demand matrix, (b) each slot uses a valid permutation, and (c) total allocated slots match frame size.

3. **Single-flow mechanism check**: One flow from GPU_0 to GPU_1 through the calendar switch. Verify the flow is served only during its allocated slots and completes within the expected time.

4. **Two-flow contention check**: Two competing flows with overlapping demand. Verify the schedule arbitrates correctly and both complete.

5. **Deterministic reproducibility**: Same config produces same results across runs.

## 13. Analysis Report Structure

The final report includes:

1. **Executive summary**: Best granularity per operator class, overall calendar vs baseline verdict.
2. **Per-operator heatmaps**: Granularity (rows) x Algorithm (columns), cell color = E2E ratio vs baseline.
3. **Message size sensitivity**: Line plots of E2E vs message size, one line per granularity.
4. **MoE skew analysis**: How expert load imbalance affects optimal granularity.
5. **Fused operator analysis**: Independent phase scheduling vs unified operator scheduling.
6. **Utilization analysis**: Link and slot utilization across configurations.
7. **Recommendation table**: Per operator, recommended (granularity, algorithm) pair with confidence level.

## 14. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| ns-3 simulation too slow at scale | Cannot complete experiment matrix | Start with 8 GPU; parallelize across machines |
| AstraSim flow model doesn't expose phase/chunk boundaries cleanly | GranularityController cannot detect boundaries | Instrument `MockNcclGroup` to emit boundary events |
| BvN decomposition is O(N^3) per schedule | Scheduling overhead becomes non-negligible for large N | N=8/16 is small enough; document scaling limit |
| MoE expert load distributions unrealistic | Results don't transfer to real workloads | Use empirical distributions from DeepSeek-V3 when available, plus sensitivity analysis with synthetic distributions |
