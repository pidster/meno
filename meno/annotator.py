"""The annotator — Tier 0, the autonomic hot gate.

Runs on every event, once, cheaply, no model. Fills embedding, surprise, and
stream membership (the shared signals every processor's trigger compares
against). Surprise is novelty against the *working set* (the hot set), not the
graph — full graph spreading activation is the expensive cognitive step.
"""
from __future__ import annotations

from collections import deque

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
        # F5: a recency buffer of recently-seen embeddings. Surprise is measured
        # against THIS, not the working set — which claim() drains mid-burst, so
        # everything looked novel (surprise ~1.0), gutting cross-burst habituation
        # and the tier thresholds.
        self.recency: deque = deque(maxlen=config.recency_window)

    def annotate(self, event: Event) -> Event:
        if event.embedding is None:
            # HOT space: surprise + stream routing run on every event and only
            # need rough novelty/topic. Never compared against graph (cold) vectors.
            event.embedding = self.embed.embed_hot(event.content)
        # surprise = unexplained residual vs. what has recently been seen
        max_sim = max((cosine(event.embedding, e) for e in self.recency), default=0.0)
        event.surprise = max(0.0, 1.0 - max_sim)
        self.recency.append(event.embedding)
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
