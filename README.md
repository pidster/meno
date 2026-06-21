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
python -m meno                 # scripted demo of the whole loop (offline)
python -m meno --interactive   # type stimuli; commands: dream | recall <q> | snapshot | quit
python -m meno --anthropic     # use real Claude models for cognition (see below)
python -m pytest -q            # offline, deterministic test suite
```

No API key or network required by default: a deterministic offline model stub, a
local hashing embedder, and an in-process graph. **Real cognitive models** are a
drop-in: `pip install anthropic`, set `ANTHROPIC_API_KEY`, and pass `--anthropic`
(or `Meno(models=make_models("anthropic"))`). The tiers map onto the Claude
family — Haiku 4.5 appraises, Sonnet 4.6 associates, Opus 4.8 synthesises — and
every call falls back to the stub on any error, so the loop never blocks. A
vector/graph DB and a real embedder are likewise selectable behind the same
interfaces (not yet implemented).

## What the demo shows

- **Gating / habituation** — most stimuli lapse; only the surprising climb.
- **Streams** — related percepts cohere into trains of thought.
- **Escalation & deferral** — a scarce deep tier; relevant-but-unaffordable work
  *defers* (builds pressure) rather than being dropped.
- **Initiative** — the heartbeat resurfaces deferred impulses and finishes them.
- **Curiosity** — under-stimulation makes meno *reach out on its own* (a
  model-routed inward thought or outward action); impulses take precedence.
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
persists its consolidated graph across restarts (`Meno.save`/`load`), and can
drive its cognition with **real Claude models** (`--anthropic`). Deferred (see
the docs' open lists): a real embedder and a vector/graph DB backend, the sensor
catalogue + event wire-schema + API, warm-tier (suspended-stream) persistence,
skills (procedural memory), and the async worker pool that would run model calls
concurrently. Scoring constants in `meno/config.py` are first cuts, to be tuned
empirically.
