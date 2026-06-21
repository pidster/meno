"""Continuity across restart: persist the cold graph so meno *remains*.

A restart is sleep, not death (system-design.md). The durable self is the
consolidated graph — nodes, edges, and reflection cues. The hot working set is
ephemeral and starts empty on wake; recall works immediately against the loaded
graph, and `Meno.resurface()` can rebuild a little working context by spreading
from the most salient memories.

Warm-tier (suspended-stream) persistence IS handled now (R4): a suspended stream is
an unfinished train of thought, and persisting it means a restart resumes
mid-thought, not only from the cold graph. The warm streams ride alongside the
graph under a "streams" key; loading them restores the deferred-impulse pressure
that makes the agent return to what it was chewing on. (Resolves the D12 deferral.)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from .graph import Graph, Node, ReflectionCue
from .streams import Stream, StreamManager


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
             "source_text": c.source_text,
             "recalls": c.recalls, "ghost_ticks": c.ghost_ticks,
             "created_at": c.created_at}
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
                            source_text=cd.get("source_text", ""),
                            recalls=cd.get("recalls", 0), ghost_ticks=cd.get("ghost_ticks", 0),
                            id=cd["id"], created_at=cd.get("created_at", 0.0))
        g.cues[cue.id] = cue
        max_cue = max(max_cue, cue.id)
    # advance THIS graph's id counters past the loaded maxima (per-instance, D15)
    # — never touch global state, so other live instances are unaffected.
    g._node_seq = max(g._node_seq, max_node)
    g._cue_seq = max(g._cue_seq, max_cue)
    return g


# --- warm tier: suspended streams (unfinished thoughts) ---------------------- #
def streams_to_dict(sm: StreamManager) -> dict:
    return {
        "stream_seq": sm._stream_seq,
        "warm": [
            {"id": s.id, "centroid": s.centroid, "pressure": s.pressure,
             "fatigue": s.fatigue, "deferred": s.deferred, "refractory": s.refractory,
             "idle_ticks": s.idle_ticks, "event_ids": s.event_ids,
             "node_ids": s.node_ids, "summary": s.summary}
            for s in sm.warm.values()
        ],
    }


def restore_streams(data: dict, sm: StreamManager) -> None:
    sm.warm.clear()
    max_sid = 0
    for sd in data.get("warm", []):
        s = Stream(centroid=sd["centroid"], pressure=sd.get("pressure", 0.0),
                   fatigue=sd.get("fatigue", 0.0), deferred=sd.get("deferred", False),
                   refractory=sd.get("refractory", False), suspended=True,
                   idle_ticks=sd.get("idle_ticks", 0), event_ids=sd.get("event_ids", []),
                   node_ids=sd.get("node_ids", []), summary=sd.get("summary", ""),
                   id=sd["id"])
        sm.warm[s.id] = s
        max_sid = max(max_sid, s.id)
    sm._stream_seq = max(sm._stream_seq, data.get("stream_seq", 0), max_sid)


def save(g: Graph, path: Union[str, Path], streams: Optional[StreamManager] = None) -> None:
    data = graph_to_dict(g)
    if streams is not None:
        data["streams"] = streams_to_dict(streams)     # warm tier rides alongside the graph
    Path(path).write_text(json.dumps(data, indent=2))


def load(g: Graph, path: Union[str, Path], streams: Optional[StreamManager] = None) -> Graph:
    data = json.loads(Path(path).read_text())
    dict_to_graph(data, g)
    if streams is not None and "streams" in data:
        restore_streams(data["streams"], streams)
    return g
