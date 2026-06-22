"""The event — the one currency. Provenance is just a tag.

The wire schema is deferred (system-design.md); these are the logical fields the
components need. Two invariants from the kernel:
  - events are commitments, not computations (a trigger that ignores emits nothing)
  - a child event inherits a *decayed* share of its parent's activation (back-pressure)
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

_ids = itertools.count(1)


class Kind(str, Enum):
    SENSE = "sense"        # afferent: pushed by the world
    SELF = "self"          # a derived thought / step output
    STORAGE = "storage"    # a write occurred (storage-as-trigger)
    INTENT = "intent"      # an action intent destined for an effector
    FEEDBACK = "feedback"  # efferent proprioception: result of an action
    REFERENCE = "reference"  # a looked-up fact from the Library: informs cognition,
                             # but is NEVER encoded as a graph node (K2 — reference is
                             # not experience; it must not contaminate the substrate)


class Status(str, Enum):
    ACTIVE = "active"
    PROVISIONAL = "provisional"
    COMMITTED = "committed"
    LAPSED = "lapsed"


@dataclass
class Event:
    content: str
    kind: Kind = Kind.SENSE
    source: str = "unknown"
    payload: dict = field(default_factory=dict)
    stream_id: Optional[int] = None
    parent_id: Optional[int] = None
    activation: float = 1.0
    surprise: float = 0.0
    depth_reached: int = 0
    embedding: Optional[list] = None
    status: Status = Status.ACTIVE
    node_id: Optional[int] = None          # graph node this event was encoded as, if any
    seen_by: set = field(default_factory=set)
    id: int = field(default_factory=lambda: next(_ids))
    created_at: float = field(default_factory=time.time)

    def child(self, content: str, *, inherit: float = 0.6, **kw) -> "Event":
        """Derive a follow-on event with decayed (inherited) activation."""
        kw.setdefault("activation", self.activation * inherit)
        kw.setdefault("parent_id", self.id)
        kw.setdefault("stream_id", self.stream_id)
        kw.setdefault("kind", Kind.SELF)
        kw.setdefault("source", "cognition")
        return Event(content=content, **kw)

    def __repr__(self) -> str:  # compact, for trace readability
        return (f"<Event#{self.id} {self.kind.value} s{self.stream_id} "
                f"act={self.activation:.2f} sur={self.surprise:.2f} d{self.depth_reached} "
                f"{self.content[:48]!r}>")
