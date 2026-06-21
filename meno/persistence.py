"""Continuity across restart: persist the cold graph so meno *remains*.

A restart is sleep, not death (system-design.md). The durable self is the
consolidated graph — nodes, edges, and reflection cues. The hot working set is
ephemeral and starts empty on wake; recall works immediately against the loaded
graph, and `Meno.resurface()` can rebuild a little working context by spreading
from the most salient memories.

Warm-tier (suspended-stream) persistence is intentionally NOT handled here — the
warm-tier placement is still an open decision (redesign.md). See decision D12.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Union

from . import graph as graphmod
from .graph import Graph, Node, ReflectionCue


def graph_to_dict(g: Graph) -> dict:
    return {
        "version": 1,
        "nodes": [
            {"id": n.id, "content": n.content, "embedding": n.embedding,
             "kind": n.kind, "salience": n.salience, "meta": n.meta,
             "created_at": n.created_at}
            for n in g.nodes.values()
        ],
        "edges": [[a, b, w] for (a, b), w in g.edges.items()],
        "cues": [
            {"id": c.id, "entry_points": c.entry_points, "occasion": c.occasion,
             "tone": c.tone, "gist": c.gist, "verbatim": c.verbatim,
             "recalls": c.recalls, "created_at": c.created_at}
            for c in g.cues.values()
        ],
    }


def dict_to_graph(data: dict, g: Graph) -> Graph:
    g.nodes.clear()
    g.edges.clear()
    g.cues.clear()
    max_node = 0
    for nd in data.get("nodes", []):
        node = Node(content=nd["content"], embedding=nd["embedding"],
                    kind=nd.get("kind", "experience"), salience=nd.get("salience", 1.0),
                    meta=nd.get("meta", {}), id=nd["id"],
                    created_at=nd.get("created_at", 0.0))
        g.nodes[node.id] = node
        max_node = max(max_node, node.id)
    for a, b, w in data.get("edges", []):
        g.edges[(min(a, b), max(a, b))] = w
    max_cue = 0
    for cd in data.get("cues", []):
        cue = ReflectionCue(entry_points=cd["entry_points"], occasion=cd["occasion"],
                            tone=cd["tone"], gist=cd["gist"], verbatim=cd.get("verbatim"),
                            recalls=cd.get("recalls", 0), id=cd["id"],
                            created_at=cd.get("created_at", 0.0))
        g.cues[cue.id] = cue
        max_cue = max(max_cue, cue.id)
    # advance the module id counters so freshly-created ids never collide with loaded ones
    graphmod._node_ids = itertools.count(max_node + 1)
    graphmod._cue_ids = itertools.count(max_cue + 1)
    return g


def save(g: Graph, path: Union[str, Path]) -> None:
    Path(path).write_text(json.dumps(graph_to_dict(g), indent=2))


def load(g: Graph, path: Union[str, Path]) -> Graph:
    return dict_to_graph(json.loads(Path(path).read_text()), g)
