"""Phase K1 — the Library: reference memory, the anti-substrate (docs/roadmap-ii.md).

Offline and deterministic. The Library has no model and no embedder dependency
(exact-key only), so the whole phase runs with the stub.
"""
import tempfile
from pathlib import Path

import pytest

from meno import (Config, Library, Meno, Reference, StubModelProvider,
                  WritebackRejected, seed_library)
from meno.aliveness import PASS, output_divergence
from meno.self_model import MENO_SELF


def _meno():
    return Meno(config=Config(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_k1_"))


# --- the defining contrast: reference does NOT decay; the substrate does --------- #
def test_library_entry_is_byte_identical_while_a_graph_edge_decays():
    m = _meno()
    a = m.graph.add_node("otters raft together").id
    b = m.graph.add_node("kelp anchors the raft").id
    m.graph.link(a, b, weight=0.45)
    before_edge = dict(m.graph.edges)[(min(a, b), max(a, b))] if (min(a, b), max(a, b)) in m.graph.edges \
        else next(iter(m.graph.edges.values()))
    before_ref = m.library.get("self-model").body

    for _ in range(5):                      # five forgetting cycles
        m.graph.decay()

    after_edge = next(iter(m.graph.edges.values())) if m.graph.edges else 0.0
    assert after_edge < before_edge          # the substrate forgot
    assert m.library.get("self-model").body == before_ref == MENO_SELF   # reference did not


def test_reference_recalled_twice_is_identical():
    lib = seed_library()
    assert lib.get("def:memory").body == lib.get("def:memory").body
    # and across a save/load round trip
    p = Path(tempfile.mkdtemp(prefix="meno_k1_")) / "library" / "index.json"
    lib.save(p)
    again = Library.load(p)
    assert again.get("def:memory").body == lib.get("def:memory").body


# --- the boundary: the Library is NOT episodic memory --------------------------- #
def test_library_entries_are_never_in_the_graph_or_recallable():
    m = _meno()
    # seed content is in the Library...
    assert "self-model" in m.library and len(m.library) > 1
    lib_bodies = set(m.library.bodies())
    # ...and NOT in the graph (no nodes, no cues seeded from it)
    node_contents = {n.content for n in m.graph.nodes.values()}
    assert not (lib_bodies & node_contents)
    assert not m.graph.cues                      # nothing reference became a reflection
    # recall can never surface a Library entry (recall reads graph.cues only)
    hit = m.recall("what is memory")
    assert hit["mode"] in ("none", "reconstructed", "ghost")
    assert hit.get("text", "") not in lib_bodies


# --- write-back is guarded: reference only, never experience -------------------- #
def test_writeback_rejects_reflections_and_self_authored_content():
    lib = seed_library()
    with pytest.raises(WritebackRejected):                 # wrong kind (a reflection)
        lib.put(Reference(key="r1", body="I feel the sea is like memory",
                          source="cognition", kind="reflection"))
    with pytest.raises(WritebackRejected):                 # self-authored provenance
        lib.put(Reference(key="r2", body="entropy is disorder",
                          source="self", kind="fact"))
    with pytest.raises(WritebackRejected):                 # empty body
        lib.put(Reference(key="r3", body="", source="seed:dictionary", kind="definition"))


def test_writeback_rejects_innocent_looking_self_authored_sources():
    """The guard is an external-source ALLOWLIST, not a 'self' denylist: a K2 caller
    cannot launder agent-authored content by labelling its source 'cognition' /
    'curiosity' / 'meno' (the real Kind.SELF event sources) with kind='fact'."""
    lib = seed_library()
    for src in ("cognition", "curiosity", "meno", "reflexion", "self-model"):
        with pytest.raises(WritebackRejected):
            lib.put(Reference(key="x", body="an agent-authored sentence",
                              source=src, kind="fact"))


def test_writeback_accepts_external_reference_knowledge():
    lib = seed_library()
    ref = lib.put(Reference(key="def:entropy", body="a measure of disorder",
                            source="dictionary:api", kind="definition"))
    assert lib.get("def:entropy") is ref
    assert "def:entropy" in lib


def test_reference_is_immutable():
    """The byte-identical guarantee is structural: a returned Reference is frozen, so
    a caller cannot mutate body in place and corrupt the store."""
    import dataclasses
    sm = seed_library().get("self-model")
    with pytest.raises(dataclasses.FrozenInstanceError):
        sm.body = "tampered"


def test_self_model_copy_is_re_derived_from_the_constant_on_load(tmp_path):
    """D24: the persisted self-model copy must never outlive the constant it copied.
    On load, a stale persisted body is overwritten from the canonical MENO_SELF."""
    m = _meno()
    substrate = Path(m.workspace) / "substrate"; substrate.mkdir(parents=True, exist_ok=True)
    graph_path = substrate / "graph.json"
    # simulate a stale persisted Library (an older image's self-model text)
    m.save(graph_path)
    stale = Library.load(m.library_path)
    stale._refs["self-model"] = Reference(key="self-model", body="OLD STALE SELF MODEL",
                                           source="meno:type", kind="reference")
    stale.save(m.library_path)
    fresh = Meno(config=Config(), models=StubModelProvider(), workspace=m.workspace)
    fresh.load(graph_path)
    assert fresh.library.get("self-model").body == MENO_SELF   # re-derived, not stale


# --- the Library holds the self-model as a reference COPY (canonical stays code) -- #
def test_library_holds_the_self_model_copy():
    lib = seed_library()
    sm = lib.get("self-model")
    assert sm is not None and sm.body == MENO_SELF
    assert sm.kind == "reference" and sm.source == "meno:type"


# --- persistence: its own home, separate from the substrate --------------------- #
def test_library_persists_to_its_own_home_beside_the_substrate():
    m = _meno()
    substrate = Path(m.workspace) / "substrate"
    substrate.mkdir(parents=True, exist_ok=True)
    graph_path = substrate / "graph.json"
    m.library.put(Reference(key="fact:tide", body="tides follow the moon",
                            source="seed:dictionary", kind="fact"))
    m.save(graph_path)
    assert m.library_path.exists()                         # <workspace>/library/index.json
    assert m.library_path != graph_path                    # its own home, not the substrate file
    fresh = Meno(config=Config(), models=StubModelProvider(), workspace=m.workspace)
    fresh.load(graph_path)
    assert fresh.library.get("fact:tide").body == "tides follow the moon"


# --- standing guard: the Library does not flatten particularity ----------------- #
def test_library_present_does_not_collapse_divergence():
    """Both minds carry the identical seeded Library; their voices must still diverge
    by substrate (the Library is shared/type-like — it cannot be where difference
    lives). Mirrors the S anti-convergence mechanism check, now with the Library in
    play (K1 standing-guard outcome)."""
    ma = _meno(); mb = _meno()
    assert ma.library.keys() == mb.library.keys()          # identical reference shelf
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
