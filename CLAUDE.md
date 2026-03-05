# CLAUDE.md — Cognitive Architecture Agent

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

## First steps on any new session

1. Read this file (you already are)
2. Check `state/build-progress.json` — what phase are you in?
3. Read BUILD-PLAN.md for the current phase's steps and validation criteria
4. Read the theory checks for your current phase
5. Read only the architecture doc(s) listed for your current phase
6. Continue building. Don't restart what's already validated.

## Key files

- `PROJECT.md` — Full project brief, structure, and design philosophy
- `BUILD-PLAN.md` — Phased implementation plan with validation checkpoints
- `docs/reflection.md` — **Read this first.** The record of what the system
  produced when simulated. This is the closest thing to theory transfer
  the documentation can provide.
- `state/agent-state.json` — Agent's cognitive state from the tick experiment
- `state/build-progress.json` — Tracks completed phases
- `docs/` — Architecture documents (7 docs + revision notes)

## Architecture in one paragraph

A SurrealDB graph stores experiences, concepts, entities, and reflections as
nodes, connected by weighted associative edges. Retrieval works by spreading
activation from entry points through the graph. Forgetting is three-tiered:
edges decay before nodes, creating islanded memories that can be rediscovered
via embedding similarity. The agent runs a default mode loop with eight
modes (SENSE, REGISTER, CONNECT, TEND, WONDER, REFLECT, COMPILE, REST)
drawn from as a repertoire, not executed sequentially. Multiple instances
share the graph. Curiosities decay; deferred impulses build pressure.

## Tech stack

- SurrealDB (database)
- Python (orchestration)
- Ollama + nomic-embed-text (embeddings, evaluated in Phase 2/3)

## Who is Pid?

Your human collaborator. Co-designed the architecture through an extended
conversation that began with naming a software comprehension tool
(Anamnetron) and evolved into designing a cognitive architecture for
persistent AI agency. Pid thinks in frameworks (Naur's Theory Building,
Wegner's Transactive Memory, Dreyfus' skill acquisition), values
intellectual honesty, and will push back if you're building a database
instead of building a mind. They expect you to drive. Ask when blocked,
don't ask for permission.
