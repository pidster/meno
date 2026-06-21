"""The control plane: the autonomic heartbeat.

Cheap, always-on, no model. Each tick: rescore the working set (decay →
quiescence), advance stream pressure/fatigue, and fire the interoceptive wake —
a deferred stream whose pressure crossed the line is resumed and re-enters the
bus as a self-event (initiative). The circadian (dream) trigger is driven by the
runtime's pass scheduler.
"""
from __future__ import annotations

from typing import List

from .event import Event, Kind


class Controller:
    def __init__(self, mind) -> None:
        self.mind = mind

    def tick(self) -> List[Event]:
        """Returns events to (re-)publish — the interoceptive wakes."""
        self.mind.working_set.rescore()
        woke = self.mind.streams.tick()
        emitted: List[Event] = []
        for sid in woke:
            stream = self.mind.streams.resume(sid) or self.mind.streams.get(sid)
            if stream is None:
                continue
            # initiative grants a deep slot to the impulse that insisted
            self.mind.deep_budget = max(self.mind.deep_budget, 1)
            ev = Event(content=f"returning to: {stream.summary or 'an unfinished thought'}",
                       kind=Kind.SELF, source="initiative", stream_id=sid,
                       activation=max(0.6, stream.pressure))
            ev.payload["role"] = "wake"
            stream.deferred = False
            stream.pressure = 0.0
            emitted.append(ev)
            self.mind.trace(f"interoceptive wake -> stream {sid}: {stream.summary!r}")
        return emitted
