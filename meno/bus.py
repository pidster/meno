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
    def __init__(self) -> None:
        self.ingress: Deque[Event] = deque()
        self.log: List[Event] = []        # raw episodic stream

    def publish(self, event: Event) -> None:
        self.log.append(event)
        self.ingress.append(event)

    def drain(self) -> List[Event]:
        out = list(self.ingress)
        self.ingress.clear()
        return out

    def pending(self) -> bool:
        return bool(self.ingress)
