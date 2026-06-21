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


def test_ghost_reflection_persists_then_is_released_with_grief_after_ttl():
    """A reflection whose web vanishes is a GHOST: not deleted on the spot (that
    would skip the islanding tier the theory prizes), but carried for cue_ghost_ttl
    dreams, then RELEASED — and the agent reflects on the loss (grief), it isn't
    silently collected."""
    m = mind(cue_ghost_ttl=2, cue_retire_max_per_dream=4)
    a = m.graph.add_node("a fleeting anchor about an old idea").id
    cue = m.graph.store_cue([a], "a thought whose web will vanish", tone=0.5,
                            conclusion="gone soon", material=["a fleeting anchor about an old idea"])
    del m.graph.nodes[a]                               # the web vanishes (no recent nodes to recover it)
    m.dream()
    assert cue.id in m.graph.cues and m.graph.cues[cue.id].ghost_ticks == 1   # carried, not deleted
    rep = m.dream()                                    # ghost_ticks reaches the ttl
    assert cue.id not in m.graph.cues                  # released
    assert rep["retired"] >= 1
    # GRIEF: a reflection ABOUT the loss now exists (the agent registers the gap)
    assert any(c.occasion.startswith("released:") for c in m.graph.cues.values())


def test_islanded_ghost_reflection_can_be_rediscovered():
    """The islanding tier earns its keep: a ghost reflection is recovered when a
    recent, semantically-similar memory re-recognises its gist — 'by a route that
    did not exist when it was lost' — rather than being destroyed."""
    m = mind(cue_ghost_ttl=3, rediscovery_threshold=0.3)
    a = m.graph.add_node("volcano eruption magma lava deep heat").id
    cue = m.graph.store_cue([a], "volcanic activity and magma", tone=0.5,
                            conclusion="volcanoes erupt magma and lava from deep heat",
                            material=["volcano eruption magma lava deep heat"])
    del m.graph.nodes[a]                               # islanded -> ghost
    b = m.graph.add_node("magma and lava from a deep volcanic eruption of heat").id
    m.dream()
    assert b in m.graph.cues[cue.id].entry_points      # re-anchored via gist recognition
    assert m.graph.cues[cue.id].ghost_ticks == 0       # recovered, ghost cleared


def test_journaled_or_recalled_reflections_never_become_ghosts():
    m = mind(cue_ghost_ttl=1, cue_retire_max_per_dream=4)
    j = m.graph.store_cue([], "a deliberately kept reflection", tone=0.9,
                          conclusion="frozen", journal=True)
    a = m.graph.add_node("anchor").id
    r = m.graph.store_cue([a], "a recalled reflection", tone=0.5, conclusion="seen")
    r.recalls = 1
    del m.graph.nodes[a]
    m.dream()
    m.dream()
    assert j.id in m.graph.cues and r.id in m.graph.cues   # both kept, anchored to the self


def test_reflection_with_a_living_anchor_is_not_a_ghost():
    m = mind(cue_ghost_ttl=1)
    a = m.graph.add_node("a living anchor").id
    b = m.graph.add_node("its neighbour").id
    m.graph.link(a, b, 0.6)                            # anchor not islanded
    cue = m.graph.store_cue([a, b], "still anchored", tone=0.5, conclusion="here",
                            material=["a living anchor"])
    m.dream()
    m.dream()
    assert cue.id in m.graph.cues and m.graph.cues[cue.id].ghost_ticks == 0
