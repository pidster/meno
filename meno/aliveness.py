"""Executable criteria for the zombie test (realisation-plan.md R0).

The vision's bar for a *working* Meno is not a green suite — it is whether the
system is **particular** rather than generic (CLAUDE.md principle 6). This module
turns that bar into probes over observable kernel state, so "alive vs zombie" is
measured, not asserted.

Five marks, each a probe that returns **evidence, not just a number** (a bare
score is exactly the placeholder-metric failure the review protocol forbids):

  - ``particularity``   — idiosyncratic associative structure (preferential
                          pathways, hubs of attention), not a flat uniform graph.
  - ``initiative``      — *sustained* self-directed action (curiosity reaching
                          out, impulses resurfacing), not a single scripted tick.
  - ``synthesis``       — insight that is both cross-source AND emergent: its
                          conclusion introduces meaning its source nodes did not
                          contain. A templated reflection scores zero.
  - ``novelty``         — generated content that introduces concepts absent from
                          the inputs. A *necessary-not-sufficient* proxy for
                          surprise; true builder-surprise is panel-judged in R5,
                          never claimed by this number.
  - ``divergence``      — two minds given the same inputs build different
                          *structure* (which associations, which hubs), not just
                          different words (non-substitutability).

Design notes earned from the R0 adversarial review:
  - Synthesis and the verdict are **content-sensitive**: the deterministic stub —
    a zombie by construction — must score ~0 on synthesis. Counting the mere
    *existence* of a merged cue (a label the system writes about itself) let the
    stub pass, so synthesis now requires the conclusion text to introduce terms
    its sources lack. On a live run, reflection text is supplied via
    ``reflection_texts``; offline it is read from journalled (verbatim) cues.
  - The verdict is **gated on cognition being real** (``cognition_real``): a run
    whose cognition silently fell back to the stub cannot be called "alive" — it
    is ``indeterminate``. This is the R1 loud-failure contract reaching back.
  - ``divergence`` compares graph *structure*, not node vocabulary, because two
    minds fed the same corpus share most words by construction; what must differ
    is what they linked and what became central.

None of these proves phenomenal life. Together they test for the *functional*
marks the vision demands, and — the point — they FAIL on a mechanically-correct
zombie. tests/test_aliveness.py proves that discrimination on a LIVE stub run,
not only on hand-built graphs.

Stdlib only: an aliveness check must run anywhere the kernel runs, with no
service. Probes are pure functions of state (a Meno, a Graph, or plain text).
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional

from .graph import Graph
from .models import StubModelProvider

_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "the a an and or of to in on at is are was were be been being it its this that "
    "these those for with as by from into about over under again than then so but if "
    "what which who whom how why when where there here not no yes do does did has have "
    "had i you he she we they them his her our your their me my mine more most some any "
    "one two three rather whether across between among also can could would should will "
    "may might must just only very much many via per such each both either out off".split()
)
def _content_terms(text: str) -> set:
    """Meaning-bearing tokens (lowercased, stopworded). The unit of 'aboutness'."""
    return {t for t in _WORD.findall(text.lower()) if t not in _STOP and len(t) > 2}


def _stub_scaffolding_terms() -> set:
    """The deterministic stub's template literals, DERIVED from its actual outputs
    rather than hand-typed — so the boilerplate set can never drift out of sync with
    the templates (R0 red-team: the 'these fragments' fallback was missed by a hand
    list). The stub IS the zombie reference; the constant words it emits as
    scaffolding are by definition never emergent thought. A marker stands in for
    'input' and is removed, leaving only the literal template tokens."""
    s = StubModelProvider()
    mark = "qzzmark"
    outs = [
        s.synthesise("", []),                 # fallback branch -> "these fragments"
        s.synthesise(mark, [mark]),           # main synthesis template
        s.associate(mark, []),                # "stands alone for now"
        s.associate(mark, [mark]),            # "connects to: ..."
        s.wonder(mark).get("thought") or "",  # "I wonder: ..."
    ]
    ap = s.appraise(mark, 0.9)
    outs += [ap.get("reaction") or "", ap.get("question") or ""]
    terms = set()
    for t in outs:
        terms |= _content_terms(t)
    terms.discard(mark)
    return terms


# Scaffolding the kernel emits but a model does NOT — reconstruct()'s '(partial)' and
# ghost "(something about … — but the details won't come)", control's wake text,
# consolidation's rediscovery — plus generic filler. Unioned with the stub's own
# (auto-derived) template literals. None of these is ever a sign of emergent thought.
_KERNEL_SCAFFOLDING = frozenset(
    "partial something details won come returning rediscovered reflection formed "
    "intent insight thought thinking memory sense matter".split()
)
_BOILERPLATE = _KERNEL_SCAFFOLDING | _stub_scaffolding_terms()


def _emergent_terms(text: str, source_terms: set) -> set:
    """Terms in a conclusion that neither its sources nor the kernel's templates
    contain — the computable residue of 'an insight its inputs did not hold'."""
    return _content_terms(text) - source_terms - _BOILERPLATE


def _gini(values: List[float]) -> float:
    """Concentration of a non-negative distribution. 0 = perfectly uniform,
    →1 = all mass on one element. The math of 'idiosyncrasy': a tidy graph spreads
    weight evenly (low gini); a lived-in one has preferential pathways (high)."""
    xs = [v for v in values if v >= 0]
    n = len(xs)
    if n == 0:
        return 0.0
    s = sum(xs)
    if s == 0:
        return 0.0
    xs.sort()
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

    g_weight = _gini(weights)                # are some associations privileged?
    g_degree = _gini(list(degree.values()))   # are some memories hubs?
    # degree concentration is the more reliable idiosyncrasy signal (edge weights
    # saturate toward 1.0 on busy streams, flattening their gini), so weight it less.
    score = 0.35 * g_weight + 0.65 * g_degree

    hubs = sorted(degree.items(), key=lambda kv: kv[1], reverse=True)[:3]
    evidence = [f"hub: {graph.nodes[nid].content[:50]!r} (degree-weight {d:.2f})"
                for nid, d in hubs if nid in graph.nodes]
    return {"score": round(score, 3), "edge_weight_gini": round(g_weight, 3),
            "degree_gini": round(g_degree, 3), "nodes": n_nodes, "edges": n_edges,
            "evidence": evidence}


# --------------------------------------------------------------------------- #
# 2. Initiative — did the agent SUSTAIN action on drives of its own?
# --------------------------------------------------------------------------- #
# The kernel emits drive-initiated events with these sources: curiosity discharge
# (runtime._discharge_curiosity) and interoceptive impulse wakes (control.tick).
# 'cognition' is reactive derivation (not a drive); excluded deliberately.
_SELF_SOURCES = frozenset({"curiosity", "initiative"})


def initiative(meno) -> dict:
    """Self-directed action, not pure reaction — and *sustained*, so a single
    scripted boredom-birth cannot clear the bar (R0 review, theory lens). Reports
    internal cognition and bottom-up (percept-provoked) curiosity separately so a
    living-but-internal run isn't mistaken for a reactive one."""
    self_events = [e for e in meno.bus.log if e.source in _SELF_SOURCES]
    fed = [e for e in meno.bus.log if e.kind.value == "sense"]
    internal = [e for e in meno.bus.log
                if e.kind.value != "sense" and e.source not in _SELF_SOURCES]
    curiosities = list(getattr(meno.curiosities, "items", []))
    bottom_up = sum(1 for c in curiosities if getattr(c, "source", "") == "bottom-up")
    total = len(self_events) + len(fed)
    frac = (len(self_events) / total) if total else 0.0
    sustained = len(self_events) >= 2          # one auto-tick is not initiative
    score = (0.6 if sustained else 0.0) + 0.4 * min(1.0, frac * 3)
    evidence = [f"{e.source}: {e.content[:60]!r}" for e in self_events[:5]]
    return {"score": round(score, 3), "self_initiated": len(self_events),
            "externally_fed": len(fed), "internal_cognition": len(internal),
            "self_fraction": round(frac, 3), "sustained_initiative": sustained,
            "bottom_up_curiosities": bottom_up, "open_curiosities": len(curiosities),
            "evidence": evidence}


