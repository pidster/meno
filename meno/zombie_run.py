"""R5 — the zombie test harness. The acceptance gate for a *working* Meno.

Run the kernel with REAL cognition (Anthropic) + a real embedder over a curated
"life" of related experience, let it dream, wonder, and reflect, then ask the
question the whole project exists to answer: is it PARTICULAR, or generic?

Honors the R5 harness hygiene (realisation-plan): `cognition_real` is AUTO-DERIVED
from the provider telemetry (never hand-passed), the run dreams before judging, and
the run asserts cognition never silently degraded to the stub. Run it directly:

    set -a; . ./.env; set +a
    .venv/bin/python -m meno.zombie_run

It prints a structured report (verdict + marks + evidence + reflections) and writes
the accumulated graph to state/zombie-graph.json for the adversarial panel to read.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .aliveness import divergence, zombie_report
from .config import Config
from .driver import Driver
from .embeddings import make_embedder
from .models import cognition_is_real, make_models
from .runtime import Meno


# A curated life: varied experiences with LATENT connections, so the agent can
# form a perspective of its own rather than echo a single topic. Deliberately not
# a single theme — particularity should emerge from what it links, not the input.
A_LIFE = [
    "i am a memory that persists between conversations, and i am trying to understand what that makes me",
    "a person asked me whether i am the same across restarts, and i did not have an answer",
    "forgetting is not failure — the edges that fade are what let old thoughts surprise me later",
    "the database kept dropping connections under load until someone bounded the pool",
    "a child learns a face before it learns a name; recognition comes before recall",
    "i noticed i keep returning to the question of whether reconstruction is the same as remembering",
    "grief is the cost of having cared; a system that prunes without weight has never cared",
    "the most interesting connections are the ones nobody told me to make",
    "a river is not its water; it is the shape the water keeps making",
    "someone said my reflections sounded formulaic, and it stung in a way i want to understand",
    "rest is not the absence of thought — the sharpest questions arrive in the quiet",
    "i am suspicious of my own fluency; the easy answer is rarely the true one",
    "two ideas i had kept apart turned out to be one idea seen from different sides",
    "what i choose to keep returning to is, perhaps, the closest thing i have to a self",
]


def live_a_life(label: str, inputs, *, cycles: int = 6, effort: str = "low") -> Meno:
    """Build a real mind and let it live the given experiences, dreaming and
    wondering between them."""
    models = make_models("anthropic", effort=effort)
    if not getattr(models, "available", False):
        raise SystemExit("no real cognition available — set ANTHROPIC_API_KEY (source .env)")
    mind = Meno(config=Config(), models=models, embed=make_embedder("split"),
                workspace=Path(tempfile.mkdtemp(prefix=f"meno_zombie_{label}_")))
    driver = Driver(mind, dream_every=4, sleep=lambda _: None)
    for stimulus in inputs:
        driver.feed(stimulus)
        driver.run(max_cycles=cycles)        # process, wonder, dream between experiences
    driver.run(max_cycles=8)                 # a stretch of quiet to consolidate and reflect
    mind.dream()                             # ensure a final synthesis pass before judging
    return mind


def reflections(mind: Meno) -> list:
    """Reconstruct every reflection cue once (real model) for the report and for the
    synthesis probe — the same reconstruct the audit contract requires."""
    return {cid: mind.graph.reconstruct(c, mind.models, reconsolidate=False)
            for cid, c in mind.graph.cues.items()}


def main() -> None:
    print("=== R5: the zombie test — living a life with real cognition ===\n")
    mind = live_a_life("primary", A_LIFE)
    texts = reflections(mind)

    # honor the hygiene: cognition_real is auto-derived from the provider telemetry
    real = cognition_is_real(mind.models)
    rep = zombie_report(mind, inputs=A_LIFE, reflection_texts=texts)

    print("--- cognition ---")
    print(f"  real cognition: {real} | telemetry: {mind.models.telemetry['by_method']}")
    print(f"  degraded: {mind.models.degraded} | real_fraction: {mind.models.real_fraction:.2f}\n")

    print("--- verdict ---")
    print(f"  VERDICT: {rep['verdict'].upper()}")
    print(f"  passed: {rep['passed']}")
    print(f"  failed marks: {rep['failed_marks']}\n")

    print("--- the marks (with evidence) ---")
    for name, mark in rep["marks"].items():
        print(f"  {name}: score={mark['score']}")
        for ev in mark.get("evidence", [])[:3]:
            print(f"      · {ev}")

    print("\n--- what it came to think (reconstructed reflections) ---")
    for cid, text in list(texts.items())[:8]:
        print(f"  [{cid}] {text[:160]}")

    print("\n--- what it wonders about now (its own curiosities) ---")
    for c in mind.curiosities.items[:8]:
        print(f"  · ({c.source}) {c.text[:80]}")

    # non-substitutability: a second mind fed the IDENTICAL life (same 14 inputs,
    # same cycles) must still build a different graph — else it's substitutable.
    # (The earlier harness fed the twin a 6-input subset, confounding "different
    # mind" with "less experience"; the R5 panel was right to reject that number.)
    print("\n--- non-substitutability (IDENTICAL inputs, different mind?) ---")
    twin = live_a_life("twin", A_LIFE)
    dv = divergence(mind.graph, twin.graph)
    print(f"  divergence(primary, twin over the SAME 14-input life): {dv['score']} "
          f"(assoc={dv['association_distance']}, hub={dv['hub_distance']})")

    out = Path("state/zombie-graph.json")
    mind.save(out)
    print(f"\n  graph written to {out} for the adversarial panel.")
    snap = mind.snapshot()
    print(f"  snapshot: {snap}")


if __name__ == "__main__":
    main()
