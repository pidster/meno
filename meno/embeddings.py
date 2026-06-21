"""Embedding model behind an interface; a deterministic local default.

Embeddings are load-bearing in v2 — rediscovery *and* reflection reconstruction
depend on them (redesign.md). The default `HashingEmbedding` needs no network or
model download, so the whole system runs offline (decision D4/D6). A real model
(local sentence-transformers, an API embedder) can be dropped in as another
`EmbeddingModel`.

**Hot vs cold (decision D20).** Two embedding *jobs* differ in frequency and in
what they need. The HOT path runs on *every* event (surprise against the recency
buffer, stream routing) — it must be cheap and only needs rough novelty/topic.
The COLD path touches the persistent graph (node vectors, reflection-cue gists,
recall probes, rediscovery) — it runs rarely and wants real semantics. So the
interface exposes `embed_hot`/`embed_cold`; a single-model embedder makes them
identical, and `SplitEmbedding` routes them to two different models. The
discipline that keeps this honest: **hot vectors are only ever compared to hot,
cold only to cold** — they never meet in a cosine (their dims may differ).
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import List, Optional

_TOKEN = re.compile(r"[a-z0-9]+")


class EmbeddingModel:
    dim: int = 64

    def embed(self, text: str) -> List[float]:  # pragma: no cover - interface
        raise NotImplementedError

    # By default the two jobs share one space (a single-model embedder). Split
    # implementations override these; everything else calls them, never `embed`
    # directly, so the hot/cold boundary is explicit at each callsite.
    def embed_hot(self, text: str) -> List[float]:
        return self.embed(text)

    def embed_cold(self, text: str) -> List[float]:
        return self.embed(text)


class HashingEmbedding(EmbeddingModel):
    """Signed-hashing bag-of-tokens into a fixed, L2-normalised vector.

    Deterministic and dependency-free. Overlapping vocabulary yields meaningful
    cosine similarity — enough to drive resonance, novelty, streams, and
    rediscovery in the bare loop.
    """

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        for tok in _TOKEN.findall(text.lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 8) & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class SplitEmbedding(EmbeddingModel):
    """Route the two jobs to two different models (decision D20): a cheap `hot`
    embedder for the reactive path (per-event surprise, stream routing) and a
    richer `cold` embedder for everything that touches the graph (node vectors,
    cue gists, recall probes, rediscovery).

    The two spaces never meet in a cosine — by the callsite discipline in the
    components, hot is only ever compared to hot and cold to cold — so their
    dimensions may legitimately differ. `dim` reports the COLD dimension, because
    that is what the graph stores and persists.
    """

    def __init__(self, hot: EmbeddingModel, cold: EmbeddingModel) -> None:
        self.hot = hot
        self.cold = cold
        self.dim = cold.dim

    def embed(self, text: str) -> List[float]:
        # the unqualified call defaults to cold: the graph is the default caller
        # and getting that wrong (probe in hot space) silently breaks recall.
        return self.cold.embed(text)

    def embed_hot(self, text: str) -> List[float]:
        return self.hot.embed(text)

    def embed_cold(self, text: str) -> List[float]:
        return self.cold.embed(text)


class SentenceTransformerEmbedding(EmbeddingModel):
    """A real local semantic embedder (sentence-transformers / torch). Optional:
    imported lazily so the default install stays dependency-free and the suite
    stays offline. Use it as the COLD half of a `SplitEmbedding` (the hot path
    doesn't need it). Vectors are L2-normalised so cosine == dot, matching
    `HashingEmbedding`.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer  # lazy, optional dep
        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed(self, text: str) -> List[float]:
        vec = self._model.encode(text, normalize_embeddings=True)
        return [float(x) for x in vec]


def make_embedder(kind: str = "hashing", **kwargs) -> EmbeddingModel:
    """Factory mirroring `make_models` (decision D20).

    - ``hashing`` (default): offline, deterministic, dependency-free.
    - ``local`` / ``sentence-transformers``: a real local semantic embedder.
    - ``split``: cheap hashing on the hot path, a real local embedder on the cold
      (graph-touching) path — the recommended real configuration.
    """
    if kind == "hashing":
        return HashingEmbedding(**kwargs)
    if kind in ("local", "sentence-transformers", "st"):
        return SentenceTransformerEmbedding(**kwargs)
    if kind == "split":
        cold_name = kwargs.get("model_name", "all-MiniLM-L6-v2")
        return SplitEmbedding(hot=HashingEmbedding(), cold=SentenceTransformerEmbedding(cold_name))
    raise ValueError(f"unknown embedder kind: {kind!r}")


def cosine(a: Optional[List[float]], b: Optional[List[float]]) -> float:
    if not a or not b:
        return 0.0
    # vectors are L2-normalised, so dot == cosine
    return sum(x * y for x, y in zip(a, b))
