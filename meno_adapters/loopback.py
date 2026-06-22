"""LoopbackAdapter — an in-memory adapter with no network, for proving the seam (I0a).

Afferent: poll() yields one canned percept (once), the R4-style pull path. Efferent:
handles a named action and echoes it, returning a structured DeliveryResult. It can
block `deliver` on a caller-supplied gate to make the off-the-mind-thread property
deterministically testable, and records which thread actually ran the delivery.
"""
from __future__ import annotations

import threading
from typing import List, Optional, Tuple

from .base import Adapter, DeliveryResult, Percept


class LoopbackAdapter(Adapter):
    name = "loopback"

    def __init__(self, *, action: str = "echo", afferent_percept: Optional[str] = None,
                 gate: Optional[threading.Event] = None, status: str = "delivered",
                 reason: str = "") -> None:
        self.action = action
        self._pending_percept = afferent_percept           # yielded once via poll()
        self.gate = gate                                   # if set, deliver() blocks on it
        self.status = status                               # let a test force refused/pending
        self.reason = reason
        self.started = threading.Event()                   # set when deliver() begins
        self.delivered: List[Tuple[dict, str]] = []        # (payload, thread name that ran it)

    # --- afferent (poll path, like R4's FilesystemSensor) ---
    def poll(self) -> List[Percept]:
        if self._pending_percept is None:
            return []
        text, self._pending_percept = self._pending_percept, None
        return [(text, self.name, {})]

    # --- efferent ---
    def handles(self, action) -> bool:
        return action == self.action

    def deliver(self, payload: dict) -> DeliveryResult:
        self.started.set()
        if self.gate is not None:
            self.gate.wait(timeout=5.0)                    # simulate slow I/O (test-controlled)
        self.delivered.append((payload, threading.current_thread().name))
        if self.status == "delivered":
            return DeliveryResult("delivered", f"echo: {payload.get('data', '')}")
        return DeliveryResult(self.status, f"{self.status}: {payload.get('data', '')}", self.reason)
