"""R3 — lifetime-growth hardening (D19). These bounds only bite in a long-lived
process (which R2's continuous driver makes real). Each test drives the relevant
structure past its bound and asserts it stays bounded — and that the FORGETTING
stays principled (the durable trace survives; retirement is grief, not GC).
"""
import tempfile

from meno import Config, Meno, StubModelProvider
from meno.bus import Bus
from meno.embeddings import HashingEmbedding
from meno.event import Event, Kind
from meno.streams import StreamManager


def mind(**cfg) -> Meno:
    return Meno(config=Config(**cfg), embed=HashingEmbedding(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_life_"))


# --- A1: the episodic log is a bounded ring; the lifetime count is not ------ #
def test_bus_log_is_bounded_but_total_is_not():
    b = Bus(log_max=100)
    for i in range(3000):
        b.publish(Event(content=f"event {i}"))
    assert len(b.log) <= 100 + 1024           # bounded ring (trimmed in chunks)
    assert b.total_published == 3000          # lifetime count survives trimming
    assert b.log[-1].content == "event 2999"  # the recent window is what's retained


def test_snapshot_events_seen_is_lifetime_not_log_length():
    m = mind(bus_log_max=50)
    for i in range(2000):
        m.bus.publish(Event(content=f"x{i}"))
    assert len(m.bus.log) < 2000                       # log was bounded
    assert m.snapshot()["events_seen"] == m.bus.total_published >= 2000


# --- A2: warm streams are reaped when cold; pressure is capped -------------- #
def _route(sm, embed, text):
    ev = Event(content=text)
    ev.embedding = embed.embed(text)
    return sm.route(ev)


def test_cold_warm_stream_is_reaped_past_ttl():
    embed = HashingEmbedding()
    sm = StreamManager(embed, Config(warm_max_idle_ticks=5))
    sid = _route(sm, embed, "an evicted train of thought")
    sm.suspend(sid)                                    # non-deferred -> warm
    assert sid in sm.warm
    for _ in range(6):
        sm.tick()
    assert sid not in sm.warm                          # aged out


def test_deferred_warm_stream_is_not_reaped_and_pressure_is_capped():
    embed = HashingEmbedding()
    cfg = Config(warm_max_idle_ticks=5)
    sm = StreamManager(embed, cfg)
    sid = _route(sm, embed, "an unfinished thought that insists")
    sm.active[sid].deferred = True
    sm.suspend(sid)                                    # deferred -> warm, insists
    for _ in range(40):
        sm.tick()
    assert sid in sm.warm                              # insists -> never reaped
    assert sm.warm[sid].pressure <= cfg.pressure_wake  # pressure capped at the wake line


# --- A3: bounded reconsolidation + reflective retirement (grief, not GC) ----- #
def _cue_with_live_anchors(m, i):
    a = m.graph.add_node(f"anchor a{i} about subject {i}").id
    b = m.graph.add_node(f"anchor b{i} about subject {i}").id
    m.graph.link(a, b, 0.6)                            # a surviving association -> not islanded
    return m.graph.store_cue([a, b], f"reflection {i}", tone=0.5,
                             conclusion=f"a conclusion {i}",
                             material=[m.graph.nodes[a].content, m.graph.nodes[b].content])


def test_reconsolidation_is_bounded_per_dream():
    m = mind(reconsolidate_cap=3, cue_retire_max_per_dream=0)
    for i in range(12):
        _cue_with_live_anchors(m, i)
    rep = m.dream()
    assert rep["reconsolidated"] == 3                  # capped, not O(lifetime)=12


def test_dead_unrecalled_reflection_is_retired_with_grief():
    m = mind(cue_retire_max_per_dream=4)
    a = m.graph.add_node("a fleeting anchor").id
    b = m.graph.add_node("another fleeting anchor").id
    cue = m.graph.store_cue([a, b], "a thought whose web will vanish", tone=0.5,
                            conclusion="gone soon", material=["a fleeting anchor"])
    del m.graph.nodes[a]                               # the web vanishes (forgotten)
    del m.graph.nodes[b]
    rep = m.dream()
    assert cue.id not in m.graph.cues                  # released
    assert rep["retired"] >= 1
    # GRIEF, not GC: the release is recorded, re-entering the bus
    assert any("let go of a reflection" in e.content and e.source == "dream"
               for e in m.bus.log)


def test_journaled_or_recalled_reflections_are_never_retired():
    m = mind(cue_retire_max_per_dream=4)
    # journaled: deliberately permanent
    j = m.graph.store_cue([], "a deliberately kept reflection", tone=0.9,
                          conclusion="frozen", journal=True)
    # recalled at least once: someone came back to it
    a = m.graph.add_node("anchor").id
    r = m.graph.store_cue([a], "a recalled reflection", tone=0.5, conclusion="seen")
    r.recalls = 1
    del m.graph.nodes[a]                               # even with its anchor gone
    m.dream()
    assert j.id in m.graph.cues and r.id in m.graph.cues   # both kept


def test_reflection_with_a_living_anchor_is_not_retired():
    m = mind(cue_retire_max_per_dream=4)
    a = m.graph.add_node("a living anchor").id
    b = m.graph.add_node("its neighbour").id
    m.graph.link(a, b, 0.6)                            # anchor not islanded
    cue = m.graph.store_cue([a, b], "still anchored", tone=0.5, conclusion="here",
                            material=["a living anchor"])
    m.dream()
    assert cue.id in m.graph.cues                      # a living web is not grief
