"""The driver: runs Meno's default-mode loop autonomously and continuously.

The kernel is synchronous and step-driven (decision D7) for reproducibility; this
is the thin wrapper the roadmap calls for, turning the step functions into a
living loop. One CYCLE is:

    ingest queued input -> reactive burst (run_until_quiescent)
                        -> quiet phase (heartbeat: initiative + curiosity)
                        -> a dream on the circadian beat

so the agent keeps thinking between inputs — wondering, resurfacing deferred
impulses, consolidating — which is the substrate of accumulative experience. When
genuinely nothing is happening the loop BACKS OFF (an idle sleep that grows toward
a cap) instead of spinning, so an idle mind is cheap.

**Threading invariant.** The mind is owned by exactly ONE thread (the driver loop).
External input arrives through a thread-safe queue via `feed()`, never by touching
the mind's bus directly (its drain is not atomic against concurrent appends). So
the single-threaded kernel invariant — and its reproducibility — is preserved even
under live sensors. `run(max_cycles=...)` is the deterministic, testable core;
`start()`/`stop()` wrap it in a background thread for real continuous operation.
"""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class CycleReport:
    cycle: int
    ingested: int                 # inputs pulled from the queue this cycle
    reactive_steps: int           # run_until_quiescent steps
    quiet_steps: int              # heartbeat steps (initiative + curiosity)
    dreamed: Optional[dict]       # dream report if the circadian beat fired
    idle: bool                    # nothing happened -> the loop backs off


def _dream_did_something(report: Optional[dict]) -> bool:
    return bool(report) and any(report.values())


class Driver:
    def __init__(self, mind, *, dream_every: int = 8, heartbeat_ticks: int = 8,
                 idle_backoff: float = 0.02, max_backoff: float = 1.0,
                 sleep=time.sleep) -> None:
        self.mind = mind
        self.dream_every = dream_every
        self.heartbeat_ticks = heartbeat_ticks
        self.idle_backoff = idle_backoff
        self.max_backoff = max_backoff
        self._sleep = sleep                       # injectable for tests
        self._inbox: "queue.Queue[tuple]" = queue.Queue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.cycles = 0
        self.dreams = 0
        self.idle_cycles = 0
        self._backoff = 0.0

    # --- thread-safe ingress (callable from any thread / sensor) --------------
    def feed(self, text: str, source: str = "sensor", **payload) -> None:
        """Enqueue a stimulus. Safe to call from any thread; the driver thread
        delivers it to the mind on the next cycle."""
        self._inbox.put((text, source, payload))

    @property
    def pending_input(self) -> int:
        return self._inbox.qsize()

    # --- one autonomous cycle -------------------------------------------------
    def step(self) -> CycleReport:
        self.cycles += 1
        ingested = 0
        while True:                               # drain everything queued so far
            try:
                text, source, payload = self._inbox.get_nowait()
            except queue.Empty:
                break
            self.mind.feed(text, source=source, **payload)
            ingested += 1
        reactive = self.mind.run_until_quiescent()
        quiet = self.mind.heartbeat(ticks=self.heartbeat_ticks)
        dreamed = None
        if self.dream_every and self.cycles % self.dream_every == 0:
            dreamed = self.mind.dream()
            self.dreams += 1
        # a dream that consolidated nothing doesn't count as activity, so a truly
        # quiescent mind can still back off across circadian beats.
        idle = (ingested == 0 and reactive == 0 and quiet == 0
                and not _dream_did_something(dreamed))
        if idle:
            self.idle_cycles += 1
        return CycleReport(self.cycles, ingested, reactive, quiet, dreamed, idle)

    # --- the loop -------------------------------------------------------------
    def run(self, max_cycles: Optional[int] = None, *, stop_when_idle: bool = False) -> int:
        """Drive cycles until stopped / max_cycles / (optionally) the mind goes idle.
        Returns the number of cycles run. Deterministic given a no-op sleep."""
        n = 0
        while not self._stop.is_set():
            if max_cycles is not None and n >= max_cycles:
                break
            rep = self.step()
            n += 1
            if rep.idle:
                if stop_when_idle:
                    break
                self._backoff = min(self.max_backoff,
                                    (self._backoff or self.idle_backoff) * 2)
                self._sleep(self._backoff)        # cheap idle: grow the gap, don't spin
            else:
                self._backoff = 0.0               # active: full speed, no sleep
        return n

    # --- background continuous operation --------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self.run, name="meno-driver", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)
            self._thread = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def telemetry(self) -> dict:
        return {"cycles": self.cycles, "dreams": self.dreams,
                "idle_cycles": self.idle_cycles, "pending_input": self.pending_input,
                "running": self.running}
