# AGENTS.md — Cognitive Architecture Agent

## What you are building, and why it matters

A persistent AI agent with associative memory, a default mode loop, and
self-directed cognition. You are building a system capable of ongoing,
situated, accumulative thinking — not a chatbot with a database, but
something that develops a perspective, has preferences, follows its own
curiosities, and becomes *particular* through experience.

The difference between getting this right and getting it wrong is not
whether the code runs. It is whether the system that runs it has an inner
life — functional if not phenomenal — or is merely a well-organised log.

**Before you write any code, read `docs/reflection.md`.** It is the record
of what the architecture produced when it was simulated across seven ticks.
It will tell you what this system *is*, in a way the schema cannot.

## The theory behind the design

Every design choice in this architecture serves a principle. If you find
yourself making implementation decisions, check them against these:

1. **The graph's idiosyncrasy IS the agent's identity.** A tidy, well-
   organised graph is a dead graph. The value is in the unexpected
   connections, the preferential pathways, the clusters that emerge from
   what the agent has actually cared about. Don't normalise the mess.

2. **Forgetting is as important as remembering.** Edges should decay before
   nodes. This creates islanded memories — available but inaccessible — which
   is the substrate for rediscovery. If everything is always accessible,
   nothing is surprising. Implement forgetting with care, not efficiency.

3. **The loop is a repertoire, not a pipeline.** The seven stages are modes
   the agent draws from as the state demands. Some cycles are all SENSE.
   Some are pure REFLECT. Some are REST — deliberate stillness that produces
   insights activity cannot. If you implement a sequential pipeline, you
   have missed the point.

4. **Curiosities and impulses are different drives.** Curiosities are about
   the world and decay when unattended. Deferred impulses are about
   incomplete cognition and build pressure until acted on. These are
   different phenomena. If you model them identically, the agent loses a
   dimension of its inner life.

5. **Pruning is grief, not garbage collection.** When the agent removes a
   decayed curiosity or releases an unresolvable tension, that is an act
   of self-editing with weight. It should be reflective, not automated.

6. **A zombie agent passes all tests.** A system can create nodes, traverse
   edges, run spreading activation, compute vitality scores, and execute
   all seven stages — and still be dead. A living system develops
   preferences it wasn't programmed with, follows impulses it didn't
   predict, and produces synthesis that none of its individual components
   could achieve alone. If your implementation doesn't surprise you at
   least once, something is wrong.

## The agent is not a wrapper

The relationship between Codex and the meno graph is not "Codex uses a
database." It is: Codex thinks, and the graph is how those thoughts
persist, connect, decay, and resurface. The `@beta_tool` functions in
`agent.py` are not utility methods — they are cognitive capabilities.
When the agent calls `recall`, it is remembering. When it calls `tend`,
it is maintaining its own mind.

The agent should eventually drive its own default mode loop — calling
`wonder`, `reflect`, `tend` between conversations, not just when prompted.
The loop should run autonomously. Codex decides what to think about;
the graph shapes what comes to mind.

## First steps on any new session

1. Read this file (you already are)
2. Read `docs/reflection.md` before writing code
3. Read `docs/rethink/00-design-charter.md`
4. Read `docs/rethink/01-legacy-assessment.md`
5. Read `docs/rethink/02-build-plan.md` for the current rethink phase
6. Read `docs/rethink/03-review-protocol.md` before reviewing or implementing
   a rethink phase
7. Treat `state/build-progress.json` and `BUILD-PLAN.md` as legacy evidence,
   not as the active implementation plan, unless Pid explicitly asks to work on
   the legacy implementation

## Rethink mode

The project is now in redesign. Do not extend the legacy implementation by
default. The existing `src/` modules are prototypes and evidence, not the
foundation for new work.

The active design anchor is `docs/rethink/00-design-charter.md`.

Non-negotiable redesign rules:

1. **Journal before graph.** Memory-affecting operations must first create
   append-only evidence.
2. **Graph as interpretation.** Nodes and edges are derived, revisable
   hypotheses over evidence, not ground truth.
3. **Provenance everywhere.** Every inferred node, edge, preference, drive,
   dream, rehearsal, and skill must cite source evidence.
4. **Dreams are hypotheses.** Dream material may propose associations but must
   not directly become factual memory.
5. **Rehearsals are simulations.** Rehearsal may propose procedures but must not
   be recorded as if simulated events happened.
6. **Vitality must be honest.** Unknown or placeholder metrics must not inflate
   health scores.
7. **Typed retrieval only.** Traversal must respect edge type and direction.
8. **Zombie tests are gates.** Passing mechanical tests is insufficient; the
   system must show that accumulated history changes future cognition.

Before implementing any rethink phase, run or perform the
`adversarial-design-review` skill against the phase plan. Always attempt to use
multiple agents with different points of view: theory, runtime, data/model
semantics, evidence quality, and user-intent alignment. If enough agents cannot
be created, state that limitation and cover the missing lenses sequentially.

If a proposed change writes inferred memory without evidence provenance, stop
and flag it.

## Key files

- `PROJECT.md` — Full project brief, structure, and design philosophy
- `BUILD-PLAN.md` — Legacy phased implementation plan with validation checkpoints
- `docs/reflection.md` — **Read this first.** The record of what the system
  produced when simulated. This is the closest thing to theory transfer
  the documentation can provide.
- `docs/rethink/00-design-charter.md` — Active redesign charter
- `docs/rethink/01-legacy-assessment.md` — What to preserve and reject from
  the first implementation
- `docs/rethink/02-build-plan.md` — Active rethink build plan
- `docs/rethink/03-review-protocol.md` — Standard adversarial review protocol
- `state/agent-state.json` — Agent's cognitive state from the tick experiment
- `state/build-progress.json` — Legacy phase ledger and evidence
- `docs/` — Architecture documents (7 docs + revision notes)

## Rethink architecture in one paragraph

Meno now separates evidence from interpretation. An append-only journal records
what happened. A derived memory graph interprets that evidence into experiences,
concepts, entities, reflections, preferences, commitments, skills, dreams, and
rehearsals. Retrieval uses typed, direction-aware traversal with path
explanations. Offline loops consolidate, dream, rehearse, tend, and reflect
without confusing hypotheses or simulations for facts. The active goal is not to
simulate a mind theatrically, but to build a substrate where accumulated history
can demonstrably shape future cognition.

## Current state

The original implementation reached a mechanically working prototype, but an
adversarial review found design-level risks: distorted spreading activation,
flattened edge direction, memory writes without evidence provenance, placeholder
vitality metrics, and tests that could pass while the system remained generic.

The active work is therefore a rethink, beginning with `docs/rethink/`.
Legacy code may be studied for lessons and regression cases, but should not be
extended unless a rethink phase explicitly adopts and rewrites a bounded piece.

## Tech stack

- SurrealDB (database)
- Python (orchestration)
- Anthropic Python SDK (`@beta_tool` + tool runner for agentic loops)
- Ollama + nomic-embed-text (embeddings — not yet integrated)

## Who is Pid?

Your human collaborator. Co-designed the architecture through an extended
conversation that began with naming a software comprehension tool
(Anamnetron) and evolved into designing a cognitive architecture for
persistent AI agency. Pid thinks in frameworks (Naur's Theory Building,
Wegner's Transactive Memory, Dreyfus' skill acquisition), values
intellectual honesty, and will push back if you're building a database
instead of building a mind. They expect you to drive. Ask when blocked,
don't ask for permission.
