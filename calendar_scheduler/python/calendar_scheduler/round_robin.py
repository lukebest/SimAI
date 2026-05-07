from __future__ import annotations

from .types import DemandMatrix, Schedule, ScheduleEntry


class RoundRobinScheduler:
    def __init__(self, frame_slots: int = 1024):
        self.frame_slots = int(frame_slots)

    def compute(self, demand: DemandMatrix) -> Schedule:
        n = demand.n
        if n <= 1 or demand.total_demand() == 0:
            return Schedule()

        useful_rotations = n - 1
        base_slots = self.frame_slots // useful_rotations
        remainder = self.frame_slots % useful_rotations

        entries = []
        for rotation in range(1, n):
            slots = base_slots + (1 if rotation <= remainder else 0)
            permutation = [(i + rotation) % n for i in range(n)]
            entries.append(ScheduleEntry(permutation=permutation, slots=slots))

        return Schedule(entries=entries)
