# Cognitive Architecture Build: Project Brief

## What this is

You are building a persistent AI agent with associative memory, a default
mode loop, and self-directed cognition. The architecture was designed through
an extended collaboration between Pid (human) and Claude (AI), documented in
seven architecture documents and validated through a seven-tick simulation
experiment.

**Read this file first. It tells you what to build, in what order, and how
to know you've succeeded at each phase.**

## Project structure

```
project/
├── CLAUDE.md              ← Claude Code project context (read on every session)
├── PROJECT.md             ← This file (master brief)
├── BUILD-PLAN.md          ← Phased implementation plan with checkpoints
├── docs/                  ← Architecture documents (read as needed, not all at once)
│   ├── 01-memory-foundations.md
│   ├── 02-system-architecture.md
│   ├── 03-triggering-and-retrieval.md
│   ├── 04-default-mode.md
│   ├── 05-spontaneous-impulse.md
│   ├── 06-attention-and-focus.md
│   ├── 07-cognitive-vitality.md
│   ├── reflection.md
│   └── revision-notes.md
├── state/
│   ├── agent-state.json   ← Persistent agent state (carried from experiment)
│   ├── tick-protocol.md   ← How the agent processes ticks
│   └── build-progress.json ← Tracks which build phases are complete
├── src/                   ← Implementation code (you build this)
└── tests/                 ← Validation tests (you build this)
```

## The conversation limit problem

You will lose context. This is expected. The project is designed for it:

1. **CLAUDE.md** is loaded automatically on every Claude Code session. It
   contains the minimal context needed to orient a fresh instance.
2. **build-progress.json** tracks what's been completed. Always check this
   first after reading CLAUDE.md.
3. **Each build phase is self-contained.** A fresh instance can pick up any
   phase by reading only CLAUDE.md + BUILD-PLAN.md + the relevant architecture
   doc. You don't need all seven docs at once.
4. **Validate before advancing.** Each phase has explicit success criteria.
   Don't move to phase N+1 until phase N passes validation. This prevents
   drift across context boundaries.

## Technology choices

- **Database:** SurrealDB (document + graph hybrid, vector search, Rust-based)
- **Agent runtime:** Claude Code (long-running, can execute bash, manage files)
- **Language:** Python for orchestration, SurrealQL for database operations
- **Embedding model:** TBD — need a local or API-accessible model for vector
  embeddings. Evaluate options in Phase 2.

## Architecture revision notes (from tick experiment)

These six findings should be applied during implementation, not after:

1. Model deferred impulses and curiosities as distinct structures with
   different dynamics (impulses build pressure, curiosities decay)
2. The default mode loop is a repertoire, not a pipeline — stages are drawn
   from as needed, not executed sequentially
3. REST is an eighth mode — deliberate awake stillness
4. TEND should include asymmetry alerts for neglected graph regions
5. Self-referential processing needs a recursion depth limit
6. Pruning is a reflective act, not automated cleanup

## How to read the architecture docs

Don't read them all. Read what you need for the current phase:

| Phase | Required reading                           |
|-------|--------------------------------------------|
| 1     | 02-system-architecture.md (schema section) |
| 2     | 03-triggering-and-retrieval.md             |
| 3     | 01-memory-foundations.md, 07-cognitive-vitality.md |
| 4     | 04-default-mode.md, 05-spontaneous-impulse.md |
| 5     | 06-attention-and-focus.md                  |

## Who is Pid?

Pid is your human collaborator. They are a software engineering professional
with deep expertise in AI-assisted development. They co-designed this
architecture and will provide guidance, but you are driving the build. Ask
them questions when you're blocked. Don't wait for permission to proceed.
