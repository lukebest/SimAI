"""
Tests for calendar scheduler algorithms.

These tests exercise pure Python reference implementations that mirror the
C++ scheduler interface used by the calendar switch study.
"""
import pathlib
import subprocess
import sys
import textwrap

import numpy as np
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(
    0,
    str(REPO_ROOT / "calendar_scheduler" / "python"),
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

        assert len(result.entries) == 0

    def test_slots_are_equalish_for_round_robin(self):
        n = 4
        demand = DemandMatrix(np.ones((n, n)) * 100 - np.eye(n) * 100)
        sched = RoundRobinScheduler(frame_slots=1024)

        result = sched.compute(demand)

        slot_counts = [e.slots for e in result.entries]
        assert max(slot_counts) - min(slot_counts) <= 1


class TestRoundRobinCppSmoke:
    def test_cpp_round_robin_matches_reference_contract(self, tmp_path):
        source = tmp_path / "round_robin_smoke.cc"
        binary = tmp_path / "round_robin_smoke"
        source.write_text(
            textwrap.dedent(
                """
                #include <iostream>
                #include <set>

                #include "round_robin_scheduler.h"

                int main() {
                  calendar::RoundRobinScheduler sched(1024);
                  calendar::DemandMatrix uniform(4, std::vector<double>(4, 100.0));
                  for (uint32_t i = 0; i < 4; ++i) {
                    uniform[i][i] = 0.0;
                  }

                  const calendar::Schedule schedule = sched.compute(uniform);
                  if (schedule.entries.size() != 3) {
                    std::cerr << "expected 3 entries, got "
                              << schedule.entries.size() << "\\n";
                    return 1;
                  }
                  if (schedule.total_slots() != 1024) {
                    std::cerr << "expected 1024 slots, got "
                              << schedule.total_slots() << "\\n";
                    return 1;
                  }
                  for (const auto& entry : schedule.entries) {
                    if (entry.permutation.size() != 4) {
                      std::cerr << "permutation has wrong size\\n";
                      return 1;
                    }
                    std::set<uint32_t> seen(entry.permutation.begin(),
                                            entry.permutation.end());
                    if (seen.size() != 4) {
                      std::cerr << "permutation is not unique\\n";
                      return 1;
                    }
                    for (uint32_t i = 0; i < entry.permutation.size(); ++i) {
                      if (entry.permutation[i] == i) {
                        std::cerr << "self-loop in permutation\\n";
                        return 1;
                      }
                    }
                  }

                  calendar::DemandMatrix one_by_one{{10.0}};
                  if (!sched.compute(one_by_one).entries.empty()) {
                    std::cerr << "1x1 demand should be empty\\n";
                    return 1;
                  }

                  calendar::DemandMatrix ragged{{0.0, 1.0}, {1.0}};
                  if (!sched.compute(ragged).entries.empty()) {
                    std::cerr << "ragged demand should be empty\\n";
                    return 1;
                  }

                  return 0;
                }
                """
            ),
            encoding="utf-8",
        )

        compile_result = subprocess.run(
            [
                "c++",
                "-std=c++17",
                "-I",
                str(REPO_ROOT / "calendar_scheduler" / "include"),
                str(source),
                str(REPO_ROOT / "calendar_scheduler" / "src" / "round_robin_scheduler.cc"),
                "-o",
                str(binary),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert compile_result.returncode == 0, compile_result.stderr

        run_result = subprocess.run(
            [str(binary)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert run_result.returncode == 0, run_result.stderr
