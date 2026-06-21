"""meno — a cognitive kernel: associative memory, a default-mode loop, and
self-directed cognition. See docs/redesign.md (logical) and docs/system-design.md
(components). This package is v2; v1 lives in branch archive/tick-simulation.
"""
from __future__ import annotations

from .config import Config
from .embeddings import (
    EmbeddingModel,
    HashingEmbedding,
    SentenceTransformerEmbedding,
    SplitEmbedding,
    cosine,
    make_embedder,
)
from .event import Event, Kind, Status
from .graph import Graph, Node, ReflectionCue
from .models import (
    AnthropicModelProvider,
    CognitionDegraded,
    ModelProvider,
    StubModelProvider,
    cognition_is_real,
    make_models,
)
from .driver import Driver
from .runtime import Meno
from .streams import Stream, StreamManager
from .aliveness import (
    divergence,
    initiative,
    novelty,
    particularity,
    synthesis,
    zombie_report,
)

__all__ = [
    "Meno", "Config", "Event", "Kind", "Status",
    "Graph", "Node", "ReflectionCue",
    "EmbeddingModel", "HashingEmbedding", "SplitEmbedding",
    "SentenceTransformerEmbedding", "make_embedder", "cosine",
    "ModelProvider", "StubModelProvider", "AnthropicModelProvider", "make_models",
    "cognition_is_real", "CognitionDegraded",
    "Stream", "StreamManager", "Driver",
    "zombie_report", "particularity", "initiative", "synthesis",
    "novelty", "divergence",
]

__version__ = "2.0.0"
