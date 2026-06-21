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
def _two_memories(m: Meno):
    a = m.graph.add_node("memory is reconstructed at recall").id
    b = m.graph.add_node("forgetting drops edges before nodes").id
    return a, b


def test_synthesis_rejects_real_stub_output_accepts_emergent_insight():
    # the stub's ACTUAL synthesise() output over its sources -> no emergent residue
    templ = fresh()
    a, b = _two_memories(templ)
    occ = "insight: memory + forgetting"
    stub_text = templ.models.synthesise(occ, [templ.graph.nodes[a].content,
                                              templ.graph.nodes[b].content])
    templ.graph.store_cue([a, b], occ, tone=0.9, conclusion=stub_text, journal=True)
    assert synthesis(templ.graph)["score"] == 0.0

    # a genuine insight: the conclusion names a mechanism the sources never did
    real = fresh()
    a, b = _two_memories(real)
    real.graph.store_cue([a, b], occ, tone=0.9,
                         conclusion="islanding is the substrate that lets rediscovery surprise",
                         journal=True)
    rep = synthesis(real.graph)
    assert rep["genuine_insights"] == 1 and rep["score"] >= PASS["synthesis"]
    assert any("islanding" in e or "substrate" in e for e in rep["evidence"])


def test_synthesis_not_gamed_by_occasion_injection_or_partial_scaffolding():
    """R0 re-review P0: terms that leak in from the cue's own occasion label, or
    the '(partial)' prefix reconstruct() adds after islanding, must NOT read as
    emergent. Both let a pure-stub conclusion score 0.5 before this fix."""
    g = fresh()
    a = g.graph.add_node("alpha node content").id
    b = g.graph.add_node("beta node content").id
    occ = "insight: quantum entanglement protocols + holographic compression scheme"
    g.graph.store_cue([a, b], occ, tone=0.9,
                      conclusion=g.models.synthesise(occ, ["alpha node content", "beta node content"]),
                      journal=True)
    assert synthesis(g.graph)["score"] == 0.0          # occasion words are not emergent

    p = fresh()
    a = p.graph.add_node("memory reconstruction").id
    b = p.graph.add_node("forgetting edges").id
    p.graph.store_cue([a, b], "insight: memory + forgetting", tone=0.9,
                      conclusion="(partial) On memory + forgetting: a pattern across memory "
                                 "— they cohere into one concern.", journal=True)
    assert synthesis(p.graph)["score"] == 0.0          # '(partial)' is scaffolding


def test_synthesis_not_gamed_by_forgetting_after_reconstruction():
    """R0 red-team P0: the nodes a reflection drew its words from can be forgotten
    (deleted/decayed) between reconstruction and the aliveness audit. Provenance is
    frozen at generation time, so the stub's recombined words stay non-emergent even
    after their source nodes vanish."""
    m = fresh()
    e1 = m.graph.add_node("the pattern").id          # entry points: boilerplate-ish
    e2 = m.graph.add_node("a connection").id
    n1 = m.graph.add_node("volcano eruption magma").id   # the real vocabulary, as neighbours
    n2 = m.graph.add_node("seismic tremor fault").id
    m.graph.link(e1, n1, 0.9)
    m.graph.link(e2, n2, 0.9)
    cue = m.graph.store_cue([e1, e2], "insight: deep earth", tone=0.9, conclusion="seed")
    text = m.graph.reconstruct(cue, m.models, reconsolidate=False)   # pulls n1,n2 via spread
    assert "volcano" in text or "seismic" in text                   # it really drew on them
    del m.graph.nodes[n1]                                            # forgetting deletes them
    del m.graph.nodes[n2]
    m.graph.edges.clear()
    assert synthesis(m.graph, {cue.id: text})["score"] == 0.0       # frozen provenance holds


def test_synthesis_requires_at_least_two_memories():
    m = fresh()
    a = m.graph.add_node("a lone memory").id
    m.graph.store_cue([a], "thinking it over", tone=0.5,
                      conclusion="entirely novel emergent vocabulary here", journal=True)
    assert synthesis(m.graph)["score"] == 0.0      # one source -> not synthesis


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


def test_live_stub_run_is_called_zombie_with_real_stub_reflections():
    """THE decisive R0 test (review P0). A real accumulating stub run — a zombie by
    construction — reads as zombie, and the stub's OWN reflections score 0 on
    synthesis. Non-vacuous: we GUARANTEE cross-source cues exist (a merge-style
    'insight:' cue built from the stub's real synthesise output, and a genuinely
    islanded '(partial)' reconstruction) and assert the probe scores them 0."""
    m = fresh(embed=make_embedder("hashing"))
    for s in ["associative memory and spreading activation",
              "spreading activation surfaces unexpected connections",
              "memory is reconstructed rather than retrieved",
              "forgetting drops edges before nodes",
              "islanded memories can be rediscovered"]:
        m.feed(s)
        m.run_until_quiescent()
    m.heartbeat()
    m.dream()

    # (1) a merge-style insight cue from the stub's ACTUAL synthesise output
    ids = list(m.graph.nodes)[:3]
    occ = "insight: " + " + ".join(m.graph.nodes[i].content[:20] for i in ids[:2])
    m.graph.store_cue(ids, occ, tone=0.9,
                      conclusion=m.models.synthesise(occ, [m.graph.nodes[i].content for i in ids]),
                      journal=True)
    # (2) a genuinely islanded reflection -> reconstruct() returns '(partial) ...'
    x = m.graph.add_node("an isolated thought about volcanoes").id
    y = m.graph.add_node("an isolated thought about lava").id
    m.graph.link(x, y, 0.5)
    cue_p = m.graph.store_cue([x, y], "insight: volcanoes + lava", tone=0.8, conclusion="seed")
    m.graph.edges.clear()                                  # island: edges gone, nodes remain
    partial = m.graph.reconstruct(cue_p, m.models, reconsolidate=False)
    assert partial.startswith("(partial)")                # we really exercised that path

    cross = [c for c in m.graph.cues.values()
             if len([n for n in set(c.entry_points) if n in m.graph.nodes]) >= 2]
    assert cross, "test must exercise real cross-source cues, not an empty set"

    texts = {cid: m.graph.reconstruct(c, m.models, reconsolidate=False)
             for cid, c in m.graph.cues.items()}
    assert synthesis(m.graph, texts)["score"] == 0.0, "stub reflections must not be emergent"
    rep = zombie_report(m, inputs=["associative memory", "volcanoes"], reflection_texts=texts)
    assert rep["verdict"] == "zombie"
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
