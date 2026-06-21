"""Embedding model behind an interface; a deterministic local default.

Embeddings are load-bearing in v2 — rediscovery *and* reflection reconstruction
depend on them (redesign.md). The default `HashingEmbedding` needs no network or
model download, so the whole system runs offline (decision D4/D6). A real model
(Ollama nomic-embed-text, an API embedder) can be dropped in as another
`EmbeddingModel`.
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


def cosine(a: Optional[List[float]], b: Optional[List[float]]) -> float:
    if not a or not b:
        return 0.0
    # vectors are L2-normalised, so dot == cosine
    return sum(x * y for x, y in zip(a, b))
