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
                 sense_every: int = 1, idle_backoff: float = 0.02, max_backoff: float = 1.0,
                 max_inbox: int = 10000, on_error: str = "continue",
                 max_consecutive_errors: int = 5, sleep=time.sleep) -> None:
        self.mind = mind
        self.dream_every = dream_every
        self.heartbeat_ticks = heartbeat_ticks
        self.sense_every = sense_every             # poll afferent sensors every N cycles
        self.sensors: list = []
        self.idle_backoff = idle_backoff
        self.max_backoff = max_backoff
        self.on_error = on_error                   # "continue" (resilient) | "stop" (loud, for strict)
        self.max_consecutive_errors = max_consecutive_errors
        self._sleep = sleep                       # injectable for tests
        self._inbox: "queue.Queue[tuple]" = queue.Queue(maxsize=max_inbox)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.cycles = 0
        self.dreams = 0
        self.idle_cycles = 0
        self.errors = 0
        self.dropped_input = 0
        self.last_error: Optional[str] = None
        self._backoff = 0.0

    # --- thread-safe ingress (callable from any thread / sensor) --------------
    def feed(self, text: str, source: str = "sensor", **payload) -> None:
        """Enqueue a stimulus. Safe to call from any thread; the driver thread
        delivers it to the mind on the next cycle. The inbox is BOUNDED — a fast
        sensor outrunning slow cognition drops the newest input (counted in
        `dropped_input`) rather than growing without limit (R2 review P1)."""
        try:
            self._inbox.put_nowait((text, source, payload))
        except queue.Full:
            self.dropped_input += 1

    @property
    def pending_input(self) -> int:
        return self._inbox.qsize()

    # --- afferent sensors (the world reaching in) -----------------------------
    def add_sensor(self, sensor) -> None:
        """Attach a live afferent channel. The driver polls it every `sense_every`
        cycles and feeds whatever it returns through the same bounded ingress."""
        self.sensors.append(sensor)

    def _poll_sensors(self) -> None:
        for sensor in self.sensors:
            try:
                for text, source, payload in sensor.poll():
                    self.feed(text, source=source, **payload)
            except Exception as exc:              # a flaky sensor must not kill the loop
                self.errors += 1
                self.last_error = f"sensor {type(sensor).__name__}: {type(exc).__name__}: {exc}"

    # --- one autonomous cycle -------------------------------------------------
    def step(self) -> CycleReport:
        self.cycles += 1
        if self.sensors and self.cycles % self.sense_every == 0:
            self._poll_sensors()
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
        Returns the number of cycles run. Deterministic given a no-op sleep.

        A cycle that raises does NOT silently end the agent's life (R2 review P0):
        with ``on_error="continue"`` (default) the error is recorded and the loop
        backs off and carries on — one transient model blip mustn't stop a
        default-mode loop — until `max_consecutive_errors` in a row, then it gives
        up loudly (`last_error` set). ``on_error="stop"`` aborts on the first error,
        for strict accumulation runs that must not proceed through degradation."""
        n = 0
        consecutive = 0
        while not self._stop.is_set():
            if max_cycles is not None and n >= max_cycles:
                break
            try:
                rep = self.step()
                consecutive = 0
            except Exception as exc:               # a model/kernel error, not a stop
                self.errors += 1
                consecutive += 1
                self.last_error = f"cycle {self.cycles}: {type(exc).__name__}: {exc}"
                n += 1
                if self.on_error == "stop" or consecutive >= self.max_consecutive_errors:
                    break
                self._sleep(min(self.max_backoff, self.idle_backoff * (2 ** consecutive)))
                continue
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

    def stop(self, timeout: float = 5.0) -> bool:
        """Signal the loop and join. Returns True if the thread actually stopped;
        False if the join timed out (the thread is still finishing its current
        cycle). On timeout the handle is KEPT and `running` stays truthful — we
        never claim the kernel is free while a cycle is still mutating it (R2
        review P0)."""
        self._stop.set()
        t = self._thread
        if t is None:
            return True
        t.join(timeout)
        if t.is_alive():
            return False
        self._thread = None
        return True

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def telemetry(self) -> dict:
        return {"cycles": self.cycles, "dreams": self.dreams,
                "idle_cycles": self.idle_cycles, "pending_input": self.pending_input,
                "errors": self.errors, "dropped_input": self.dropped_input,
                "last_error": self.last_error, "running": self.running}
