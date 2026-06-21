"""Kernel-fidelity tests (P1): assert the *meaning* the theory promises, not the
mechanical surface — so the zombie failure mode the review found can't return.

These are the tests that should have existed: each pins a behaviour the
adversarial review proved was absent or inert.
"""
from meno import Config, HashingEmbedding, StubModelProvider
from meno.graph import Graph


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
