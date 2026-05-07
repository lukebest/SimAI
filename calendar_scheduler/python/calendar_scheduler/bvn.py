from __future__ import annotations

import math

import numpy as np

from .solstice import _max_weight_matching
from .types import DemandMatrix, Schedule, ScheduleEntry


_EPSILON = 1e-9


def _is_identity(permutation: list[int]) -> bool:
    return all(row == column for row, column in enumerate(permutation))


def _normalize_demand(
    demand: DemandMatrix,
    max_iterations: int,
    tolerance: float,
) -> np.ndarray:
    residual = np.maximum(demand.data.copy().astype(float), 0.0)
    np.fill_diagonal(residual, 0.0)
    if float(residual.sum()) <= tolerance:
        return residual

    for _ in range(max_iterations):
        row_sums = residual.sum(axis=1)
        for row, row_sum in enumerate(row_sums):
            if row_sum > tolerance:
                residual[row, :] /= row_sum

        col_sums = residual.sum(axis=0)
        for column, col_sum in enumerate(col_sums):
            if col_sum > tolerance:
                residual[:, column] /= col_sum

        row_error = np.max(np.abs(residual.sum(axis=1) - 1.0))
        col_error = np.max(np.abs(residual.sum(axis=0) - 1.0))
        if max(float(row_error), float(col_error)) <= tolerance:
            break

    residual[residual < tolerance] = 0.0
    return residual


class BvNScheduler:
    def __init__(
        self,
        frame_slots: int = 1024,
        max_iterations: int = 64,
        sinkhorn_iterations: int = 1000,
        tolerance: float = _EPSILON,
    ):
        self.frame_slots = int(frame_slots)
        self.max_iterations = int(max_iterations)
        self.sinkhorn_iterations = int(sinkhorn_iterations)
        self.tolerance = float(tolerance)

    def compute(self, demand: DemandMatrix) -> Schedule:
        n = demand.n
        if n <= 1 or self.frame_slots <= 0:
            return Schedule()

        residual = _normalize_demand(
            demand,
            max_iterations=self.sinkhorn_iterations,
            tolerance=self.tolerance,
        )
        if float(residual.sum()) <= self.tolerance:
            return Schedule()

        remaining_slots = self.frame_slots
        entries: list[ScheduleEntry] = []

        for _ in range(self.max_iterations):
            if remaining_slots <= 0 or float(residual.sum()) <= self.tolerance:
                break

            permutation = _max_weight_matching(residual)
            assigned_weights = [
                float(residual[row][permutation[row]])
                for row in range(n)
            ]
            if any(weight <= self.tolerance for weight in assigned_weights):
                break

            weight = min(assigned_weights)
            for row in range(n):
                column = permutation[row]
                residual[row][column] = max(
                    0.0,
                    float(residual[row][column]) - weight,
                )
            residual[residual < self.tolerance] = 0.0

            if _is_identity(permutation):
                continue

            slots = math.floor(weight * self.frame_slots + 0.5)
            slots = min(max(1, int(slots)), remaining_slots)
            entries.append(ScheduleEntry(permutation=permutation, slots=slots))
            remaining_slots -= slots

        return Schedule(entries=entries)
