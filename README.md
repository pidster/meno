# meno

*μένω — "I remain"*

A cognitive kernel: a persistent agent with associative memory, a default-mode
loop, and self-directed cognition. Not a chatbot with a database — an attempt at
something that accumulates a perspective and becomes particular through
experience.

This is **v2**. The first implementation (a hand-cranked "tick simulation") lives
in branch `archive/tick-simulation`. v2 is a continuous, event-driven kernel.

## The idea in one paragraph

Everything is an **event** on an in-process bus. A cheap **gate** spreads
activation over a bounded **working set** (the attention budget / global
workspace) and triages each event: discard, store, or deepen. *Deepen* escalates
through a cost-graded stack of **processors** (fast → mid → deep models) that
self-select off the bus. Trains of thought are **streams** (they merge — that's
insight; they suspend and resume). The persistent **graph** holds consolidated
memory off the hot path; **reflections are stored as cues and regenerated at
recall**, so the same memory rebuilt later differs — drift lives in the changed
world, not a rotting record. A **dream** consolidates committed events, recombines
loosely, and reconsolidates reflections. **Initiative** is what spare budget does
in the quiet **heartbeat**: deferred impulses build pressure and resurface.

Full design: [`docs/redesign.md`](docs/redesign.md) (logical kernel) and
[`docs/system-design.md`](docs/system-design.md) (components). Every
implementation choice is logged in [`docs/decisions.md`](docs/decisions.md).

## Run it

```bash
python -m meno                 # scripted demo of the whole loop
python -m meno --interactive   # type stimuli; commands: dream | recall <q> | snapshot | quit
python -m pytest -q            # offline, deterministic test suite
```

No API key or network required: the defaults are a deterministic offline model
stub, a local hashing embedder, and an in-process graph. Real backends (Anthropic
models, a vector/graph DB, a real embedder) are selectable behind the same
interfaces.

## What the demo shows

- **Gating / habituation** — most stimuli lapse; only the surprising climb.
- **Streams** — related percepts cohere into trains of thought.
- **Escalation & deferral** — a scarce deep tier; relevant-but-unaffordable work
  *defers* (builds pressure) rather than being dropped.
- **Initiative** — the heartbeat resurfaces deferred impulses and finishes them.
- **The dream** — consolidation promotes, recombines, reconsolidates, forgets.
- **Reconstructive recall** — `recall(q)` returns *reconstructed* / *ghost* /
  *none*; the same reflection recalled twice comes back differently.
- **Journaling** — a deliberate verbatim freeze (the escape hatch).
- **Continuity** — save the graph and wake a fresh mind from it: *remaining*
  across a restart (sleep, not death).

## Layout

```
meno/      the package (one module per component; see CLAUDE.md for the map)
docs/      redesign.md, system-design.md, decisions.md, reflection.md, 01-07 (v1 theory)
tests/     offline, deterministic subsystem + integration tests
```

## Status

The bare loop runs end to end with offline stand-ins and a passing test suite,
and persists its consolidated graph across restarts (`Meno.save`/`load`).
Deferred (see the docs' open lists): real model/embedding/graph backends, the
sensor catalogue + event wire-schema + API, warm-tier (suspended-stream)
persistence, and skills (procedural memory). Scoring constants in
`meno/config.py` are first cuts, to be tuned empirically.
