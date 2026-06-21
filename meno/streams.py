"""Streams: the logical trains of thought. Lifecycle = born / merge / suspend /
resume / end (redesign.md). Threads (the workers) are separate and have no
lifecycle; streams do. Streams — not events — are the unit eviction protects.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import Config
from .embeddings import EmbeddingModel, cosine
from .event import Event


@dataclass
class Stream:
    centroid: List[float]
    pressure: float = 0.0           # deferred-impulse pressure (builds while unattended-but-wanted)
    fatigue: float = 0.0            # lateral inhibition (rises when worked hard)
    deferred: bool = False          # wanted deep work but couldn't afford it
    refractory: bool = False        # just synthesised — can't re-fire until the next dream (F6)
    suspended: bool = False
    idle_ticks: int = 0             # ticks spent cold in `warm` -> reaped past a TTL (D19/A2)
    event_ids: List[int] = field(default_factory=list)
    node_ids: List[int] = field(default_factory=list)   # graph nodes encoded from this stream
    summary: str = ""
    id: int = 0                     # assigned by StreamManager.route (per-instance, D15)
    last_active: float = field(default_factory=time.time)


class StreamManager:
    def __init__(self, embed: EmbeddingModel, config: Config) -> None:
        self.embed = embed
        self.cfg = config
        self.active: Dict[int, Stream] = {}
        self.warm: Dict[int, Stream] = {}   # suspended, resumable
        self._stream_seq = 0                 # per-instance id counter (D15)

    def get(self, sid: Optional[int]) -> Optional[Stream]:
        if sid is None:
            return None
        return self.active.get(sid)

    # --- born / route (cheap, Tier-0-ish: similarity to centroids) ---
    def route(self, event: Event) -> int:
        if event.stream_id is not None and event.stream_id in self.active:
            self._absorb(event)
            return event.stream_id
        # pick the genuinely best-matching stream, THEN test the threshold.
        # seed at -inf so zero/negative cosines can still win (a 0.0 seed silently
        # rejected them, making low thresholds a no-op — D15/M2).
        best_id, best_sim = None, float("-inf")
        for sid, s in self.active.items():
            sim = cosine(event.embedding, s.centroid)
            if sim > best_sim:
                best_id, best_sim = sid, sim
        if best_id is not None and best_sim >= self.cfg.stream_match_threshold:
            event.stream_id = best_id
            self._absorb(event)
            return best_id
        # born: a new line of thought
        self._stream_seq += 1
        s = Stream(centroid=list(event.embedding), summary=event.content[:60], id=self._stream_seq)
        self.active[s.id] = s
        event.stream_id = s.id
        self._absorb(event)
        return s.id

    def _absorb(self, event: Event) -> None:
        s = self.active[event.stream_id]
        s.event_ids.append(event.id)
        # window the id list so a long-lived stream's event_ids can't grow without
        # bound (D19 int-list leak); only recent material is ever read (merge, synth).
        w = self.cfg.stream_material_window
        if len(s.event_ids) > w:
            s.event_ids = s.event_ids[-w:]
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
        w = self.cfg.stream_material_window
        a.event_ids = (a.event_ids + b.event_ids)[-w:]
        a.node_ids = (a.node_ids + b.node_ids)[-w:]
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

    # --- autonomic tick: pressure builds, fatigue relaxes, cold warm streams reaped ---
    def tick(self) -> List[int]:
        """Returns ids of streams whose pressure crossed the interoceptive wake line.

        Pressure is CAPPED at the wake line (D19/A2): an impulse insists until it is
        granted the slot, it does not grow without bound. Suspended (warm) streams
        that stay cold past `warm_max_idle_ticks` are reaped — a dormant train of
        thought nobody returned to is released; its graph nodes persist, so the
        thinking it produced isn't lost, only the idle thread object."""
        woke = []
        wake = self.cfg.pressure_wake
        for sid, s in list(self.active.items()):
            s.fatigue *= self.cfg.fatigue_decay
            if s.deferred:
                s.pressure = min(s.pressure + self.cfg.pressure_growth, wake)
                if s.pressure >= wake:
                    woke.append(sid)
        for sid, s in list(self.warm.items()):
            if s.deferred:                                  # deferred warm streams insist
                s.idle_ticks = 0
                s.pressure = min(s.pressure + self.cfg.pressure_growth, wake)
                if s.pressure >= wake:
                    woke.append(sid)
            else:                                           # cold (not wanted) -> age out
                s.idle_ticks += 1
                if s.idle_ticks > self.cfg.warm_max_idle_ticks:
                    del self.warm[sid]
        return woke
