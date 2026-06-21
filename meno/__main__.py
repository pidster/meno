"""A scripted demonstration of the bare loop end to end.

    python -m meno              # run the scripted scenario
    python -m meno --interactive   # type stimuli yourself; 'dream', 'recall X', 'quit'

Shows: gating/habituation, stream formation, escalation to a reflection,
storage-as-trigger, a consolidation (dream) pass, and a reconstructive recall.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from .config import Config
from .models import make_models
from .runtime import Meno


def banner(title: str) -> None:
    print(f"\n=== {title} ===")


def _models(use_anthropic: bool):
    if not use_anthropic:
        return make_models("stub")
    provider = make_models("anthropic")
    if getattr(provider, "available", False):
        print("  [using real Anthropic models: Haiku/Sonnet/Opus]")
    else:
        print("  [--anthropic requested but no client/key available; falling back to stub]")
    return provider


def scripted(use_anthropic: bool = False) -> None:
    mind = Meno(config=Config(), models=_models(use_anthropic),
                workspace=Path(tempfile.mkdtemp(prefix="meno_")), verbose=True)

    stimuli = [
        # a "memory" cluster (will cohere into one stream)
        "the user is asking about associative memory and spreading activation",
        "spreading activation surfaces unexpected connections between memories",
        "the user wonders whether memory is reconstructed rather than retrieved",
        # an "ops" cluster (a second stream that competes for the scarce deep slot)
        "the database connection dropped again under heavy load",
        "the database is refusing connections and the pool is exhausted",
        # a repeat -> habituation at the gate
        "the user is asking about associative memory and spreading activation",
        # a lone novel percept
        "a network event: webhook received from the deploy pipeline",
    ]

    banner("WAKING — feeding stimuli (reactive)")
    for s in stimuli:
        print(f"\n> {s}")
        mind.feed(s)
        mind.run_until_quiescent()

    banner("SNAPSHOT after waking")
    for k, v in mind.snapshot().items():
        print(f"  {k}: {v}")

    banner("QUIET — heartbeat: initiative (impulses) + curiosity (reaching out)")
    n0 = len(mind.bus.log)
    mind.heartbeat()
    self_made = [e for e in mind.bus.log[n0:] if e.source in ("initiative", "curiosity")]
    from_cur = sum(e.source == "curiosity" for e in self_made)
    print(f"  meno acted on its own: {len(self_made)} self-generated events "
          f"({from_cur} from curiosity)")

    banner("DREAM — consolidation pass")
    report = mind.dream()
    print(f"  report: {report}")

    banner("RECALL — reconstructive reflection")
    for q in ["associative memory and spreading activation",
              "database connections and the pool",
              "quantum chromodynamics"]:
        r = mind.recall(q)
        print(f"  recall({q!r}) -> {r['mode']} (sim={r['similarity']:.2f})")
        if r["text"]:
            print(f"      {r['text']}")

    banner("JOURNALING — deliberate verbatim freeze (the escape hatch)")
    q = "associative memory and spreading activation"
    j = mind.journal(q)
    cue = mind.graph.cues[j["cue"]]
    a = mind.graph.reconstruct(cue, mind.models)
    b = mind.graph.reconstruct(cue, mind.models)
    print(f"  journaled cue {j['cue']}; two reconstructions identical? {a == b}")
    print(f"      frozen: {a}")

    banner("REMAIN — save, then wake a fresh mind from the saved graph")
    save_path = Path(tempfile.mkdtemp(prefix="meno_save_")) / "memory.json"
    mind.save(save_path)
    woken = Meno(config=Config(), workspace=Path(tempfile.mkdtemp(prefix="meno_")))
    print(f"  fresh mind nodes before load: {woken.snapshot()['nodes']}")
    woken.load(save_path)
    print(f"  after waking from saved graph: {woken.snapshot()}")
    r = woken.recall("associative memory and spreading activation")
    print(f"  recall after restart -> {r['mode']} (sim={r['similarity']:.2f})")
    if r["text"]:
        print(f"      {r['text']}")

    banner("SNAPSHOT after dreaming")
    for k, v in mind.snapshot().items():
        print(f"  {k}: {v}")


def interactive(use_anthropic: bool = False) -> None:
    mind = Meno(config=Config(), models=_models(use_anthropic),
                workspace=Path(tempfile.mkdtemp(prefix="meno_")), verbose=True)
    print("meno interactive. commands: dream | recall <q> | snapshot | quit")
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line == "quit":
            break
        if line == "dream":
            print(mind.dream())
        elif line == "snapshot":
            print(mind.snapshot())
        elif line.startswith("recall "):
            print(mind.recall(line[7:]))
        else:
            mind.feed(line)
            mind.run_until_quiescent()


if __name__ == "__main__":
    anthropic = "--anthropic" in sys.argv
    if "--interactive" in sys.argv:
        interactive(anthropic)
    else:
        scripted(anthropic)
