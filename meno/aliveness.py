"""Executable criteria for the zombie test (realisation-plan.md R0).

The vision's bar for a *working* Meno is not a green suite — it is whether the
system is **particular** rather than generic (CLAUDE.md principle 6). This module
turns that bar into probes over observable kernel state, so "alive vs zombie" is
measured, not asserted.

Five marks, each a probe that returns **evidence, not just a number** (a bare
score is exactly the placeholder-metric failure the review protocol forbids):

  - ``particularity``   — idiosyncratic associative structure (preferential
                          pathways, hubs of attention), not a flat uniform graph.
  - ``initiative``      — self-generated drives the agent acted on (curiosity
                          reaching out, impulses resurfacing), not pure reaction.
  - ``synthesis``       — insight no single input/stream contained (merged
                          streams, multi-source reflection).
  - ``novelty``         — generated content that introduces concepts absent from
                          the inputs (a computable proxy for surprise).
  - ``divergence``      — two minds given the same inputs do NOT converge on the
                          same graph (non-substitutability).

None of these proves phenomenal life. Together they test for the *functional*
marks the vision demands, and — the point — they FAIL on a mechanically-correct
zombie. The fidelity tests in tests/test_aliveness.py prove that discrimination.

Stdlib only: an aliveness check must run anywhere the kernel runs, with no
service. Probes are pure functions of state (a Meno, a Graph, or plain text), so
they are equally usable in an offline unit test and on a live accumulated run.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional

from .graph import Graph

_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "the a an and or of to in on at is are was were be been being it its this that "
    "these those for with as by from into about over under again than then so but if "
    "what which who whom how why when where there here not no yes do does did has have "
    "had i you he she we they them his her our your their me my mine more most some any "
    "one two three rather whether across between among also can could would should will "
    "may might must just only very much many".split()
)


def _content_terms(text: str) -> set:
    """Meaning-bearing tokens (lowercased, stopworded). The unit of 'aboutness'."""
    return {t for t in _WORD.findall(text.lower()) if t not in _STOP and len(t) > 2}


def _gini(values: List[float]) -> float:
    """Concentration of a non-negative distribution. 0 = perfectly uniform,
    →1 = all mass on one element. This is the math of 'idiosyncrasy': a tidy graph
    spreads weight evenly (low gini); a lived-in one has preferential pathways and
    hubs (high gini)."""
    xs = [v for v in values if v >= 0]
    n = len(xs)
    if n == 0:
        return 0.0
    s = sum(xs)
    if s == 0:
        return 0.0
    xs.sort()
    # cumulative-share form, stable and O(n log n)
    cum = 0.0
    for i, x in enumerate(xs, 1):
        cum += i * x
    return (2 * cum) / (n * s) - (n + 1) / n


# --------------------------------------------------------------------------- #
# 1. Particularity — is the associative structure idiosyncratic or flat?
# --------------------------------------------------------------------------- #
def particularity(graph: Graph) -> dict:
    """Idiosyncrasy of the graph: preferential pathways (edge-weight concentration)
    and hubs of attention (degree concentration). A dead, tidy, uniform graph
    scores low; one shaped by what the agent actually cared about scores high."""
    weights = list(graph.edges.values())
    degree: Dict[int, float] = {}
    for (a, b), w in graph.edges.items():
        degree[a] = degree.get(a, 0.0) + w
        degree[b] = degree.get(b, 0.0) + w

    n_nodes, n_edges = len(graph.nodes), len(graph.edges)
    if n_nodes < 3 or n_edges < 2:
        return {"score": 0.0, "reason": "too small to be particular yet",
                "nodes": n_nodes, "edges": n_edges, "evidence": []}

    g_weight = _gini(weights)               # are some associations privileged?
    g_degree = _gini(list(degree.values()))  # are some memories hubs?
    score = 0.5 * g_weight + 0.5 * g_degree

    # evidence: the densest neighbourhoods — what this mind clustered around
    hubs = sorted(degree.items(), key=lambda kv: kv[1], reverse=True)[:3]
    evidence = [f"hub: {graph.nodes[nid].content[:50]!r} (degree-weight {d:.2f})"
                for nid, d in hubs if nid in graph.nodes]
    return {"score": round(score, 3), "edge_weight_gini": round(g_weight, 3),
            "degree_gini": round(g_degree, 3), "nodes": n_nodes, "edges": n_edges,
            "evidence": evidence}


# --------------------------------------------------------------------------- #
# 2. Initiative — did the agent act on drives of its own?
# --------------------------------------------------------------------------- #
_SELF_SOURCES = frozenset({"curiosity", "initiative"})


def initiative(meno) -> dict:
    """Self-directed action, not pure reaction. Counts events the agent generated
    from its own drives (curiosity reaching out; impulses resurfacing a deferred
    thought) against externally-fed stimuli, and reports the actual self-acts."""
    self_events = [e for e in meno.bus.log if e.source in _SELF_SOURCES]
    fed = [e for e in meno.bus.log if e.kind.value == "sense"]
    curiosities = list(getattr(meno.curiosities, "items", []))
    total = len(self_events) + len(fed)
    frac = (len(self_events) / total) if total else 0.0
    acted = len(self_events) > 0
    # score rewards BOTH that it reached out and that reaching-out is a real share
    score = (0.6 if acted else 0.0) + 0.4 * min(1.0, frac * 3)
    evidence = [f"{e.source}: {e.content[:60]!r}" for e in self_events[:5]]
    return {"score": round(score, 3), "self_initiated": len(self_events),
            "externally_fed": len(fed), "self_fraction": round(frac, 3),
            "open_curiosities": len(curiosities), "acted_on_impulse": acted,
            "evidence": evidence}


# --------------------------------------------------------------------------- #
# 3. Synthesis — insight no single input contained
# --------------------------------------------------------------------------- #
def synthesis(graph: Graph) -> dict:
    """Emergent insight: convergent streams merged into one (occasion 'insight:'),
    or a reflection drawn over several distinct memories at once. A reflection
    over a single node is just a restatement; synthesis spans sources."""
    insights, multi = [], []
    for cue in graph.cues.values():
        if cue.occasion.lower().startswith("insight"):
            insights.append(cue)
        elif len(set(cue.entry_points)) >= 2:
            multi.append(cue)
    # an insight (cross-stream merge) is worth more than a multi-node reflection
    score = min(1.0, 0.6 * len(insights) + 0.25 * len(multi))
    evidence = [f"insight: {c.occasion[:70]!r} (over {len(set(c.entry_points))} nodes)"
                for c in insights[:3]]
    evidence += [f"multi-source reflection: {c.occasion[:60]!r} "
                 f"({len(set(c.entry_points))} nodes)" for c in multi[:3]]
    return {"score": round(score, 3), "insights": len(insights),
            "multi_source_reflections": len(multi), "evidence": evidence}


# --------------------------------------------------------------------------- #
# 4. Novelty — generated content that the inputs did not contain
# --------------------------------------------------------------------------- #
def novelty(generated_texts: List[str], input_texts: List[str]) -> dict:
    """Surprise made computable: the share of meaning-bearing terms in what the
    agent PRODUCED that never appeared in what it was GIVEN. Pure text function so
    it works on stored curiosity questions offline and on live reconstructed
    reflections alike."""
    given = set()
    for t in input_texts:
        given |= _content_terms(t)
    produced, fresh = set(), set()
    for t in generated_texts:
        terms = _content_terms(t)
        produced |= terms
        fresh |= (terms - given)
    score = (len(fresh) / len(produced)) if produced else 0.0
    return {"score": round(score, 3), "fresh_terms": sorted(fresh)[:12],
            "produced_terms": len(produced), "given_terms": len(given)}


# --------------------------------------------------------------------------- #
# 5. Divergence — two minds, same inputs, different graphs (non-substitutable)
# --------------------------------------------------------------------------- #
def _graph_terms(graph: Graph) -> set:
    terms = set()
    for node in graph.nodes.values():
        terms |= _content_terms(node.content)
    return terms


def divergence(graph_a: Graph, graph_b: Graph) -> dict:
    """Non-substitutability: how much two accumulated minds differ. Jaccard
    *distance* over node-content meaning plus a difference in reflection occasions.
    0.0 = the same mind (a zombie: any instance reproduces it); →1.0 = particular
    histories that did not converge."""
    ta, tb = _graph_terms(graph_a), _graph_terms(graph_b)
    union = ta | tb
    content_dist = 1.0 - (len(ta & tb) / len(union)) if union else 0.0
    oa = {c.occasion.lower() for c in graph_a.cues.values()}
    ob = {c.occasion.lower() for c in graph_b.cues.values()}
    ounion = oa | ob
    reflection_dist = 1.0 - (len(oa & ob) / len(ounion)) if ounion else 0.0
    score = 0.7 * content_dist + 0.3 * reflection_dist
    return {"score": round(score, 3), "content_distance": round(content_dist, 3),
            "reflection_distance": round(reflection_dist, 3),
            "shared_terms": len(ta & tb), "distinct_terms": len(union - (ta & tb))}


# --------------------------------------------------------------------------- #
# Aggregate verdict
# --------------------------------------------------------------------------- #
# Thresholds are the bar for "this mark is genuinely present", not fitted numbers.
# Particularity/synthesis/initiative are the *core* marks; novelty/divergence are
# checked only when inputs / a comparison mind are supplied.
PASS = {"particularity": 0.20, "initiative": 0.60, "synthesis": 0.25,
        "novelty": 0.30, "divergence": 0.25}


def zombie_report(meno, *, inputs: Optional[List[str]] = None,
                  generated: Optional[List[str]] = None,
                  other: Optional["object"] = None) -> dict:
    """Run the marks and return a structured, auditable verdict.

    A mechanically-correct system that creates nodes, runs activation, and
    executes every mode can still score ~0 here — that is the whole point. The
    verdict is ``alive`` only if the three core marks pass; ``zombie`` otherwise.
    Every criterion carries its evidence so the conclusion can be inspected, not
    trusted.
    """
    marks: Dict[str, dict] = {
        "particularity": particularity(meno.graph),
        "initiative": initiative(meno),
        "synthesis": synthesis(meno.graph),
    }
    if inputs is not None:
        gen = generated if generated is not None else _default_generated(meno)
        marks["novelty"] = novelty(gen, inputs)
    if other is not None:
        marks["divergence"] = divergence(meno.graph, other.graph)

    passed = {k: (m["score"] >= PASS[k]) for k, m in marks.items()}
    core = ["particularity", "initiative", "synthesis"]
    verdict = "alive" if all(passed[k] for k in core) else "zombie"
    failed = [k for k, ok in passed.items() if not ok]
    return {"verdict": verdict, "passed": passed, "failed_marks": failed,
            "core_marks": core, "marks": marks}


def _default_generated(meno) -> List[str]:
    """What the agent has 'said' that we can read without a model: its curiosity
    questions and stream summaries (reflection text itself is a model
    reconstruction, supplied explicitly on a live run)."""
    out = [c.text for c in getattr(meno.curiosities, "items", [])]
    out += [s.summary for s in meno.streams.active.values() if s.summary]
    out += [c.occasion for c in meno.graph.cues.values()]
    return out
