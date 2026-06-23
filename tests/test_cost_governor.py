"""Pathology containment — the cost governor + the health surface (D32).

The governor is a circuit-breaker on EXPENSIVE cognition: it counts deep ops (Tier-3
synthesis, the outward curiosity reach, the dream) over a rolling window and, when the
windowed count exceeds the budget, TRIPS — the driver then throttles (skips dreams; the
mind suppresses the reach + Tier-3) until the rate falls back. Containment, not a kill
switch: cheap heartbeat cognition keeps running. Offline/deterministic.
"""
import tempfile

from meno import Config, Driver, Meno, StubModelProvider
from meno.event import Event, Kind
from meno.governor import CostGovernor
from meno.processors import Synthesiser


def _mind(**cfg):
    return Meno(config=Config(**cfg), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_gov_"))


# --- the governor in isolation ---------------------------------------------------- #
def test_a_zero_budget_governor_never_trips():
    g = CostGovernor(Config(cost_budget_per_window=0))
    assert g.enabled is False
    for _ in range(100):
        assert g.observe(1000) is False             # disabled: nothing trips it
    assert g.tripped is False and g.trips == 0


def test_governor_trips_when_the_windowed_deep_op_count_exceeds_budget():
    g = CostGovernor(Config(cost_window_cycles=5, cost_budget_per_window=10))
    assert g.observe(4) is False                    # 4
    assert g.observe(4) is False                    # 8 — still under
    assert g.observe(4) is True                     # 12 >= 10 — trips
    assert g.tripped and g.trips == 1


def test_governor_resets_with_hysteresis_when_the_rate_falls_back():
    g = CostGovernor(Config(cost_window_cycles=4, cost_budget_per_window=8, cost_resume_ratio=0.5))
    g.observe(8)                                    # trips immediately (8 >= 8)
    assert g.tripped
    # four quiet cycles push the burst out of the 4-wide window; resets at <= 8*0.5 = 4
    for _ in range(4):
        g.observe(0)
    assert g.tripped is False and g.windowed == 0
    assert g.health()["trips"] == 1                 # the trip is remembered for telemetry


# --- the containment gate: throttle WITHHOLDS Tier-3 (it defers, not discards) ----- #
def test_throttle_withholds_tier3_synthesis():
    mind = _mind()
    synth = Synthesiser()
    ev = Event(content="returning to an unfinished thought", kind=Kind.SELF,
               source="initiative", stream_id=1)
    ev.payload["role"] = "wake"                     # a resurfaced impulse always WANTS depth
    mind.deep_budget = 1
    mind.throttled = False
    assert synth.wants(ev, mind) is True and synth.triggers(ev, mind) is True
    mind.throttled = True
    assert synth.wants(ev, mind) is True            # it still wants it...
    assert synth.triggers(ev, mind) is False        # ...but the breaker withholds the slot


def test_throttle_suppresses_the_outward_curiosity_reach():
    mind = _mind()
    for t in ["otters raft in kelp beds", "kelp anchors a floating raft",
              "sea otters hold paws while sleeping"]:
        mind.feed(t, source="test")                # give it memory to be curious ABOUT
    mind.run_until_quiescent()
    before = mind.cost_units
    mind.throttled = True
    for _ in range(10):                            # boredom accrues across beats (idle, no input)
        mind.heartbeat(ticks=2)
    assert mind.cost_units == before               # throttled: the outward reach stays suppressed
    mind.throttled = False
    for _ in range(10):
        mind.heartbeat(ticks=2)
    assert mind.cost_units > before                # un-throttled: it reaches (a wonder = a deep op)


# --- the driver wiring: a burst trips it, throttling skips the dream, then it recovers #
def test_a_cost_burst_throttles_the_loop_then_it_self_recovers():
    mind = _mind(cost_window_cycles=4, cost_budget_per_window=6, cost_resume_ratio=0.5,
                 # dream every cycle so we can see it get skipped while throttled
                 )
    driver = Driver(mind, sleep=lambda _: None, dream_every=1)
    mind.cost_units += 20                            # simulate a deep-op burst this cycle
    driver.step()
    assert driver.governor.tripped is True           # the burst tripped the breaker
    dreams_at_trip = driver.dreams
    driver.step()                                    # next cycle applies the throttle
    assert mind.throttled is True
    assert driver.dreams == dreams_at_trip           # the (expensive) dream was skipped
    # quiet cycles drain the window; the breaker resets and the dream resumes
    for _ in range(6):
        driver.step()
    assert driver.governor.tripped is False and mind.throttled is False
    assert driver.dreams > dreams_at_trip            # dreaming resumed after recovery


def test_the_governor_is_inert_by_default_so_ordinary_runs_never_throttle():
    mind = _mind()                                   # default budget (60) — a generous backstop
    driver = Driver(mind, sleep=lambda _: None)
    driver.run(max_cycles=30)
    assert driver.governor.tripped is False and driver.governor.trips == 0


# --- the health surface: status.json carries the operational signals -------------- #
def test_status_json_carries_a_health_block():
    from pathlib import Path
    import json
    from meno.cli import run_instance
    from meno.home import init_home
    home = init_home(Path(tempfile.mkdtemp(prefix="meno_health_")) / "inst", handle="meno-h")
    inst = run_instance(home, max_cycles=4, status_every=2, sleep=lambda _: None,
                        feed=["a thought to chew on"])
    data = json.loads(inst.status_path.read_text())
    h = data["health"]
    for key in ("idle_fraction", "pending_input", "dropped_input", "egress_denied",
                "throttled", "cost", "cognition_degraded"):
        assert key in h, key
    assert h["cost"]["enabled"] in (True, False) and "windowed" in h["cost"]
