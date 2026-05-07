"""
Tests for calendar scheduler algorithms.

These tests exercise pure Python reference implementations that mirror the
C++ scheduler interface used by the calendar switch study.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(
    0,
    str(pathlib.Path(__file__).resolve().parents[2] / "calendar_scheduler" / "python"),
)

from calendar_scheduler import (  # noqa: E402
    BvNScheduler,
    DemandMatrix,
    RoundRobinScheduler,
    SolsticeScheduler,
)


class TestRoundRobinScheduler:
    def test_uniform_demand_produces_useful_rotations(self):
        n = 4
        demand = DemandMatrix(np.ones((n, n)) * 100 - np.eye(n) * 100)
        sched = RoundRobinScheduler(frame_slots=1024)

        result = sched.compute(demand)

        assert len(result.entries) == n - 1
        assert result.total_slots == 1024

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
                assert perm[i] != i

    def test_empty_demand_produces_empty_schedule(self):
        n = 4
        demand = DemandMatrix(np.zeros((n, n)))
        sched = RoundRobinScheduler(frame_slots=1024)

        result = sched.compute(demand)

        assert len(result.entries) == 0 or all(e.slots == 0 for e in result.entries)

    def test_slots_are_equalish_for_round_robin(self):
        n = 4
        demand = DemandMatrix(np.ones((n, n)) * 100 - np.eye(n) * 100)
        sched = RoundRobinScheduler(frame_slots=1024)

        result = sched.compute(demand)

        slot_counts = [e.slots for e in result.entries]
        assert max(slot_counts) - min(slot_counts) <= 1