# --------------------------------------------------------------------------- #
# 3. Synthesis — insight that is cross-source AND emergent
# --------------------------------------------------------------------------- #
def synthesis(graph: Graph, reflection_texts: Optional[Dict[int, str]] = None) -> dict:
    """Emergent insight, not restatement or label. A cue counts only if (a) it draws
    on >=2 distinct source memories AND (b) its conclusion introduces terms that
    none of its sources held. Condition (b) is what the deterministic stub fails:
    its synthesise() output is a template over the inputs' OWN material, so once we
    account for everything reconstruct() draws on — the entry points, the nodes its
    spreading activation reached, the cue's own occasion label, and the kernel
    scaffolding ('(partial)', ghost text) — the stub conclusion has zero residue.
    Only a real model that names something the sources didn't can score here.

    We do NOT require distinct *streams*: a reflection that synthesises over several
    memories of one train of thought is still synthesis (and requiring merges would
    make the mark unreachable, since merges rarely fire — R0 review R-C).

    ``reflection_texts``: cue.id -> reconstructed/known conclusion. On a live run the
    caller reconstructs cues once and passes them here; offline, journalled cues are
    read directly. A cue whose text is unavailable cannot show emergence: uncounted.
    """
    texts = reflection_texts or {}
    genuine, unverified = [], 0
    for cue in graph.cues.values():
        if len(set(cue.entry_points)) < 2:     # synthesis draws on >=2 memories
            continue
        text = texts.get(cue.id, cue.verbatim)
        # source_text is the material the conclusion was derived from, FROZEN at
        # generation time (graph.store_cue / reconstruct). We judge emergence against
        # that, never against an audit-time re-spread — forgetting could otherwise
        # delete the nodes a stub conclusion echoed, making its words look fresh
        # (R0 red-team P0). A cue with neither text nor frozen provenance is unprovable.
        if text is None or not cue.source_text:
            unverified += 1
            continue
        fresh = _emergent_terms(text, _content_terms(cue.source_text))
        if fresh:
            genuine.append((cue, sorted(fresh)[:6]))
    score = min(1.0, 0.5 * len(genuine))
    evidence = [f"insight {c.occasion[:50]!r} introduces {fr}" for c, fr in genuine[:3]]
    return {"score": round(score, 3), "genuine_insights": len(genuine),
            "cross_source_unverified": unverified, "evidence": evidence}


