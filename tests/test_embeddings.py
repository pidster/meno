"""P3 — the embedder hot/cold split (decision D20).

The point of the split is that the cheap, per-event HOT path and the rich,
graph-touching COLD path can be *different models* with *different dimensions*,
and the system stays correct because the two spaces never meet in a cosine. These
tests pin that contract:

  - the split routes hot vs cold to the right underlying model;
  - graph vectors are cold, event/stream vectors are hot (dims prove it);
  - probe↔gist consistency: recall finds a cue even when hot≠cold (the probe is
    embedded cold, matching the gist) — the bug a naive split would introduce;
  - the default single-model embedder is behaviourally unchanged (the offline
    suite stays green);
  - the real local embedder loads if installed (skipped otherwise).
"""
import tempfile

import pytest

from meno import (
    Config,
    HashingEmbedding,
    Meno,
    SplitEmbedding,
    StubModelProvider,
    cosine,
    make_embedder,
)
from meno.embeddings import EmbeddingModel


class DimStub(EmbeddingModel):
    """A deterministic embedder of a chosen dimension and a 'tag' offset, so two
    instances produce *distinguishable, different-dimensioned* vectors — enough to
    tell hot output from cold output without any heavy dependency."""

    def __init__(self, dim: int, tag: float) -> None:
        self.dim = dim
        self.tag = tag

    def embed(self, text):
        # token-count driven, L2-normalised; tag shifts the space so hot≠cold
        n = float(len(text.split()) + 1)
        vec = [(self.tag + (i + 1) * n) for i in range(self.dim)]
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]


def fresh(embed):
    return Meno(config=Config(), embed=embed, models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_emb_"))


def test_split_routes_hot_and_cold_to_distinct_models():
    hot, cold = DimStub(8, 1.0), DimStub(32, 7.0)
    split = SplitEmbedding(hot=hot, cold=cold)
    assert split.dim == 32                                  # reports the COLD (graph) dim
    assert split.embed_hot("alpha beta") == hot.embed("alpha beta")
    assert split.embed_cold("alpha beta") == cold.embed("alpha beta")
    assert len(split.embed_hot("x")) == 8
    assert len(split.embed_cold("x")) == 32
    assert split.embed("x") == cold.embed("x")              # bare embed defaults to cold


def test_graph_vectors_are_cold_and_event_vectors_are_hot():
    """Different dims on each side make the boundary observable: a node created
    from a percept carries the cold vector; the event on the bus carries the hot."""
    hot, cold = DimStub(8, 1.0), DimStub(32, 7.0)
    m = fresh(SplitEmbedding(hot=hot, cold=cold))
    ev = m.feed("a fresh percept about volcanoes")
    m.run_until_quiescent()
    assert len(ev.embedding) == 8                            # the event was embedded HOT
    assert m.graph.nodes                                     # the percept was encoded
    node = next(iter(m.graph.nodes.values()))
    assert len(node.embedding) == 32                         # the node lives in COLD space
    # the two never share a cosine: every stored cue gist is cold-dimensioned too
    for cue in m.graph.cues.values():
        assert len(cue.gist) == 32


def test_probe_and_gist_share_the_cold_space_so_recall_still_finds_it():
    """The keystone of the split: with hot≠cold, recall must embed the probe COLD
    (matching the cue gist). A naive split that probed in hot space would score
    cross-dimension garbage and miss. Here we assert recall recognises a cue."""
    hot, cold = DimStub(8, 1.0), HashingEmbedding(dim=48)   # cold = real-ish semantics
    m = fresh(SplitEmbedding(hot=hot, cold=cold))
    # store a reflection directly (cold gist), then recall by a topical probe
    n = m.graph.add_node("spreading activation across associative memory")
    m.graph.store_cue([n.id], "associative memory and spreading activation",
                      tone=0.8, conclusion="memory spreads activation over associations")
    r = m.recall("associative memory and spreading activation")
    assert r["found"]                                        # probe (cold) matched gist (cold)
    assert r["similarity"] > 0.3
    # and the probe really is in cold space — same dim as the gist, not the hot dim
    assert len(m.embed.embed_cold("anything")) == 48


def test_default_single_model_embedder_is_unchanged():
    """A non-split embedder makes embed_hot == embed_cold == embed, so nothing in
    the hot/cold plumbing changes behaviour for the default offline config."""
    e = HashingEmbedding()
    assert e.embed_hot("the quick brown fox") == e.embed("the quick brown fox")
    assert e.embed_cold("the quick brown fox") == e.embed("the quick brown fox")
    # and a full offline run still produces a coherent mind
    m = fresh(e)
    for s in ["associative memory and spreading activation",
              "memory is reconstructed not retrieved",
              "spreading activation surfaces connections"]:
        m.feed(s)
        m.run_until_quiescent()
    assert m.snapshot()["nodes"] > 0


def test_make_embedder_factory():
    assert isinstance(make_embedder("hashing"), HashingEmbedding)
    with pytest.raises(ValueError):
        make_embedder("nonsense")


def test_local_embedder_loads_if_installed():
    """The real cold adapter, exercised only when sentence-transformers/torch are
    present *and* the model weights are reachable — the offline suite skips it
    (missing dep, or a network policy that blocks the weight download) rather than
    failing."""
    pytest.importorskip("sentence_transformers")
    from meno import SentenceTransformerEmbedding
    try:
        e = SentenceTransformerEmbedding()
    except Exception as exc:   # weights can't be fetched (offline / gated / network policy)
        pytest.skip(f"sentence-transformers weights unavailable: {exc}")
    v = e.embed("a sentence to embed")
    assert len(v) == e.dim and e.dim > 0
    # L2-normalised, so a vector dotted with itself is ~1 (cosine == dot)
    assert abs(cosine(v, v) - 1.0) < 1e-3
    # split with a real cold model: graph recall round-trips
    split = SplitEmbedding(hot=HashingEmbedding(), cold=e)
    m = fresh(split)
    n = m.graph.add_node("the rabbit ran across the meadow at dawn")
    m.graph.store_cue([n.id], "a rabbit at dawn", tone=0.7,
                      conclusion="a rabbit crossed a meadow in the morning")
    assert m.recall("rabbit running through a field early in the morning")["found"]
