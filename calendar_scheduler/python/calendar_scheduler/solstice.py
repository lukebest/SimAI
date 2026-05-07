from __future__ import annotations

import math

from .types import DemandMatrix, Schedule, ScheduleEntry


def _max_weight_matching(residual) -> list[int]:
    n = residual.shape[0]
    max_weight = max(
        float(residual[row][column])
        for row in range(n)
        for column in range(n)
    )
    costs = [
        [max_weight - float(residual[row][column]) for column in range(n)]
        for row in range(n)
    ]

    potentials_rows = [0.0] * (n + 1)
    potentials_cols = [0.0] * (n + 1)
    matched_rows = [0] * (n + 1)
    previous_cols = [0] * (n + 1)

    for row in range(1, n + 1):
        matched_rows[0] = row
        col0 = 0
        min_values = [float("inf")] * (n + 1)
        used_cols = [False] * (n + 1)

        while True:
            used_cols[col0] = True
            row0 = matched_rows[col0]
            delta = float("inf")
            col1 = 0

            for col in range(1, n + 1):
                if used_cols[col]:
                    continue
                current = (
                    costs[row0 - 1][col - 1]
                    - potentials_rows[row0]
                    - potentials_cols[col]
                )
                if current < min_values[col]:
                    min_values[col] = current
                    previous_cols[col] = col0
                if min_values[col] < delta:
                    delta = min_values[col]
                    col1 = col

            for col in range(n + 1):
                if used_cols[col]:
                    potentials_rows[matched_rows[col]] += delta
                    potentials_cols[col] -= delta
                else:
                    min_values[col] -= delta

            col0 = col1
            if matched_rows[col0] == 0:
                break

        while True:
            col1 = previous_cols[col0]
            matched_rows[col0] = matched_rows[col1]
            col0 = col1
            if col0 == 0:
                break

    permutation = [0] * n
    for col in range(1, n + 1):
        permutation[matched_rows[col] - 1] = col - 1

    return permutation


class SolsticeScheduler:
    def __init__(self, frame_slots: int = 1024, max_iterations: int = 64):
        self.frame_slots = int(frame_slots)
        self.max_iterations = int(max_iterations)

    def compute(self, demand: DemandMatrix) -> Schedule:
        n = demand.n
        if n <= 1 or self.frame_slots <= 0 or demand.total_demand() <= 0:
            return Schedule()

        residual = demand.data.copy().astype(float)
        original_total_demand = float(residual.sum())
        remaining_slots = self.frame_slots
        entries: list[ScheduleEntry] = []

        for _ in range(self.max_iterations):
            if remaining_slots <= 0 or float(residual.sum()) <= 1e-9:
                break

            permutation = _max_weight_matching(residual)
            matching_weight = sum(
                max(0.0, float(residual[row][permutation[row]]))
                for row in range(n)
            )
            if matching_weight <= 1e-9:
                break

            proportional_slots = math.floor(
                (matching_weight / original_total_demand) * self.frame_slots + 0.5
            )
            slots = min(max(1, int(proportional_slots)), remaining_slots)

            served_fraction = slots / max(
                1.0,
                self.frame_slots * (matching_weight / original_total_demand),
            )
            for row in range(n):
                column = permutation[row]
                if residual[row][column] > 0:
                    residual[row][column] = max(
                        0.0,
                        float(residual[row][column]) * (1.0 - served_fraction),
                    )

            entries.append(ScheduleEntry(permutation=permutation, slots=slots))
            remaining_slots -= slots

        return Schedule(entries=entries)
