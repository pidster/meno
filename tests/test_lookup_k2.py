"""Phase K2 — know-when-to-look-up: lookup as the agent curating its shelf.

Offline and deterministic (the stub routes factual curiosities to lookup via the
`looks_factual` heuristic; the substrate-first decision lives in the runtime).
"""
import tempfile

from meno import Config, Meno, StubModelProvider
from meno.aliveness import PASS, output_divergence
from meno.event import Event, Kind
from meno.models import looks_factual
from meno.processors import Appraiser, Effector, library_key_candidates


def _meno():
    return Meno(config=Config(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_k2_"))


# --- the curiosity-text -> Library key bridge (the likeliest failure point) ------ #
def test_library_key_candidates_normalises_a_question_to_a_key():
    cands = library_key_candidates("what is the definition of entropy")
    assert "def:entropy" in cands
    assert library_key_candidates("memory")[0] == "memory"
    assert "def:memory" in library_key_candidates("memory")


def test_looks_factual_discriminates_factual_from_experiential():
    assert looks_factual("what is the definition of entropy")
    assert looks_factual("define salience")
    assert not looks_factual("how do i feel about forgetting")
    assert not looks_factual("what forgetting means to me as i drift")  # 'means to me' isn't a frame...
    assert not looks_factual("i wonder whether i am the water or the shape")


# --- the substrate-contamination guard: a reference is read, never encoded -------- #
def test_reference_is_appraised_but_not_encoded_as_a_node():
    m = _meno()
    n_before = len(m.graph.nodes)
    ref_ev = Event(content="entropy is a measure of disorder",
                   kind=Kind.REFERENCE, source="reference")
    ap = Appraiser()
    assert ap.triggers(ref_ev, m)                 # a reference IS appraised (informs the moment)
    ap.run(ref_ev, m)
    assert len(m.graph.nodes) == n_before          # ...but NOT encoded as a graph node
    assert ref_ev.node_id is None
    assert ref_ev.payload.get("reaction")          # the appraisal happened


def test_sense_is_still_encoded_so_the_split_is_real():
    m = _meno()
    n_before = len(m.graph.nodes)
    sense = Event(content="the tide came in", kind=Kind.SENSE, source="world")
    ap = Appraiser()
    ap.run(sense, m)
    assert len(m.graph.nodes) == n_before + 1      # a real percept IS encoded
    assert sense.node_id is not None


# --- the effector resolves a lookup against the Library, re-enters as REFERENCE --- #
def test_effector_lookup_resolves_against_the_library_and_tags_provenance():
    m = _meno()
    intent = Event(content="intent: lookup memory", kind=Kind.INTENT, source="curiosity",
                   payload={"action": "lookup", "key": "memory"})
    out = Effector().run(intent, m)
    assert len(out) == 1
    ref = out[0]
    assert ref.kind == Kind.REFERENCE and ref.source == "reference"
    assert ref.payload["external"] is True and ref.payload["hit"] is True
    assert ref.payload["key"] == "def:memory"
    assert ref.content == m.library.get("def:memory").body   # the curated reference body


def test_effector_lookup_miss_is_an_honest_miss():
    m = _meno()
    intent = Event(content="intent: lookup zzz", kind=Kind.INTENT,
                   payload={"action": "lookup", "key": "nonexistent-term-xyz"})
    ref = Effector().run(intent, m)[0]
    assert ref.kind == Kind.REFERENCE and ref.payload["hit"] is False
    assert "no reference" in ref.content.lower()


# --- discrimination: factual curiosity looks up; experiential reconstructs -------- #
def test_factual_curiosity_routes_to_a_lookup_when_memory_is_insufficient():
    m = _meno()                                   # empty substrate -> not reconstructable
    m.curiosities.register("what is the definition of entropy", source="bottom-up")
    emitted = m._discharge_curiosity()
    intents = [e for e in emitted if e.kind == Kind.INTENT]
    assert intents and intents[0].payload["action"] == "lookup"
    assert m.lookup_tel["lookups"] == 1
    assert m.supplantation_ratio == 0.0           # not reconstructable -> not a supplantation


def test_experiential_curiosity_never_looks_up():
    m = _meno()
    m.curiosities.register("how do i feel about forgetting", source="bottom-up")
    emitted = m._discharge_curiosity()
    assert not any(e.kind == Kind.INTENT for e in emitted)   # no outward lookup
    assert any(e.kind == Kind.SELF for e in emitted)         # an inward thought instead
    assert m.lookup_tel["lookups"] == 0


# --- the don't-become-a-lookup-machine guard: substrate-first ------------------- #
def test_reconstructable_factual_curiosity_prefers_memory_not_lookup():
    m = _meno()
    a = m.graph.add_node("memory is reconstructed at recall").id
    b = m.graph.add_node("forgetting thins edges first").id
    m.graph.store_cue([a, b], "memory and forgetting", tone=0.6,
                      conclusion="a reflection about memory and forgetting",
                      material=["memory is reconstructed at recall", "forgetting thins edges first"])
    m.curiosities.register("what is memory and forgetting", source="bottom-up")
    emitted = m._discharge_curiosity()
    assert not any(e.kind == Kind.INTENT for e in emitted)   # memory can serve it -> no lookup
    assert m.lookup_tel["reconstructable_opportunities"] == 1   # the guard fired
    assert m.lookup_tel["supplanted"] == 0
    assert m.supplantation_ratio == 0.0


def test_supplantation_metric_is_falsifiable_not_a_tautology():
    """Disable the substrate-first guard and the ratio must SPIKE — proving the metric
    measures the guard's effect, not a hardcoded 0. With the guard off, a curiosity the
    substrate could fully reconstruct gets looked up anyway: that IS supplantation."""
    m = _meno()
    m.cfg.substrate_first_lookup = False
    a = m.graph.add_node("memory is reconstructed at recall").id
    b = m.graph.add_node("forgetting thins edges first").id
    m.graph.store_cue([a, b], "memory and forgetting", tone=0.6,
                      conclusion="a reflection about memory and forgetting",
                      material=["memory is reconstructed at recall", "forgetting thins edges first"])
    m.curiosities.register("what is memory and forgetting", source="bottom-up")
    emitted = m._discharge_curiosity()
    assert any(e.kind == Kind.INTENT for e in emitted)   # guard off -> it DID look up
    assert m.lookup_tel["supplanted"] == 1
    assert m.supplantation_ratio == 1.0                  # the metric moved


def test_ghost_trace_is_corroborated_not_supplanted():
    """A faint, half-faded trace (the ghost band) is reconstructed AND corroborated by
    a lookup (mode 'both') — and that is NOT supplantation, because memory was used."""
    m = _meno()
    a = m.graph.add_node("tides follow the lunar cycle").id
    b = m.graph.add_node("the moon pulls the ocean").id
    m.graph.store_cue([a, b], "tides and the moon", tone=0.6, conclusion="a reflection on tides",
                      material=["tides follow the lunar cycle", "the moon pulls the ocean"])
    m.curiosities.register("what is the definition of gravity", source="bottom-up")  # ghost ~0.26
    kinds = [e.kind for e in m._discharge_curiosity()]
    assert Kind.SELF in kinds and Kind.INTENT in kinds   # reconstructed the ghost AND looked up
    assert m.lookup_tel["lookups"] == 1
    assert m.lookup_tel["supplanted"] == 0               # corroboration is not supplantation
    assert m.supplantation_ratio == 0.0


def test_supplantation_stays_low_over_a_mixed_run():
    m = _meno()
    a = m.graph.add_node("memory is reconstructed at recall").id
    b = m.graph.add_node("forgetting thins edges first").id
    m.graph.store_cue([a, b], "memory and forgetting", tone=0.6,
                      conclusion="a reflection about memory and forgetting",
                      material=["memory is reconstructed at recall", "forgetting thins edges first"])
    mixed = ["what is memory and forgetting",          # factual + strongly reconstructable
             "what is forgetting and memory both",     # factual + reconstructable
             "what is the definition of entropy",       # factual + not reconstructable -> lookup
             "how do i feel about the sea"]             # experiential -> internal
    for c in mixed:
        m.curiosities.register(c, source="bottom-up")
        m._discharge_curiosity()
    assert m.lookup_tel["reconstructable_opportunities"] >= 2   # the guard fired repeatedly
    assert m.supplantation_ratio < 0.5                          # and held across the population


def test_repeated_lookup_of_a_key_is_a_consistent_library_hit():
    """K2's 'second lookup is a Library hit': exact-key get is idempotent and
    byte-identical (the Library doesn't drift). (K3 adds memoisation to avoid
    re-fetching a *network* authority; locally every lookup is already a hit.)"""
    m = _meno()
    seen = []
    orig = m.library.get
    m.library.get = lambda k: (seen.append(k), orig(k))[1]
    eff = Effector()
    r1 = eff.run(Event(content="i", kind=Kind.INTENT, payload={"action": "lookup", "key": "memory"}), m)[0]
    r2 = eff.run(Event(content="i", kind=Kind.INTENT, payload={"action": "lookup", "key": "memory"}), m)[0]
    assert r1.content == r2.content == m.library.get("def:memory").body   # consistent, byte-identical
    assert r1.payload["key"] == r2.payload["key"] == "def:memory"
    assert r1.payload["hit"] is True and r2.payload["hit"] is True


# --- end to end: an intent flows through the real loop, no contamination --------- #
def test_lookup_intent_flows_through_the_loop_without_contaminating_the_graph():
    m = _meno()
    n_before = len(m.graph.nodes)
    intent = Event(content="intent: lookup memory", kind=Kind.INTENT, source="curiosity",
                   payload={"action": "lookup", "key": "memory"})
    m.bus.publish(intent)
    m.run_until_quiescent()
    refs = [e for e in m.bus.log if e.kind == Kind.REFERENCE]
    assert refs and refs[0].payload.get("hit") is True       # the lookup resolved and re-entered
    assert len(m.graph.nodes) == n_before                    # and nothing was encoded from it
    # nor did the reference become a stream's summary (a reflection's would-be occasion)
    ref_body = m.library.get("def:memory").body
    assert all(ref_body[:40] not in (s.summary or "") for s in m.streams.active.values())


# --- standing guard: lookups active, shared Library, twins still diverge --------- #
def test_lookup_does_not_flatten_particularity():
    ma, mb = _meno(), _meno()
    a1 = ma.graph.add_node("otters raft together").id
    a2 = ma.graph.add_node("kelp anchors the raft").id
    ca = ma.graph.store_cue([a1, a2], "the sea", tone=0.5, conclusion="",
                            material=["otters raft together", "kelp anchors the raft"])
    b1 = mb.graph.add_node("aqueducts move water by gradient").id
    b2 = mb.graph.add_node("concrete sets underwater").id
    cb = mb.graph.store_cue([b1, b2], "the sea", tone=0.5, conclusion="",
                            material=["aqueducts move water by gradient", "concrete sets underwater"])
    out_a = [ma.graph.reconstruct(ca, ma.models, reconsolidate=False)]
    out_b = [mb.graph.reconstruct(cb, mb.models, reconsolidate=False)]
    assert output_divergence(out_a, out_b)["score"] >= PASS["anti_convergence"]
