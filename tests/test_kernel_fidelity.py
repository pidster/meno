"""Kernel-fidelity tests (P1): assert the *meaning* the theory promises, not the
mechanical surface — so the zombie failure mode the review found can't return.

These are the tests that should have existed: each pins a behaviour the
adversarial review proved was absent or inert.
"""
import tempfile

from meno import Config, HashingEmbedding, Meno, StubModelProvider
from meno.event import Event
from meno.graph import Graph
from meno.processors import Associator


def fresh(**cfg):
    return Meno(config=Config(**cfg), workspace=tempfile.mkdtemp(prefix="meno_fid_"))


def test_islanding_thins_reconstruction_then_ghosts():
    """F1 — the keystone. A reflection over a live neighbourhood reconstructs in
    full; once its edges island it goes *partial*; once the anchor also fades it
    becomes a *ghost*. The pre-fix code returned the full reflection in all three
    states (it rebuilt from the entry points' own content)."""
    g = Graph(HashingEmbedding(), Config())
    model = StubModelProvider()

    a = g.add_node("memory is reconstructed from cues")
    b = g.add_node("spreading activation finds related ideas")
    c = g.add_node("rediscovery bridges islanded nodes")
    g.link(a.id, b.id, 0.8)
    g.link(a.id, c.id, 0.8)
    cue = g.store_cue([a.id], "memory", tone=0.9, conclusion="memory is rebuilt from cues")

    full = g.reconstruct(cue, model, reconsolidate=False)
    assert not full.startswith("(partial)")          # neighbourhood reachable -> rich

    # forgetting: edges decay (before nodes) until the anchor is islanded
    for _ in range(40):
        g.decay()
    assert g.islanded(a.id)                            # edges gone, node survives
    assert g.nodes[a.id].salience >= g.cfg.recall_salience_floor   # anchor not yet faded

    partial = g.reconstruct(cue, model, reconsolidate=False)
    assert partial.startswith("(partial)")            # islanding measurably thinned recall
    assert partial != full

    # the anchor itself now fades below the salience floor -> available but inaccessible
    g.nodes[a.id].salience = 0.0
    ghost = g.reconstruct(cue, model, reconsolidate=False)
    assert "the details won't come" in ghost          # the ghost signal


def test_young_reflection_is_not_falsely_partial():
    """A freshly-formed reflection whose entry points are a chained stream is NOT
    'thin' — its anchors are still connected to each other. (Guards against the
    naive 'no neighbours == partial' reading.)"""
    g = Graph(HashingEmbedding(), Config())
    model = StubModelProvider()
    n1 = g.add_node("idea one in the stream")
    n2 = g.add_node("idea two in the stream")
    g.link(n1.id, n2.id, 0.8)                          # the stream's Hebbian chain
    cue = g.store_cue([n1.id, n2.id], "a fresh thought", tone=0.7,
                      conclusion="a coherent young reflection")
    out = g.reconstruct(cue, model, reconsolidate=False)
    assert not out.startswith("(partial)")            # connected -> full, even with no outside neighbours


def test_habituation_holds_across_bursts():
    """F5 — surprise is measured against a recency buffer, not the draining
    working set, so an identical percept in a *separate* burst habituates and
    creates no new node. (Pre-fix it was re-encoded as fully novel.)"""
    m = fresh()
    m.feed("the exact same observation")
    m.run_until_quiescent()
    n1 = m.snapshot()["nodes"]
    m.feed("the exact same observation")     # separate burst
    m.run_until_quiescent()
    assert m.snapshot()["nodes"] == n1       # habituated across the burst boundary


def test_heartbeat_does_not_storm():
    """F6 — a synthesised stream is refractory until the next dream, so initiative
    can't resume/re-defer it in a tight loop (the review measured 26 reflections
    from 4 stimuli)."""
    m = fresh(stream_match_threshold=0.2)
    for s in ["topic alpha one", "topic alpha two", "topic alpha three", "topic alpha four"]:
        m.feed(s)
        m.run_until_quiescent()
    before = m.snapshot()["reflections"]
    m.heartbeat()
    after = m.snapshot()["reflections"]
    assert after <= before + 2               # bounded — no storm
    assert after <= 5


def test_cognition_uses_graph_spreading_activation():
    """F7 — the Associator reaches resonant nodes via graph.spread (the spine),
    not just flat cosine. A node two hops away through surviving edges gets linked."""
    m = fresh()
    a = m.graph.add_node("alpha")
    b = m.graph.add_node("beta")
    c = m.graph.add_node("gamma")
    m.graph.link(a.id, b.id, 0.8)
    m.graph.link(b.id, c.id, 0.8)            # A-B-C chain; C is 2 hops from A
    ev = Event(content="alpha")
    ev.embedding = m.embed.embed("alpha")
    sid = m.streams.route(ev)
    m.streams.get(sid).node_ids = [a.id, b.id]
    ev.node_id = a.id
    key = (min(a.id, c.id), max(a.id, c.id))
    assert key not in m.graph.edges
    Associator().run(ev, m)
    assert key in m.graph.edges              # spread reached C and forged the link


def test_streams_merge_into_insight_through_the_dream():
    """F2 — convergent streams merge (model-judged) and the merge synthesises an
    'insight' reflection. Merge was previously dead code (test-only)."""
    m = fresh(stream_match_threshold=0.99, merge_threshold=0.5)
    a = Event(content="alpha beta one"); a.embedding = m.embed.embed("alpha beta one")
    b = Event(content="alpha beta two"); b.embedding = m.embed.embed("alpha beta two")
    m.streams.route(a)
    m.streams.route(b)                       # forced into separate streams
    assert a.stream_id != b.stream_id
    # give each stream a node so the insight synthesis has material
    for ev in (a, b):
        n = m.graph.add_node(ev.content)
        m.streams.get(ev.stream_id).node_ids.append(n.id)
    report = m.dream()
    assert report["merges"] >= 1
    assert any(c.occasion.startswith("insight") for c in m.graph.cues.values())


def test_islanded_node_is_rediscovered_in_the_dream():
    """F4 — a recently-added node bridges to an islanded one it resembles,
    recovering it. Wires the formerly-dead similar()/islanded()."""
    m = fresh()
    a = m.graph.add_node("volcano lava eruption magma")
    b = m.graph.add_node("volcano lava eruption magma flow")
    m.graph.link(a.id, b.id, 0.5)
    m.graph.edges.clear()                    # island everything (edges gone, nodes remain)
    assert m.graph.islanded(b.id)
    m.graph.add_node("volcano lava eruption magma stream")   # a bridging new percept
    report = m.dream()
    assert report["rediscovered"] >= 1
    assert not m.graph.islanded(b.id)        # brought back via a path that did not exist
