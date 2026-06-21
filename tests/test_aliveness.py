"""R0 fidelity — the aliveness probes must DISCRIMINATE alive from zombie.

These are not mechanism tests. Each asserts that a mark scores low on a
mechanically-correct-but-dead structure and high on a particular one, and that
the aggregate verdict calls a flat mind a zombie and a lived-in mind alive. If
these pass, the zombie test in R5 measures something real; if a probe can't tell
the two apart, it is a zombie-passable checklist and fails here.
"""
import tempfile

from meno import Config, Event, Kind, Meno, StubModelProvider
from meno.embeddings import HashingEmbedding
from meno.aliveness import (
    PASS,
    _gini,
    divergence,
    initiative,
    novelty,
    particularity,
    synthesis,
    zombie_report,
)


def fresh() -> Meno:
    return Meno(config=Config(), embed=HashingEmbedding(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_alive_"))


def _ring(m: Meno, n: int, weight: float) -> Meno:
    """A tidy, uniform graph: n nodes in a ring, every edge identical. The dead
    graph — mechanically valid, utterly generic."""
    ids = [m.graph.add_node(f"node {i}").id for i in range(n)]
    for i in range(n):
        m.graph.link(ids[i], ids[(i + 1) % n], weight)
    return m


def _idiosyncratic(m: Meno) -> Meno:
    """A lived-in graph: one hub, preferential pathways of varied strength, leaves
    reachable only through it — the shape of attention that actually happened."""
    hub = m.graph.add_node("associative memory and spreading activation").id
    leaves = [m.graph.add_node(f"thought about {w}").id
              for w in ("reconstruction", "forgetting", "curiosity", "dreams", "islands")]
    for leaf, wt in zip(leaves, (0.95, 0.85, 0.2, 0.15, 0.1)):
        m.graph.link(hub, leaf, wt)
    m.graph.link(leaves[0], leaves[1], 0.7)   # a strong off-hub association
    return m


# --- the math of idiosyncrasy --------------------------------------------- #
def test_gini_uniform_is_zero_concentrated_is_high():
    assert _gini([1, 1, 1, 1]) < 0.01           # perfectly even = no idiosyncrasy
    assert _gini([0, 0, 0, 4]) > 0.6            # all weight on one path
    assert _gini([]) == 0.0


# --- 1. particularity ------------------------------------------------------ #
def test_particularity_low_for_uniform_high_for_idiosyncratic():
    flat = particularity(_ring(fresh(), 8, 0.5).graph)
    lived = particularity(_idiosyncratic(fresh()).graph)
    assert flat["score"] < PASS["particularity"]        # a ring is generic
    assert lived["score"] > flat["score"]
    assert lived["score"] >= PASS["particularity"]
    assert lived["evidence"]                             # names the hub it clustered around


# --- 2. initiative --------------------------------------------------------- #
def test_initiative_low_for_pure_reaction_high_when_self_driven():
    react = fresh()
    for s in ["a", "b", "c", "d", "e"]:
        react.feed(s)                                   # only externally fed
    assert initiative(react)["score"] < PASS["initiative"]

    driven = fresh()
    for s in ["a", "b", "c"]:
        driven.feed(s)
    driven.bus.log.append(Event(content="I wonder what connects these",
                                kind=Kind.SELF, source="curiosity"))
    driven.bus.log.append(Event(content="returning to an unfinished thought",
                                kind=Kind.SELF, source="initiative"))
    rep = initiative(driven)
    assert rep["acted_on_impulse"] and rep["score"] >= PASS["initiative"]
    assert rep["evidence"]


# --- 3. synthesis ---------------------------------------------------------- #
def test_synthesis_needs_cross_source_insight_not_restatement():
    restater = fresh()
    n = restater.graph.add_node("a lone memory").id
    restater.graph.store_cue([n], "thinking about a lone memory", tone=0.5,
                             conclusion="it is a memory")          # single-source
    assert synthesis(restater.graph)["score"] < PASS["synthesis"]

    synthesiser = fresh()
    a = synthesiser.graph.add_node("memory is reconstructed").id
    b = synthesiser.graph.add_node("forgetting enables rediscovery").id
    synthesiser.graph.store_cue([a, b], "insight: reconstruction + forgetting",
                                tone=0.9, conclusion="they are one mechanism")
    rep = synthesis(synthesiser.graph)
    assert rep["insights"] == 1 and rep["score"] >= PASS["synthesis"]


# --- 4. novelty ------------------------------------------------------------ #
def test_novelty_zero_when_echoing_input_high_when_emergent():
    echo = novelty(["the database connection pool"],
                   ["the database connection pool is exhausted"])
    assert echo["score"] < PASS["novelty"]

    emergent = novelty(["reconstructive memory hypothesis emerges from cues"],
                       ["the user asked something about a server"])
    assert emergent["score"] >= PASS["novelty"]
    assert "reconstructive" in emergent["fresh_terms"]


# --- 5. divergence --------------------------------------------------------- #
def test_divergence_zero_for_twins_high_for_distinct_histories():
    a, b = fresh(), fresh()
    for m in (a, b):
        for c in ("alpha topic", "beta topic", "gamma topic"):
            m.graph.add_node(c)
    assert divergence(a.graph, b.graph)["score"] < 0.05      # same inputs, same mind

    c, d = fresh(), fresh()
    for c_ in ("volcano lava magma", "eruption ash plume"):
        c.graph.add_node(c_)
    for d_ in ("sonata cello adagio", "fugue counterpoint baroque"):
        d.graph.add_node(d_)
    assert divergence(c.graph, d.graph)["score"] >= PASS["divergence"]


# --- aggregate verdict: the discrimination that matters -------------------- #
def test_zombie_report_calls_a_flat_mind_a_zombie():
    dead = _ring(fresh(), 8, 0.5)
    for s in ["x", "y", "z"]:
        dead.feed(s)                                        # reaction only, no insight
    rep = zombie_report(dead)
    assert rep["verdict"] == "zombie"
    assert "particularity" in rep["failed_marks"]


def test_zombie_report_calls_a_lived_in_mind_alive():
    alive = _idiosyncratic(fresh())
    # it reached out on its own...
    alive.bus.log.append(Event(content="what more is there about reconstruction?",
                               kind=Kind.SELF, source="curiosity"))
    alive.bus.log.append(Event(content="returning to forgetting",
                               kind=Kind.SELF, source="initiative"))
    alive.feed("an external nudge")
    # ...and synthesised across sources
    ids = list(alive.graph.nodes)
    alive.graph.store_cue(ids[:2], "insight: memory and forgetting are one",
                          tone=0.9, conclusion="reconstruction needs forgetting")
    rep = zombie_report(alive)
    assert rep["verdict"] == "alive", rep["failed_marks"]
    assert rep["passed"]["particularity"] and rep["passed"]["synthesis"]
