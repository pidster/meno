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

### D12 — Continuity across restart persists the cold graph only
- **Decision.** `Meno.save(path)`/`load(path)` serialise the **graph** (nodes,
  edges, reflection cues) to JSON. On wake the working set starts empty; recall
  works immediately against the loaded graph, and `resurface()` re-enters the
  most salient memories as self-events to rebuild a little working context. Load
  advances the id counters past the loaded maxima so new ids never collide.
- **Why.** A restart is *sleep, not death* — meno must remain. The durable self
  is the consolidated graph; the hot layer is ephemeral by design.
- **Rules out / defers.** Warm-tier (suspended-stream) persistence is *not*
  handled, because the warm-tier placement is still an open decision. Until that
  lands, suspended trains of thought do not survive a restart — only consolidated
  memory does, which is the faithful minimum.

### D13 — Real cognitive models: Anthropic tiers behind the provider interface
- **Decision.** `AnthropicModelProvider` maps the three cognitive tiers onto the
  Claude family — **Tier 1 `claude-haiku-4-5`** (fast appraisal via structured
  JSON output), **Tier 2 `claude-sonnet-4-6`** (association), **Tier 3
  `claude-opus-4-8`** (synthesis with adaptive thinking + `effort`). Selectable
  via `make_models("anthropic")`, the `Meno(models=...)` arg, or `python -m meno
  --anthropic`. The offline `StubModelProvider` remains the default (D4).
- **Why / how, grounded in the API reference.** Opus 4.8 takes adaptive thinking
  only (`thinking={"type":"adaptive"}`) with `output_config.effort` — `budget_tokens`
  and `temperature` are removed and 400. Appraisal uses `output_config.format`
  (json_schema, supported on Haiku 4.5) so the Tier-1 reaction/question parse
  reliably. Every call **falls back to the stub on any error** (no client, no key,
  network failure, refusal, parse failure) so the kernel never blocks on the
  network — matching the design's graceful-degradation assumption.
- **Rules out / defers.** Real *embeddings* are not integrated — Anthropic offers
  no embeddings endpoint, so a real embedder stays a separate pluggable upgrade;
  `HashingEmbedding` remains the default. The synchronous core (D7) means real
  calls run serially per quiescence pass; the async worker pool that would issue
  them concurrently is still deferred. Tests inject a fake client, so the suite
  stays offline and deterministic.

### D14 — Strategy after the adversarial review: embedder before graph DB; stay on Python
- **Decision.** Two strategic forks are now locked (see `review-findings.md`):
  (1) **a real embedder before a graph database** — wire rediscovery, add a real
  embedder on graph-touching ops, and defer the graph DB to a genuine
  scale/persistence trigger (and prefer a single store with native vectors when it
  comes). Embeddings and a graph DB are complements: the embedder carries
  *capability*, the DB only *scale*. (2) **Stay on Python** — build the deferred
  async execution layer and index the two naive structures in Python; a PyO3 Rust
  graph core stays a *profile-triggered* future, not a present rewrite.
- **Why.** The review showed the bottleneck is wiring and algorithms, not the
  backend or the language; Python's ecosystem and iteration speed fit this
  still-exploratory, dynamics-dominated phase, and the concurrency we need
  (overlapping network waits) is asyncio's sweet spot.
- **Sequencing.** Fundamentals (wire the kernel) and correctness come *before*
  either backend work.

### D15 — Correctness fixes (P2), pre-wiring
- **Decision.** Fixed the HIGH/MED correctness bugs the review found, ahead of the
  P0 kernel-wiring:
  - **Per-instance id allocation.** Node/cue/stream ids now come from counters on
    `Graph`/`StreamManager`, not module-global `itertools.count`. `persistence.load`
    sets the instance counter past the loaded maximum instead of clobbering a
    global. (Fixes the multi-instance collision/overwrite hazard, F10.) Event ids
    stay process-global — they are ephemeral, never persisted, and only keyed
    within one instance, so monotonic uniqueness suffices.
  - **`_enforce_capacity` rewrite.** Orphan (`stream_id is None`) and singleton
    events lapse individually; a stream larger than the working set is trimmed to
    capacity event-by-event (it cannot be held whole — the honest concession)
    rather than collapsing the set to ~1; whole-stream demotion only when the
    stream fits; a progress guard prevents any spin. (Fixes F9.)
  - **Stream routing seed.** `best_sim` seeds at `-inf` so the genuinely
    best-matching stream is chosen before the threshold test (a 0.0 seed silently
    rejected zero/negative cosines). (Fixes M2.)
  - **Journaling no longer drifts on freeze.** `reconstruct(..., reconsolidate=False)`
    lets `journal()` freeze a reflection without first mutating its gist. (Fixes L4.)
  - **Empty wake message.** A summary-less resumed stream wakes as "an unfinished
    thought" rather than an empty string. (Fixes L1.)
- **Deferred to P0:** the *fundamentals* (islanding-thins-reconstruction, merge,
  curiosity, rediscovery, graph-spread-in-cognition, cross-burst surprise, the
  heartbeat storm) and the meaning-asserting tests that pin them.
