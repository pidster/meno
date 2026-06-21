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
        cap = self.cfg.working_set_capacity
        while len(self.events) > cap:
            before = len(self.events)
            lowest = min(self.events, key=lambda i: self.score(self.events[i]))
            ev = self.events[lowest]
            sid = ev.stream_id
            cohort = [e for e in self.events.values()
                      if sid is not None and e.stream_id == sid]
            if sid is None or len(cohort) <= 1 or len(cohort) > cap:
                # an orphan (no stream), a singleton, or a stream too big to ever
                # hold whole: lapse just this one event. (A stream larger than the
                # working set cannot be held intact — trimming its lowest events is
                # the honest concession, rather than collapsing the set to ~1.)
                self.events.pop(lowest, None)
                ev.status = Status.LAPSED
            else:
                # demote the WHOLE stream intact (suspended, resumable) — the design
                # intent: set a train of thought down gently, never split it.
                for e in cohort:
                    self.events.pop(e.id, None)
                self.streams.suspend(sid)
                self.demoted_streams.append(sid)
            if len(self.events) >= before:   # progress guard: never spin
                break
