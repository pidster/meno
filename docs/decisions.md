# meno v2 — Decision Log

A running record of implementation decisions, so the reasoning is followable.
Each entry: what was decided, why, and what it rules out. Newest at the bottom.

Authoritative design: `redesign.md` (logical kernel) and `system-design.md`
(components). Where code and those docs disagree, the docs win.

---

### D1 — Preserve v1, strip to bare ground
- **Decision.** v1 (the tick simulation) is preserved unchanged in branch
  `archive/tick-simulation`. On the working branch we removed `src/`, `tests/`,
  `state/`, `skills/`, `BUILD-PLAN.md`, `PROJECT.md`.
- **Kept:** all of `docs/` — the seven architecture docs, `reflection.md`,
  `revision-notes.md`, and the v2 docs. *Code is disposable; theory is not.*
- **Why.** The agreed redesign approach: archive the first working theory, re-earn
  every line. v1's tick protocol and JSON-state assumptions would only anchor the
  new design to ideas we've outgrown.

### D2 — Language/runtime: Python + asyncio
- **Decision.** Implement in Python with a single `asyncio` event loop and an
  async worker pool.
- **Why.** The kernel calls for one in-process cooperative loop with many
  concurrent *in-flight* model calls (I/O-bound, awaitable) — that is precisely
  asyncio's sweet spot. Python also carries the graph/vector/LLM ecosystem we'll
  want later. This is the substrate "re-earning its place" rather than being
  inherited: chosen for the concurrency profile, not because v1 used it.
- **Rules out (for now).** OS-thread parallelism as the primary mechanism; the
  worker "pool" is a fixed set of async tasks.

### D3 — Package layout: `meno/` at repo root
- **Decision.** Source lives in a `meno/` package (not `src/`), one module per
  major component, mirroring `system-design.md`.
- **Why.** Clean `import meno` ergonomics and a 1:1 map from design sections to
  modules makes the code followable against the docs.

### D4 — Everything pluggable behind interfaces; offline by default
- **Decision.** The three external dependencies the design names as TBD —
  **models** (the cognitive tiers), **embeddings**, and the **graph store** — sit
  behind interfaces. The default build ships in-process, deterministic
  implementations so meno runs with **no network and no API key**. Real backends
  (Anthropic models, a vector/graph DB, a real embedding model) are selectable
  adapters added later.
- **Why.** "A working meno" must actually run in this environment, which may have
  no API access. It also lets us tune the scoring constants empirically (as
  `system-design.md` urges) against a fast, free, deterministic loop. The kernel
  is substrate-agnostic by design, so this costs us nothing architecturally.
- **Rules out.** Hard-coding Anthropic/SurrealDB/Ollama into the core loop.

### D5 — All tunable constants live in `meno/config.py`
- **Decision.** Every scoring weight, threshold, decay rate, and size (N/P/D,
  gate, tiers, stream, memory, reflection) is a field on one `Config` dataclass.
- **Why.** `system-design.md` says these are empirical, to be settled by running
  the bare loop. One home makes the tuning legible and keeps magic numbers out of
  the logic.

### D6 — Default embedding is a local signed-hashing bag-of-tokens
- **Decision.** `HashingEmbedding` (md5-hashed tokens into a 64-d L2-normalised
  vector) is the default `EmbeddingModel`.
- **Why.** Dependency-free and deterministic, so the loop runs offline and tests
  are reproducible. Overlapping vocabulary yields enough cosine signal to drive
  resonance, novelty, streams, and rediscovery. A real embedder swaps in behind
  the same interface.
- **Cost.** Similarity is brittle for paraphrases with no shared tokens — fine
  for the bare loop, to be upgraded with a real model.

### D7 — Deterministic synchronous core; async is a thin outer driver (deferred)
- **Decision.** The core loop (`run_until_quiescent`, `heartbeat`) is synchronous
  and step-driven. The asyncio worker-pool form (D2) is a wrapper to add when real
  model I/O is introduced.
- **Why.** Reproducibility for tuning and testing. The kernel only requires
  *bounded* concurrency, which the worker-budget (P / deep-slots) models without
  real parallelism. Revises D2's emphasis without abandoning it.

### D8 — Only percepts are encoded as nodes; derived cognition flows but isn't each stored
- **Decision.** The appraiser encodes graph nodes only for afferent `SENSE` and
  effector `FEEDBACK` events. Derived `SELF`/`STORAGE` events still flow and can
  climb, but are not each turned into nodes. Residual questions are raised only by
  percepts (so questions never recursively spawn questions).
- **Why.** Without this the graph exploded (2570 events → 1059 nodes from 7
  stimuli). It also matches the principle that the graph is consolidated
  *experience*, with reflections stored as cues, not a transcript of every
  internal step.

### D9 — Dream recombination is bounded (window + hard cap)
- **Decision.** Loose-gate recombination only considers the most-recent
  `dream_recombine_window` nodes and stops after `dream_recombine_cap` new links.
- **Why.** The naive all-pairs pass produced 182k links. Bounding keeps the dream
  cheap and the graph from fusing into a hairball, while still letting novelty in.

### D10 — Journaling is a deliberate act, not surprise-triggered
- **Decision.** Reflections are reconstructive by default; the synthesiser never
  auto-journals. `Meno.journal(query)` freezes a chosen reflection's current
  reconstruction verbatim.
- **Why.** Surprise is the wrong proxy — a novel percept is ~1.0, so a
  surprise-trigger journaled everything and defeated reconstructive memory.
  Journaling is the *marked exception* (a diary entry), so it must be chosen.

### D11 — Initiative lives in the heartbeat, not the hot drain
- **Decision.** `run_until_quiescent` does reactive processing only (no wakes).
  Interoceptive wakes — resurfacing deferred streams, each granted a deep slot —
  fire in `heartbeat()`, the quiet/idle phase. Deep budget is a standing resource
  replenished by the dream, not reset per stimulus.
- **Why.** Firing wakes inside the hot drain caused a resume/re-defer storm. The
  clean separation matches the kernel: reactive cognition under load, initiative
  in the spare capacity between bursts; deep thought deferred during waking is
  worked off during quiet and sleep.