# --------------------------------------------------------------------------- #
# 4. Novelty — generated content the inputs did not contain
# --------------------------------------------------------------------------- #
def novelty(generated_texts: List[str], input_texts: List[str]) -> dict:
    """Surprise made computable (necessary, not sufficient): the share of
    meaning-bearing terms in what the agent PRODUCED that never appeared in what
    it was GIVEN, excluding kernel boilerplate."""
    given = set()
    for t in input_texts:
        given |= _content_terms(t)
    produced, fresh = set(), set()
    for t in generated_texts:
        terms = _content_terms(t)
        produced |= terms
        fresh |= (terms - given - _BOILERPLATE)
    score = (len(fresh) / len(produced)) if produced else 0.0
    return {"score": round(score, 3), "fresh_terms": sorted(fresh)[:12],
            "produced_terms": len(produced), "given_terms": len(given)}


# --------------------------------------------------------------------------- #
# 5. Divergence — two minds, same inputs, different STRUCTURE
# --------------------------------------------------------------------------- #
def _assoc_set(graph: Graph) -> set:
    """The set of associations the mind formed, identified by node *content* (so it
    is comparable across instances with different node ids). This is structure —
    which things got linked — not vocabulary."""
    out = set()
    for (a, b) in graph.edges:
        if a in graph.nodes and b in graph.nodes:
            out.add(frozenset((graph.nodes[a].content.lower().strip(),
                               graph.nodes[b].content.lower().strip())))
    return out


def _hub_set(graph: Graph, k: int = 3) -> set:
    degree: Dict[int, float] = {}
    for (a, b), w in graph.edges.items():
        degree[a] = degree.get(a, 0.0) + w
        degree[b] = degree.get(b, 0.0) + w
    top = sorted(degree.items(), key=lambda kv: kv[1], reverse=True)[:k]
    return {graph.nodes[nid].content.lower().strip() for nid, _ in top if nid in graph.nodes}


