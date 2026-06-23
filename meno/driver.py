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

import json
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .event import Kind
from .governor import CostGovernor


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
                 sense_every: int = 1, reach_every: int = 0,
                 idle_backoff: float = 0.02, max_backoff: float = 1.0,
                 max_inbox: int = 10000, on_error: str = "continue",
                 max_consecutive_errors: int = 5, sleep=time.sleep, egress=None,
                 audit_path=None) -> None:
        self.mind = mind
        self.egress = egress                       # D21 egress allowlist; gates outbound to a host
        self.audit_path = Path(audit_path) if audit_path else None   # outbound-action audit trail
        self.dream_every = dream_every
        self.heartbeat_ticks = heartbeat_ticks
        self.sense_every = sense_every             # poll afferent sensors every N cycles
        self.reach_every = reach_every             # I4: consider reaching OUT every N cycles (0 = off)
        self.sensors: list = []
        self.adapters: list = []                   # integration adapters (afferent + efferent)
        self._outbound_thread: Optional[threading.Thread] = None
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
        self.dropped_outbound = 0                  # outbound intents no adapter handled
        self.egress_denied = 0                     # outbound intents refused by the egress allowlist
        self.last_error: Optional[str] = None
        self._backoff = 0.0
        # cost governor (D32): a circuit-breaker on expensive cognition. Samples the mind's
        # deep-op delta each cycle; while tripped the loop throttles (skips dreams; the mind
        # suppresses the outward reach + Tier-3). Disabled by default budget=0 -> never trips.
        self.governor = CostGovernor(mind.cfg)
        self._last_cost = getattr(mind, "cost_units", 0)

    # --- thread-safe ingress (callable from any thread / sensor) --------------
    def feed(self, text: str, source: str = "sensor", kind: Kind = Kind.SENSE, **payload) -> None:
        """Enqueue a stimulus. Safe to call from any thread; the driver thread
        delivers it to the mind on the next cycle. The inbox is BOUNDED — a fast
        sensor outrunning slow cognition drops the newest input (counted in
        `dropped_input`) rather than growing without limit (R2 review P1). `kind`
        lets an adapter worker re-enter a result as FEEDBACK (proprioception) rather
        than a fresh SENSE."""
        try:
            self._inbox.put_nowait((text, source, kind, payload))
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
        # One guarded afferent path for both sensors (R4) and poll-based adapters (I0a):
        # a flaky channel is recorded and skipped, never fatal to the loop.
        for src in self.sensors + self.adapters:
            poll = getattr(src, "poll", None)
            if poll is None:
                continue
            try:
                for text, source, payload in poll():
                    self.feed(text, source=source, **payload)
            except Exception as exc:              # a flaky channel must not kill the loop
                self.errors += 1
                self.last_error = f"poll {type(src).__name__}: {type(exc).__name__}: {exc}"

    # --- integration adapters (afferent + efferent, the reach layer) -----------
    def add_adapter(self, adapter) -> None:
        """Attach an integration adapter. Its afferent side is started with the loop
        (it feeds percepts through the thread-safe ingress on its own schedule); its
        efferent side delivers outbound intents the mind hands to the outbox — run by
        a dedicated worker thread, OFF the mind thread, so a slow network call never
        blocks cognition (I0a). Network/async live in the adapter, never the kernel.
        The egress policy is handed to the adapter too, so its own send path enforces
        the boundary, not only the driver dispatch."""
        if self.egress is not None and getattr(adapter, "egress", "unset") is None:
            adapter.egress = self.egress
        self.adapters.append(adapter)

    def _deliver_outbound(self, payload: dict) -> bool:
        """Dispatch one outbound intent to the adapter that handles it. Runs on the
        OUTBOUND worker thread (or, in tests, via `drain_outbox_once`) — never on the
        mind thread. The structured result decides the proprioception: a delivered or
        refused action feeds back as FEEDBACK (a refusal carries its reason, so the
        mind feels 'I was blocked' distinctly from 'I acted'); a `pending` (confirm-
        first) action is NOT fed back and does NOT block the worker. An action no
        adapter handles, or one that raises, feeds back a miss — an effector is never
        blind. Returns True if an adapter handled it."""
        action = payload.get("action")
        for ad in self.adapters:
            if ad.handles(action):
                name = getattr(ad, "name", "adapter")
                # D21 egress boundary, enforced on the ADAPTER'S declared reach (not a
                # mind-authored payload field): an adapter that reaches a non-allowlisted
                # host is refused BEFORE deliver() runs — the boundary precedes the send.
                # Any per-call host the intent names is checked too.
                if self.egress is not None:
                    hosts = tuple(getattr(ad, "hosts", ())) + (
                        (payload["host"],) if payload.get("host") else ())
                    try:
                        for h in hosts:
                            self.egress.check(h)
                    except Exception as exc:
                        self.egress_denied += 1
                        self.last_error = f"egress: {exc}"
                        self._audit_outbound(name, action, "refused", "egress", str(exc))
                        self.feed(f"(egress denied: {exc})", source="driver",
                                  kind=Kind.FEEDBACK, action=None, refused="egress",
                                  proprioceptive=True)
                        return False
                try:
                    result = ad.deliver(payload)          # the slow part, off the mind thread
                    status = getattr(result, "status", "delivered")
                    ref = getattr(result, "reference", None)
                    self._audit_outbound(name, action, status,
                                         getattr(result, "reason", ""), getattr(result, "detail", ""))
                    if ref and status == "delivered":     # curate ONLY a genuinely delivered reference
                        # K3: a looked-up fact re-enters as a REFERENCE (read, NEVER
                        # encoded as experience) tagged for curation into the Library —
                        # the result of a network authority is reference, not feedback.
                        self.feed(ref.get("body", getattr(result, "detail", "")),
                                  source="reference", kind=Kind.REFERENCE, action=None,
                                  curate=True, key=ref.get("key"),
                                  provenance=ref.get("source", "lookup"), external=True)
                    elif getattr(result, "feeds_back", True):
                        # proprioception of meno's OWN outward action — it reacts to having
                        # acted (appraised) but this is NOT world-experience, so it is NOT
                        # encoded as a memory (D38 review): otherwise meno reflects on its own
                        # posts and re-voices them, a feedback loop. Mirrors REFERENCE (K2).
                        fb = {"action": None, "outbound": action, "proprioceptive": True}
                        if status == "refused":
                            fb["refused"] = getattr(result, "reason", "")
                        self.feed(getattr(result, "detail", str(result)),
                                  source=name, kind=Kind.FEEDBACK, **fb)
                except Exception as exc:                  # an effector must not be blind/fatal
                    self.errors += 1
                    self.last_error = f"adapter {name}: {type(exc).__name__}: {exc}"
                    self._audit_outbound(name, action, "error", type(exc).__name__, str(exc))
                    self.feed(f"(action {action!r} failed: {type(exc).__name__})",
                              source=name, kind=Kind.FEEDBACK, action=None, proprioceptive=True)
                return True
        # no adapter handled it: don't let the act vanish silently — feed back a miss
        self.dropped_outbound += 1
        self._audit_outbound("driver", action, "refused", "no-adapter", "")
        self.feed(f"(no adapter for action {action!r})", source="driver",
                  kind=Kind.FEEDBACK, action=None, proprioceptive=True)
        return False

    def _audit_outbound(self, adapter: str, action, outcome: str, reason: str, detail: str) -> None:
        """Durable, append-only audit of EVERY outbound decision across all adapters —
        delivered, refused (scope/rate/egress/no-adapter), error. The single outward-
        action trail the safety review weights highest; best-effort (a write failure
        never blocks a send, which can't be un-sent). Runs on the worker thread."""
        if self.audit_path is None:
            return
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            rec = {"ts": time.time(), "adapter": adapter, "action": action,
                   "outcome": outcome, "reason": reason, "detail": (detail or "")[:200]}
            with open(self.audit_path, "a") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception as exc:
            self.errors += 1
            self.last_error = f"outbound audit: {type(exc).__name__}: {exc}"

    def drain_outbox_once(self, timeout: float = 0.0) -> bool:
        """Deliver at most one queued outbound intent (deterministic test seam)."""
        try:
            payload = self.mind.outbox.get(timeout=timeout) if timeout else self.mind.outbox.get_nowait()
        except queue.Empty:
            return False
        return self._deliver_outbound(payload)

    def _outbound_loop(self) -> None:
        while not self._stop.is_set():
            try:
                payload = self.mind.outbox.get(timeout=0.05)
            except queue.Empty:
                continue
            self._deliver_outbound(payload)

    @property
    def _outbound_worker_running(self) -> bool:
        return bool(self._outbound_thread and self._outbound_thread.is_alive())

    # --- one autonomous cycle -------------------------------------------------
    def step(self) -> CycleReport:
        self.cycles += 1
        self.mind.throttled = self.governor.tripped   # apply the breaker state for this cycle (D32)
        self.mind.engage_budget = self.mind.cfg.engage_per_cycle   # I3: bound replies/cycle
        if (self.sensors or self.adapters) and self.cycles % self.sense_every == 0:
            self._poll_sensors()
        ingested = 0
        while True:                               # drain everything queued so far
            try:
                text, source, kind, payload = self._inbox.get_nowait()
            except queue.Empty:
                break
            self.mind.feed(text, source=source, kind=kind, **payload)
            ingested += 1
        reactive = self.mind.run_until_quiescent()
        quiet = self.mind.heartbeat(ticks=self.heartbeat_ticks)
        # I4: on its cadence, meno CONSIDERS reaching out unprompted (a self-directed intent
        # the adapter then gates). The model's high bar means it mostly stays quiet.
        if self.reach_every and self.cycles % self.reach_every == 0:
            self.mind.reach()
        # No background worker (deterministic run() mode)? Drain the outbox inline so a
        # run()-only deployment can still act outward — synchronous here BY DESIGN
        # (one thread, reproducible); the off-thread worker is the start() path. Drain
        # regardless of adapters so an unhandled outbound action feeds back its miss
        # (a no-op when the outbox is empty).
        if not self._outbound_worker_running:
            while self.drain_outbox_once():
                pass
        dreamed = None
        if self.dream_every and self.cycles % self.dream_every == 0:
            # the dream still runs while throttled, but CHEAPLY: consolidation skips its
            # model-call passes (merge/reconsolidation) and templates its grief, so the
            # forgetting work — including the substrate ceiling (D33) — stays enforced even
            # under the cost breaker, while the expensive generative work is withheld (D32).
            dreamed = self.mind.dream()
            self.dreams += 1
        # a dream that consolidated nothing doesn't count as activity, so a truly
        # quiescent mind can still back off across circadian beats.
        idle = (ingested == 0 and reactive == 0 and quiet == 0
                and not _dream_did_something(dreamed))
        if idle:
            self.idle_cycles += 1
        # feed this cycle's deep-op count to the governor; it sets the throttle for next
        # cycle (self-regulating: throttling suppresses the ops it counts, so it resets).
        cost_now = getattr(self.mind, "cost_units", 0)
        self.governor.observe(cost_now - self._last_cost)
        self._last_cost = cost_now
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
        for ad in self.adapters:                  # afferent: push adapters open a subscription
            try:                                  # a channel's start() must not kill the driver
                if hasattr(ad, "start"):
                    ad.start(self)
            except Exception as exc:
                self.errors += 1
                self.last_error = f"adapter start {getattr(ad, 'name', '?')}: {type(exc).__name__}: {exc}"
        if self.adapters and not (self._outbound_thread and self._outbound_thread.is_alive()):
            self._outbound_thread = threading.Thread(
                target=self._outbound_loop, name="meno-outbound", daemon=True)
            self._outbound_thread.start()
        self._thread = threading.Thread(target=self.run, name="meno-driver", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> bool:
        """Signal the loop and join. Returns True if the thread actually stopped;
        False if the join timed out (the thread is still finishing its current
        cycle). On timeout the handle is KEPT and `running` stays truthful — we
        never claim the kernel is free while a cycle is still mutating it (R2
        review P0)."""
        self._stop.set()
        for ad in self.adapters:                  # stop afferent producers
            if hasattr(ad, "stop"):
                try:
                    ad.stop()
                except Exception:
                    pass
        # Honest, symmetric join: report clean ONLY if BOTH the mind thread and the
        # outbound worker actually stopped. A `deliver` blocked in slow I/O when stop()
        # is called keeps the worker alive past the timeout — we say so (False) rather
        # than claim the kernel is free while a socket is still held (R2 review P0).
        clean = True
        ot = self._outbound_thread
        if ot is not None:
            ot.join(timeout)
            if ot.is_alive():
                clean = False
            else:
                self._outbound_thread = None
        t = self._thread
        if t is not None:
            t.join(timeout)
            if t.is_alive():
                clean = False
            else:
                self._thread = None
        return clean

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def telemetry(self) -> dict:
        return {"cycles": self.cycles, "dreams": self.dreams,
                "idle_cycles": self.idle_cycles, "pending_input": self.pending_input,
                "errors": self.errors, "dropped_input": self.dropped_input,
                "dropped_outbound": self.dropped_outbound,
                "egress_denied": self.egress_denied,
                "throttled": self.governor.tripped, "cost": self.governor.health(),
                "last_error": self.last_error, "running": self.running}
