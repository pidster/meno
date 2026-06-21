"""meno — a cognitive kernel: associative memory, a default-mode loop, and
self-directed cognition. See docs/redesign.md (logical) and docs/system-design.md
(components). This package is v2; v1 lives in branch archive/tick-simulation.
"""
from __future__ import annotations

from .config import Config
from .embeddings import EmbeddingModel, HashingEmbedding, cosine
from .event import Event, Kind, Status
from .graph import Graph, Node, ReflectionCue
from .models import AnthropicModelProvider, ModelProvider, StubModelProvider
from .runtime import Meno
from .streams import Stream, StreamManager

__all__ = [
    "Meno", "Config", "Event", "Kind", "Status",
    "Graph", "Node", "ReflectionCue",
    "EmbeddingModel", "HashingEmbedding", "cosine",
    "ModelProvider", "StubModelProvider", "AnthropicModelProvider",
    "Stream", "StreamManager",
]

__version__ = "2.0.0"
