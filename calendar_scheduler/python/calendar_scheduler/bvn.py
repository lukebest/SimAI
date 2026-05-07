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


def _active_matching(
    residual: np.ndarray,
    tolerance: float,
) -> tuple[list[int], list[tuple[int, int]]]:
    n = int(residual.shape[0])
    active_rows = [
        row for row in range(n) if float(np.max(residual[row, :])) > tolerance
    ]
    active_columns = [
        column for column in range(n) if float(np.max(residual[:, column])) > tolerance
    ]
    if not active_rows or not active_columns:
        return list(range(n)), []

    matching_size = max(len(active_rows), len(active_columns))
    matching_weights = np.zeros((matching_size, matching_size), dtype=float)
    cardinality_bonus = float(residual.sum()) + 1.0
    for local_row, row in enumerate(active_rows):
        for local_column, column in enumerate(active_columns):
            edge_weight = float(residual[row][column])
            if edge_weight > tolerance:
                matching_weights[local_row][local_column] = (
                    cardinality_bonus + edge_weight
                )

    local_permutation = _max_weight_matching(matching_weights)
    permutation = [-1] * n
    used_columns: set[int] = set()
    matched_edges: list[tuple[int, int]] = []

    for local_row, row in enumerate(active_rows):
        local_column = local_permutation[local_row]
        if local_column >= len(active_columns):
            continue

        column = active_columns[local_column]
        if float(residual[row][column]) <= tolerance:
            continue

        permutation[row] = column
        used_columns.add(column)
        matched_edges.append((row, column))

    unused_columns = [column for column in range(n) if column not in used_columns]
    for row in range(n):
        if permutation[row] == -1:
            permutation[row] = unused_columns.pop(0)

    return permutation, matched_edges


class BvNScheduler:
    def __init__(
        self,
        frame_slots: int = 1024,
        max_iterations: int | None = None,
        sinkhorn_iterations: int = 1000,
        tolerance: float = _EPSILON,
    ):
        self.frame_slots = int(frame_slots)
        self.max_iterations = None if max_iterations is None else int(max_iterations)
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
        iteration_limit = (
            self.max_iterations
            if self.max_iterations is not None
            else max(self.frame_slots, n * n * 4)
        )

        for _ in range(iteration_limit):
            if remaining_slots <= 0 or float(residual.sum()) <= self.tolerance:
                break

            permutation, matched_edges = _active_matching(residual, self.tolerance)
            if not matched_edges:
                break

            weight = min(float(residual[row][column]) for row, column in matched_edges)
            for row, column in matched_edges:
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
