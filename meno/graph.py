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
    # the material the conclusion was derived from (occasion + the content the model
    # was given), frozen at generation time. Provenance for the aliveness synthesis
    # probe: emergence must be judged against what the reflection actually drew on,
    # not against a graph that has since forgotten those nodes (R0 red-team P0).
    source_text: str = ""
    recalls: int = 0
    ghost_ticks: int = 0              # dreams spent islanded-and-unrecovered (D19/A3 tiered forgetting)
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
        emb = embedding if embedding is not None else self.embed.embed_cold(content)
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
                  conclusion: str, journal: bool = False,
                  material: Optional[List[str]] = None) -> ReflectionCue:
        self._cue_seq += 1
        # Provenance = exactly what the conclusion was derived from. Prefer the
        # caller's `material` (the list actually handed to synthesise, which can
        # diverge from entry-point content via a fallback or deleted nodes); fall
        # back to entry-point content. Covers the conclusion's true sources so the
        # aliveness synthesis probe can't be tricked by a stored conclusion whose
        # words came from material that isn't in entry_points (R0 red-team P1).
        entry_content = " ".join(self.nodes[n].content for n in entry_points if n in self.nodes)
        material_text = " ".join(material) if material else ""
        cue = ReflectionCue(
            entry_points=list(entry_points),
            occasion=occasion,
            tone=tone,
            # gist embeds occasion + conclusion (meaning), so a topical probe can find it
            gist=self.embed.embed_cold(f"{occasion} {conclusion}"),
            verbatim=conclusion if journal else None,
            source_text=self._accrue_provenance(f"{occasion} {entry_content}", material_text),
            id=self._cue_seq,
        )
        self.cues[cue.id] = cue
        return cue

    @staticmethod
    def _accrue_provenance(existing: str, addition: str) -> str:
        """Provenance is MONOTONIC: a reflection's source_text may grow as it is
        re-reconstructed against new neighbourhoods, but never narrows. A term the
        reflection ever legitimately drew on stays accounted for, so a later thinning
        (after forgetting) can't strand an earlier, richer reconstruction and make
        its words look emergent (R0 red-team P0, desync variant). Word-deduped to
        stay bounded over a long life."""
        return " ".join(dict.fromkeys((existing + " " + addition).split()))

    def recognise(self, cue: ReflectionCue, probe_embedding: List[float]) -> float:
        """Cheap, gist-level recognition (the ghost signal). No model."""
        return cosine(cue.gist, probe_embedding)

    def reconstruct(self, cue: ReflectionCue, model: ModelProvider,
                    reconsolidate: bool = True) -> str:
        """Reconstruct a reflection from its cue against the CURRENT graph.

        Richness comes from the **reachable neighbourhood** — the associations the
        entry points still connect to via surviving edges — not from the entry
        points' own content. So forgetting genuinely thins recall (F1): when edges
        have decayed the neighbourhood is gone and only the (fading) anchors
        remain → a *partial* reconstruction; when even the anchors have faded
        below salience → a *ghost* ("I know I concluded something here but can't
        recover it"). The same cue therefore yields a different reflection as the
        world changes — drift lives in the graph, not a frozen record.

        Journaled cues return their frozen verbatim. ``reconsolidate=False`` reads
        without mutating the cue (used by journaling — D15)."""
        if cue.verbatim is not None:
            return cue.verbatim
        act = self.spread(cue.entry_points, hops=2, decay=0.5)
        entry = set(cue.entry_points)
        # neighbours reached via surviving edges (NOT the entry points themselves)
        neighbours = sorted(((nid, a) for nid, a in act.items()
                             if nid not in entry and nid in self.nodes),
                            key=lambda kv: kv[1], reverse=True)
        # anchors: entry points still present and not yet faded by node-decay
        anchors = [nid for nid in cue.entry_points
                   if nid in self.nodes and self.nodes[nid].salience >= self.cfg.recall_salience_floor]

        if not anchors and not neighbours:
            # islanded AND faded: available but inaccessible — the ghost signal
            cue.source_text = self._accrue_provenance(cue.source_text, cue.occasion)
            return f"(something about {cue.occasion} — but the details won't come)"

        material = ([self.nodes[nid].content for nid in anchors] +
                    [self.nodes[nid].content for nid, _ in neighbours])[:6]
        text = model.synthesise(cue.occasion, material)
        # accrue provenance NOW, while the material still exists: the reflection drew
        # on these nodes (incl. spread neighbours not in entry_points). Forgetting may
        # delete them before the aliveness probe audits the text (R0 red-team P0).
        cue.source_text = self._accrue_provenance(
            cue.source_text, cue.occasion + " " + " ".join(material))
        # "structured" = the entry set still has surviving associative edges (to
        # neighbours, or amongst its own anchors). Forgetting strips those edges;
        # when none remain the reflection has lost its web and recall goes thin.
        structured = bool(neighbours) or any(not self.islanded(nid) for nid in anchors)
        if not structured:
            text = "(partial) " + text

        if reconsolidate:
            new_gist = self.embed.embed_cold(text)
            p = self.cfg.reconsolidation_plasticity
            cue.gist = [(1 - p) * g + p * n for g, n in zip(cue.gist, new_gist)]
            cue.recalls += 1
            # the recall touched these nodes -> they become the updated entry points
            touched = anchors + [nid for nid, _ in neighbours]
            cue.entry_points = touched[:max(1, len(cue.entry_points))] or cue.entry_points
            # co-activation during recall REINFORCES the web (Hebbian): returning to a
            # reflection strengthens the associations it rests on, so a theme the agent
            # keeps coming back to becomes a genuine hub through EARNED attention — not
            # merely whichever node was encoded most recently. This connects accumulated
            # return (cue.recalls) to graph structure, which it otherwise never reached
            # (R5 panel: particularity was a recency artifact). Read-only audits use
            # reconsolidate=False and so never contaminate the measurement.
            core = touched[:4]
            for x, y in zip(core, core[1:]):
                self.link(x, y, weight=self.cfg.hebbian_increment * 0.5)
        return text
