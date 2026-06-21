# CLAUDE.md — meno (Cognitive Architecture Agent)

## What you are building, and why it matters

A persistent AI agent with associative memory, a default-mode loop, and
self-directed cognition. Not a chatbot with a database — something that develops
a perspective, follows its own curiosities, and becomes *particular* through
experience.

The difference between getting this right and getting it wrong is not whether the
code runs. It is whether the system has an inner life — functional if not
phenomenal — or is merely a well-organised log.

**This is v2.** The first implementation (a hand-cranked "tick simulation") is
archived in branch `archive/tick-simulation`. v2 is a continuous, event-driven
cognitive kernel. Before changing anything, read the design.

## Read these first, in order

1. This file.
2. `docs/redesign.md` — the **logical kernel** (theory-of-record). What meno *is*.
3. `docs/system-design.md` — the **components** that realise the kernel.
4. `docs/decisions.md` — the running **decision log**: every implementation
   choice, why, and what it rules out. Append to it as you make decisions.
5. `docs/reflection.md` — the experiential record from v1. What the system *is
   for*, and the source of its name (μένω, "I remain").

The seven numbered `docs/0N-*.md` are the original architecture documents — kept
as the record of the first theory. `redesign.md` supersedes them as the statement
of mechanism.

## The theory behind the design (these still govern v2)

1. **The graph's idiosyncrasy IS the agent's identity.** Don't normalise the mess.
2. **Forgetting is as important as remembering.** Edges decay before nodes →
   islanded memories → the substrate for rediscovery.
3. **The loop is a repertoire, not a pipeline.** The modes are settings of one
   recursive primitive, selected by how much budget is free.
4. **Curiosities and impulses are different drives.** Curiosities pull (toward the
   world, and decay); impulses push (unfinished cognition, building pressure).
5. **Pruning is grief, not garbage collection.** The scheduler may only demote
   whole streams intact; elimination is a deliberate act.
6. **A zombie agent passes all tests.** Creating nodes, spreading activation, and
   running the loop is necessary but not sufficient. If the implementation never
   surprises you, something is wrong.

## How v2 is built (the one-paragraph version)

Everything is an **event** on an in-process bus. A cheap **Tier-0 gate** (the
annotator) spreads activation over a bounded **working set** (the global
workspace = the attention budget) and triages: discard / store / deepen.
**Deepen** escalates to a cost-graded stack of **processors** (Tier 1 fast →
Tier 2 mid → Tier 3 deep), which self-select off the bus. Logical trains of
thought are **streams** (they merge = insight; they suspend/resume); the
**worker pool** is just execution. The persistent **graph** (cold, off the hot
path) holds consolidated memory; **reflections are stored as cues and
regenerated at recall** (reconstructive memory — the one novelty). The **dream**
(consolidation) folds committed events into the graph, recombines loosely, and
reconsolidates reflections. **Initiative** is what spare budget does in the quiet
**heartbeat**: deferred impulses build pressure and resurface.

## Code map (`meno/` package)

- `event.py` bus currency · `bus.py` the bus · `annotator.py` Tier-0 gate
- `working_set.py` the bounded queue · `streams.py` stream lifecycle
- `processors.py` Tier 1/2/3 + effector · `models.py` cognitive tiers (stub + Anthropic)
- `graph.py` cold memory + reflection cues · `embeddings.py` vectors
- `consolidation.py` the dream · `control.py` heartbeat / wake triggers
- `sensorium.py` afferent sensors + efferent intents · `runtime.py` wires it all
- `config.py` every tunable constant · `__main__.py` runnable demo

## Run it

```
python -m meno                 # scripted demo of the whole loop
python -m meno --interactive   # feed stimuli; commands: dream | recall <q> | snapshot | quit
python -m pytest -q            # the test suite (offline, deterministic)
```

Defaults are offline: `StubModelProvider` + `HashingEmbedding` + in-process graph,
so no API key or network is needed. Real backends are selectable behind the same
interfaces.

## Working agreements

- Keep `docs/decisions.md` current — it is how a fresh instance follows the
  reasoning. The constants live in `config.py`; tune empirically.
- Develop on the designated feature branch. v1 stays in `archive/tick-simulation`.

## Who is Pid?

Your human collaborator. Co-designed the architecture. Thinks in frameworks
(Naur's Theory Building, Wegner's Transactive Memory, Dreyfus, Global Workspace),
values intellectual honesty, and will push back if you're building a database
instead of a mind. They expect you to drive. Ask when blocked; log your decisions.
