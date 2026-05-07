from __future__ import annotations

from .types import DemandMatrix, Schedule, ScheduleEntry


def _max_weight_matching(residual) -> list[int]:
    n = residual.shape[0]
    permutation = [-1] * n
    used_columns: set[int] = set()

    cells = [
        (float(residual[row][column]), row, column)
        for row in range(n)
        for column in range(n)
        if residual[row][column] > 0
    ]
    cells.sort(key=lambda cell: (-cell[0], cell[1], cell[2]))

    for _weight, row, column in cells:
        if permutation[row] != -1 or column in used_columns:
            continue
        permutation[row] = column
        used_columns.add(column)
        if len(used_columns) == n:
            break

    remaining_columns = [column for column in range(n) if column not in used_columns]
    next_remaining = 0
    for row in range(n):
        if permutation[row] == -1:
            permutation[row] = remaining_columns[next_remaining]
            next_remaining += 1

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

            proportional_slots = round(
                (matching_weight / original_total_demand) * self.frame_slots
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
