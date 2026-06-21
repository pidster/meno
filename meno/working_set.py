"""The working set: the short, bounded priority queue that IS the attention
budget and the global workspace (redesign.md).

Dynamic score = activation*surprise + stream.pressure - stream.fatigue.
Capacity overflow demotes a WHOLE stream (never split, never auto-eliminate).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .config import Config
from .event import Event, Status
from .streams import StreamManager


class WorkingSet:
    def __init__(self, config: Config, streams: StreamManager) -> None:
        self.cfg = config
        self.streams = streams
        self.events: Dict[int, Event] = {}
        self.demoted_streams: List[int] = []   # observable trace for tests/logging

    def score(self, e: Event) -> float:
        s = e.activation * (0.3 + e.surprise)
        st = self.streams.get(e.stream_id)
        if st:
            s += st.pressure - st.fatigue
        return s

    def admit(self, event: Event) -> None:
        self.events[event.id] = event
        self._enforce_capacity()

    def claim(self) -> Optional[Event]:
        """Pull the highest-scoring event (a worker taking work)."""
        if not self.events:
            return None
        eid = max(self.events, key=lambda i: self.score(self.events[i]))
        return self.events.pop(eid)

    def rescore(self) -> None:
        """Continuous decay; unclaimed low-activation events lapse (quiescence)."""
        for e in list(self.events.values()):
            e.activation *= self.cfg.activation_decay
            if e.activation < self.cfg.lapse_threshold:
                self.events.pop(e.id, None)
                e.status = Status.LAPSED

    def depth(self) -> int:
        return len(self.events)

    def load(self) -> float:
        return self.depth() / self.cfg.load_norm_base

    def embeddings(self) -> List[List[float]]:
        return [e.embedding for e in self.events.values() if e.embedding]

    def _enforce_capacity(self) -> None:
        while len(self.events) > self.cfg.working_set_capacity:
            # find the lowest-scoring event, demote its WHOLE stream intact
            lowest = min(self.events, key=lambda i: self.score(self.events[i]))
            sid = self.events[lowest].stream_id
            for e in [ev for ev in self.events.values() if ev.stream_id == sid]:
                self.events.pop(e.id, None)
            self.streams.suspend(sid)
            self.demoted_streams.append(sid)
