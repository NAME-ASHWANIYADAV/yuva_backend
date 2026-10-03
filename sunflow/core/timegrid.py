"""15-minute time grid for one operating day (96 blocks)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimeGrid:
    dt_min: int = 15

    @property
    def N(self) -> int:
        return 24 * 60 // self.dt_min

    @property
    def dt_h(self) -> float:
        return self.dt_min / 60.0

    def block_of(self, hhmm: str) -> int:
        h, m = hhmm.split(":")
        minutes = int(h) * 60 + int(m)
        if minutes % self.dt_min:
            raise ValueError(f"{hhmm} is not aligned to {self.dt_min}-minute blocks")
        return minutes // self.dt_min

    def label(self, t: int) -> str:
        minutes = (t % self.N) * self.dt_min
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def blocks_between(self, start: str, end: str) -> range:
        """Blocks from start (inclusive) to end (exclusive)."""
        return range(self.block_of(start), self.block_of(end))
