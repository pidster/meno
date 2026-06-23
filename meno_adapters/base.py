"""The Adapter contract — the seam between the world and the stdlib kernel (I0a).

Designed against I1 (afferent channels) and I2 (gated effectors), not just loopback.

  - **Afferent (sense).** `poll()` returns percepts the driver feeds in — polled on
    the driver's cadence, guarded so a flaky channel can't kill the loop, the same
    discipline as R4's `FilesystemSensor` (so I1's bounds/redaction template carries
    straight over). A channel that needs a long-lived subscription (a websocket) may
    instead use `start(driver)`/`stop()` to push via `driver.feed`; `start` is guarded
    by the driver. Afferent percepts are **SENSE** — the world reaching in. The world's
    *reply* to one of Meno's outbound actions re-enters here, afferently, as SENSE too
    — it is the world speaking, not Meno's own proprioception.

  - **Efferent (act).** `handles(action)` claims an outbound action; `deliver(payload)`
    performs it OFF the mind thread (a Driver worker calls it) and returns a structured
    `DeliveryResult`. The result's `detail` is fed back as **FEEDBACK** (proprioception
    of *my own* action — distinct from the world's SENSE). The structured result is
    what gives I2 its gating seam: a send can be `delivered`, `refused` (disabled /
    out of scope / rate-limited — carry the reason for the audit trail), or `pending`
    (confirm-first: not sent yet, and crucially NOT fed back and NOT blocking the
    worker — a later confirmation completes it).

The network SDKs an adapter imports live in THIS package, never in `meno/`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

# what `poll()` yields: (text, source, payload) — the same shape a Sensor yields, so
# the driver polls sensors and adapters through one guarded path.
Percept = Tuple[str, str, dict]


@dataclass
class DeliveryResult:
    """The outcome of an outbound action. `status` lets the driver tell a refusal from
    a send from a deferral — so the mind *feels* the difference (it does not for a bare
    string), and so I2's gating has somewhere to report scope/rate/confirm.

    `reference` distinguishes a *knowledge* result (K3) from a *proprioceptive* one: a
    posted message feeds back as FEEDBACK (encoded as experience), but a looked-up fact
    must re-enter as a REFERENCE (read, never encoded) and be curated into the Library.
    When set, it carries `{key, body, source}` and the driver re-enters it that way."""
    status: str          # "delivered" | "refused" | "pending"
    detail: str          # proprioceptive text (fed back as FEEDBACK), unless pending
    reason: str = ""     # refused: "disabled" | "scope" | "rate" | ... (audit/telemetry)
    reference: "Optional[dict]" = None   # K3: {key, body, source} — re-enter as REFERENCE + curate

    @property
    def feeds_back(self) -> bool:
        return self.status != "pending"   # a pending (confirm-first) send hasn't happened yet


class Adapter:
    name = "adapter"
    # The hosts this adapter actually reaches on the network — declared, so the egress
    # boundary checks the adapter's REAL reach, not a field the generative mind
    # volunteers. An adapter with network reach lists its hosts (e.g. SlackAdapter:
    # ("slack.com", "*.slack.com")); a local/loopback adapter declares none.
    hosts: tuple = ()

    # --- afferent (sense) ---
    def poll(self) -> List[Percept]:
        """Return any percepts available now (non-blocking). Polled on the driver
        cadence, guarded. Default: nothing (a push-only or efferent-only adapter)."""
        return []

    def start(self, driver) -> None:
        """Optional: begin a long-lived afferent subscription that pushes via
        `driver.feed`. Guarded by the driver. Default: no-op (poll-based adapters)."""

    def stop(self) -> None:
        """Stop the afferent producer. Idempotent. Default: no-op."""

    # --- efferent (act) ---
    def handles(self, action) -> bool:
        """Does this adapter perform `action` (the outbound INTENT's action kind)?"""
        return False

    def deliver(self, payload: dict) -> "DeliveryResult":
        """Perform the outbound action OFF the mind thread (may block on I/O) and
        return a structured result. I2 overrides to gate (refuse/pending) before any
        network call."""
        raise NotImplementedError
