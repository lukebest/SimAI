from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class DemandMatrix:
    """Square demand matrix where data[i][j] is demand from input i to output j."""

    data: np.ndarray

    def __post_init__(self) -> None:
        self.data = np.asarray(self.data, dtype=float)
        if self.data.ndim != 2:
            raise ValueError("DemandMatrix must be two-dimensional")
        if self.data.shape[0] != self.data.shape[1]:
            raise ValueError("DemandMatrix must be square")

    @property
    def n(self) -> int:
        return int(self.data.shape[0])

    def total_demand(self) -> float:
        return float(self.data.sum())


@dataclass
class ScheduleEntry:
    permutation: list[int]
    slots: int


@dataclass
class Schedule:
    entries: list[ScheduleEntry] = field(default_factory=list)

    @property
    def total_slots(self) -> int:
        return sum(entry.slots for entry in self.entries)
