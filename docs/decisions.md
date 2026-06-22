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

### D16 — Reconstruction richness comes from surviving structure (F1, the keystone)
- **Decision.** `Graph.reconstruct` no longer rebuilds a reflection from its entry
  points' own content. Material now comes from the **reachable neighbourhood**
  (associations via surviving edges) plus the entry points as *anchors* gated by
  node salience (`recall_salience_floor`). Recall degrades with forgetting:
  full → **(partial)** once the entry set is islanded (no surviving edges) →
  **ghost** ("the details won't come") once the anchors also fade. "Thin" keys on
  *loss of surviving structure*, not absolute neighbour count, so a freshly-chained
  young reflection is not falsely marked partial.
- **Why.** The review proved the old code returned the full reflection even with
  the entire neighbourhood islanded — the keystone reconstructive claim was false.
  Forgetting must actually impoverish recall, or "reconstructive memory" is a
  lookup. Pinned by `tests/test_kernel_fidelity.py` (fails on the old behaviour).

### D17 — Curiosity: the pull-toward-the-world drive (F3, P0)
- **Decision.** A `CuriosityRegister` parallel to impulse pressure, with intensity
  that **decays** (relaxes when unattended) — the opposite dynamic to impulse.
  Two origins: **bottom-up** (an appraiser question that goes unresolved registers
  a curiosity) and **top-down** (sustained under-stimulation — empty working set +
  bus for `boredom_ticks` — births a reach toward the most salient memory).
  **Discharge is model-routed**: when there's spare capacity and no pending
  impulse, `ModelProvider.wonder` chooses across the internal/external matrix —
  an inward thought (SELF), an outward action (INTENT → the Effector self-fires),
  both, or neither. The stub gives a deterministic default (world-referent →
  external read; else internal); a real model decides freely. A reflection
  `satisfy`s its stream's curiosities.
- **Why.** Curiosity was entirely absent — only impulse (push) existed, so meno
  never reached toward the world on its own. This is the initiative the project's
  purpose hinges on. Per Pid: the discharge form isn't predetermined (the full
  internal/external matrix is possible) — the mechanism provides the capacity and
  the *model* makes the call.
- **Ordering.** **Impulses before curiosity** for the spare slot (finish
  unfinished cognition before wandering). Pinned by kernel-fidelity tests:
  bottom-up registration, boredom producing a self-generated event, and
  impulse-precedence.

### D18 — Impulses-first is enforced by pending-state, not timing (P0 verification fix)
- **Decision.** Curiosity discharge in `heartbeat` is gated behind *no deferred
  stream pending* (active or warm), not merely on the wake-line being crossed. So
  while any unfinished cognition exists — even with pressure still building toward
  its interoceptive wake — curiosity will not jump the queue.
- **Why.** The P0 re-audit found the precedence leaked: at `boredom_ticks=3`,
  curiosity discharged before a deferred stream's pressure built to `pressure_wake`
  (~4 ticks). The unit test had masked it by pre-loading pressure. The test now
  exercises the build-up and asserts initiative precedes any curiosity event.

