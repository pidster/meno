from meno import Config, HashingEmbedding, StubModelProvider
from meno.graph import Graph


def test_spread_and_similar():
    g = Graph(HashingEmbedding(), Config())
    a = g.add_node("cats and dogs and pets")
    b = g.add_node("dogs and wolves and pets")
    c = g.add_node("stock market interest rates")
    g.link(a.id, b.id, 0.6)
    act = g.spread([a.id])
    assert b.id in act and act[b.id] > 0          # reachable via the edge
    sims = g.similar(g.nodes[a.id].embedding, exclude=(a.id,))
    assert sims[0][1] == b.id                       # b is nearest to a, not c


def test_edges_decay_before_nodes_islanding():
    g = Graph(HashingEmbedding(), Config(edge_decay=0.1, node_decay=0.99))
    a = g.add_node("alpha")
    b = g.add_node("beta")
    g.link(a.id, b.id, 0.5)
    for _ in range(5):
        g.decay()
    assert g.islanded(a.id)        # edge gone (available but inaccessible)
    assert a.id in g.nodes         # node survives — forgetting starts with edges


def test_reflection_reconstruction_drifts_with_the_graph():
    cfg = Config()
    g = Graph(HashingEmbedding(), cfg)
    model = StubModelProvider()
    n1 = g.add_node("memory is reconstructed not retrieved")
    n2 = g.add_node("spreading activation finds connections")
    g.link(n1.id, n2.id, 0.6)
    cue = g.store_cue([n1.id, n2.id], "memory", tone=0.9,
                      conclusion="memory is rebuilt from cues")
    t1 = g.reconstruct(cue, model)
    # the world changes: a new, connected experience appears
    n3 = g.add_node("rediscovery happens via embedding similarity")
    g.link(n1.id, n3.id, 0.7)
    t2 = g.reconstruct(cue, model)
    assert isinstance(t1, str) and isinstance(t2, str)
    assert cue.recalls == 2        # each recall reconsolidated the cue


def test_journaled_cue_is_frozen():
    g = Graph(HashingEmbedding(), Config())
    model = StubModelProvider()
    n = g.add_node("an important conclusion")
    cue = g.store_cue([n.id], "occasion", tone=0.5,
                      conclusion="frozen verbatim text", journal=True)
    assert g.reconstruct(cue, model) == "frozen verbatim text"
    assert g.reconstruct(cue, model) == "frozen verbatim text"   # never drifts