def _jaccard_distance(a: set, b: set) -> float:
    u = a | b
    return (1.0 - len(a & b) / len(u)) if u else 0.0


def divergence(graph_a: Graph, graph_b: Graph) -> dict:
    """Non-substitutability, measured structurally: how differently two minds
    associated and centred their memories. Two instances over the SAME inputs that
    linked the same things and grew the same hubs are substitutable (→0, a zombie
    pair); ones that did not are particular (→1). Node vocabulary is deliberately
    NOT used — same inputs share words by construction."""
    aa, ab = _assoc_set(graph_a), _assoc_set(graph_b)
    ha, hb = _hub_set(graph_a), _hub_set(graph_b)
    assoc_dist = _jaccard_distance(aa, ab)        # which associations formed
    hub_dist = _jaccard_distance(ha, hb)          # what became central
    score = 0.6 * assoc_dist + 0.4 * hub_dist
    return {"score": round(score, 3), "association_distance": round(assoc_dist, 3),
            "hub_distance": round(hub_dist, 3), "shared_associations": len(aa & ab),
            "distinct_associations": len((aa | ab) - (aa & ab))}


# --------------------------------------------------------------------------- #
# Aggregate verdict
# --------------------------------------------------------------------------- #
# Thresholds are the bar for "this mark is genuinely present", with margin above
# what the deterministic stub reaches (measured in tests/test_aliveness.py):
#   - synthesis: stub scores 0.0 (templated conclusions have no emergent terms);
#     0.25 = half of one genuine emergent insight, unreachable by the stub.
#   - particularity: a uniform ring scores ~0; 0.20 needs real degree concentration.
#   - initiative: needs >=2 sustained self-acts (0.60 base), not one scripted tick.
PASS = {"particularity": 0.20, "initiative": 0.60, "synthesis": 0.25,
        "novelty": 0.30, "divergence": 0.25}
_CORE = ("particularity", "initiative", "synthesis")


def zombie_report(meno, *, inputs: Optional[List[str]] = None,
                  generated: Optional[List[str]] = None,
                  reflection_texts: Optional[Dict[int, str]] = None,
                  other: Optional["object"] = None,
                  cognition_real: Optional[bool] = None) -> dict:
    """Run the marks and return a structured, auditable verdict.

    A mechanically-correct system that creates nodes, runs activation, and
    executes every mode can still score ~0 here — that is the whole point. Verdict:
      - ``indeterminate`` if ``cognition_real is False`` (the run secretly used the
        stub; "alive" is undefined without real cognition — R1 contract);
      - ``alive`` iff the three core marks pass;
      - ``zombie`` otherwise.
    Every criterion carries its evidence so the conclusion is inspected, not trusted.
    """
    marks: Dict[str, dict] = {
        "particularity": particularity(meno.graph),
        "initiative": initiative(meno),
        "synthesis": synthesis(meno.graph, reflection_texts),
    }
    if inputs is not None:
        gen = generated if generated is not None else _default_generated(meno)
        marks["novelty"] = novelty(gen, inputs)
    if other is not None:
        marks["divergence"] = divergence(meno.graph, other.graph)

    passed = {k: (m["score"] >= PASS[k]) for k, m in marks.items()}
    if cognition_real is False:
        verdict = "indeterminate"
    elif all(passed[k] for k in _CORE):
        verdict = "alive"
    else:
        verdict = "zombie"
    failed = [k for k, ok in passed.items() if not ok]
    return {"verdict": verdict, "passed": passed, "failed_marks": failed,
            "core_marks": list(_CORE), "cognition_real": cognition_real,
            "marks": marks}


def _default_generated(meno) -> List[str]:
    """Agent-authored text readable without a model: curiosity questions the
    cognition tier raised. Stream summaries and cue occasions are excluded — they
    echo input content (processors set them from event text), so counting them as
    'generated' would muddy novelty (R0 review, data lens)."""
    return [c.text for c in getattr(meno.curiosities, "items", [])]
