"""R0 fidelity — the aliveness probes must DISCRIMINATE alive from zombie.

Not mechanism tests. Each asserts a mark scores low on a mechanically-correct-but-
dead structure and high on a particular one, and — the decisive test the R0 review
demanded — that a LIVE accumulating stub run (a zombie by construction) is called
zombie, including when handed the stub's own reflection text. If these pass, the
R5 zombie gate measures something real.
"""
import tempfile

from meno import Config, Event, Kind, Meno, StubModelProvider
from meno.embeddings import HashingEmbedding, make_embedder
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


def fresh(embed=None) -> Meno:
    return Meno(config=Config(), embed=embed or HashingEmbedding(),
                models=StubModelProvider(), workspace=tempfile.mkdtemp(prefix="meno_alive_"))


def _ring(m: Meno, n: int, weight: float) -> Meno:
    """A tidy, uniform graph: n nodes in a ring, every edge identical. Dead —
    mechanically valid, utterly generic."""
    ids = [m.graph.add_node(f"node {i}").id for i in range(n)]
    for i in range(n):
        m.graph.link(ids[i], ids[(i + 1) % n], weight)
    return m


def _idiosyncratic(m: Meno) -> Meno:
    """A lived-in graph: one hub, preferential pathways of varied strength."""
    hub = m.graph.add_node("associative memory and spreading activation").id
    leaves = [m.graph.add_node(f"thought about {w}").id
              for w in ("reconstruction", "forgetting", "curiosity", "dreams", "islands")]
    for leaf, wt in zip(leaves, (0.95, 0.85, 0.2, 0.15, 0.1)):
        m.graph.link(hub, leaf, wt)
    m.graph.link(leaves[0], leaves[1], 0.7)
    return m


# --- the math of idiosyncrasy --------------------------------------------- #
def test_gini_uniform_is_zero_concentrated_is_high():
    assert _gini([1, 1, 1, 1]) < 0.01
    assert _gini([0, 0, 0, 4]) > 0.6
    assert _gini([]) == 0.0


# --- 1. particularity ------------------------------------------------------ #
def test_particularity_low_for_uniform_high_for_idiosyncratic():
    flat = particularity(_ring(fresh(), 8, 0.5).graph)
    lived = particularity(_idiosyncratic(fresh()).graph)
    assert flat["score"] < PASS["particularity"]
    assert lived["score"] > flat["score"] and lived["score"] >= PASS["particularity"]
    assert lived["evidence"]


# --- 2. initiative: requires SUSTAINED self-direction ---------------------- #
def test_initiative_one_scripted_tick_is_not_enough_two_is():
    react = fresh()
    for s in ["a", "b", "c", "d", "e"]:
        react.feed(s)
    assert initiative(react)["score"] < PASS["initiative"]

    one = fresh()
    one.feed("a")
    one.bus.log.append(Event(content="a single boredom-born curiosity",
                             kind=Kind.SELF, source="curiosity"))
    assert not initiative(one)["sustained_initiative"]
    assert initiative(one)["score"] < PASS["initiative"]      # one tick != initiative

    driven = fresh()
    for s in ["a", "b", "c"]:
        driven.feed(s)
    driven.bus.log.append(Event(content="I wonder what connects these",
                                kind=Kind.SELF, source="curiosity"))
    driven.bus.log.append(Event(content="returning to an unfinished thought",
                                kind=Kind.SELF, source="initiative"))
    rep = initiative(driven)
    assert rep["sustained_initiative"] and rep["score"] >= PASS["initiative"]


# --- 3. synthesis: cross-source AND emergent ------------------------------- #
def _two_stream_nodes(m: Meno):
    a = m.graph.add_node("memory is reconstructed at recall", meta={"stream": 1}).id
    b = m.graph.add_node("forgetting drops edges before nodes", meta={"stream": 2}).id
    return a, b


def test_synthesis_rejects_templated_restatement_accepts_emergent_insight():
    # a templated 'insight' whose words are all from its sources + boilerplate -> 0
    templ = fresh()
    a, b = _two_stream_nodes(templ)
    templ.graph.store_cue([a, b], "insight: memory + forgetting", tone=0.9,
                          conclusion="a pattern across memory and forgetting — they cohere",
                          journal=True)
    assert synthesis(templ.graph)["score"] == 0.0          # no emergent terms

    # a genuine insight: the conclusion names a mechanism the sources never did
    real = fresh()
    a, b = _two_stream_nodes(real)
    real.graph.store_cue([a, b], "insight: memory + forgetting", tone=0.9,
                         conclusion="islanding is the substrate that lets rediscovery surprise",
                         journal=True)
    rep = synthesis(real.graph)
    assert rep["genuine_insights"] == 1 and rep["score"] >= PASS["synthesis"]
    assert any("islanding" in e or "substrate" in e or "rediscovery" in e for e in rep["evidence"])


def test_synthesis_single_stream_reflection_is_not_cross_source():
    m = fresh()
    a = m.graph.add_node("a lone memory", meta={"stream": 7}).id
    b = m.graph.add_node("more of the same lone memory", meta={"stream": 7}).id
    m.graph.store_cue([a, b], "thinking it over", tone=0.5,
                      conclusion="entirely novel emergent vocabulary here", journal=True)
    assert synthesis(m.graph)["score"] == 0.0      # same stream -> not cross-source


