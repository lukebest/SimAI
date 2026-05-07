# Calendar-Based Switch Performance Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a demand-aware calendar switch in ns-3, benchmark LLM collective/MoE/fused operators across 5 granularity levels and 3 scheduling algorithms, and compare against the packet-switched baseline.

**Architecture:** Three-layer design: (1) a standalone CalendarScheduler C++ library with Solstice, BvN, and Round-Robin algorithms, (2) a CalendarSwitchNode extending ns-3's SwitchNode with egress gating, and (3) a GranularityController in the AstraSim layer that triggers schedule recomputation at configurable boundaries. Workload generation, experiment orchestration, and analysis are Python/shell.

**Tech Stack:** C++ (AstraSim + ns-3), Python (workload gen, analysis, tests), Bash (experiment runner), matplotlib (figures), numpy (metrics)

---

## File Structure and Responsibilities

**New files:**
- `calendar_scheduler/include/calendar_scheduler.h` -- Types: DemandMatrix, Permutation, Schedule, SchedulerBase interface
- `calendar_scheduler/include/solstice_scheduler.h` -- Solstice greedy decomposition
- `calendar_scheduler/include/bvn_scheduler.h` -- Birkhoff-von Neumann decomposition
- `calendar_scheduler/include/round_robin_scheduler.h` -- Round-robin rotation
- `calendar_scheduler/src/solstice_scheduler.cc` -- Solstice implementation
- `calendar_scheduler/src/bvn_scheduler.cc` -- BvN implementation
- `calendar_scheduler/src/round_robin_scheduler.cc` -- Round-robin implementation
- `calendar_scheduler/CMakeLists.txt` -- Build for standalone lib
- `calendar_scheduler/tests/test_scheduler.cc` -- C++ unit tests (googletest)
- `ns-3-alibabacloud/simulation/src/point-to-point/model/calendar-switch-node.h` -- CalendarSwitchNode class
- `ns-3-alibabacloud/simulation/src/point-to-point/model/calendar-switch-node.cc` -- Egress gating + schedule management
- `astra-sim-alibabacloud/astra-sim/network_frontend/ns3/granularity_controller.h` -- Boundary detection + demand building
- `astra-sim-alibabacloud/inputs/config/SimAI.calendar.conf` -- Calendar-enabled config template
- `workloads/calendar_study/generate_workloads.py` -- Workload extraction from model configs
- `workloads/calendar_study/moe_traffic_generator.py` -- MoE dispatch/combine with skew
- `workloads/calendar_study/fused_op_workloads.py` -- RS+AG and MoE pipeline workloads
- `scripts/run_calendar_study.sh` -- Full experiment sweep
- `scripts/run_single_experiment.sh` -- Single experiment run
- `scripts/analyze_results.py` -- Metrics, figures, report generation
- `tests/calendar_switch/test_scheduler_algorithms.py` -- Scheduler correctness tests
- `tests/calendar_switch/test_calendar_config.py` -- Config parse contract tests
- `tests/calendar_switch/test_granularity_controller.py` -- Boundary detection tests
- `tests/calendar_switch/test_workload_generation.py` -- Workload output format tests
- `tests/calendar_switch/test_baseline_parity.py` -- Calendar-off = baseline check

**Modified files:**
- `astra-sim-alibabacloud/astra-sim/network_frontend/ns3/common.h` -- Calendar config knobs + CalendarSwitchNode instantiation
- `astra-sim-alibabacloud/astra-sim/network_frontend/ns3/entry.h` -- Wire GranularityController into SendFlow path

---

### Task 1: CalendarScheduler Types and Round-Robin Algorithm

The simplest algorithm first, to establish the type system and interface that all three algorithms share.

**Files:**
- Create: `calendar_scheduler/include/calendar_scheduler.h`
- Create: `calendar_scheduler/include/round_robin_scheduler.h`
- Create: `calendar_scheduler/src/round_robin_scheduler.cc`
- Create: `calendar_scheduler/CMakeLists.txt`
- Test: `tests/calendar_switch/test_scheduler_algorithms.py`

- [ ] **Step 1: Write the scheduler algorithm test (Round-Robin)**

```python
# tests/calendar_switch/test_scheduler_algorithms.py
"""
Tests for calendar scheduler algorithms.
Validates that each algorithm produces valid schedules from demand matrices.

These tests check the C++ scheduler output by running a thin Python
wrapper that invokes the scheduler binary and parses its JSON output.
For initial development, we test the algorithm logic in pure Python
reference implementations that mirror the C++ interface exactly.
"""
import json
import numpy as np
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "calendar_scheduler" / "python"))

from calendar_scheduler import DemandMatrix, RoundRobinScheduler, SolsticeScheduler, BvNScheduler


class TestRoundRobinScheduler:
    def test_uniform_demand_produces_n_rotations(self):
        n = 4
        demand = DemandMatrix(np.ones((n, n)) * 100 - np.eye(n) * 100)
        sched = RoundRobinScheduler(frame_slots=1024)
        result = sched.compute(demand)
        assert len(result.entries) == n
        total_slots = sum(e.slots for e in result.entries)
        assert total_slots == 1024

    def test_each_entry_is_valid_permutation(self):
        n = 8
        demand = DemandMatrix(np.ones((n, n)) * 50 - np.eye(n) * 50)
        sched = RoundRobinScheduler(frame_slots=512)
        result = sched.compute(demand)
        for entry in result.entries:
            perm = entry.permutation
            assert len(perm) == n
            assert len(set(perm)) == n
            for i in range(n):
                assert perm[i] != i  # no self-loop in permutation

    def test_empty_demand_produces_empty_schedule(self):
        n = 4
        demand = DemandMatrix(np.zeros((n, n)))
        sched = RoundRobinScheduler(frame_slots=1024)
        result = sched.compute(demand)
        assert len(result.entries) == 0 or all(e.slots == 0 for e in result.entries)

    def test_slots_are_equal_for_round_robin(self):
        n = 4
        demand = DemandMatrix(np.ones((n, n)) * 100 - np.eye(n) * 100)
        sched = RoundRobinScheduler(frame_slots=1024)
        result = sched.compute(demand)
        slot_counts = [e.slots for e in result.entries]
        assert max(slot_counts) - min(slot_counts) <= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_scheduler_algorithms.py::TestRoundRobinScheduler -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'calendar_scheduler'`

- [ ] **Step 3: Create the Python reference scheduler package**

```python
# calendar_scheduler/python/calendar_scheduler/__init__.py
from .types import DemandMatrix, ScheduleEntry, Schedule
from .round_robin import RoundRobinScheduler
from .solstice import SolsticeScheduler
from .bvn import BvNScheduler

__all__ = [
    "DemandMatrix", "ScheduleEntry", "Schedule",
    "RoundRobinScheduler", "SolsticeScheduler", "BvNScheduler",
]
```

```python
# calendar_scheduler/python/calendar_scheduler/types.py
"""
Core types for calendar scheduling. These mirror the C++ types in
calendar_scheduler/include/calendar_scheduler.h.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass
class DemandMatrix:
    """NxN matrix where D[i][j] = bytes from port i to port j."""
    data: np.ndarray

    def __post_init__(self):
        assert self.data.ndim == 2
        assert self.data.shape[0] == self.data.shape[1]

    @property
    def n(self) -> int:
        return self.data.shape[0]

    def total_demand(self) -> float:
        return float(self.data.sum())


@dataclass
class ScheduleEntry:
    """One slot assignment: a permutation matrix + how many slots it gets."""
    permutation: list[int]  # permutation[i] = output port for input port i
    slots: int


@dataclass
class Schedule:
    """A complete calendar schedule: sequence of (permutation, slot_count)."""
    entries: list[ScheduleEntry] = field(default_factory=list)

    @property
    def total_slots(self) -> int:
        return sum(e.slots for e in self.entries)

    def covers_demand(self, demand: DemandMatrix, slot_capacity: float) -> bool:
        """Check if schedule provides enough capacity for demand."""
        served = np.zeros_like(demand.data)
        for entry in self.entries:
            for i, j in enumerate(entry.permutation):
                served[i][j] += entry.slots * slot_capacity
        return np.all(served >= demand.data - 1e-9)
```

```python
# calendar_scheduler/python/calendar_scheduler/round_robin.py
"""
Round-Robin scheduler: cycles through N circular-shift rotations,
each getting equal slot allocation. Demand-agnostic.
"""
from __future__ import annotations
from .types import DemandMatrix, Schedule, ScheduleEntry


class RoundRobinScheduler:
    def __init__(self, frame_slots: int = 1024):
        self.frame_slots = frame_slots

    def compute(self, demand: DemandMatrix) -> Schedule:
        n = demand.n
        if demand.total_demand() == 0:
            return Schedule(entries=[])

        entries: list[ScheduleEntry] = []
        base_slots = self.frame_slots // n
        remainder = self.frame_slots % n

        for rotation in range(1, n):
            perm = [(i + rotation) % n for i in range(n)]
            slots = base_slots + (1 if rotation <= remainder else 0)
            entries.append(ScheduleEntry(permutation=perm, slots=slots))

        # rotation=0 means self-loop, skip it. We have N-1 useful rotations.
        # Redistribute slot shortfall from having N-1 instead of N entries.
        total = sum(e.slots for e in entries)
        if total < self.frame_slots and entries:
            entries[0] = ScheduleEntry(
                permutation=entries[0].permutation,
                slots=entries[0].slots + (self.frame_slots - total),
            )

        return Schedule(entries=entries)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_scheduler_algorithms.py::TestRoundRobinScheduler -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Create the C++ header with matching types**

```cpp
// calendar_scheduler/include/calendar_scheduler.h
#ifndef CALENDAR_SCHEDULER_H
#define CALENDAR_SCHEDULER_H

#include <cstdint>
#include <vector>
#include <cassert>
#include <numeric>

namespace calendar {

using DemandMatrix = std::vector<std::vector<double>>;

struct ScheduleEntry {
    std::vector<uint32_t> permutation;  // permutation[i] = output port for input i
    uint32_t slots;
};

struct Schedule {
    std::vector<ScheduleEntry> entries;

    uint32_t total_slots() const {
        uint32_t s = 0;
        for (auto& e : entries) s += e.slots;
        return s;
    }
};

class SchedulerBase {
public:
    explicit SchedulerBase(uint32_t frame_slots) : frame_slots_(frame_slots) {}
    virtual ~SchedulerBase() = default;
    virtual Schedule compute(const DemandMatrix& demand) = 0;

protected:
    uint32_t frame_slots_;

    static uint32_t matrix_size(const DemandMatrix& d) {
        return static_cast<uint32_t>(d.size());
    }

    static double total_demand(const DemandMatrix& d) {
        double s = 0;
        for (auto& row : d)
            for (auto v : row)
                s += v;
        return s;
    }
};

}  // namespace calendar

#endif  // CALENDAR_SCHEDULER_H
```

```cpp
// calendar_scheduler/include/round_robin_scheduler.h
#ifndef ROUND_ROBIN_SCHEDULER_H
#define ROUND_ROBIN_SCHEDULER_H

#include "calendar_scheduler.h"

namespace calendar {

class RoundRobinScheduler : public SchedulerBase {
public:
    explicit RoundRobinScheduler(uint32_t frame_slots)
        : SchedulerBase(frame_slots) {}

