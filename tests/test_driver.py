"""R2 — continuous operation: the driver runs the default-mode loop autonomously.

Model-agnostic (stub + hashing). The point is that Meno keeps thinking between
inputs (the substrate of accumulation), ingests input thread-safely, backs off
when idle instead of spinning, and starts/stops cleanly as a background thread —
all while the single-threaded kernel invariant holds.
"""
import tempfile
import threading
import time

from meno import Config, Driver, Meno, StubModelProvider
from meno.embeddings import HashingEmbedding


def mind() -> Meno:
    return Meno(config=Config(), embed=HashingEmbedding(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_drv_"))


def _noop_sleep(_):                      # deterministic, fast tests
    pass


def _boom(*_a, **_k):
    raise RuntimeError("cognition exploded")


def _seed(m: Meno, n: int = 4) -> None:
    for i in range(n):
        m.feed(f"a thought about topic {i} and how it connects to memory")
        m.run_until_quiescent()


# --- core loop ------------------------------------------------------------- #
def test_run_executes_a_bounded_number_of_cycles():
    d = Driver(mind(), sleep=_noop_sleep)
    assert d.run(max_cycles=10) == 10
    assert d.cycles == 10


def test_queued_input_is_ingested_on_the_next_cycle():
    m = mind()
    d = Driver(m, sleep=_noop_sleep)
    d.feed("a fresh percept about volcanoes")
    assert d.pending_input == 1
    n0 = d.pending_input
    rep = d.step()
    # the queued percept was pulled and processed this cycle (the loop may re-queue its
    # OWN outbound feedback — e.g. a knowledge-lookup miss — so the inbox need not be
    # empty afterward; what matters is the input was consumed, not that nothing followed)
    assert rep.ingested == 1 and d.pending_input < n0 + 1
    assert any("volcano" in n.content for n in m.graph.nodes.values())   # the percept was encoded


def test_dreams_fire_on_the_circadian_beat():
    m = mind()
    _seed(m)
    d = Driver(m, dream_every=3, sleep=_noop_sleep)
    for _ in range(6):
        d.feed("more material about memory and topics")
        d.step()
    assert d.dreams == 2                  # cycles 3 and 6


# --- idle behaviour: back off, don't spin ---------------------------------- #
def test_idle_mind_backs_off_geometrically_and_is_capped():
    sleeps = []
    d = Driver(mind(), idle_backoff=0.01, max_backoff=0.1,
               sleep=lambda s: sleeps.append(s))     # empty mind -> every cycle idle
    d.run(max_cycles=12)
    assert d.idle_cycles == 12
    assert sleeps, "an idle loop must sleep, not spin"
    assert sleeps == sorted(sleeps)                  # non-decreasing back-off
    assert max(sleeps) <= 0.1 and sleeps[-1] == 0.1  # capped


def test_run_can_stop_when_idle():
    d = Driver(mind(), sleep=_noop_sleep)
    n = d.run(max_cycles=100, stop_when_idle=True)
    assert n == 1                                    # empty mind is idle immediately


# --- autonomy: the agent thinks on its own between inputs ------------------ #
def test_autonomous_cycles_generate_self_initiated_activity():
    """With a seeded memory and no new input, the default-mode loop should produce
    self-generated events (curiosity reaching out / impulses resurfacing) — Meno
    thinking on its own, not merely reacting."""
    m = mind()
    _seed(m, 5)
    before = sum(e.source in ("curiosity", "initiative") for e in m.bus.log)
    d = Driver(m, sleep=_noop_sleep)
    d.run(max_cycles=15)                             # no input fed to the driver
    after = sum(e.source in ("curiosity", "initiative") for e in m.bus.log)
    assert after > before                            # it acted on its own drives


# --- autonomy is genuine, not a metronome (theory review P0) --------------- #
def test_autonomous_curiosity_varies_target_and_framing():
    """Boredom must reach for varied, neglected memories with varied framing — not
    fire the same wonder about the most-salient hub forever (the metronome the R2
    review flagged as manufactured initiative)."""
    m = mind()
    for s in ["volcanoes erupt with molten lava", "the ocean is deep and cold and dark",
              "memory is reconstructed at recall", "forests breathe out oxygen slowly",
              "music moves in time and tension"]:
        m.feed(s)
        m.run_until_quiescent()
    d = Driver(m, dream_every=50, sleep=_noop_sleep)
    d.run(max_cycles=60)
    wonders = [e.content for e in m.bus.log if e.source == "curiosity"]
    assert len(wonders) >= 3
    # not a single repeated sentence: genuine curiosity ranges over the graph
    assert len(set(wonders)) >= 2, wonders


# --- resilience: a cycle error must not silently end the agent's life ------- #
def test_run_survives_a_transient_cycle_error():
    m = mind()
    d = Driver(m, sleep=_noop_sleep)
    boom = {"n": 0}
    real_heartbeat = m.heartbeat

    def flaky(*a, **k):
        boom["n"] += 1
        if boom["n"] == 2:
            raise RuntimeError("transient model blip")
        return real_heartbeat(*a, **k)

    m.heartbeat = flaky
    d.run(max_cycles=5)                          # default on_error='continue'
    assert d.errors == 1 and "transient model blip" in d.last_error
    assert d.cycles >= 4                          # it kept going after the blip


def test_on_error_stop_aborts_loudly():
    m = mind()
    d = Driver(m, on_error="stop", sleep=_noop_sleep)
    m.heartbeat = _boom
    n = d.run(max_cycles=10)
    assert n == 1 and d.errors == 1 and d.last_error      # stopped on the first error


def test_run_gives_up_after_consecutive_errors():
    m = mind()
    d = Driver(m, max_consecutive_errors=3, sleep=_noop_sleep)
    m.heartbeat = _boom
    d.run(max_cycles=100)
    assert d.errors == 3                          # not an infinite error spin


# --- bounded ingress: drop, don't grow without limit ----------------------- #
def test_inbox_is_bounded_and_drops_newest():
    d = Driver(mind(), max_inbox=4, sleep=_noop_sleep)
    for i in range(10):
        d.feed(f"input {i}")
    assert d.pending_input == 4 and d.dropped_input == 6


# --- background thread: start / feed / stop -------------------------------- #
def test_background_loop_processes_input_and_stops_cleanly():
    m = mind()
    d = Driver(m, dream_every=4, idle_backoff=0.005, max_backoff=0.02)
    d.start()
    try:
        assert d.running
        for s in ["alpha topic", "beta topic", "gamma topic"]:
            d.feed(s)
        deadline = time.time() + 3.0
        while time.time() < deadline and (d.pending_input or not m.graph.nodes):
            time.sleep(0.01)
        assert d.pending_input == 0 and m.graph.nodes   # background loop did the work
        assert d.cycles > 0
    finally:
        d.stop()
    assert not d.running                              # clean join, thread cleared


def test_stop_reports_timeout_honestly_without_orphaning():
    """R2 review P0: on a join timeout, stop() must NOT claim the thread stopped —
    it keeps the handle and `running` stays truthful, so a caller never touches the
    mind while a cycle is still mutating it."""
    m = mind()
    slow = threading.Event()

    def slow_heartbeat(*a, **k):
        slow.wait(2.0)                                # hold the cycle open
        return 0

    m.heartbeat = slow_heartbeat
    d = Driver(m, dream_every=0, idle_backoff=0.001, max_backoff=0.001)
    d.start()
    time.sleep(0.05)                                  # let it enter a cycle
    stopped = d.stop(timeout=0.1)                     # cycle still in flight
    try:
        assert stopped is False                       # honest: did not stop in time
        assert d.running                              # handle kept, still truthful
    finally:
        slow.set()
        d.stop(timeout=2.0)
    assert not d.running