# --- 4. novelty ------------------------------------------------------------ #
def test_novelty_zero_when_echoing_input_high_when_emergent():
    echo = novelty(["the database connection pool"],
                   ["the database connection pool is exhausted"])
    assert echo["score"] < PASS["novelty"]
    emergent = novelty(["reconstructive hippocampal indexing emerges from cues"],
                       ["the user asked something about a server"])
    assert emergent["score"] >= PASS["novelty"]
    assert "reconstructive" in emergent["fresh_terms"]


# --- 5. divergence: STRUCTURE, not vocabulary ------------------------------ #
def test_divergence_zero_for_structural_twins():
    a, b = fresh(), fresh()
    for m in (a, b):
        ids = [m.graph.add_node(c).id for c in ("alpha", "beta", "gamma")]
        m.graph.link(ids[0], ids[1], 0.6)
        m.graph.link(ids[1], ids[2], 0.6)
    assert divergence(a.graph, b.graph)["score"] < 0.05


def test_divergence_high_for_same_words_different_structure():
    """The vision's actual claim: same inputs, DIFFERENT graph. Identical node
    vocabulary, but the two minds linked different things and grew different hubs."""
    a, b = fresh(), fresh()
    ax = [a.graph.add_node(c).id for c in ("alpha", "beta", "gamma", "delta")]
    a.graph.link(ax[0], ax[1], 0.9)            # alpha is the hub
    a.graph.link(ax[0], ax[2], 0.9)
    a.graph.link(ax[0], ax[3], 0.9)
    bx = [b.graph.add_node(c).id for c in ("alpha", "beta", "gamma", "delta")]
    b.graph.link(bx[3], bx[1], 0.9)            # delta is the hub; different links
    b.graph.link(bx[3], bx[2], 0.9)
    b.graph.link(bx[1], bx[2], 0.9)
    rep = divergence(a.graph, b.graph)
    assert rep["score"] >= PASS["divergence"]       # vocab identical, structure differs
    assert rep["association_distance"] > 0.5


# --- aggregate verdict: the discrimination that matters -------------------- #
def test_zombie_report_calls_a_flat_mind_a_zombie():
    dead = _ring(fresh(), 8, 0.5)
    for s in ["x", "y", "z"]:
        dead.feed(s)
    rep = zombie_report(dead)
    assert rep["verdict"] == "zombie" and "particularity" in rep["failed_marks"]


def test_live_stub_run_is_called_zombie_even_with_its_own_reflection_text():
    """THE decisive R0 test (review P0). A real accumulating stub run — a zombie by
    construction — must read as zombie, and its templated reflections must score 0
    on synthesis even when we hand the probe the stub's own reconstructed text."""
    m = fresh(embed=make_embedder("hashing"))
    for s in ["associative memory and spreading activation",
              "spreading activation surfaces unexpected connections",
              "memory is reconstructed rather than retrieved",
              "forgetting drops edges before nodes",
              "islanded memories can be rediscovered",
              "the database connection dropped under load",
              "the database pool is exhausted"]:
        m.feed(s)
        m.run_until_quiescent()
    m.heartbeat()
    m.dream()
    # hand synthesis the stub's actual reflection text for every cue
    texts = {cid: m.graph.reconstruct(c, m.models, reconsolidate=False)
             for cid, c in m.graph.cues.items()}
    assert synthesis(m.graph, texts)["score"] == 0.0          # templated -> no emergence
    rep = zombie_report(m, inputs=["associative memory", "database pool"],
                        reflection_texts=texts)
    assert rep["verdict"] == "zombie", rep["marks"]
    assert not rep["passed"]["synthesis"]


def test_zombie_report_calls_a_lived_in_mind_alive():
    alive = _idiosyncratic(fresh())
    alive.bus.log.append(Event(content="what more is there about reconstruction?",
                               kind=Kind.SELF, source="curiosity"))
    alive.bus.log.append(Event(content="returning to forgetting",
                               kind=Kind.SELF, source="initiative"))
    alive.feed("an external nudge")
    ids = list(alive.graph.nodes)[:2]
    for nid, sid in zip(ids, (1, 2)):
        alive.graph.nodes[nid].meta["stream"] = sid          # genuinely cross-source
    alive.graph.store_cue(ids, "insight: memory and forgetting are one", tone=0.9,
                          conclusion="islanding is the hinge that makes rediscovery possible",
                          journal=True)
    rep = zombie_report(alive)
    assert rep["verdict"] == "alive", rep["failed_marks"]
    assert rep["passed"]["particularity"] and rep["passed"]["synthesis"]


def test_verdict_is_indeterminate_when_cognition_was_not_real():
    """Even a perfectly alive-looking graph cannot be called alive if cognition
    secretly fell back to the stub (the R1 loud-failure contract)."""
    alive = _idiosyncratic(fresh())
    alive.bus.log.append(Event(content="q1", kind=Kind.SELF, source="curiosity"))
    alive.bus.log.append(Event(content="q2", kind=Kind.SELF, source="initiative"))
    ids = list(alive.graph.nodes)[:2]
    for nid, sid in zip(ids, (1, 2)):
        alive.graph.nodes[nid].meta["stream"] = sid
    alive.graph.store_cue(ids, "insight: x", tone=0.9,
                          conclusion="islanding underwrites surprising rediscovery", journal=True)
    rep = zombie_report(alive, cognition_real=False)
    assert rep["verdict"] == "indeterminate"
