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
implementation choice is logged in [`docs/decisions.md`](docs/decisions.md). The
realised kernel (R0–R5) is in [`docs/realisation-plan.md`](docs/realisation-plan.md);
the self-knowledge / reference / reach chapter is in
[`docs/roadmap-ii.md`](docs/roadmap-ii.md). To **run one**, see
[`docs/operating.md`](docs/operating.md) (build / configure / start) and
[`docs/instance-layout.md`](docs/instance-layout.md) (the on-disk home).

## Run it

**The offline demo** (no key, no network — see one run of the whole loop):

```bash
python -m meno                 # scripted demo of the whole loop (offline)
python -m meno --interactive   # type stimuli; commands: dream | recall <q> | snapshot | quit
python -m meno --anthropic     # use real Claude models for cognition (see below)
python -m meno --split-embed   # real local semantic memory (cheap hot + ST cold; see below)
python -m pytest -q            # offline, deterministic test suite
```

**A real, persistent instance** (`pip install .` puts `meno` on the path):

```bash
meno init   ~/.meno/meno-pid --handle meno-pid   # scaffold an instance home
meno run    ~/.meno/meno-pid                      # run the home-bound daemon
meno status ~/.meno/meno-pid                      # cycles, nodes, cognition real-fraction
```

Configure it via `~/.meno/meno-pid/meno.toml` (cognition tier, embedder, egress
allowlist), supply secrets as environment variables, and — optionally — package it as
an OCI image with the home as a mounted volume. **Full build / configure / start
guide: [`docs/operating.md`](docs/operating.md).**

No API key or network required by default: a deterministic offline model stub, a
local hashing embedder, and an in-process graph. **Real cognitive models** are a
drop-in: `pip install anthropic`, set `ANTHROPIC_API_KEY`, and pass `--anthropic`
(or `Meno(models=make_models("anthropic"))`). The tiers map onto the Claude
family — Haiku 4.5 appraises, Sonnet 4.6 associates, Opus 4.8 synthesises — and
every call falls back to the stub on any error, so the loop never blocks.

**Real embeddings** are a drop-in too, and they *split by job*: a cheap **hot**
embedder runs on every event (surprise, stream routing) while a richer **cold**
embedder serves everything that touches the graph (node vectors, reflection
gists, recall, rediscovery). `pip install sentence-transformers` and pass
`--split-embed` (cheap hashing hot + local sentence-transformers cold — the
recommended real config) or `--local-embed` (the local model for both); both fall
back to the offline hashing embedder if the package or its weights are
unavailable. The two spaces never meet in a cosine, so they may differ in
dimension. A vector/graph DB is likewise selectable behind the same interface
(not yet implemented).

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
meno/           the kernel (one module per component; see CLAUDE.md for the map)
meno_adapters/  the integration layer — channels/network, kept OUT of the kernel
docs/           redesign.md, system-design.md, decisions.md, operating.md, …
tests/          offline, deterministic subsystem + integration tests
```

## Status

The loop runs end to end with offline stand-ins and a passing suite, persists its
graph across restarts, drives cognition with **real Claude models** (`--anthropic`)
and a **real local embedder** (`--split-embed`). On top of the realised kernel
(R0–R5), the **self-knowledge / reference / reach** chapter is built (see
[`docs/roadmap-ii.md`](docs/roadmap-ii.md)):

- **S** — a mechanics-only self-model on every cognitive tier (type, not identity).
- **K1/K2** — a **Library** (reference memory, distinct from the substrate) and
  *know-when-to-look-up*: a factual curiosity routes to a lookup, the result informs
  cognition but is never encoded as experience.
- **I0–I2** — a runnable **instance**: `meno init / run / status`, a home-bound daemon
  (sleep-not-amnesia), an **OCI image** (image = type, home = volume), a deny-by-default
  **egress** boundary, and a **Slack** channel — afferent (consented, redacted) and a
  **gated** efferent (disabled by default, scoped, rate-limited, confirm-first, audited).
- **K3** — external network **authorities**: a Library miss falls out to a web/MCP
  authority, the result curated back so a repeat is a local hit; egress-gated, audited.

**Roadmap II is complete** — every phase through a multi-lens adversarial review.
`meno run` wires the channels/authorities an instance's `adapters/*.toml` enables
(the kernel stays adapter-blind; the entrypoint is a composition root). What remains is
*live* validation, gated on credentials/runtime (a funded model key, a Slack token, a
container runtime, a real authority client), plus deferred scale items (a vector/graph
DB, the async worker pool, D19 lifetime-growth). Scoring constants in `meno/config.py`
are first cuts, tuned empirically.
