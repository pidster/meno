import tempfile

from meno import Config, Kind, Meno
from meno.sensorium import fs_read_intent, fs_write_intent


def fresh(**cfg):
    return Meno(config=Config(**cfg), workspace=tempfile.mkdtemp(prefix="meno_test_"))


def test_percept_becomes_memory():
    m = fresh()
    m.feed("associative memory and spreading activation are the spine")
    m.feed("spreading activation surfaces unexpected connections in memory")
    m.run_until_quiescent()
    assert m.snapshot()["nodes"] >= 2
    assert m.bus.log                      # something flowed


def test_habituation_at_the_gate():
    m = fresh()
    # two identical percepts in the same burst: the second sees the first still hot
    m.feed("the exact same observation twice")
    m.feed("the exact same observation twice")
    m.run_until_quiescent()
    assert m.snapshot()["nodes"] == 1     # the repeat habituated, no new node


# sentences sharing strong vocabulary so they cohere into one stream
_MEMORY_TOPIC = [
    "memory reconstruction recall is associative and surprising one",
    "memory reconstruction recall keeps developing surprisingly two",
    "memory reconstruction recall connects across the graph three",
]


def test_reflection_forms_and_storage_is_a_trigger():
    m = fresh(stream_match_threshold=0.2)
    for s in _MEMORY_TOPIC:
        m.feed(s)
        m.run_until_quiescent()
    m.heartbeat()                          # initiative works any deferred backlog
    assert m.snapshot()["reflections"] >= 1
    # forming a reflection re-entered the loop as a STORAGE event
    assert any(e.kind == Kind.STORAGE for e in m.bus.log)


def test_tiered_recall():
    m = fresh(stream_match_threshold=0.2)
    for s in _MEMORY_TOPIC:
        m.feed(s)
        m.run_until_quiescent()
    m.heartbeat()
    hit = m.recall("memory reconstruction recall associative")
    assert hit["mode"] in ("reconstructed", "ghost")
    miss = m.recall("quantum chromodynamics lattice gauge theory")
    assert miss["mode"] == "none"


def test_interoceptive_initiative_produces_reflection_when_deep_budget_scarce():
    # deep budget of 1 forces all-but-one stream to defer; the heartbeat must
    # resurface them and produce the deferred reflections (initiative).
    m = fresh(deep_per_pass=1)
    for s in ["topic alpha is fascinating and surprising and deep",
              "topic alpha keeps developing in surprising new directions",
              "topic beta is entirely different yet equally surprising deep",
              "topic beta also develops along its own surprising path"]:
        m.feed(s)
        m.run_until_quiescent()
    before = m.snapshot()["reflections"]
    m.heartbeat()
    after = m.snapshot()["reflections"]
    assert after >= before                 # initiative did not lose work
    assert after >= 1


def test_effector_acts_and_feeds_back():
    m = fresh()
    m.submit(fs_write_intent("note.txt", "hello meno"))
    m.run_until_quiescent()
    assert (m.workspace / "note.txt").read_text() == "hello meno"
    assert any(e.kind == Kind.FEEDBACK for e in m.bus.log)
    m.submit(fs_read_intent("note.txt"))
    m.run_until_quiescent()
    assert any("hello meno" in e.content for e in m.bus.log if e.kind == Kind.FEEDBACK)


def test_runs_bounded_no_storm():
    # the tamed dynamics: a handful of stimuli must not explode the graph
    m = fresh()
    for s in ["one observation", "another observation", "a third observation",
              "one observation"]:
        m.feed(s)
        m.run_until_quiescent()
    snap = m.snapshot()
    assert snap["nodes"] < 50
    assert snap["events_seen"] < 200
