"""The annotator — Tier 0, the autonomic hot gate.

Runs on every event, once, cheaply, no model. Fills embedding, surprise, and
stream membership (the shared signals every processor's trigger compares
against). Surprise is novelty against the *working set* (the hot set), not the
graph — full graph spreading activation is the expensive cognitive step.
"""
from __future__ import annotations

from .config import Config
from .embeddings import EmbeddingModel, cosine
from .event import Event
from .streams import StreamManager
from .working_set import WorkingSet


class Annotator:
    def __init__(self, embed: EmbeddingModel, working_set: WorkingSet,
                 streams: StreamManager, config: Config) -> None:
        self.embed = embed
        self.ws = working_set
        self.streams = streams
        self.cfg = config

    def annotate(self, event: Event) -> Event:
        if event.embedding is None:
            event.embedding = self.embed.embed(event.content)
        # surprise = unexplained residual vs. what is already hot
        actives = self.ws.embeddings()
        max_sim = max((cosine(event.embedding, e) for e in actives), default=0.0)
        event.surprise = max(0.0, 1.0 - max_sim)
        # activation modulated by surprise (you pay attention to what surprises you)
        event.activation *= (0.5 + 0.5 * event.surprise)
        # stream membership (cheap, similarity-based)
        self.streams.route(event)
        return event

    def gate_threshold(self, loose: bool = False) -> float:
        """Greedy while loaded, loose while dreaming."""
        if loose:
            return self.cfg.gate_loose
        return self.cfg.gate_base + self.cfg.gate_load_gain * self.ws.load()

    def passes(self, event: Event, loose: bool = False) -> bool:
        return self.score(event) >= self.gate_threshold(loose)

    def score(self, event: Event) -> float:
        return event.activation * (0.3 + event.surprise)
