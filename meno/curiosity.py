"""Curiosity — the pull-toward-the-world drive (F3).

Distinct from impulse: a curiosity **decays** (it relaxes when unattended), where
an impulse builds pressure. Two origins (redesign.md, principle 4):
  - bottom-up: an unresolved question raised by a percept (residue that climbs);
  - top-down: boredom under sustained under-stimulation (a reach toward the world).
Discharge is routed by the model across the internal/external matrix
(`ModelProvider.wonder`) — the mechanism provides the capacity; the model decides.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Curiosity:
    text: str
    intensity: float
    source: str                       # "bottom-up" | "top-down"
    referent: Optional[str] = None    # a world handle (e.g. a path) if there is one
    stream_id: Optional[int] = None   # the train of thought it arose from, if any


class CuriosityRegister:
    def __init__(self, config) -> None:
        self.cfg = config
        self.items: List[Curiosity] = []

    def register(self, text: str, source: str, referent: Optional[str] = None,
                 stream_id: Optional[int] = None) -> None:
        self.items.append(Curiosity(text, self.cfg.curiosity_birth, source, referent, stream_id))
        self.items.sort(key=lambda c: c.intensity, reverse=True)
        del self.items[self.cfg.curiosity_register_cap:]    # bounded

    def decay(self) -> None:
        for c in self.items:
            c.intensity *= self.cfg.curiosity_decay
        self.items = [c for c in self.items if c.intensity >= 0.05]

    def satisfy(self, stream_id: Optional[int]) -> None:
        """A reflection answered this train of thought — its curiosities relax."""
        if stream_id is None:
            return
        for c in self.items:
            if c.stream_id == stream_id:
                c.intensity *= 0.3

    def top(self) -> Optional[Curiosity]:
        return max(self.items, key=lambda c: c.intensity, default=None)
