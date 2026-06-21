"""R2 — continuous operation: the driver runs the default-mode loop autonomously.

Model-agnostic (stub + hashing). The point is that Meno keeps thinking between
inputs (the substrate of accumulation), ingests input thread-safely, backs off
when idle instead of spinning, and starts/stops cleanly as a background thread —
all while the single-threaded kernel invariant holds.
"""
import tempfile
import time

from meno import Config, Driver, Meno, StubModelProvider
from meno.embeddings import HashingEmbedding


def mind() -> Meno:
    return Meno(config=Config(), embed=HashingEmbedding(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_drv_"))


def _noop_sleep(_):                      # deterministic, fast tests
    pass


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
    rep = d.step()
    assert rep.ingested == 1 and d.pending_input == 0
    assert m.graph.nodes                 # the percept was encoded by the loop


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