### D19 — Re-audit verdict (post-P0): go for P3; three growth items deferred
- **Decision.** A full re-audit of the post-P0 code (regressions / unbounded
  growth / dangling references) returned **go for P3**. Findings:
  - **Regressions:** none — 43/43 tests pass, including every kernel-fidelity
    test (F1–F7); the P0 wiring is consistent across modules.
  - **Dangling references:** none — every cross-structure deref is guarded
    (`nid in graph.nodes`, `n in g.nodes`); `streams.get` returns `None` for
    merged-away / suspended ids; `merge` cleans `b_id` and stale `event.stream_id`
    degrades gracefully.
  - **Unbounded growth (lifetime-accumulation, logged, NOT P3 blockers):**
    **A1** `bus.log` retains every Event ever published (with embeddings) — the
    real leak; **A2** `streams.warm` has no reaper and warm-deferred `pressure`
    grows unbounded until wake; **A3** `graph.cues` is never pruned and
    reconsolidation re-spreads all cues each dream (dream cost O(lifetime·cues)).
    `graph.nodes` growing is *by design* (islanding, not deletion — "pruning is
    grief"), so it is not counted a leak.
- **Why deferred.** A1–A3 only bite in a *long-lived* process; they belong with
  the deferred continuous-operation work (async layer + warm-tier persistence),
  and P3 (the embedder split) is orthogonal to all three and doesn't worsen them.

### D20 — Embedder: hot/cold split, local cold adapter, stay offline by default (P3)
- **Decision.** Embedding is split into two **jobs** behind one interface:
  - **HOT** (`embed_hot`) runs on *every* event — surprise vs the recency buffer,
    stream routing. Cheap; needs only rough novelty/topic.
  - **COLD** (`embed_cold`) touches the persistent graph — node vectors, cue
    gists, recall probes, rediscovery. Rare; wants real semantics.
  A single-model embedder makes the two identical (the default `HashingEmbedding`,
  so the offline suite is behaviourally unchanged). `SplitEmbedding(hot, cold)`
  routes them to two different models, and a `SentenceTransformerEmbedding`
  (lazy-imported sentence-transformers / torch) is the recommended **cold** half.
  `make_embedder("hashing"|"local"|"split")` mirrors `make_models`; the demo CLI
  gains `--local-embed` / `--split-embed` (both fall back to hashing if the local
  model or its weights are unavailable, so the loop never blocks).
- **The contract that makes it safe.** Hot and cold are *different spaces with
  possibly different dimensions*; they must **never meet in a cosine**. The
  discipline is enforced at exactly four crossing points: the Appraiser gives a
  new node a **cold** vector (not the event's hot one); the Associator probes the
  graph with a **cold** vector; `recall`/`journal` embed the probe **cold** (to
  match the cue gist); `resurface` re-enters content and lets the annotator embed
  it **hot**. Everything else is already wholly hot (event/stream/working-set) or
  wholly cold (graph/cue). **Probe↔gist consistency** is the keystone: a naive
  split that probed recall in hot space would score cross-dimension garbage and
  miss every memory.
- **Why.** The stub embedder throttled merge/coherence/recall (the P3 motivation):
  the cold path needed real semantics, but the hot path runs per-event and only
  needs to be cheap. The split lets each be right.
- **Validation.** `tests/test_embeddings.py` pins the contract with
  *different-dimensioned* stub embedders (so any cross-space cosine would corrupt
  observably): split routing, node-vectors-are-cold / event-vectors-are-hot,
  probe↔gist recall round-trip, default-embedder-unchanged. The real local adapter
  is import- and round-trip-tested when present; it **skips** if the package or
  its weights are unavailable (this environment's network policy blocks the
  Hugging Face weight download, so the live-semantics check skips here).
- **Rules out (for now):** an API embedder and a vector/graph-DB index remain
  deferred (D14 ordering held: embedder before DB). A persisted graph is tied to
  the cold embedder that made it — loading it under a different cold model would
  mismatch the gist space; that pairing is the caller's responsibility.

### D21 — Package an instance as an OCI image; the home is a mounted volume
- **Decision.** A Meno instance is deployed as an **OCI image** (the *type*: Python
  + the `meno` package + pinned extras + baked embedder weights) with the
  **instance home** (`substrate/`, `library/`, `skills/`, `adapters/`,
  `meno.toml`) as a **mounted volume** (the *identity*). Secrets are env-injected,
  never baked. Planned in `docs/roadmap-ii.md` I0; the home is specified in
  `docs/instance-layout.md`. It lands **before** the I2 effectors so the
  network/egress boundary exists before any outward action.
- **Why.** Continuous operation (R2) already made Meno a daemon; integrations (I)
  add network and outward action. The image gives a reproducible runtime and bakes
  the embedder weights (no Hugging Face cold-download — the R1 gap). The container
  is the real safety boundary for I2: non-root, read-only rootfs, dropped caps, and
  an **egress policy** scoping which hosts it may reach. The image=type /
  volume=identity split mirrors the project's type≠identity principle and the
  layout's "only `substrate/` carries identity."
- **Rules out / bounds.** NOT per-call sandboxes — one long-lived container per
  instance (this is not Managed-Agents / code-execution territory). NOT the dev
  loop — `python -m meno` in a venv stays the inner loop; the image is a
  deployment target. The substrate MUST be the volume, never container-internal
  (a restart is sleep, not amnesia — D12). OCI-neutral (Docker/Podman/containerd);
  rootless preferred. The stdlib kernel is unaffected — network/async lives in the
  integration layer (I0), deps are pinned at the image layer.

### D22 — Bump the Python floor to 3.11; read `meno.toml` with stdlib `tomllib`
- **Decision.** `requires-python = ">=3.11"`. Operator config (`meno.toml`,
  `adapters/*.toml`) is **read** with stdlib `tomllib`; the kernel never writes
  config. Supersedes the prior 3.9 floor (the original 3.9.6 constraint, set when
  `import anthropic` hung, no longer binds — anthropic is an optional extra and the
  deployment target is a container, not the host interpreter).
- **Why.** The instance home (`docs/instance-layout.md`, D21) is configured by a
  human-edited TOML file; comments and hand-editing are the point, so JSON is the
  wrong format. `tomllib` is stdlib only on **3.11+**. The alternatives were a
  `tomli` backport dep (breaks "stdlib-only kernel" for a file the kernel must read
  on every start) or JSON config (loses operator-friendly comments). A version
  bump is the cleanest: a daemon shipped as an OCI image (D21) controls its own
  interpreter, so the floor costs nothing and removes a runtime dependency.
- **Rules out / bounds.** No `tomli`/`tomllib-w` dependency. The kernel **reads**
  TOML and **writes** JSON/JSONL (machine state) — it never serialises TOML, so no
  writer is pulled in. Pre-3.11 interpreters are unsupported; CI and the image base
  pin 3.11+. The stdlib-only-kernel invariant is *preserved* (tomllib is stdlib),
  not weakened. This is a prerequisite for I0b (`meno init` + the config loader +
  the home-bound daemon); see `docs/roadmap-ii.md` I0.

### D23 — Phase S: a mechanics-only self-model, per-tier and cache-controlled
- **Decision.** Every cognitive surface carries a shared type-description of what a
  Meno is and how it operates (`meno/self_model.py`: `MENO_SELF` full,
  `MENO_SELF_BRIEF` abridged), read through one accessor (`self_model(deep)`) so K1
  can relocate the backing store to `library/self-model.md` without touching call
  sites. Deep tiers (associate, synthesise, wonder) get the full text; reflexive
  tiers (appraise, relate) get the brief + the escalation pointer. `models.py`
  passes `system=` as a content-block list so the self-model is a `cache_control`
  prefix (D-prior: plain strings can't carry it).
- **Three disciplines, each test-enforced.** (1) *Mechanics, not meaning* — the text
  plants no conclusion/value/affect/disposition (`IDENTITY_DENYLIST` substring
  tripwire + the S review lens as the binding prescriptive-mood check). (2) *Type,
  not identity* — shared verbatim by every instance; particularity stays in the
  graph. (3) *True to the implementation, this phase* — every named capability maps
  to a real kernel symbol (`SELF_MODEL_CLAIMS`, with directional claims checked
  against kernel *values*, not just name-existence), and nothing from a later phase
  is claimed (`EARNED_NOT_GIVEN`: the transactive stance/lookup/Library are absent
  until K2 — earned, not given).
- **Caching reality (honest bounds).** Caches are model-scoped with a per-model
  min-cacheable floor. The mechanics-only text is ~3.4k tokens: it clears Sonnet
  (2048) so associate+wonder share one cache entry, but is **below Opus's 4096**, so
  synthesise does not cache yet. The Opus floor is reached only by genuine added
  mechanism, never padding — until then it stays deferred. The breakpoint is
  attached on the deep path only (the ~180-token brief is sub-floor on Haiku; a
  breakpoint there could only no-op). Live confirmation (`cache_read>0`, real
  `count_tokens`) is the S-exit smoke, gated on a funded key.
- **Standing guard gains a second axis.** `divergence()` is structural (graph) and
  blind to a prompt/config change; `aliveness.output_divergence()` adds the
  prompt/config axis — two different-graph minds over the same percepts must still
  produce divergent *output*. Offline it only proves the mechanism (substrate drives
  voice; the stub ignores `system=`); the real guard (does the shared self-model
  homogenise voice under real cognition?) is the panel-judged litmus + a key-gated
  live test. A `verdict != "alive"` test confirms the self-model did not animate the
  stub.
- **Rules out / bounds.** No instance identity or earned disposition in the prompt
  (type and mechanics only). The self-model is NOT loaded dynamically per call (the
  surfaces are stateless single calls) — full-vs-brief is a static per-tier constant;
  true load-on-demand is the Agent-Skills pattern, not this. Reviewed via the 5-lens
  gate (theory + test/evidence + kernel-fit); one P0 (the offline anti-convergence
  test was mislabelled as proving prompt-homogenisation) and the P1s were fixed
  before close.
