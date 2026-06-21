"""The cold, persistent associative memory: nodes, weighted edges, vectors.

Off the reactive hot path (system-design.md) — touched only by cognitive-tier
retrieval and by consolidation. Implements the kept-from-v1 machinery:
spreading activation, embedding similarity (rediscovery), and edge-before-node
decay (islanding). Also home to reflection *cues* (reconstructive memory).

The default store is in-process (D4). A real graph+vector DB can replace it
behind the same surface.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .config import Config
from .embeddings import EmbeddingModel, cosine
from .models import ModelProvider


@dataclass
class Node:
    content: str
    embedding: List[float]
    kind: str = "experience"          # experience | concept | provisional
    salience: float = 1.0
    meta: dict = field(default_factory=dict)
    id: int = 0                       # assigned by Graph.add_node (per-instance, D15)
    created_at: float = field(default_factory=time.time)


@dataclass
class ReflectionCue:
    """A reflection is stored as a recipe for re-deriving it, never as text."""
    entry_points: List[int]           # node ids that were active when it formed
    occasion: str                     # what prompted it
    tone: float                       # affective/salience signature
    gist: List[float]                 # lossy embedding of the conclusion (meaning, not words)
    verbatim: Optional[str] = None    # set only if deliberately journaled
    recalls: int = 0
    id: int = 0                       # assigned by Graph.store_cue (per-instance, D15)
    created_at: float = field(default_factory=time.time)


class Graph:
    def __init__(self, embed: EmbeddingModel, config: Config) -> None:
        self.embed = embed
        self.cfg = config
        self.nodes: Dict[int, Node] = {}
        self.edges: Dict[Tuple[int, int], float] = {}   # undirected, key = (min,max)
        self.cues: Dict[int, ReflectionCue] = {}
        self._node_seq = 0              # per-instance id counters (D15) — no global state
        self._cue_seq = 0

    # --- structure ---
    def add_node(self, content: str, *, kind: str = "experience",
                 salience: float = 1.0, embedding: Optional[List[float]] = None,
                 meta: Optional[dict] = None) -> Node:
        emb = embedding if embedding is not None else self.embed.embed(content)
        self._node_seq += 1
        node = Node(content, emb, kind, salience, meta or {}, id=self._node_seq)
        self.nodes[node.id] = node
        return node

    def link(self, a: int, b: int, weight: float = 0.45) -> None:
        if a == b or a not in self.nodes or b not in self.nodes:
            return
        key = (min(a, b), max(a, b))
        self.edges[key] = min(1.0, self.edges.get(key, 0.0) + weight)   # Hebbian

    def neighbors(self, nid: int):
        for (a, b), w in self.edges.items():
            if a == nid:
                yield b, w
            elif b == nid:
                yield a, w

    # --- retrieval (expensive, cognitive-tier) ---
    def spread(self, entry_points: List[int], hops: int = 2, decay: float = 0.5) -> Dict[int, float]:
        act: Dict[int, float] = {n: 1.0 for n in entry_points if n in self.nodes}
        frontier = dict(act)
        for _ in range(hops):
            nxt: Dict[int, float] = {}
            for nid, a in frontier.items():
                for m, w in self.neighbors(nid):
                    nxt[m] = nxt.get(m, 0.0) + a * w * decay
            for nid, a in nxt.items():
                act[nid] = act.get(nid, 0.0) + a
            frontier = nxt
        return act

    def similar(self, embedding: List[float], k: int = 5,
                exclude: Tuple[int, ...] = ()) -> List[Tuple[float, int]]:
        scored = [(cosine(embedding, n.embedding), nid)
                  for nid, n in self.nodes.items() if nid not in exclude]
        scored.sort(reverse=True)
        return scored[:k]

    # --- forgetting: edges decay before nodes (islanding) ---
    def decay(self) -> None:
        for key in list(self.edges):
            self.edges[key] *= self.cfg.edge_decay
            if self.edges[key] < self.cfg.edge_prune_floor:
                del self.edges[key]
        for node in self.nodes.values():
            node.salience *= self.cfg.node_decay

    def islanded(self, nid: int) -> bool:
        """Available but inaccessible: the node exists, its edges are gone."""
        return nid in self.nodes and not any(True for _ in self.neighbors(nid))

    # --- reflection cues (reconstructive memory) ---
    def store_cue(self, entry_points: List[int], occasion: str, tone: float,
                  conclusion: str, journal: bool = False) -> ReflectionCue:
        self._cue_seq += 1
        cue = ReflectionCue(
            entry_points=list(entry_points),
            occasion=occasion,
            tone=tone,
            # gist embeds occasion + conclusion (meaning), so a topical probe can find it
            gist=self.embed.embed(f"{occasion} {conclusion}"),
            verbatim=conclusion if journal else None,
            id=self._cue_seq,
        )
        self.cues[cue.id] = cue
        return cue

    def recognise(self, cue: ReflectionCue, probe_embedding: List[float]) -> float:
        """Cheap, gist-level recognition (the ghost signal). No model."""
        return cosine(cue.gist, probe_embedding)

    def reconstruct(self, cue: ReflectionCue, model: ModelProvider,
                    reconsolidate: bool = True) -> str:
        """Full reconstruction: spread from the cue's entry points over the
        CURRENT graph, regenerate, then (by default) reconsolidate. The same cue
        yields a different reflection because the graph changed — drift lives in
        the world. Journaled cues return their frozen verbatim instead. Pass
        ``reconsolidate=False`` to read without mutating the cue (used by
        journaling, so freezing doesn't first drift the gist — D15)."""
        if cue.verbatim is not None:
            return cue.verbatim
        act = self.spread(cue.entry_points, hops=2, decay=0.5)
        reachable = sorted(act.items(), key=lambda kv: kv[1], reverse=True)
        material = [self.nodes[nid].content for nid, _ in reachable if nid in self.nodes][:6]
        text = model.synthesise(cue.occasion, material)
        if reconsolidate:
            # blend the gist toward this fresh reconstruction (plasticity)
            new_gist = self.embed.embed(text)
            p = self.cfg.reconsolidation_plasticity
            cue.gist = [(1 - p) * g + p * n for g, n in zip(cue.gist, new_gist)]
            cue.recalls += 1
            # the recall touched these nodes -> they become the updated entry points
            cue.entry_points = [nid for nid, _ in reachable[:max(1, len(cue.entry_points))]
                                if nid in self.nodes] or cue.entry_points
        return text
