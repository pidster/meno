"""Streams: the logical trains of thought. Lifecycle = born / merge / suspend /
resume / end (redesign.md). Threads (the workers) are separate and have no
lifecycle; streams do. Streams — not events — are the unit eviction protects.
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import Config
from .embeddings import EmbeddingModel, cosine
from .event import Event

_stream_ids = itertools.count(1)


@dataclass
class Stream:
    centroid: List[float]
    pressure: float = 0.0           # deferred-impulse pressure (builds while unattended-but-wanted)
    fatigue: float = 0.0            # lateral inhibition (rises when worked hard)
    deferred: bool = False          # wanted deep work but couldn't afford it
    suspended: bool = False
    event_ids: List[int] = field(default_factory=list)
    node_ids: List[int] = field(default_factory=list)   # graph nodes encoded from this stream
    summary: str = ""
    id: int = field(default_factory=lambda: next(_stream_ids))
    last_active: float = field(default_factory=time.time)


class StreamManager:
    def __init__(self, embed: EmbeddingModel, config: Config) -> None:
        self.embed = embed
        self.cfg = config
        self.active: Dict[int, Stream] = {}
        self.warm: Dict[int, Stream] = {}   # suspended, resumable

    def get(self, sid: Optional[int]) -> Optional[Stream]:
        if sid is None:
            return None
        return self.active.get(sid)

    # --- born / route (cheap, Tier-0-ish: similarity to centroids) ---
    def route(self, event: Event) -> int:
        if event.stream_id in self.active:
            self._absorb(event)
            return event.stream_id
        best_id, best_sim = None, 0.0
        for sid, s in self.active.items():
            sim = cosine(event.embedding, s.centroid)
            if sim > best_sim:
                best_id, best_sim = sid, sim
        if best_id is not None and best_sim >= self.cfg.stream_match_threshold:
            event.stream_id = best_id
            self._absorb(event)
            return best_id
        # born: a new line of thought
        s = Stream(centroid=list(event.embedding), summary=event.content[:60])
        self.active[s.id] = s
        event.stream_id = s.id
        self._absorb(event)
        return s.id

    def _absorb(self, event: Event) -> None:
        s = self.active[event.stream_id]
        s.event_ids.append(event.id)
        b = self.cfg.centroid_blend
        s.centroid = [(1 - b) * c + b * e for c, e in zip(s.centroid, event.embedding)]
        s.last_active = time.time()
        if not s.summary:
            s.summary = event.content[:60]

    # --- merge: convergence = insight ---
    def detect_merge(self) -> List[tuple]:
        ids = list(self.active)
        out = []
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = self.active[ids[i]], self.active[ids[j]]
                if cosine(a.centroid, b.centroid) >= self.cfg.merge_threshold:
                    out.append((ids[i], ids[j]))
        return out

    def merge(self, a_id: int, b_id: int) -> Optional[int]:
        a, b = self.active.get(a_id), self.active.get(b_id)
        if not a or not b:
            return None
        a.event_ids.extend(b.event_ids)
        a.node_ids.extend(b.node_ids)
        a.centroid = [(x + y) / 2 for x, y in zip(a.centroid, b.centroid)]
        a.pressure = max(a.pressure, b.pressure)
        a.summary = (a.summary + " + " + b.summary)[:90]
        del self.active[b_id]
        return a_id

    # --- suspend / resume / end ---
    def suspend(self, sid: Optional[int]) -> None:
        s = self.active.pop(sid, None) if sid is not None else None
        if s is not None:
            s.suspended = True
            self.warm[sid] = s

    def resume(self, sid: int) -> Optional[Stream]:
        s = self.warm.pop(sid, None)
        if s is not None:
            s.suspended = False
            s.last_active = time.time()
            self.active[sid] = s
        return s

    def end(self, sid: int) -> None:
        self.active.pop(sid, None)
        self.warm.pop(sid, None)

    # --- autonomic tick: pressure builds, fatigue relaxes ---
    def tick(self) -> List[int]:
        """Returns ids of streams whose pressure crossed the interoceptive wake line."""
        woke = []
        for sid, s in list(self.active.items()):
            s.fatigue *= self.cfg.fatigue_decay
            if s.deferred:
                s.pressure += self.cfg.pressure_growth
                if s.pressure >= self.cfg.pressure_wake:
                    woke.append(sid)
        # suspended deferred streams also build pressure (they insist)
        for sid, s in list(self.warm.items()):
            if s.deferred:
                s.pressure += self.cfg.pressure_growth
                if s.pressure >= self.cfg.pressure_wake:
                    woke.append(sid)
        return woke