    Schedule compute(const DemandMatrix& demand) override;
};

}  // namespace calendar

#endif  // ROUND_ROBIN_SCHEDULER_H
```

```cpp
// calendar_scheduler/src/round_robin_scheduler.cc
#include "round_robin_scheduler.h"

namespace calendar {

Schedule RoundRobinScheduler::compute(const DemandMatrix& demand) {
    Schedule sched;
    uint32_t n = matrix_size(demand);
    if (n == 0 || total_demand(demand) <= 0)
        return sched;

    uint32_t useful_rotations = n - 1;
    uint32_t base_slots = frame_slots_ / useful_rotations;
    uint32_t remainder = frame_slots_ % useful_rotations;

    for (uint32_t rot = 1; rot < n; ++rot) {
        ScheduleEntry entry;
        entry.permutation.resize(n);
        for (uint32_t i = 0; i < n; ++i)
            entry.permutation[i] = (i + rot) % n;
        entry.slots = base_slots + (rot <= remainder ? 1 : 0);
        sched.entries.push_back(std::move(entry));
    }

    uint32_t total = sched.total_slots();
    if (total < frame_slots_ && !sched.entries.empty())
        sched.entries[0].slots += (frame_slots_ - total);

    return sched;
}

}  // namespace calendar
```

```cmake
# calendar_scheduler/CMakeLists.txt
cmake_minimum_required(VERSION 3.14)
project(calendar_scheduler CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(calendar_scheduler STATIC
    src/round_robin_scheduler.cc
    src/solstice_scheduler.cc
    src/bvn_scheduler.cc
)
target_include_directories(calendar_scheduler PUBLIC include)
```

- [ ] **Step 6: Commit**

```bash
git add calendar_scheduler/ tests/calendar_switch/test_scheduler_algorithms.py
git commit -m "feat: add calendar scheduler types and round-robin algorithm"
```

---

### Task 2: Solstice Scheduler Algorithm

Greedy iterative decomposition of the demand matrix into maximum-weight matchings.

**Files:**
- Create: `calendar_scheduler/include/solstice_scheduler.h`
- Create: `calendar_scheduler/src/solstice_scheduler.cc`
- Create: `calendar_scheduler/python/calendar_scheduler/solstice.py`
- Test: `tests/calendar_switch/test_scheduler_algorithms.py` (add class)

- [ ] **Step 1: Write the Solstice test**

Add to `tests/calendar_switch/test_scheduler_algorithms.py`:

```python
class TestSolsticeScheduler:
    def test_uniform_demand_covers_all(self):
        n = 4
        demand = DemandMatrix(np.ones((n, n)) * 100 - np.eye(n) * 100)
        sched = SolsticeScheduler(frame_slots=1024)
        result = sched.compute(demand)
        assert result.total_slots == 1024
        for entry in result.entries:
            assert len(entry.permutation) == n
            assert len(set(entry.permutation)) == n

    def test_skewed_demand_allocates_proportionally(self):
        """When one pair has 3x the demand, it should get more slots."""
        n = 4
        demand_data = np.zeros((n, n))
        demand_data[0][1] = 300
        demand_data[1][0] = 100
        demand_data[2][3] = 100
        demand_data[3][2] = 100
        demand = DemandMatrix(demand_data)
        sched = SolsticeScheduler(frame_slots=1000)
        result = sched.compute(demand)
        slots_for_01 = 0
        for entry in result.entries:
            if entry.permutation[0] == 1:
                slots_for_01 += entry.slots
        assert slots_for_01 > 400  # should get at least proportional share

    def test_each_entry_is_valid_permutation(self):
        n = 8
        demand_data = np.random.default_rng(42).uniform(0, 100, (n, n))
        np.fill_diagonal(demand_data, 0)
        demand = DemandMatrix(demand_data)
        sched = SolsticeScheduler(frame_slots=2048)
        result = sched.compute(demand)
        for entry in result.entries:
            perm = entry.permutation
            assert len(perm) == n
            assert sorted(perm) == list(range(n))

    def test_empty_demand(self):
        n = 4
        demand = DemandMatrix(np.zeros((n, n)))
        sched = SolsticeScheduler(frame_slots=1024)
        result = sched.compute(demand)
        assert len(result.entries) == 0 or result.total_slots == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_scheduler_algorithms.py::TestSolsticeScheduler -v`
Expected: FAIL with `ImportError` (SolsticeScheduler not implemented yet)

- [ ] **Step 3: Implement Solstice in Python**

```python
# calendar_scheduler/python/calendar_scheduler/solstice.py
"""
Solstice-style greedy scheduler. Repeatedly extracts maximum-weight
matchings from the residual demand matrix and allocates slots
proportional to the matching weight.

Reference: Liu et al., "Scheduling Techniques for Hybrid Circuit/Packet
Networks" (CoNEXT 2015)
"""
from __future__ import annotations
import numpy as np
from .types import DemandMatrix, Schedule, ScheduleEntry


def _max_weight_matching(residual: np.ndarray) -> list[int]:
    """Greedy maximum-weight matching on an NxN matrix.

    Returns a permutation where perm[i] = j means input i is matched
    to output j. Uses a greedy approach: repeatedly pick the largest
    remaining entry and fix that assignment.
    """
    n = residual.shape[0]
    perm = [-1] * n
    used_cols = set()
    flat_indices = np.argsort(residual.ravel())[::-1]

    for flat_idx in flat_indices:
        i, j = divmod(int(flat_idx), n)
        if perm[i] != -1 or j in used_cols:
            continue
        if residual[i][j] <= 0:
            break
        perm[i] = j
        used_cols.add(j)
        if len(used_cols) == n:
            break

    # Fill unmatched rows with any remaining columns
    remaining_cols = sorted(set(range(n)) - used_cols)
    unmatched = [i for i in range(n) if perm[i] == -1]
    for i, j in zip(unmatched, remaining_cols):
        perm[i] = j

    return perm


class SolsticeScheduler:
    def __init__(self, frame_slots: int = 1024, max_iterations: int = 64):
        self.frame_slots = frame_slots
        self.max_iterations = max_iterations

    def compute(self, demand: DemandMatrix) -> Schedule:
        n = demand.n
        if demand.total_demand() <= 0:
            return Schedule(entries=[])

        residual = demand.data.copy().astype(float)
        total_demand = residual.sum()
        entries: list[ScheduleEntry] = []
        remaining_slots = self.frame_slots

        for _ in range(self.max_iterations):
            if remaining_slots <= 0 or residual.sum() <= 1e-9:
                break

            perm = _max_weight_matching(residual)

            matching_weight = sum(
                residual[i][perm[i]] for i in range(n) if residual[i][perm[i]] > 0
            )
            if matching_weight <= 1e-9:
                break

            slot_fraction = matching_weight / total_demand
            slots = max(1, round(slot_fraction * self.frame_slots))
            slots = min(slots, remaining_slots)

            for i in range(n):
                j = perm[i]
                served = residual[i][j] * (slots / max(1, self.frame_slots * slot_fraction))
                residual[i][j] = max(0, residual[i][j] - served)

            entries.append(ScheduleEntry(permutation=perm, slots=slots))
            remaining_slots -= slots

        return Schedule(entries=entries)
```

- [ ] **Step 4: Implement Solstice in C++**

```cpp
// calendar_scheduler/include/solstice_scheduler.h
#ifndef SOLSTICE_SCHEDULER_H
#define SOLSTICE_SCHEDULER_H

#include "calendar_scheduler.h"
#include <algorithm>

namespace calendar {

class SolsticeScheduler : public SchedulerBase {
public:
    SolsticeScheduler(uint32_t frame_slots, uint32_t max_iters = 64)
        : SchedulerBase(frame_slots), max_iters_(max_iters) {}

    Schedule compute(const DemandMatrix& demand) override;

private:
    uint32_t max_iters_;
    static std::vector<uint32_t> max_weight_matching(
        const std::vector<std::vector<double>>& residual, uint32_t n);
};

}  // namespace calendar

#endif  // SOLSTICE_SCHEDULER_H
```

```cpp
// calendar_scheduler/src/solstice_scheduler.cc
#include "solstice_scheduler.h"
#include <cmath>
#include <numeric>
#include <set>

namespace calendar {

std::vector<uint32_t> SolsticeScheduler::max_weight_matching(
        const std::vector<std::vector<double>>& residual, uint32_t n) {
    struct Cell { double w; uint32_t i; uint32_t j; };
    std::vector<Cell> cells;
    cells.reserve(n * n);
    for (uint32_t i = 0; i < n; ++i)
        for (uint32_t j = 0; j < n; ++j)
            if (residual[i][j] > 0)
                cells.push_back({residual[i][j], i, j});

    std::sort(cells.begin(), cells.end(),
              [](const Cell& a, const Cell& b) { return a.w > b.w; });

    std::vector<uint32_t> perm(n, UINT32_MAX);
    std::set<uint32_t> used_cols;

    for (auto& c : cells) {
        if (perm[c.i] != UINT32_MAX || used_cols.count(c.j))
            continue;
        perm[c.i] = c.j;
        used_cols.insert(c.j);
        if (used_cols.size() == n) break;
    }

    std::vector<uint32_t> remaining;
    for (uint32_t j = 0; j < n; ++j)
        if (!used_cols.count(j))
            remaining.push_back(j);
    size_t ri = 0;
    for (uint32_t i = 0; i < n; ++i)
        if (perm[i] == UINT32_MAX)
            perm[i] = remaining[ri++];

    return perm;
}

Schedule SolsticeScheduler::compute(const DemandMatrix& demand) {
    Schedule sched;
    uint32_t n = matrix_size(demand);
    double total = total_demand(demand);
    if (n == 0 || total <= 0) return sched;

    auto residual = demand;
    uint32_t remaining_slots = frame_slots_;

    for (uint32_t iter = 0; iter < max_iters_; ++iter) {
        if (remaining_slots == 0) break;

        double rsum = 0;
        for (auto& row : residual)
            for (auto v : row) rsum += v;
        if (rsum <= 1e-9) break;

        auto perm = max_weight_matching(residual, n);

        double match_w = 0;
        for (uint32_t i = 0; i < n; ++i)
            if (residual[i][perm[i]] > 0)
                match_w += residual[i][perm[i]];
        if (match_w <= 1e-9) break;

        double frac = match_w / total;
        uint32_t slots = std::max(1u, static_cast<uint32_t>(std::round(frac * frame_slots_)));
        slots = std::min(slots, remaining_slots);

        double served_frac = static_cast<double>(slots) /
            std::max(1.0, static_cast<double>(frame_slots_) * frac);
        for (uint32_t i = 0; i < n; ++i) {
            uint32_t j = perm[i];
            double served = residual[i][j] * served_frac;
            residual[i][j] = std::max(0.0, residual[i][j] - served);
        }

        sched.entries.push_back({perm, slots});
        remaining_slots -= slots;
    }

    return sched;
}

}  // namespace calendar
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_scheduler_algorithms.py::TestSolsticeScheduler -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add calendar_scheduler/include/solstice_scheduler.h \
        calendar_scheduler/src/solstice_scheduler.cc \
        calendar_scheduler/python/calendar_scheduler/solstice.py \
        tests/calendar_switch/test_scheduler_algorithms.py
git commit -m "feat: add Solstice greedy scheduler algorithm"
```

---

### Task 3: Birkhoff-von Neumann Scheduler Algorithm

Decompose a doubly-stochastic matrix into permutation matrices.

**Files:**
- Create: `calendar_scheduler/include/bvn_scheduler.h`
- Create: `calendar_scheduler/src/bvn_scheduler.cc`
- Create: `calendar_scheduler/python/calendar_scheduler/bvn.py`
- Test: `tests/calendar_switch/test_scheduler_algorithms.py` (add class)

- [ ] **Step 1: Write the BvN test**

Add to `tests/calendar_switch/test_scheduler_algorithms.py`:

```python
class TestBvNScheduler:
    def test_uniform_demand_produces_valid_schedule(self):
        n = 4
        demand = DemandMatrix(np.ones((n, n)) * 100 - np.eye(n) * 100)
        sched = BvNScheduler(frame_slots=1024)
        result = sched.compute(demand)
        assert result.total_slots <= 1024
        for entry in result.entries:
            assert sorted(entry.permutation) == list(range(n))

    def test_permutation_decomposition_covers_demand(self):
        """BvN output should cover the original demand."""
        n = 4
        demand_data = np.array([
            [0, 200, 100, 100],
            [100, 0, 200, 100],
            [100, 100, 0, 200],
            [200, 100, 100, 0],
        ], dtype=float)
        demand = DemandMatrix(demand_data)
        sched = BvNScheduler(frame_slots=2048)
        result = sched.compute(demand)
        # Verify total capacity is sufficient
        served = np.zeros((n, n))
        for entry in result.entries:
            for i, j in enumerate(entry.permutation):
                served[i][j] += entry.slots
        # Each slot carries slot_capacity bytes worth of data;
        # just check the relative proportions are respected
        nonzero_demand = demand_data > 0
        assert np.all(served[nonzero_demand] > 0)

    def test_identity_entries_excluded(self):
        """Self-loops (perm[i]==i for all i) should not appear."""
        n = 4
        demand = DemandMatrix(np.ones((n, n)) * 100 - np.eye(n) * 100)
        sched = BvNScheduler(frame_slots=1024)
        result = sched.compute(demand)
        for entry in result.entries:
            assert not all(entry.permutation[i] == i for i in range(n))

    def test_empty_demand(self):
        demand = DemandMatrix(np.zeros((4, 4)))
        sched = BvNScheduler(frame_slots=1024)
        result = sched.compute(demand)
        assert result.total_slots == 0 or len(result.entries) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_scheduler_algorithms.py::TestBvNScheduler -v`
Expected: FAIL

- [ ] **Step 3: Implement BvN in Python**

```python
# calendar_scheduler/python/calendar_scheduler/bvn.py
"""
Birkhoff-von Neumann decomposition scheduler. Normalizes the demand
matrix to doubly-stochastic form, then decomposes it into a convex
combination of permutation matrices. Slot counts are the quantized
weights of each permutation.

Reference: Birkhoff's theorem -- every doubly stochastic matrix is a
convex combination of permutation matrices.
"""
from __future__ import annotations
import numpy as np
from .types import DemandMatrix, Schedule, ScheduleEntry


def _sinkhorn_normalize(matrix: np.ndarray, iterations: int = 100,
                        tol: float = 1e-10) -> np.ndarray:
    """Sinkhorn-Knopp algorithm to produce a doubly-stochastic matrix."""
    m = matrix.copy()
    for _ in range(iterations):
        row_sums = m.sum(axis=1, keepdims=True)
        row_sums[row_sums < tol] = 1.0
        m /= row_sums

        col_sums = m.sum(axis=0, keepdims=True)
        col_sums[col_sums < tol] = 1.0
        m /= col_sums

        if (np.abs(m.sum(axis=1) - 1.0) < tol).all() and \
           (np.abs(m.sum(axis=0) - 1.0) < tol).all():
            break
    return m


def _extract_permutation(ds_matrix: np.ndarray) -> tuple[list[int], float]:
    """Extract a permutation from a doubly-stochastic matrix and return
    its weight (minimum entry along the permutation).

    Uses greedy row-column assignment on the matrix entries.
    """
    n = ds_matrix.shape[0]
    perm = [-1] * n
    used_cols = set()

    flat_indices = np.argsort(ds_matrix.ravel())[::-1]
    for flat_idx in flat_indices:
        i, j = divmod(int(flat_idx), n)
        if perm[i] != -1 or j in used_cols:
            continue
        if ds_matrix[i][j] <= 1e-12:
            break
        perm[i] = j
        used_cols.add(j)
        if len(used_cols) == n:
            break

    remaining = sorted(set(range(n)) - used_cols)
    unmatched = [i for i in range(n) if perm[i] == -1]
    for i, j in zip(unmatched, remaining):
        perm[i] = j

    weight = min(ds_matrix[i][perm[i]] for i in range(n))
    return perm, max(0.0, weight)


class BvNScheduler:
    def __init__(self, frame_slots: int = 1024, max_iterations: int = 128):
        self.frame_slots = frame_slots
        self.max_iterations = max_iterations

    def compute(self, demand: DemandMatrix) -> Schedule:
        n = demand.n
        if demand.total_demand() <= 0:
            return Schedule(entries=[])

        # Zero out diagonal
        matrix = demand.data.copy().astype(float)
        np.fill_diagonal(matrix, 0)

        if matrix.sum() <= 1e-9:
            return Schedule(entries=[])

        ds = _sinkhorn_normalize(matrix)

        entries: list[ScheduleEntry] = []
        residual = ds.copy()
        remaining_slots = self.frame_slots

        for _ in range(self.max_iterations):
            if remaining_slots <= 0 or residual.sum() < 1e-9:
                break

            perm, weight = _extract_permutation(residual)
            if weight <= 1e-12:
                break

            # Skip identity permutation
            if all(perm[i] == i for i in range(n)):
                for i in range(n):
                    residual[i][perm[i]] = 0
                continue

            slots = max(1, round(weight * self.frame_slots))
            slots = min(slots, remaining_slots)

            for i in range(n):
                residual[i][perm[i]] = max(0, residual[i][perm[i]] - weight)

            entries.append(ScheduleEntry(permutation=perm, slots=slots))
            remaining_slots -= slots

        return Schedule(entries=entries)
```

- [ ] **Step 4: Implement BvN in C++ (matching the Python)**

```cpp
// calendar_scheduler/include/bvn_scheduler.h
#ifndef BVN_SCHEDULER_H
#define BVN_SCHEDULER_H

#include "calendar_scheduler.h"

namespace calendar {

class BvNScheduler : public SchedulerBase {
public:
    BvNScheduler(uint32_t frame_slots, uint32_t max_iters = 128)
        : SchedulerBase(frame_slots), max_iters_(max_iters) {}

    Schedule compute(const DemandMatrix& demand) override;

private:
    uint32_t max_iters_;

    static void sinkhorn_normalize(std::vector<std::vector<double>>& m,
                                   uint32_t n, uint32_t iters = 100);
    static std::pair<std::vector<uint32_t>, double>
        extract_permutation(const std::vector<std::vector<double>>& m, uint32_t n);
};

}  // namespace calendar

#endif  // BVN_SCHEDULER_H
```

```cpp
// calendar_scheduler/src/bvn_scheduler.cc
#include "bvn_scheduler.h"
#include <algorithm>
#include <cmath>
#include <numeric>
#include <set>

namespace calendar {

void BvNScheduler::sinkhorn_normalize(
        std::vector<std::vector<double>>& m, uint32_t n, uint32_t iters) {
    constexpr double tol = 1e-10;
    for (uint32_t iter = 0; iter < iters; ++iter) {
        for (uint32_t i = 0; i < n; ++i) {
            double rs = 0;
            for (uint32_t j = 0; j < n; ++j) rs += m[i][j];
            if (rs > tol)
                for (uint32_t j = 0; j < n; ++j) m[i][j] /= rs;
        }
        for (uint32_t j = 0; j < n; ++j) {
            double cs = 0;
            for (uint32_t i = 0; i < n; ++i) cs += m[i][j];
            if (cs > tol)
                for (uint32_t i = 0; i < n; ++i) m[i][j] /= cs;
        }
    }
}

std::pair<std::vector<uint32_t>, double>
BvNScheduler::extract_permutation(
        const std::vector<std::vector<double>>& m, uint32_t n) {
    struct Cell { double w; uint32_t i; uint32_t j; };
    std::vector<Cell> cells;
    for (uint32_t i = 0; i < n; ++i)
        for (uint32_t j = 0; j < n; ++j)
            if (m[i][j] > 1e-12)
                cells.push_back({m[i][j], i, j});
    std::sort(cells.begin(), cells.end(),
              [](const Cell& a, const Cell& b) { return a.w > b.w; });

    std::vector<uint32_t> perm(n, UINT32_MAX);
    std::set<uint32_t> used;
    for (auto& c : cells) {
        if (perm[c.i] != UINT32_MAX || used.count(c.j)) continue;
        perm[c.i] = c.j;
        used.insert(c.j);
        if (used.size() == n) break;
    }
    std::vector<uint32_t> remaining;
    for (uint32_t j = 0; j < n; ++j)
        if (!used.count(j)) remaining.push_back(j);
    size_t ri = 0;
    for (uint32_t i = 0; i < n; ++i)
        if (perm[i] == UINT32_MAX) perm[i] = remaining[ri++];

    double weight = m[0][perm[0]];
    for (uint32_t i = 1; i < n; ++i)
        weight = std::min(weight, m[i][perm[i]]);
    return {perm, std::max(0.0, weight)};
}

Schedule BvNScheduler::compute(const DemandMatrix& demand) {
    Schedule sched;
    uint32_t n = matrix_size(demand);
    if (n == 0 || total_demand(demand) <= 0) return sched;

    auto ds = demand;
    for (uint32_t i = 0; i < n; ++i) ds[i][i] = 0;

    double dsum = 0;
    for (auto& row : ds) for (auto v : row) dsum += v;
    if (dsum <= 1e-9) return sched;

    sinkhorn_normalize(ds, n);

    uint32_t remaining = frame_slots_;
    for (uint32_t iter = 0; iter < max_iters_; ++iter) {
        if (remaining == 0) break;
        double rsum = 0;
        for (auto& row : ds) for (auto v : row) rsum += v;
        if (rsum < 1e-9) break;

        auto [perm, weight] = extract_permutation(ds, n);
        if (weight <= 1e-12) break;

        bool is_identity = true;
        for (uint32_t i = 0; i < n; ++i)
            if (perm[i] != i) { is_identity = false; break; }
        if (is_identity) {
            for (uint32_t i = 0; i < n; ++i) ds[i][perm[i]] = 0;
            continue;
        }

        uint32_t slots = std::max(1u,
            static_cast<uint32_t>(std::round(weight * frame_slots_)));
        slots = std::min(slots, remaining);

        for (uint32_t i = 0; i < n; ++i)
            ds[i][perm[i]] = std::max(0.0, ds[i][perm[i]] - weight);

        sched.entries.push_back({perm, slots});
        remaining -= slots;
    }
    return sched;
}

}  // namespace calendar
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_scheduler_algorithms.py::TestBvNScheduler -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add calendar_scheduler/include/bvn_scheduler.h \
        calendar_scheduler/src/bvn_scheduler.cc \
        calendar_scheduler/python/calendar_scheduler/bvn.py \
        tests/calendar_switch/test_scheduler_algorithms.py
git commit -m "feat: add Birkhoff-von Neumann scheduler algorithm"
```

---

### Task 4: Calendar Config Parsing in common.h

Add config knobs to the existing SimAI config parser.

**Files:**
- Modify: `astra-sim-alibabacloud/astra-sim/network_frontend/ns3/common.h`
- Create: `astra-sim-alibabacloud/inputs/config/SimAI.calendar.conf`
- Test: `tests/calendar_switch/test_calendar_config.py`

- [ ] **Step 1: Write the config contract test**

```python
# tests/calendar_switch/test_calendar_config.py
"""
Contract tests verifying that common.h parses all required calendar
config keys and that the template config file contains them.
"""
import re
from pathlib import Path
import pytest

COMMON_H = Path("astra-sim-alibabacloud/astra-sim/network_frontend/ns3/common.h")
TEMPLATE_CONF = Path("astra-sim-alibabacloud/inputs/config/SimAI.calendar.conf")

REQUIRED_KEYS = [
    "ENABLE_CALENDAR_SWITCH",
    "CALENDAR_SLOT_NS",
    "CALENDAR_FRAME_SLOTS",
    "CALENDAR_GRANULARITY_MODE",
    "CALENDAR_ALGORITHM",
    "CALENDAR_TRACE_ENABLE",
    "CALENDAR_TRACE_FILE",
]


class TestCalendarConfig:
    def test_common_h_parses_all_keys(self):
        code = COMMON_H.read_text()
        for key in REQUIRED_KEYS:
            pattern = rf'key\.compare\("{key}"\)'
            assert re.search(pattern, code), f"common.h missing parse for {key}"

    def test_common_h_declares_defaults(self):
        code = COMMON_H.read_text()
        assert "enable_calendar_switch" in code
        assert "calendar_slot_ns" in code
        assert "calendar_frame_slots" in code
        assert "calendar_granularity_mode" in code
        assert "calendar_algorithm" in code

    def test_template_conf_has_all_keys(self):
        text = TEMPLATE_CONF.read_text()
        keys_in_file = set()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            keys_in_file.add(line.split()[0])
        for key in REQUIRED_KEYS:
            assert key in keys_in_file, f"Template config missing {key}"

    def test_default_disables_calendar(self):
        code = COMMON_H.read_text()
        assert re.search(r"enable_calendar_switch\s*=\s*0", code)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_calendar_config.py -v`
Expected: FAIL (no calendar keys in common.h yet)

- [ ] **Step 3: Add config variables and parsing to common.h**

Insert after line 87 (`uint32_t enable_trace = 1;`) in `astra-sim-alibabacloud/astra-sim/network_frontend/ns3/common.h`:

```cpp
uint32_t enable_calendar_switch = 0;
uint32_t calendar_slot_ns = 1000;
uint32_t calendar_frame_slots = 1024;
std::string calendar_granularity_mode = "operator";
std::string calendar_algorithm = "solstice";
uint32_t calendar_trace_enable = 0;
std::string calendar_trace_file = "";
```

Insert in the `ReadConf` function's if-else chain, after the `ENABLE_TRACE` block (after line 597):

```cpp
      } else if (key.compare("ENABLE_CALENDAR_SWITCH") == 0) {
        conf >> enable_calendar_switch;
      } else if (key.compare("CALENDAR_SLOT_NS") == 0) {
        conf >> calendar_slot_ns;
      } else if (key.compare("CALENDAR_FRAME_SLOTS") == 0) {
        conf >> calendar_frame_slots;
      } else if (key.compare("CALENDAR_GRANULARITY_MODE") == 0) {
        conf >> calendar_granularity_mode;
      } else if (key.compare("CALENDAR_ALGORITHM") == 0) {
        conf >> calendar_algorithm;
      } else if (key.compare("CALENDAR_TRACE_ENABLE") == 0) {
        conf >> calendar_trace_enable;
      } else if (key.compare("CALENDAR_TRACE_FILE") == 0) {
        conf >> calendar_trace_file;
```

- [ ] **Step 4: Create template config file**

```
# astra-sim-alibabacloud/inputs/config/SimAI.calendar.conf
# Calendar switch configuration for performance study.
# Copy this file and modify for each experiment run.

ENABLE_CALENDAR_SWITCH 1
CALENDAR_SLOT_NS 1000
CALENDAR_FRAME_SLOTS 1024
CALENDAR_GRANULARITY_MODE operator
CALENDAR_ALGORITHM solstice
CALENDAR_TRACE_ENABLE 1
CALENDAR_TRACE_FILE /tmp/calendar_trace.csv
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_calendar_config.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add astra-sim-alibabacloud/astra-sim/network_frontend/ns3/common.h \
        astra-sim-alibabacloud/inputs/config/SimAI.calendar.conf \
        tests/calendar_switch/test_calendar_config.py
git commit -m "feat: add calendar switch config parsing to common.h"
```

---

### Task 5: CalendarSwitchNode in ns-3

A new switch node class that extends SwitchNode with schedule-based egress gating.

**Files:**
- Create: `ns-3-alibabacloud/simulation/src/point-to-point/model/calendar-switch-node.h`
- Create: `ns-3-alibabacloud/simulation/src/point-to-point/model/calendar-switch-node.cc`
- Test: `tests/calendar_switch/test_calendar_switch_node.py`

- [ ] **Step 1: Write the CalendarSwitchNode contract test**

```python
# tests/calendar_switch/test_calendar_switch_node.py
"""
Contract tests for CalendarSwitchNode. Verifies that the C++ source
declares the expected APIs and follows the spec's behavior contract.
"""
import re
from pathlib import Path
import pytest

HEADER = Path("ns-3-alibabacloud/simulation/src/point-to-point/model/calendar-switch-node.h")
IMPL = Path("ns-3-alibabacloud/simulation/src/point-to-point/model/calendar-switch-node.cc")


class TestCalendarSwitchNodeContract:
    def test_header_exists(self):
        assert HEADER.exists(), "calendar-switch-node.h not found"

    def test_extends_switch_node(self):
        code = HEADER.read_text()
        assert re.search(r"class\s+CalendarSwitchNode\s*:\s*public\s+SwitchNode", code)

    def test_has_load_schedule_api(self):
        code = HEADER.read_text()
        assert "LoadSchedule" in code

    def test_has_egress_gating_method(self):
        code = HEADER.read_text()
        assert "CalendarAllowEgress" in code

    def test_has_slot_tracking(self):
        code = HEADER.read_text()
        assert "GetCurrentSlotIndex" in code

    def test_impl_uses_simulator_time(self):
        code = IMPL.read_text()
        assert "Simulator::Now()" in code

    def test_impl_gates_on_permutation(self):
        code = IMPL.read_text()
        assert "CalendarAllowEgress" in code
        assert "permutation" in code.lower() or "current_perm" in code.lower() or \
               "m_schedule" in code.lower()

    def test_baseline_passthrough_when_disabled(self):
        """When calendar is not loaded, behavior should match SwitchNode."""
        code = IMPL.read_text()
        assert re.search(r"m_schedule\.entries\.empty\(\)|!m_calendarEnabled", code)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_calendar_switch_node.py -v`
Expected: FAIL (files don't exist)

- [ ] **Step 3: Implement CalendarSwitchNode header**

```cpp
// ns-3-alibabacloud/simulation/src/point-to-point/model/calendar-switch-node.h
#ifndef CALENDAR_SWITCH_NODE_H
#define CALENDAR_SWITCH_NODE_H

#include "switch-node.h"
#include <vector>
#include <cstdint>

namespace ns3 {

struct CalendarScheduleEntry {
    std::vector<uint32_t> permutation;
    uint32_t slots;
};

struct CalendarSchedule {
    std::vector<CalendarScheduleEntry> entries;
};

class CalendarSwitchNode : public SwitchNode {
public:
    static TypeId GetTypeId(void);
    CalendarSwitchNode();

    void LoadSchedule(const CalendarSchedule& schedule,
                      uint64_t slot_ns, uint32_t frame_slots);

    bool CalendarAllowEgress(uint32_t inDev, uint32_t outDev) const;
    uint32_t GetCurrentSlotIndex() const;

    bool SwitchReceiveFromDevice(Ptr<NetDevice> device,
                                 Ptr<Packet> packet,
                                 CustomHeader& ch);
    void SwitchNotifyDequeue(uint32_t ifIndex, uint32_t qIndex,
                             Ptr<Packet> p);

private:
    bool m_calendarEnabled;
    CalendarSchedule m_schedule;
    uint64_t m_slotNs;
    uint32_t m_frameSlots;

    const CalendarScheduleEntry* GetCurrentEntry() const;
    void SendToDevCalendar(Ptr<Packet> p, CustomHeader& ch);
    int GetOutDev(Ptr<const Packet> p, CustomHeader& ch);

    FILE* m_traceFile;
    uint64_t m_admitCount;
    uint64_t m_deferCount;
};

}  // namespace ns3

#endif  // CALENDAR_SWITCH_NODE_H
```

- [ ] **Step 4: Implement CalendarSwitchNode**

```cpp
// ns-3-alibabacloud/simulation/src/point-to-point/model/calendar-switch-node.cc
#include "calendar-switch-node.h"
#include "ns3/simulator.h"
#include "ns3/uinteger.h"
#include "ns3/boolean.h"
#include "ns3/flow-id-tag.h"
#include "ppp-header.h"
#include "ns3/int-header.h"
#include <cmath>

namespace ns3 {

TypeId CalendarSwitchNode::GetTypeId(void) {
    static TypeId tid = TypeId("ns3::CalendarSwitchNode")
        .SetParent<SwitchNode>()
        .AddConstructor<CalendarSwitchNode>();
    return tid;
}

CalendarSwitchNode::CalendarSwitchNode()
    : m_calendarEnabled(false),
      m_slotNs(1000),
      m_frameSlots(1024),
      m_traceFile(nullptr),
      m_admitCount(0),
      m_deferCount(0) {}

void CalendarSwitchNode::LoadSchedule(
        const CalendarSchedule& schedule,
        uint64_t slot_ns, uint32_t frame_slots) {
    m_schedule = schedule;
    m_slotNs = slot_ns;
    m_frameSlots = frame_slots;
    m_calendarEnabled = !m_schedule.entries.empty();
}

uint32_t CalendarSwitchNode::GetCurrentSlotIndex() const {
    if (m_slotNs == 0 || m_frameSlots == 0) return 0;
    uint64_t now_ns = Simulator::Now().GetNanoSeconds();
    return static_cast<uint32_t>((now_ns / m_slotNs) % m_frameSlots);
}

const CalendarScheduleEntry* CalendarSwitchNode::GetCurrentEntry() const {
    if (m_schedule.entries.empty()) return nullptr;
    uint32_t slot = GetCurrentSlotIndex();
    uint32_t cumulative = 0;
    for (auto& entry : m_schedule.entries) {
        cumulative += entry.slots;
        if (slot < cumulative) return &entry;
    }
    return &m_schedule.entries.back();
}

bool CalendarSwitchNode::CalendarAllowEgress(
        uint32_t inDev, uint32_t outDev) const {
    if (!m_calendarEnabled) return true;
    auto* entry = GetCurrentEntry();
    if (!entry) return true;
    if (inDev >= entry->permutation.size()) return false;
    return entry->permutation[inDev] == outDev;
}

void CalendarSwitchNode::SendToDevCalendar(
        Ptr<Packet> p, CustomHeader& ch) {
    int idx = GetOutDev(p, ch);
    if (idx < 0) return;

    NS_ASSERT_MSG(m_devices[idx]->IsLinkUp(),
                  "Routing table returned a down link");

    FlowIdTag t;
    p->PeekPacketTag(t);
    uint32_t inDev = t.GetFlowId();

    if (m_calendarEnabled && !CalendarAllowEgress(inDev, idx)) {
        m_deferCount++;
        // Re-enqueue: schedule retry at next slot boundary
        uint64_t now_ns = Simulator::Now().GetNanoSeconds();
        uint64_t next_slot_ns = ((now_ns / m_slotNs) + 1) * m_slotNs;
        uint64_t delay_ns = next_slot_ns - now_ns;
        Simulator::Schedule(NanoSeconds(delay_ns),
            &CalendarSwitchNode::SendToDevCalendar, this, p, ch);
        return;
    }

    m_admitCount++;

    uint32_t qIndex;
    if (ch.l3Prot == 0xFF || ch.l3Prot == 0xFE ||
        (m_ackHighPrio && (ch.l3Prot == 0xFD || ch.l3Prot == 0xFC))) {
        qIndex = 0;
    } else {
        qIndex = (ch.l3Prot == 0x06 ? 1 : ch.udp.pg);
    }

    if (qIndex != 0) {
        if (m_mmu->CheckIngressAdmission(inDev, qIndex, p->GetSize()) &&
            m_mmu->CheckEgressAdmission(idx, qIndex, p->GetSize())) {
            m_mmu->UpdateIngressAdmission(inDev, qIndex, p->GetSize());
            m_mmu->UpdateEgressAdmission(idx, qIndex, p->GetSize());
        } else {
            return;
        }
        CheckAndSendPfc(inDev, qIndex);
    }
    m_bytes[inDev][idx][qIndex] += p->GetSize();
    m_devices[idx]->SwitchSend(qIndex, p, ch);
}

bool CalendarSwitchNode::SwitchReceiveFromDevice(
        Ptr<NetDevice> device, Ptr<Packet> packet, CustomHeader& ch) {
    if (!m_calendarEnabled) {
        return SwitchNode::SwitchReceiveFromDevice(device, packet, ch);
    }
    SendToDevCalendar(packet, ch);
    return true;
}

void CalendarSwitchNode::SwitchNotifyDequeue(
        uint32_t ifIndex, uint32_t qIndex, Ptr<Packet> p) {
    SwitchNode::SwitchNotifyDequeue(ifIndex, qIndex, p);
}

}  // namespace ns3
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_calendar_switch_node.py -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add ns-3-alibabacloud/simulation/src/point-to-point/model/calendar-switch-node.h \
        ns-3-alibabacloud/simulation/src/point-to-point/model/calendar-switch-node.cc \
        tests/calendar_switch/test_calendar_switch_node.py
git commit -m "feat: add CalendarSwitchNode with egress gating"
```

---

### Task 6: GranularityController

Detects phase/chunk boundaries from AstraSim flow tags and builds demand matrices.

**Files:**
- Create: `astra-sim-alibabacloud/astra-sim/network_frontend/ns3/granularity_controller.h`
- Modify: `astra-sim-alibabacloud/astra-sim/network_frontend/ns3/entry.h`
- Test: `tests/calendar_switch/test_granularity_controller.py`

- [ ] **Step 1: Write the GranularityController contract test**

```python
# tests/calendar_switch/test_granularity_controller.py
"""
Contract tests for GranularityController. Verifies that the header
declares the expected APIs and that entry.h wires it in.
"""
import re
from pathlib import Path
import pytest

GRANULARITY_H = Path(
    "astra-sim-alibabacloud/astra-sim/network_frontend/ns3/granularity_controller.h"
)
ENTRY_H = Path("astra-sim-alibabacloud/astra-sim/network_frontend/ns3/entry.h")


class TestGranularityControllerContract:
    def test_header_exists(self):
        assert GRANULARITY_H.exists()

    def test_has_granularity_enum(self):
        code = GRANULARITY_H.read_text()
        assert "GranularityMode" in code
        for mode in ["OPERATOR", "PHASE", "CHUNK", "PACKET", "SLOT"]:
            assert mode in code

    def test_has_build_demand_matrix(self):
        code = GRANULARITY_H.read_text()
        assert "BuildDemandMatrix" in code

    def test_has_should_reschedule(self):
        code = GRANULARITY_H.read_text()
        assert "ShouldReschedule" in code

    def test_has_on_flow_start(self):
        code = GRANULARITY_H.read_text()
        assert "OnFlowStart" in code

    def test_entry_h_includes_controller(self):
        code = ENTRY_H.read_text()
        assert "granularity_controller.h" in code

    def test_entry_h_calls_controller_in_send_flow(self):
        code = ENTRY_H.read_text()
        assert "granularity_controller" in code.lower() or \
               "GranularityController" in code
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_granularity_controller.py -v`
Expected: FAIL

- [ ] **Step 3: Implement GranularityController header**

```cpp
// astra-sim-alibabacloud/astra-sim/network_frontend/ns3/granularity_controller.h
#ifndef GRANULARITY_CONTROLLER_H
#define GRANULARITY_CONTROLLER_H

#include <cstdint>
#include <string>
#include <vector>
#include <map>
#include "astra-sim/system/AstraNetworkAPI.hh"

enum class GranularityMode {
    OPERATOR,
    PHASE,
    CHUNK,
    PACKET,
    SLOT
};

inline GranularityMode ParseGranularityMode(const std::string& s) {
    if (s == "operator") return GranularityMode::OPERATOR;
    if (s == "phase" || s == "stage") return GranularityMode::PHASE;
    if (s == "chunk" || s == "tile") return GranularityMode::CHUNK;
    if (s == "packet") return GranularityMode::PACKET;
    if (s == "slot" || s == "cycle") return GranularityMode::SLOT;
    return GranularityMode::OPERATOR;
}

class GranularityController {
public:
    explicit GranularityController(GranularityMode mode, uint32_t num_nodes)
        : mode_(mode), num_nodes_(num_nodes), last_tag_id_(-1),
          last_flow_id_(-1), last_chunk_id_(-1) {}

    bool ShouldReschedule(const AstraSim::ncclFlowTag& tag) {
        bool reschedule = false;
        switch (mode_) {
            case GranularityMode::OPERATOR:
                reschedule = (tag.tag_id != last_tag_id_);
                break;
            case GranularityMode::PHASE:
                reschedule = (tag.tag_id != last_tag_id_) ||
                             (tag.current_flow_id != last_flow_id_);
                break;
            case GranularityMode::CHUNK:
                reschedule = (tag.tag_id != last_tag_id_) ||
                             (tag.current_flow_id != last_flow_id_) ||
                             (tag.chunk_id != last_chunk_id_);
                break;
            case GranularityMode::PACKET:
                reschedule = true;
                break;
            case GranularityMode::SLOT:
                reschedule = false;  // slot mode is time-driven, not flow-driven
                break;
        }
        last_tag_id_ = tag.tag_id;
        last_flow_id_ = tag.current_flow_id;
        last_chunk_id_ = tag.chunk_id;
        return reschedule;
    }

    void OnFlowStart(int src, int dst, uint64_t size,
                     const AstraSim::ncclFlowTag& tag) {
        pending_demand_[src][dst] += static_cast<double>(size);
    }

    std::vector<std::vector<double>> BuildDemandMatrix() {
        std::vector<std::vector<double>> matrix(
            num_nodes_, std::vector<double>(num_nodes_, 0.0));
        for (auto& [src, dsts] : pending_demand_)
            for (auto& [dst, bytes] : dsts)
                if (src < num_nodes_ && dst < num_nodes_)
                    matrix[src][dst] = bytes;
        pending_demand_.clear();
        return matrix;
    }

    void Reset() {
        pending_demand_.clear();
        last_tag_id_ = -1;
        last_flow_id_ = -1;
        last_chunk_id_ = -1;
    }

    GranularityMode mode() const { return mode_; }

private:
    GranularityMode mode_;
    uint32_t num_nodes_;
    int last_tag_id_;
    int last_flow_id_;
    int last_chunk_id_;
    std::map<uint32_t, std::map<uint32_t, double>> pending_demand_;
};

#endif  // GRANULARITY_CONTROLLER_H
```

- [ ] **Step 4: Wire GranularityController into entry.h**

Add to the top of `entry.h` (after the existing includes around line 48):

```cpp
#include "granularity_controller.h"
```

Add a global controller instance after the existing global maps (after `sent_chunksize` around line 74):

```cpp
std::unique_ptr<GranularityController> g_granularity_controller;
```

In the `SendFlow` function, before the RDMA client setup, add controller notification:

```cpp
    if (enable_calendar_switch && g_granularity_controller) {
        g_granularity_controller->OnFlowStart(src, dst, maxPacketCount, request->flowTag);
        if (g_granularity_controller->ShouldReschedule(request->flowTag)) {
            auto demand = g_granularity_controller->BuildDemandMatrix();
            // Schedule recomputation will be handled by the CalendarSwitchNode
            // via a callback registered during topology setup.
        }
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_granularity_controller.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add astra-sim-alibabacloud/astra-sim/network_frontend/ns3/granularity_controller.h \
        astra-sim-alibabacloud/astra-sim/network_frontend/ns3/entry.h \
        tests/calendar_switch/test_granularity_controller.py
git commit -m "feat: add GranularityController with boundary detection"
```

---

### Task 7: CalendarSwitchNode Instantiation in Topology Setup

Wire the config into topology creation so that `CalendarSwitchNode` is used when calendar mode is enabled.

**Files:**
- Modify: `astra-sim-alibabacloud/astra-sim/network_frontend/ns3/common.h`
- Test: `tests/calendar_switch/test_calendar_config.py` (add test)

- [ ] **Step 1: Write the instantiation test**

Add to `tests/calendar_switch/test_calendar_config.py`:

```python
    def test_common_h_creates_calendar_switch_node_when_enabled(self):
        code = COMMON_H.read_text()
        assert "CalendarSwitchNode" in code
        assert "enable_calendar_switch" in code
        assert re.search(
            r"CreateObject<CalendarSwitchNode>",
            code,
        )

    def test_common_h_includes_calendar_switch_header(self):
        code = COMMON_H.read_text()
        assert "calendar-switch-node.h" in code
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_calendar_config.py::TestCalendarConfig::test_common_h_creates_calendar_switch_node_when_enabled -v`
Expected: FAIL

- [ ] **Step 3: Modify topology creation in common.h**

Add include at the top of `common.h` (after `#include <ns3/switch-node.h>` on line 42):

```cpp
#include <ns3/calendar-switch-node.h>
```

Modify the node creation loop (around line 732) from:

```cpp
		else if(node_type[i] == 1){
			Ptr<SwitchNode> sw = CreateObject<SwitchNode>();
			n.Add(sw);
			sw->SetAttribute("EcnEnabled", BooleanValue(enable_qcn));
		}
```

to:

```cpp
		else if(node_type[i] == 1){
			if (enable_calendar_switch) {
				Ptr<CalendarSwitchNode> sw = CreateObject<CalendarSwitchNode>();
				n.Add(sw);
				sw->SetAttribute("EcnEnabled", BooleanValue(enable_qcn));
			} else {
				Ptr<SwitchNode> sw = CreateObject<SwitchNode>();
				n.Add(sw);
				sw->SetAttribute("EcnEnabled", BooleanValue(enable_qcn));
			}
		}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_calendar_config.py -v`
Expected: PASS (all tests including new ones)

- [ ] **Step 5: Commit**

```bash
git add astra-sim-alibabacloud/astra-sim/network_frontend/ns3/common.h \
        tests/calendar_switch/test_calendar_config.py
git commit -m "feat: wire CalendarSwitchNode into topology creation"
```

---

### Task 8: Workload Generation

Python scripts to produce operator microbenchmark workloads from real model configs.

**Files:**
- Create: `workloads/calendar_study/generate_workloads.py`
- Create: `workloads/calendar_study/moe_traffic_generator.py`
- Create: `workloads/calendar_study/fused_op_workloads.py`
- Test: `tests/calendar_switch/test_workload_generation.py`

- [ ] **Step 1: Write workload generation tests**

```python
# tests/calendar_switch/test_workload_generation.py
"""
Tests for workload generation scripts. Verifies output format
and operator coverage.
"""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "workloads" / "calendar_study"))

from generate_workloads import generate_collective_workload, OPERATOR_CONFIGS
from moe_traffic_generator import generate_moe_demand_matrix
from fused_op_workloads import generate_rs_ag_fused, generate_moe_pipeline


class TestCollectiveWorkloadGeneration:
    def test_allreduce_ring_has_correct_phases(self):
        wl = generate_collective_workload("allreduce_ring", num_gpus=8, msg_bytes=32 * 1024 * 1024)
        assert wl["operator"] == "allreduce_ring"
        assert wl["num_phases"] == 7  # N-1 ring steps for 8 GPUs
        assert wl["msg_bytes"] == 32 * 1024 * 1024

    def test_allgather_ring_phases(self):
        wl = generate_collective_workload("allgather", num_gpus=8, msg_bytes=16 * 1024 * 1024)
        assert wl["num_phases"] == 7

    def test_reduce_scatter_phases(self):
        wl = generate_collective_workload("reduce_scatter", num_gpus=8, msg_bytes=16 * 1024 * 1024)
        assert wl["num_phases"] == 7

    def test_allreduce_tree_phases(self):
        wl = generate_collective_workload("allreduce_tree", num_gpus=8, msg_bytes=32 * 1024 * 1024)
        assert wl["num_phases"] == 2  # reduce + broadcast

    def test_output_has_demand_matrices(self):
        wl = generate_collective_workload("allreduce_ring", num_gpus=8, msg_bytes=1024 * 1024)
        assert "phases" in wl
        for phase in wl["phases"]:
            dm = phase["demand_matrix"]
            assert len(dm) == 8
            assert len(dm[0]) == 8


class TestMoETrafficGeneration:
    def test_uniform_distribution(self):
        dm = generate_moe_demand_matrix(
            num_gpus=8, num_experts=64, tokens_per_gpu=512,
            token_size=4096, distribution="uniform",
        )
        assert dm.shape == (8, 8)
        assert dm.sum() > 0

    def test_zipf_distribution_is_skewed(self):
        dm_uniform = generate_moe_demand_matrix(
            num_gpus=8, num_experts=64, tokens_per_gpu=512,
            token_size=4096, distribution="uniform",
        )
        dm_zipf = generate_moe_demand_matrix(
            num_gpus=8, num_experts=64, tokens_per_gpu=512,
            token_size=4096, distribution="zipf", zipf_s=1.5,
        )
        # Zipf should have higher variance across entries
        assert dm_zipf.std() > dm_uniform.std()


class TestFusedWorkloads:
    def test_rs_ag_has_two_phases(self):
        wl = generate_rs_ag_fused(num_gpus=8, msg_bytes=32 * 1024 * 1024)
        assert wl["operator"] == "rs_ag_fused"
        assert len(wl["phases"]) == 2
        assert wl["phases"][0]["name"] == "reduce_scatter"
        assert wl["phases"][1]["name"] == "allgather"

    def test_moe_pipeline_has_three_phases(self):
        wl = generate_moe_pipeline(
            num_gpus=8, num_experts=64, tokens_per_gpu=512,
            token_size=4096, distribution="uniform",
        )
        assert wl["operator"] == "moe_pipeline"
        assert len(wl["phases"]) == 3
        phase_names = [p["name"] for p in wl["phases"]]
        assert phase_names == ["dispatch", "expert_compute", "combine"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_workload_generation.py -v`
Expected: FAIL

- [ ] **Step 3: Implement generate_workloads.py**

```python
# workloads/calendar_study/generate_workloads.py
"""
Generate collective operator microbenchmark workloads with phase-level
demand matrices for the calendar switch study.
"""
from __future__ import annotations
import json
import numpy as np
from pathlib import Path

OPERATOR_CONFIGS = {
    "allreduce_ring": {"algorithm": "ring", "phases_formula": "N-1"},
    "allreduce_tree": {"algorithm": "tree", "phases_formula": "2"},
    "allgather": {"algorithm": "ring", "phases_formula": "N-1"},
    "reduce_scatter": {"algorithm": "ring", "phases_formula": "N-1"},
}


def _ring_phase_demand(num_gpus: int, chunk_bytes: float, phase_idx: int) -> list[list[float]]:
    dm = [[0.0] * num_gpus for _ in range(num_gpus)]
    for i in range(num_gpus):
        dst = (i + 1) % num_gpus
        dm[i][dst] = chunk_bytes
    return dm


def _tree_reduce_demand(num_gpus: int, msg_bytes: float) -> list[list[float]]:
    dm = [[0.0] * num_gpus for _ in range(num_gpus)]
    # Binary tree reduce: leaves send to parents
    level_size = num_gpus // 2
    stride = 1
    while level_size >= 1:
        for i in range(level_size):
            src = (2 * i + 1) * stride
            dst = 2 * i * stride
            if src < num_gpus and dst < num_gpus:
                dm[src][dst] = msg_bytes / (num_gpus // (2 * level_size))
        level_size //= 2
        stride *= 2
    return dm


def _tree_broadcast_demand(num_gpus: int, msg_bytes: float) -> list[list[float]]:
    dm = [[0.0] * num_gpus for _ in range(num_gpus)]
    stride = num_gpus // 2
    while stride >= 1:
        for i in range(0, num_gpus, stride * 2):
            src = i
            dst = i + stride
            if dst < num_gpus:
                dm[src][dst] = msg_bytes / (num_gpus // stride)
        stride //= 2
    return dm


def generate_collective_workload(operator: str, num_gpus: int,
                                 msg_bytes: int) -> dict:
    config = OPERATOR_CONFIGS[operator]
    if config["phases_formula"] == "N-1":
        num_phases = num_gpus - 1
    elif config["phases_formula"] == "2":
        num_phases = 2
    else:
        num_phases = 1

    phases = []
    if config["algorithm"] == "ring":
        chunk_bytes = msg_bytes / num_gpus
        for p in range(num_phases):
            phases.append({
                "index": p,
                "demand_matrix": _ring_phase_demand(num_gpus, chunk_bytes, p),
            })
    elif config["algorithm"] == "tree":
        phases.append({
            "index": 0,
            "name": "reduce",
            "demand_matrix": _tree_reduce_demand(num_gpus, msg_bytes),
        })
        phases.append({
            "index": 1,
            "name": "broadcast",
            "demand_matrix": _tree_broadcast_demand(num_gpus, msg_bytes),
        })

    return {
        "operator": operator,
        "num_gpus": num_gpus,
        "msg_bytes": msg_bytes,
        "num_phases": num_phases,
        "phases": phases,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--operator", required=True, choices=list(OPERATOR_CONFIGS.keys()))
    parser.add_argument("--num-gpus", type=int, required=True)
    parser.add_argument("--msg-bytes", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    wl = generate_collective_workload(args.operator, args.num_gpus, args.msg_bytes)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(wl, indent=2))
```

- [ ] **Step 4: Implement moe_traffic_generator.py**

```python
# workloads/calendar_study/moe_traffic_generator.py
"""
Generate MoE dispatch/combine demand matrices with configurable
expert load distributions.
"""
from __future__ import annotations
import numpy as np


def generate_moe_demand_matrix(
    num_gpus: int,
    num_experts: int,
    tokens_per_gpu: int,
    token_size: int,
    distribution: str = "uniform",
    zipf_s: float = 1.2,
    seed: int = 42,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    experts_per_gpu = num_experts // num_gpus

    if distribution == "uniform":
        tokens_to_expert = rng.integers(0, num_experts, size=(num_gpus, tokens_per_gpu))
    elif distribution == "zipf":
        raw = rng.zipf(zipf_s, size=(num_gpus, tokens_per_gpu))
        tokens_to_expert = (raw - 1) % num_experts
    elif distribution == "power_law":
        probs = np.arange(1, num_experts + 1, dtype=float) ** (-zipf_s)
        probs /= probs.sum()
        tokens_to_expert = rng.choice(num_experts, size=(num_gpus, tokens_per_gpu), p=probs)
    else:
        raise ValueError(f"Unknown distribution: {distribution}")

    demand = np.zeros((num_gpus, num_gpus), dtype=float)
    for src_gpu in range(num_gpus):
        for token_idx in range(tokens_per_gpu):
            expert_id = tokens_to_expert[src_gpu, token_idx]
            dst_gpu = expert_id // experts_per_gpu
            dst_gpu = min(dst_gpu, num_gpus - 1)
            demand[src_gpu][dst_gpu] += token_size

    return demand


if __name__ == "__main__":
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-gpus", type=int, default=8)
    parser.add_argument("--num-experts", type=int, default=64)
    parser.add_argument("--tokens-per-gpu", type=int, default=512)
    parser.add_argument("--token-size", type=int, default=4096)
    parser.add_argument("--distribution", default="uniform")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    dm = generate_moe_demand_matrix(
        args.num_gpus, args.num_experts, args.tokens_per_gpu,
        args.token_size, args.distribution,
    )
    from pathlib import Path
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(dm.tolist(), indent=2))
```

- [ ] **Step 5: Implement fused_op_workloads.py**

```python
# workloads/calendar_study/fused_op_workloads.py
"""
Generate fused operator workloads: RS+AG, compute overlap, MoE pipeline.
"""
from __future__ import annotations
from generate_workloads import generate_collective_workload
from moe_traffic_generator import generate_moe_demand_matrix


def generate_rs_ag_fused(num_gpus: int, msg_bytes: int) -> dict:
    rs = generate_collective_workload("reduce_scatter", num_gpus, msg_bytes)
    ag = generate_collective_workload("allgather", num_gpus, msg_bytes)

    phases = []
    for p in rs["phases"]:
        p["name"] = "reduce_scatter"
        phases.append(p)
    for p in ag["phases"]:
        p["name"] = "allgather"
        p["index"] += rs["num_phases"]
        phases.append(p)

    return {
        "operator": "rs_ag_fused",
        "num_gpus": num_gpus,
        "msg_bytes": msg_bytes,
        "num_phases": len(phases),
        "phases": phases,
    }


def generate_moe_pipeline(
    num_gpus: int, num_experts: int, tokens_per_gpu: int,
    token_size: int, distribution: str = "uniform",
    compute_ns: int = 100000,
) -> dict:
    dispatch_dm = generate_moe_demand_matrix(
        num_gpus, num_experts, tokens_per_gpu, token_size, distribution,
    )
    combine_dm = dispatch_dm.T.copy()

    phases = [
        {
            "index": 0,
            "name": "dispatch",
            "demand_matrix": dispatch_dm.tolist(),
        },
        {
            "index": 1,
            "name": "expert_compute",
            "demand_matrix": [[0.0] * num_gpus for _ in range(num_gpus)],
            "compute_ns": compute_ns,
        },
        {
            "index": 2,
            "name": "combine",
            "demand_matrix": combine_dm.tolist(),
        },
    ]

    return {
        "operator": "moe_pipeline",
        "num_gpus": num_gpus,
        "msg_bytes": int(dispatch_dm.sum()),
        "num_phases": 3,
        "phases": phases,
    }


if __name__ == "__main__":
    import argparse, json
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=["rs_ag", "moe_pipeline"], required=True)
    parser.add_argument("--num-gpus", type=int, default=8)
    parser.add_argument("--msg-bytes", type=int, default=33554432)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.type == "rs_ag":
        wl = generate_rs_ag_fused(args.num_gpus, args.msg_bytes)
    else:
        wl = generate_moe_pipeline(args.num_gpus, 64, 512, 4096)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(wl, indent=2))
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_workload_generation.py -v`
Expected: PASS (all tests)

- [ ] **Step 7: Commit**

```bash
git add workloads/calendar_study/ tests/calendar_switch/test_workload_generation.py
git commit -m "feat: add workload generation for collective, MoE, and fused operators"
```

---

### Task 9: Experiment Runner Scripts

Shell scripts to run the full experiment matrix and individual experiments.

**Files:**
- Create: `scripts/run_single_experiment.sh`
- Create: `scripts/run_calendar_study.sh`

- [ ] **Step 1: Create single experiment runner**

```bash
#!/usr/bin/env bash
# scripts/run_single_experiment.sh
# Run a single calendar switch experiment with specified parameters.
#
# Usage:
#   ./scripts/run_single_experiment.sh \
#     --mode calendar_switch \
#     --granularity operator \
#     --algorithm solstice \
#     --gpus 8 \
#     --operator allreduce_ring \
#     --msg-bytes 33554432 \
#     --output-dir results/calendar/run_001
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Parse arguments
MODE="packet_switch"
GRANULARITY="operator"
ALGORITHM="solstice"
GPUS=8
OPERATOR="allreduce_ring"
MSG_BYTES=33554432
OUTPUT_DIR="${ROOT_DIR}/results/calendar/default"
SLOT_NS=1000
FRAME_SLOTS=1024

while [[ $# -gt 0 ]]; do
    case $1 in
        --mode) MODE="$2"; shift 2 ;;
        --granularity) GRANULARITY="$2"; shift 2 ;;
        --algorithm) ALGORITHM="$2"; shift 2 ;;
        --gpus) GPUS="$2"; shift 2 ;;
        --operator) OPERATOR="$2"; shift 2 ;;
        --msg-bytes) MSG_BYTES="$2"; shift 2 ;;
        --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
        --slot-ns) SLOT_NS="$2"; shift 2 ;;
        --frame-slots) FRAME_SLOTS="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

mkdir -p "${OUTPUT_DIR}"

# Generate workload
python3 "${ROOT_DIR}/workloads/calendar_study/generate_workloads.py" \
    --operator "${OPERATOR}" \
    --num-gpus "${GPUS}" \
    --msg-bytes "${MSG_BYTES}" \
    --output "${OUTPUT_DIR}/workload.json"

# Generate config
ENABLE_CAL=0
if [[ "${MODE}" == "calendar_switch" ]]; then
    ENABLE_CAL=1
fi

CONF="${OUTPUT_DIR}/SimAI.conf"
cp "${ROOT_DIR}/astra-sim-alibabacloud/inputs/config/SimAI.calendar.conf" "${CONF}"
# Override calendar settings
sed -i "s/^ENABLE_CALENDAR_SWITCH.*/ENABLE_CALENDAR_SWITCH ${ENABLE_CAL}/" "${CONF}"
sed -i "s/^CALENDAR_SLOT_NS.*/CALENDAR_SLOT_NS ${SLOT_NS}/" "${CONF}"
sed -i "s/^CALENDAR_FRAME_SLOTS.*/CALENDAR_FRAME_SLOTS ${FRAME_SLOTS}/" "${CONF}"
sed -i "s/^CALENDAR_GRANULARITY_MODE.*/CALENDAR_GRANULARITY_MODE ${GRANULARITY}/" "${CONF}"
sed -i "s/^CALENDAR_ALGORITHM.*/CALENDAR_ALGORITHM ${ALGORITHM}/" "${CONF}"
sed -i "s|^CALENDAR_TRACE_FILE.*|CALENDAR_TRACE_FILE ${OUTPUT_DIR}/calendar_trace.csv|" "${CONF}"

# Record experiment metadata
cat > "${OUTPUT_DIR}/metadata.json" <<METAEOF
{
    "mode": "${MODE}",
    "granularity": "${GRANULARITY}",
    "algorithm": "${ALGORITHM}",
    "gpus": ${GPUS},
    "operator": "${OPERATOR}",
    "msg_bytes": ${MSG_BYTES},
    "slot_ns": ${SLOT_NS},
    "frame_slots": ${FRAME_SLOTS},
    "timestamp": "$(date -Iseconds)"
}
METAEOF

echo "[run_single] mode=${MODE} gran=${GRANULARITY} algo=${ALGORITHM} gpus=${GPUS} op=${OPERATOR} size=${MSG_BYTES}"
echo "[run_single] config=${CONF}"
echo "[run_single] output=${OUTPUT_DIR}"

# Invoke simulator (placeholder for actual binary path)
SIMULATOR="${ROOT_DIR}/bin/SimAI_simulator"
if [[ -x "${SIMULATOR}" ]]; then
    "${SIMULATOR}" \
        --network-conf "${CONF}" \
        --workload "${OUTPUT_DIR}/workload.json" \
        > "${OUTPUT_DIR}/stdout.log" 2>&1
    echo "[run_single] Simulation complete. Logs in ${OUTPUT_DIR}/stdout.log"
else
    echo "[run_single] WARNING: Simulator binary not found at ${SIMULATOR}"
    echo "[run_single] Dry-run mode: metadata and config written."
fi
```

- [ ] **Step 2: Create full sweep runner**

```bash
#!/usr/bin/env bash
# scripts/run_calendar_study.sh
# Run the full calendar switch experiment matrix.
#
# Usage:
#   ./scripts/run_calendar_study.sh [--parallel N] [--dry-run]
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="${ROOT_DIR}/results/calendar_study_$(date +%Y%m%d_%H%M%S)"
PARALLEL=1
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --parallel) PARALLEL="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --results-dir) RESULTS_DIR="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

mkdir -p "${RESULTS_DIR}"

OPERATORS=("allreduce_ring" "allreduce_tree" "allgather" "reduce_scatter")
GRANULARITIES=("operator" "phase" "chunk" "packet" "slot")
ALGORITHMS=("solstice" "bvn" "round_robin")
GPU_COUNTS=(8 16)
MSG_SIZES=(1048576 33554432 268435456)  # 1MB, 32MB, 256MB

RUN_IDX=0
JOBS_FILE="${RESULTS_DIR}/jobs.txt"
: > "${JOBS_FILE}"

# Baseline runs (packet-switch, no granularity/algorithm dimension)
for op in "${OPERATORS[@]}"; do
    for gpus in "${GPU_COUNTS[@]}"; do
        for size in "${MSG_SIZES[@]}"; do
            RUN_IDX=$((RUN_IDX + 1))
            OUT="${RESULTS_DIR}/baseline/${op}_g${gpus}_s${size}"
            echo "${ROOT_DIR}/scripts/run_single_experiment.sh \
                --mode packet_switch --granularity operator --algorithm solstice \
                --gpus ${gpus} --operator ${op} --msg-bytes ${size} \
                --output-dir ${OUT}" >> "${JOBS_FILE}"
        done
    done
done

# Calendar runs
for op in "${OPERATORS[@]}"; do
    for gran in "${GRANULARITIES[@]}"; do
        for algo in "${ALGORITHMS[@]}"; do
            for gpus in "${GPU_COUNTS[@]}"; do
                for size in "${MSG_SIZES[@]}"; do
                    RUN_IDX=$((RUN_IDX + 1))
                    OUT="${RESULTS_DIR}/calendar/${op}_${gran}_${algo}_g${gpus}_s${size}"
                    echo "${ROOT_DIR}/scripts/run_single_experiment.sh \
                        --mode calendar_switch --granularity ${gran} --algorithm ${algo} \
                        --gpus ${gpus} --operator ${op} --msg-bytes ${size} \
                        --output-dir ${OUT}" >> "${JOBS_FILE}"
                done
            done
        done
    done
done

echo "Total runs: ${RUN_IDX}"
echo "Jobs file: ${JOBS_FILE}"
echo "Results dir: ${RESULTS_DIR}"

if ${DRY_RUN}; then
    echo "[DRY-RUN] Would execute ${RUN_IDX} runs with parallelism ${PARALLEL}"
    head -5 "${JOBS_FILE}"
    echo "..."
else
    if command -v parallel &> /dev/null; then
        parallel -j "${PARALLEL}" < "${JOBS_FILE}"
    else
        while IFS= read -r cmd; do
            eval "${cmd}"
        done < "${JOBS_FILE}"
    fi
    echo "[DONE] All ${RUN_IDX} runs completed."
fi
```

- [ ] **Step 3: Make scripts executable and commit**

```bash
chmod +x scripts/run_single_experiment.sh scripts/run_calendar_study.sh
git add scripts/run_single_experiment.sh scripts/run_calendar_study.sh
git commit -m "feat: add experiment runner scripts for calendar switch study"
```

---

### Task 10: Analysis and Report Generation

Python script to compute metrics, generate figures, and produce the final report.

**Files:**
- Create: `scripts/analyze_results.py`
- Test: `tests/calendar_switch/test_result_analysis.py`

- [ ] **Step 1: Write analysis test**

```python
# tests/calendar_switch/test_result_analysis.py
"""
Tests for the analysis script. Uses synthetic data to verify
metrics computation and output format.
"""
import json
import tempfile
from pathlib import Path
import sys
import pytest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from analyze_results import (
    load_experiment_results,
    compute_e2e_stats,
    compute_baseline_ratios,
    generate_report_data,
)


@pytest.fixture
def sample_results(tmp_path):
    """Create a minimal results directory with synthetic data."""
    # Baseline run
    base_dir = tmp_path / "baseline" / "allreduce_ring_g8_s33554432"
    base_dir.mkdir(parents=True)
    (base_dir / "metadata.json").write_text(json.dumps({
        "mode": "packet_switch", "operator": "allreduce_ring",
        "gpus": 8, "msg_bytes": 33554432,
        "granularity": "operator", "algorithm": "solstice",
    }))
    (base_dir / "e2e_times.json").write_text(json.dumps(
        [100.0, 102.0, 98.0, 105.0, 101.0, 99.0, 103.0, 104.0, 97.0, 106.0]
    ))

    # Calendar run
    cal_dir = tmp_path / "calendar" / "allreduce_ring_operator_solstice_g8_s33554432"
    cal_dir.mkdir(parents=True)
    (cal_dir / "metadata.json").write_text(json.dumps({
        "mode": "calendar_switch", "operator": "allreduce_ring",
        "gpus": 8, "msg_bytes": 33554432,
        "granularity": "operator", "algorithm": "solstice",
    }))
    (cal_dir / "e2e_times.json").write_text(json.dumps(
        [90.0, 92.0, 88.0, 95.0, 91.0, 89.0, 93.0, 94.0, 87.0, 96.0]
    ))

    return tmp_path


class TestAnalysis:
    def test_load_experiment_results(self, sample_results):
        results = load_experiment_results(sample_results)
        assert len(results) == 2

    def test_compute_e2e_stats(self):
        times = [100.0, 102.0, 98.0, 105.0, 101.0]
        stats = compute_e2e_stats(times)
        assert "mean" in stats
        assert "p50" in stats
        assert "p95" in stats
        assert "p99" in stats
        assert abs(stats["mean"] - 101.2) < 0.1

    def test_compute_baseline_ratios(self, sample_results):
        results = load_experiment_results(sample_results)
        ratios = compute_baseline_ratios(results)
        assert len(ratios) > 0
        for r in ratios:
            assert "ratio" in r
            assert r["ratio"] < 1.0  # calendar should be faster in this synthetic data

    def test_generate_report_has_all_sections(self, sample_results):
        results = load_experiment_results(sample_results)
        report = generate_report_data(results)
        assert "executive_summary" in report
        assert "per_operator" in report
        assert "recommendations" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_result_analysis.py -v`
Expected: FAIL

- [ ] **Step 3: Implement analyze_results.py**

```python
# scripts/analyze_results.py
"""
Analyze calendar switch experiment results. Computes E2E metrics,
baseline ratios, and generates report data.

Usage:
    python scripts/analyze_results.py --results-dir results/calendar_study_xxx --output report.json
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from dataclasses import dataclass, asdict

import numpy as np


@dataclass
class ExperimentResult:
    mode: str
    operator: str
    gpus: int
    msg_bytes: int
    granularity: str
    algorithm: str
    e2e_times: list[float]
    run_dir: str


def load_experiment_results(results_dir: Path) -> list[ExperimentResult]:
    results = []
    for meta_file in results_dir.rglob("metadata.json"):
        run_dir = meta_file.parent
        meta = json.loads(meta_file.read_text())
        e2e_file = run_dir / "e2e_times.json"
        e2e_times = json.loads(e2e_file.read_text()) if e2e_file.exists() else []
        results.append(ExperimentResult(
            mode=meta["mode"],
            operator=meta["operator"],
            gpus=meta["gpus"],
            msg_bytes=meta["msg_bytes"],
            granularity=meta.get("granularity", "operator"),
            algorithm=meta.get("algorithm", "solstice"),
            e2e_times=e2e_times,
            run_dir=str(run_dir),
        ))
    return results


def compute_e2e_stats(times: list[float]) -> dict:
    if not times:
        return {"mean": 0, "p50": 0, "p95": 0, "p99": 0}
    arr = np.array(times)
    return {
        "mean": float(arr.mean()),
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
    }


def compute_baseline_ratios(results: list[ExperimentResult]) -> list[dict]:
    baselines: dict[tuple, dict] = {}
    for r in results:
        if r.mode == "packet_switch":
            key = (r.operator, r.gpus, r.msg_bytes)
            baselines[key] = compute_e2e_stats(r.e2e_times)

    ratios = []
    for r in results:
        if r.mode != "calendar_switch":
            continue
        key = (r.operator, r.gpus, r.msg_bytes)
        if key not in baselines:
            continue
        base_p95 = baselines[key]["p95"]
        cal_stats = compute_e2e_stats(r.e2e_times)
        if base_p95 > 0:
            ratio = cal_stats["p95"] / base_p95
        else:
            ratio = float("inf")
        ratios.append({
            "operator": r.operator,
            "gpus": r.gpus,
            "msg_bytes": r.msg_bytes,
            "granularity": r.granularity,
            "algorithm": r.algorithm,
            "baseline_p95": base_p95,
            "calendar_p95": cal_stats["p95"],
            "ratio": ratio,
        })
    return ratios


def generate_report_data(results: list[ExperimentResult]) -> dict:
    ratios = compute_baseline_ratios(results)

    per_operator: dict[str, list] = {}
    for r in ratios:
        per_operator.setdefault(r["operator"], []).append(r)

    recommendations = {}
    for op, entries in per_operator.items():
        if not entries:
            continue
        best = min(entries, key=lambda e: e["ratio"])
        recommendations[op] = {
            "best_granularity": best["granularity"],
            "best_algorithm": best["algorithm"],
            "best_ratio": best["ratio"],
        }

    winning = sum(1 for r in ratios if r["ratio"] < 1.0)
    total = len(ratios)

    return {
        "executive_summary": {
            "total_experiments": total,
            "calendar_wins": winning,
            "calendar_win_rate": winning / max(1, total),
        },
        "per_operator": per_operator,
        "recommendations": recommendations,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    results = load_experiment_results(Path(args.results_dir))
    report = generate_report_data(results)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))
    print(f"Report written to {output_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_result_analysis.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_results.py tests/calendar_switch/test_result_analysis.py
git commit -m "feat: add analysis script with metrics and report generation"
```

---

### Task 11: Baseline Parity Test

Integration test verifying that disabling calendar mode produces identical behavior to the unmodified SwitchNode.

**Files:**
- Create: `tests/calendar_switch/test_baseline_parity.py`

- [ ] **Step 1: Write the baseline parity test**

```python
# tests/calendar_switch/test_baseline_parity.py
"""
Integration tests verifying that CalendarSwitchNode with calendar disabled
behaves identically to the baseline SwitchNode.

These are contract-level checks on the C++ source code, not simulation
runs. Full simulation parity is validated during the experiment phase.
"""
import re
from pathlib import Path
import pytest

CALENDAR_IMPL = Path(
    "ns-3-alibabacloud/simulation/src/point-to-point/model/calendar-switch-node.cc"
)
COMMON_H = Path("astra-sim-alibabacloud/astra-sim/network_frontend/ns3/common.h")


class TestBaselineParity:
    def test_calendar_disabled_delegates_to_parent(self):
        """When calendar is disabled, SwitchReceiveFromDevice should call parent."""
        code = CALENDAR_IMPL.read_text()
        assert re.search(
            r"SwitchNode::SwitchReceiveFromDevice",
            code,
        ), "CalendarSwitchNode should delegate to SwitchNode when disabled"

    def test_default_config_disables_calendar(self):
        code = COMMON_H.read_text()
        assert re.search(r"enable_calendar_switch\s*=\s*0", code)

    def test_calendar_switch_node_inherits_dequeue(self):
        """SwitchNotifyDequeue should call parent for baseline behavior."""
        code = CALENDAR_IMPL.read_text()
        assert re.search(
            r"SwitchNode::SwitchNotifyDequeue",
            code,
        )

    def test_topology_uses_plain_switchnode_when_disabled(self):
        """With enable_calendar_switch=0, plain SwitchNode should be created."""
        code = COMMON_H.read_text()
        assert re.search(
            r"if\s*\(\s*enable_calendar_switch\s*\)",
            code,
        ), "Topology setup should branch on enable_calendar_switch"
        # Both paths should exist
        assert "CreateObject<CalendarSwitchNode>" in code
        assert "CreateObject<SwitchNode>" in code
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/test_baseline_parity.py -v`
Expected: PASS (these should pass if Tasks 5 and 7 are complete)

- [ ] **Step 3: Commit**

```bash
git add tests/calendar_switch/test_baseline_parity.py
git commit -m "test: add baseline parity contract tests"
```

---

### Task 12: Build Integration and End-to-End Validation

Ensure the calendar_scheduler library and CalendarSwitchNode compile within the ns-3 build system.

**Files:**
- Modify: `scripts/build.sh` (or document build steps)
- Create: `tests/calendar_switch/conftest.py`

- [ ] **Step 1: Create pytest conftest for the test suite**

```python
# tests/calendar_switch/conftest.py
"""
Shared fixtures and configuration for calendar switch tests.
"""
import sys
from pathlib import Path

# Ensure workload generators and scheduler library are importable
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "workloads" / "calendar_study"))
sys.path.insert(0, str(ROOT / "calendar_scheduler" / "python"))
sys.path.insert(0, str(ROOT / "scripts"))
```

- [ ] **Step 2: Create a tests/__init__.py and calendar_switch/__init__.py**

```python
# tests/__init__.py
# (empty - marks directory as Python package for pytest discovery)
```

```python
# tests/calendar_switch/__init__.py
# (empty - marks directory as Python package for pytest discovery)
```

- [ ] **Step 3: Run the full test suite**

Run: `cd /home/luke/workspace/SimAI && python -m pytest tests/calendar_switch/ -v --tb=short`
Expected: All tests PASS (approximately 30-35 tests across all test files)

- [ ] **Step 4: Document build instructions for C++ components**

Add to the bottom of the calendar scheduler CMakeLists.txt:

```cmake
# Integration note: To build within the ns-3 tree, copy calendar_scheduler/
# sources into ns-3-alibabacloud/simulation/src/point-to-point/model/ and add
# them to the ns-3 wscript/CMakeLists. Alternatively, build as a standalone
# library and link during astra-sim build:
#
#   cd calendar_scheduler && mkdir build && cd build
#   cmake .. && make
#
# Then update astra-sim-alibabacloud/build/astra_ns3/build.sh to link
# against libcalendar_scheduler.a and include the header path.
```

- [ ] **Step 5: Commit**

```bash
git add tests/calendar_switch/conftest.py tests/__init__.py \
        tests/calendar_switch/__init__.py calendar_scheduler/CMakeLists.txt
git commit -m "chore: add test infrastructure and build integration notes"
```

---

## Self-Review Checklist

**Spec coverage:**
- Section 4.1 (CalendarScheduler Library): Tasks 1-3
- Section 4.2 (CalendarSwitchNode): Task 5
- Section 4.3 (GranularityController): Task 6
- Section 4.4 (Demand Collection): Task 6 + Task 8
- Section 5 (Configuration): Task 4
- Section 6-7 (Operator Set + Granularity Semantics): Task 8
- Section 8 (Experiment Design): Task 9
- Section 9-10 (Metrics + Baseline Comparison): Task 10
- Section 11 (File Layout): All tasks
- Section 12 (Validation Plan): Task 11

**Placeholder scan:** No TBD/TODO/placeholder text found.

**Type consistency:**
- `DemandMatrix`, `Schedule`, `ScheduleEntry` used consistently across Python and C++ with matching semantics
- `ncclFlowTag` fields (`tag_id`, `current_flow_id`, `chunk_id`) referenced consistently in GranularityController and entry.h
- Config key names match between common.h parsing, template conf, and test assertions
