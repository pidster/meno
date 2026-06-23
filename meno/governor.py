"""The cost governor — a circuit-breaker on expensive cognition (D32).

A continuously-running mind can run away: a hot loop synthesising every pass, or an
unbounded curiosity reach, burns real model calls without limit. The governor counts
"deep ops" — Tier-3 synthesis, the outward curiosity reach, and the dream, the very
operations that cost paid model calls online — over a rolling window of cycles. When the
windowed count exceeds the budget it TRIPS, and the driver throttles: it skips the dream
and the mind suppresses the outward reach and Tier-3 while throttled. Cheap heartbeat
cognition continues — the agent is slowed, never stopped (containment, not a kill switch).

Self-regulating: throttling suppresses the ops it counts, so the windowed rate falls and
the breaker resets (with hysteresis, at `budget * resume_ratio`). It counts deep ops, not
wall-clock or tokens, so it is deterministic and testable offline (where the same ops run
free) and bounds cost online (where they map to real calls). A budget of 0 disables it.
"""
from __future__ import annotations

from collections import deque


class CostGovernor:
    def __init__(self, cfg) -> None:
        self.window = max(1, getattr(cfg, "cost_window_cycles", 20))
        self.budget = max(0, getattr(cfg, "cost_budget_per_window", 0))
        self.resume_at = self.budget * getattr(cfg, "cost_resume_ratio", 0.5)
        self._samples: deque = deque(maxlen=self.window)
        self.tripped = False
        self.trips = 0                               # lifetime trip count (telemetry)

    @property
    def enabled(self) -> bool:
        return self.budget > 0

    def observe(self, deep_ops: int) -> bool:
        """Record one cycle's deep-op count; update the breaker; return the new throttle
        state. With the breaker disabled (budget 0) it never trips."""
        self._samples.append(max(0, int(deep_ops)))
        if not self.enabled:
            return False
        total = sum(self._samples)
        if not self.tripped and total >= self.budget:
            self.tripped = True
            self.trips += 1
        elif self.tripped and total <= self.resume_at:
            self.tripped = False                     # rate fell back -> resume (hysteresis)
        return self.tripped

    @property
    def windowed(self) -> int:
        return sum(self._samples)

    def health(self) -> dict:
        """Operator-facing breaker state for the status surface."""
        return {"enabled": self.enabled, "throttled": self.tripped,
                "windowed": self.windowed, "budget": self.budget, "trips": self.trips}
