"""The event bus — in-process, decoupled. The single shared field through which
everything flows (the broadcast substrate of the global workspace).

Kept deliberately simple and synchronous: `publish` appends to an ingress queue
and to the raw episodic `log`. The runtime drains ingress → annotate → working
set. The episodic log is the raw experiential stream; consolidation later folds
its *committed subset* into the graph (the episodic→semantic projection).
"""
from __future__ import annotations

from collections import deque
from typing import Deque, List

from .event import Event


class Bus:
    def __init__(self, log_max: int = 4096) -> None:
        self.ingress: Deque[Event] = deque()
        self.log: List[Event] = []        # raw episodic stream, BOUNDED (a ring)
        self.total_published = 0          # lifetime count (log is trimmed; this isn't)
        self._log_max = log_max

    def publish(self, event: Event) -> None:
        self.log.append(event)
        self.ingress.append(event)
        self.total_published += 1
        # bound the episodic stream (D19/A1): the durable trace is the GRAPH, which
        # consolidation folds the committed subset into; the raw log is just the
        # recent working window. Trim oldest in chunks so it's O(1) amortised and
        # short in-burst slices (n0:) stay valid (a trim only fires far past log_max).
        if len(self.log) > self._log_max + 1024:
            del self.log[:len(self.log) - self._log_max]

    def drain(self) -> List[Event]:
        out = list(self.ingress)
        self.ingress.clear()
        return out

    def pending(self) -> bool:
        return bool(self.ingress)
