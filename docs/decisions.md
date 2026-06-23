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

### D24 — The self-model's canonical home is the code constant; the Library holds a copy
- **Decision.** The self-model document's single source of truth is the code constant
  `self_model.MENO_SELF` (baked into the image — the *type*, D21). `self_model()`
  reads the constant. K1's Library holds a **lookup-able copy** (`key="self-model"`,
  `kind="reference"`, `source="meno:type"`) seeded *from* the constant, and the copy
  is **re-derived from the constant on load** so it can never outlive the image that
  produced it. The Library copy never overrides the constant. Supersedes the roadmap's
  earlier tentative "relocate the self-model to the Library in K1 / served from the
  Library"; D23's accessor rationale ("so K1 can swap the backing store") is therefore
  superseded — the accessor remains a useful single read-seam, but the relocation it
  anticipated is rejected.
- **Why.** type≠identity (D21) is decisive: the self-model is the *type*. If the
  canonical self-model lived in the mutable, per-instance Library (`<home>/library/`,
  the volume = identity), an operator could make two instances of *one image* differ
  in **kind** by editing one instance's `index.json` — exactly the type/identity
  confusion D21 forbids ("only `substrate/` carries identity"). The constant-in-image
  is the only home consistent with that. The Library copy exists solely so the agent
  can *look up* its own self-model in K2 (transactive memory), not to define it.
  Re-deriving on load closes the drift a K1 review flagged: an image upgrade changes
  the constant while a persisted Library still holds the old body, and K2 would read
  the stale copy — so the copy is always refreshed from the constant at load.
- **Rules out / bounds.** No per-instance self-model customisation (that would be
  customising the type). The Library is NOT the self-model's backing store. `library/
  self-model.md` (instance-layout) is a copy/export, not the source. K1 also hardened
  the Library this entails: `Reference` is frozen (byte-identical is structural, not
  convention), and the Library saves atomically (temp + `os.replace`). *(The
  write-back guard's shape was revised by D25 — see there.)*

### D25 — The Library is the self's self-managed, curated reference material
- **Decision.** The Library is **not** external-only reference the self merely
  consults; it is the self's **own curated shelf**, which the self **manages** (looks
  things up, decides what to keep, prunes). The write-back boundary is therefore by
  **content kind, not authorship**: `put` accepts the reference kinds
  (`definition`/`fact`/`reference`) from any provenance — including the agent's own
  curation — and rejects only non-reference kinds (experience/reflection/perspective,
  which are the substrate) and entries missing a key/body/provenance. Provenance
  (`source`) is *recorded* (lookup / operator seed / agent curation), never used to
  reject self-curation. Supersedes K1's first cut, where a review had inverted the
  guard to an external-source *allowlist* that rejected self-authored writes — that
  closed a real bypass but under the wrong model, making the Library external-only and
  forbidding the self-management that is its purpose.
- **Why (Pid).** "The Library is not the self — the substrate provides this. The
  Library is the self's self-managed, curated reference material." The substrate (the
  graph) is identity: idiosyncratic, forgetful, reconstructive. The Library is a
  *tool the identity curates*, stable where the substrate drifts. The real invariant
  is not "keep the self out of the Library" but "keep *experience* out of the Library
  and *reference* out of the substrate": experience/reflection stay in the substrate
  so they remain free to be forgotten and reconstructed (forgetting is load-bearing);
  reference is stable and looked-up. Authorship is orthogonal — the agent curating a
  fact it looked up is the whole point of a transactive memory.
- **Rules out / bounds.** The episodic≠semantic boundary is enforced by **kind**, not
  source. What `put` cannot catch — reflective *content* mislabelled `kind="fact"` —
  is **caller discipline**: the K2 lookup effector files looked-up *results*, never
  the agent's perspective; reflections route to the substrate as `Kind.SELF` nodes,
  not into the Library. Curating the shelf cannot manufacture a self: the aliveness
  marks (particularity, divergence) read the **graph**, never the Library, so a
  self-managed reference shelf is never read as identity. K2 is reframed accordingly:
  lookup is the agent *curating* its shelf (resolve + decide-to-retain), not an
  external-only fetch.

### D26 — Slack afferent redaction is blunt and best-effort
- **Decision.** The I1 Slack adapter redacts obvious secrets and PII (slack/openai/aws/
  github tokens, JWTs, private-key blocks, `password=…`, emails, US SSNs) from a
  message BEFORE it becomes a percept — and before truncation, so a secret cannot
  survive by straddling the size cap. Redaction is deliberately blunt (a regex pass,
  over-redacts rather than under), and is **best-effort, not a guarantee**.
- **Why.** A Slack channel carries text anyone in it can paste; an un-redacted secret
  that becomes a percept is encoded as a near-permanent graph node and consolidated by
  the dream. So content redaction is the one content guard on world-text entering the
  substrate, and it must see the whole message (hence redact-before-truncate). But no
  regex catches every secret/PII shape, and aggressive entropy-based redaction would
  gut normal chat. So the residual risk is bounded operationally: the operator chooses
  which channels to list, and **must not list channels carrying regulated PII** — the
  adapter is consent-scoped (listed AND joined) precisely so this is a deliberate choice.
- **Rules out / bounds.** NOT a compliance control. NOT a substitute for channel
  hygiene. The bot's own posts are skipped (subtype/bot_user_id) as the afferent half
  of I2's self-echo guard, but the authoritative self-echo guard is I2's
  `source="self:slack"` tag. A bot_user_id should be auto-derived (auth.test) in I2.
- **Extension (egress side).** The same redactor scrubs the **at-rest audit copy** of an
  outbound post (`journal/traces/slack-sends.jsonl`): the mind may author a post quoting
  a secret it recalled, and the audit log is the wrong place for a credential to persist.
  Only the audited copy is redacted — the message actually sent, and the confirm-first
  operator preview (`_pending`), keep the real text (the operator authored it
  deliberately and reviews it in the clear). SDK exception strings reaching `last_error`
  are redacted too, and `xapp-` (Socket Mode app token) is in the secret pattern.

### D27 — Two daemon modes: bounded step-loop (deterministic) vs unbounded start() (non-blocking)
- **Decision.** `meno run --cycles N` drives the deterministic single-thread step loop
  (tests, one-shots, reproducible). `meno run` with no `--cycles` (the real daemon) uses
  `Driver.start()` — the background loop PLUS the off-thread outbound worker — so a slow
  network call from an efferent adapter (I2/K3) never blocks cognition. The home's
  advisory lock (`run/instance.lock`, `fcntl.flock`) is held for the daemon's life so two
  processes can't race on one substrate (last-writer-wins would silently corrupt the
  identity). The substrate is persisted **periodically** (`save_every`), not only on
  shutdown, so a crash/SIGKILL resumes from a recent point, not the seed.
- **Why.** A K1 review flagged that a step-loop daemon drains the outbox inline (on the
  mind thread), so the first efferent adapter would block the whole loop — defeating the
  reason I0a built the outbox/worker. The two-mode split keeps tests deterministic while
  the production daemon gets the non-blocking path. The lock and periodic save close two
  data-integrity gaps the I0b review found (two-daemon corruption; shutdown-only save
  losing a whole session on a kill).
- **Rules out / bounds.** `--cycles` mode is NOT for production with efferent adapters
  (it would block on a network deliver) — it is the deterministic/test path. SIGKILL still
  loses work since the last periodic save (unavoidable; the floor is the last snapshot).
  The lock is POSIX (`fcntl`); a no-op where unavailable.

### D28 — Allowlisted knowledge authorities are TRUSTED; the allowlist is the boundary
- **Decision.** A K3 external authority's response is curated into the Library verbatim
  (after redaction + size-bounding), with no content-truthfulness validation. The
  `[egress] allow` list (and `knowledge.toml hosts`) is therefore the **trust
  boundary**: an operator must only allowlist authorities they trust, exactly as D26
  makes the operator responsible for which Slack channels are listed. Curated entries
  record the **actual host** in their provenance (`authority:<kind>:<host>`), are the
  **lowest-trust** class, and are the **first evicted** when the Library hits its cap
  (operator seeds and the self-model are protected).
- **Why.** There is no general way to verify a looked-up fact is true; a hostile or
  low-quality authority on the allowlist could otherwise write a permanent false belief
  (the Library is non-decaying, and a curated hit is not re-fetched). Three mitigations
  bound the blast radius rather than eliminate it: (1) a curated reference is **never
  encoded into the substrate** (K2 guard) — a falsehood can poison the *shelf*, never
  the *self*; (2) redaction + `max_chars` stop a credential or unbounded blob entering
  permanent reference (D26 hygiene, now shared inbound/outbound); (3) the host-named
  provenance + the durable outbound audit (`journal/traces/outbound.jsonl`) make a bad
  fact attributable after the fact, and the eviction order makes authority knowledge
  prunable as a class.
- **Rules out / bounds.** NOT a fact-checker. The agent can "know" a looked-up falsehood
  as stable reference until evicted/overwritten — accepted, contained to the shelf. A
  re-verification/TTL policy on authority entries is deferred (the live network client
  is deferred); the cap + eviction + audit are the v1 floor.

### D29 — Slack afferent has two receive modes; Socket Mode senses only bare messages
- **Decision.** The `SlackAdapter` supports both receive models behind one
  `socket_mode` flag (`adapters/slack.toml`): **polling** (`conversations.history`, bot
  token only) and **Socket Mode** (real-time Events API over an outbound WebSocket, the
  `start(driver)` push contract, needs an app-level token `$SLACK_APP_TOKEN`). Neither
  needs a public endpoint — both are outbound-only, gated by the same `*.slack.com`
  egress (D21). Socket Mode is active only in the unbounded `meno run` daemon (D27),
  which calls `adapter.start()`; bounded `--cycles` runs stay on poll. Both paths share
  one `_shape()` (consent + self-echo + redaction-before-truncation), pinned by a parity
  test. The push path additionally: **drops every subtyped `message` event** (accepts
  only bare `message`/`app_mention`); honours a message's **`bot_id`** as a self-echo
  signal; **de-duplicates by Slack `event_id`** (bounded cache); and **acks before
  dispatch**.
- **Why.** (1) Subtype drop closes a real self-echo bypass: a `message_changed` edit
  carries the true author/body *nested* under `event['message']`, invisible to a
  top-level guard — meno editing its own post could re-enter as experience. Dropping all
  subtypes is the conservative bound (it also forgoes real-time threaded-broadcast /
  file-share text — poll still sees those). (2) `bot_id` keeps the self-echo guard intact
  even when `auth_test` failed and meno's own user id is unknown (its own posts arrive
  without the `bot_message` subtype). (3) `event_id` dedup makes "ack-first" safe: a
  failed/slow ack triggers a Slack resend, which dedup absorbs — so a transient ack
  failure costs neither a lost percept nor a doubled one. (4) SDK exception text is
  redacted before it reaches `last_error`/telemetry, and `xapp-` is added to the secret
  pattern, so an app token can't leak through an error string.
- **Rules out / bounds.** Socket Mode percepts dropped under inbox backpressure are NOT
  recoverable (ack precedes ingest), unlike poll's self-healing cursor — accepted (the
  drop is counted in `dropped_input`; a reflective agent need not ingest faster than it
  thinks). No per-window rate cap on the push path beyond the bounded inbox (deferred).
  Membership ('joined') consent rests on Slack only delivering events for joined
  channels plus the operator's listed-channel filter — no extra `_joined()` network call
  on the WS thread. Mentions enter cognition as ordinary percepts; there is no
  "always-reply-when-mentioned" reflex (any reply goes through the gated efferent path).

### D30 — uv + a committed lockfile; multi-stage uv container build
- **Decision.** `uv` is the preferred resolver/installer for development and the
  container build, with `uv.lock` committed for a reproducible dependency graph. The
  `Containerfile` is multi-stage: a `ghcr.io/astral-sh/uv` builder runs
  `uv sync --frozen --no-dev --extra anthropic --extra slack` into `/app/.venv`, and only
  that venv is copied into a clean `python:3.13-slim` runtime (both stages share the
  `python:3.13-bookworm` lineage, so the copied venv's interpreter resolves). `pip` still
  works as a fallback; the kernel stays stdlib-only (uv is a build/dev tool, never a
  runtime import).
- **Why.** The single-stage pip build timed out resolving/compiling the `anthropic` layer
  in the sandbox; the same install under uv completes in ~1s and the whole image builds
  in ~6s. `--frozen` pins the exact graph (supply-chain reproducibility) instead of
  re-resolving per build; multi-stage keeps uv, build tools, and caches out of the final
  image (smaller surface). Validated end-to-end: image builds, then `init`/`run`/restart
  pass under the hardened profile (read-only rootfs, non-root uid 10001, cap-drop=ALL).
- **Rules out / bounds.** Not distroless (yet): a distroless runtime needs the venv's
  interpreter relocated/copied to match its Python, a fiddly step deferred — the security
  boundary is non-root + read-only rootfs + dropped caps + the egress allowlist, which a
  slim runtime carries identically. `requires-python >= 3.11` (D22) unchanged; the lock
  resolves across that range. Baking the `local` embedder weights stays an opt-in,
  commented build stage (adds torch, ~100s of MB).

### D31 — Secrets resolved by name in the composition root; no store the mind can read
- **Decision.** A `SecretResolver` (in `meno_adapters`, never the kernel) resolves
  config-declared secret NAMES (`SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, later DB creds) to
  values at adapter-construction time. Values live only inside the adapter object —
  outside cognition and outside the substrate. Backends are pluggable and tried in order
  behind a `SecretBackend` protocol (`get(name) -> str | None`): the default is the
  process environment (12-factor); a read-only `DotenvBackend` is an explicit opt-in via
  `meno.toml [secrets] file = …` (env wins; a relative path resolves against the home and
  is gitignored, an absolute path keeps secrets outside the home entirely). The resolver
  holds no values and its repr hides the chain, so it can't leak a credential through a
  log line or stack trace. `SlackAdapter` now reads both tokens through the resolver
  instead of `os.environ`.
- **Why.** Formalises the indirection the architecture already implied and answers
  "does Meno need a K/V store for secrets?" — NO mind-accessible one. Giving the agent a
  vault it could read would let a prompt-injected percept recall-and-exfiltrate a
  credential; keeping secrets in the process/adapter boundary (and out of the graph,
  which D26 redaction already enforces for inbound text) is the containment. Pluggable
  backends leave a clean seam for an external manager (Vault, SOPS, a cloud secrets API)
  without touching the kernel or the mind.
- **Rules out / bounds.** Not a secrets *manager* (no rotation, no leasing) — it RESOLVES,
  it doesn't store or issue. The default posture is unchanged (env-only, nothing in the
  home); the dotenv file is a convenience, never required. The kernel-purity test is
  extended to forbid `meno/` importing the resolver, same as the rest of the adapter layer.

### D32 — Cost governor + a health surface (pathology containment, part 1)
- **Decision.** A continuously-running mind gets a circuit-breaker on EXPENSIVE cognition.
  `CostGovernor` (meno/governor.py) counts "deep ops" — Tier-3 synthesis, the outward
  curiosity reach, and the dream (the operations that cost real model calls online) — over
  a rolling window of cycles. When the windowed count crosses `cost_budget_per_window` it
  TRIPS; the driver then sets `mind.throttled`, which (a) skips the dream and (b) makes the
  mind suppress the outward reach and withhold Tier-3 — withheld deep work DEFERS (builds
  impulse pressure) and resumes when the throttle lifts, it is never discarded. Self-
  regulating with hysteresis (resets at `budget * cost_resume_ratio`); disabled at
  `budget = 0`; generous default (60/20 cycles) so it's a runaway backstop, not a normal
  limiter. A `health` block in `status.json` surfaces the operator-facing signals — idle
  fraction, queue depth, dropped input/outbound, egress denials, working-set/stream depth,
  degraded cognition, and the breaker state — so pathology is VISIBLE.
- **Why.** Containment of *action* was already strong (egress allowlist, the efferent gate,
  bounded queues); the gap was containment of *cost/compute*. A hot loop or a percept flood
  could burn unbounded API spend with no brake and no operator signal. The governor counts
  deep ops rather than wall-clock/tokens so it is deterministic and testable offline (the
  same ops run free under the stub) yet bounds real cost online. Throttling slows, never
  stops — cheap heartbeat cognition continues, so the agent stays alive while shedding the
  expensive work; and because withheld work defers, nothing is silently lost.
- **Rules out / bounds.** Not a token-accurate budget (a coarse deep-op proxy). Not a kill
  switch. The substrate-size ceiling and the fixation watchdog (their config knobs land
  here, inert by default — `node_ceiling = 0`, `fixation_ttl_ticks`) are implemented in the
  containment slice (D33). A bare `Meno` with no driver is unchanged: `throttled` is False
  and `cost_units` simply counts.

### D33 — Fixation watchdog + substrate ceiling with grief-pruning (containment, part 2)
- **Decision (fixation).** An impulse (a deferred stream) builds pressure and never decays
  (intrinsic, F4); if its synthesis keeps being withheld — e.g. a sustained D32 throttle, or
  a deep-budget race — it can push forever without discharging. A watchdog counts ticks a
  stream is continuously deferred-WITHOUT-discharge (`deferred_ticks`); past `fixation_ttl_ticks`
  it FORCES the take-up: a forced wake that (a) bypasses the novelty gate so it always reaches
  a processor, (b) bypasses the throttle in `Synthesiser.triggers`, and (c) resets the clock
  only on CONFIRMED discharge — so a forced take-up that somehow failed would re-arm, not
  silently abandon the impulse. Counted as `fixations` in telemetry. This honours the ethos
  (the impulse is finally TAKEN UP, not decayed away). 0 disables it.
- **Decision (ceiling).** A hard cap on graph node count (`node_ceiling`, 0 = off). Overflow
  does NOT garbage-collect: the dream grief-prunes whole islanded node-streams — synthesises a
  "letting go" reflection and JOURNALS it (durable, recallable), then releases the cohort and
  its edges. Whole streams only (orphan/untagged nodes are NEVER pruned, so a train of thought
  is never split); faint + islanded + dormant cohorts go first; SPARED are live (working-set)
  streams, deferred impulses, and the anchors of deliberately-journaled OR frequently-recalled
  (`recalls>0`) reflections. Bounded per dream (`node_grief_max_per_dream`).
- **Why.** Containment of compute (D32) wasn't enough: an impulse could fixate, and the graph
  could grow unbounded over a long life (forgetting only reclaimed islanded provisionals + cues,
  never consolidated node-streams). Both are now bounded WITHOUT betraying the architecture:
  pruning is grief (deliberate, reflected-on, journaled), the impulse/curiosity asymmetry holds.
- **Rules out / bounds.** The ceiling is a SOFT cap: if every cohort is live or protected it
  stays over the ceiling rather than killing live thought (correct for the ethos). It runs even
  while throttled — but CHEAPLY: the dream's model-call passes (merge, reconsolidation) skip and
  all grief is templated (no model call) under throttle, so forgetting stays enforced under the
  cost breaker while the expensive generative work is withheld. Not a token-exact bound; the
  grief reflection under throttle is templated prose, not model-authored.

### D34 — The substrate store is a selectable backend; a DB is a sidecar, not baked in
- **Decision.** Persistence goes behind a `Store` interface (`meno/store.py`): `save(mind)`
  / `load(mind)`, selected by `meno.toml [storage] backend`. `FileStore` (the JSON substrate
  under the home volume) is the default and the only backend that ships. A graph/vector DB
  (SurrealDB) plugs in behind the same interface and is provisioned as a SIDECAR
  (`deploy/compose.yaml`, gated behind the `db` compose profile) — a separate, digest-pinned
  container with its own volume on an internal network, NEVER co-baked into the app image.
  Selecting an unimplemented backend raises `NotImplementedError` with a pointer; it never
  silently falls back.
- **Why.** For a single instance the file substrate IS the right persistence — the mounted
  volume is the identity, with no service to run; a DB is premature until an instance outgrows
  it (concurrent readers, vector search at scale). Co-packaging a stateful DB into the app
  container would break the hardened, single-process, read-only-rootfs image and couple their
  lifecycles. The sidecar keeps the app image minimal and the DB independently
  backup-able/upgradable. A loud failure on an unbuilt backend honours the zombie test — a
  substrate that doesn't persist must never look like it does.
- **Rules out / bounds.** No SurrealDB backend ships yet (it needs a running service to build
  and test against; deferred until needed). The `Store` seam stays kernel-pure (the file store
  is stdlib); a network backend, when added, lazily imports its client like the Anthropic
  provider does. Secrets for the DB are resolved by name (D31), never baked.

### D26a — Slack consent is the INVITE; channel allow-list is optional
- **Update to D26.** The afferent consent boundary is "the bot was invited" (joined), not a
  hand-maintained channel-ID list. With `adapters/slack.toml [afferent] channels = []` (now
  the default), meno senses EVERY channel `@meno` is invited to — discovered dynamically via
  `users.conversations` (poll) and enforced by Slack delivering only joined-channel events
  (Socket Mode). A non-empty `channels` is an OPTIONAL further restriction to a subset, not a
  requirement. Inviting a bot to a channel is already a deliberate human act, so it is the
  right consent signal; making the operator also collect channel IDs was friction without
  added safety. Redaction (D26) and the off-by-default gated efferent (I2) are unchanged.
- **Presentation.** The manifest now sets `bot_user.always_online: true` and enables
  `app_home.messages_tab` so the bot shows a presence dot and appears in the workspace Apps
  list — installation/registration was always fine; visibility just wasn't configured.

### D35 — No per-post approval; the efferent is autonomous within standing bounds + dry-run
- **Decision.** Confirm-first (the `_pending` store + `confirm_send` operator step) is REMOVED.
  A file-based per-post approval was too cumbersome for something meant to converse. Outward
  posting is instead gated by standing bounds: the master `enabled` toggle, the `post_channels`
  scope, a `rate` limit, the egress allowlist, and an append-only audit — plus, for the mind,
  the may-respond restraint (it only considers posting when *addressed*, and may stay silent)
  and the cost governor. A `dry_run` flag diverts a composed post to the audit instead of the
  channel: the mind still "spoke" (and feels it as FEEDBACK), but nothing reaches Slack —
  a watched-then-live tuning ramp you flip off in one step, not approve-per-message.
- **Why.** Confirm-first was built for I2 when posting was the highest-stakes unknown; per-post
  human approval is the wrong ergonomics for engagement (it makes conversation impossible). The
  honest safety story for autonomous outward action is layered standing bounds + after-the-fact
  audit + an instant kill (`enabled = false`), not a signature on every utterance. `dry_run`
  preserves a real safety ramp during tuning without the ceremony.
- **Rules out / bounds.** This IS a real step up in autonomy: once enabled for a channel, meno
  posts there without a human in the loop per message. `DeliveryResult` loses `pending`; every
  decision (`delivered` / `refused` / `dry-run`) now feeds back. Replies thread to the
  originating message (`thread_ts`). The addressed-ness detection + the may-respond loop that
  drive *when* it posts are the engagement phase (built next).

### D36 — Engagement: meno reacts to being addressed (may-respond, not a chatbot)
- **Decision.** Being addressed is a percept, and reacting to it can flow outward — so meno
  MAY turn toward an interlocutor and reply, through the gated effector. It is not a chatbot:
  it weighs whether it has something earned to say and may stay SILENT. Addressed-ness is
  graded (the adapter tags each percept): **directed** (structural certainty — an @mention;
  DM/1:1 once im scopes land), **possibly** (a soft lexical cue: meno's own name + a question
  in un-@'d text), **ambient** (sensed, never replied). The mind knows its addressable name
  (the handle). An `Engagement` processor, on a directed/possibly percept, consults memory
  (substrate-first) and calls `models.respond` → `{speak, text}`; if it speaks, it emits a
  POST intent to the percept's channel/thread through the same egress-gated outbound path.
  Replies thread to the originating message. The stub turns toward `directed`, stays silent
  on `possibly` (may-not-must even offline); a real model judges both.
- **Why.** This is the honest reading of "react to sensing" — responsiveness emerges from
  appraising "I'm being addressed" as salient and choosing to act, not a reply reflex. The
  gradient reconciles broad addressing with not-a-chatterbox: ambient chatter is sensed but
  never triggers a paid addressing judgment.
- **Bounds (review fixes).** (1) A per-cycle `engage_per_cycle` budget caps replies COMPOSED
  per cycle, so a burst of @mentions in one cycle can't each fire a paid `respond` call (the
  cost governor only bounds the cross-cycle average; `deep_budget` is per-dream and would
  starve replies). (2) Outbound reply text is REDACTED on the send path (not only the audit):
  a reply is mind-composed from recalled memory, so a substrate secret must not egress via a
  post (supersedes the D26 "sent message intact" stance, which assumed operator-authored
  posts — posts are now mind-authored). (3) The reply channel comes from the delivered event
  (not message text) and is re-checked against `post_channels` at send — injection can't
  redirect a reply. Self-echo (bot_id) prevents meno's own posts re-entering as a new address.
- **Rules out / bounds.** DMs (`message.im`, im:* scopes) and 1:1-channel detection
  (conversations.members, cached) are now wired — a DM or a meno+one-other channel is
  'directed'. Group DMs (mpim) remain optional. No interlocutor model yet (the transactive
  follow-on). With the stub, replies are templated, not meaningful.

### D37 — The Assistant surface (I3.5): meno's dedicated Slack pane
- **Decision.** Adopt Slack's Agents/Assistants feature as meno's primary conversational
  surface: a dedicated split-view pane with greeting, suggested prompts, a "thinking…"
  status, thread titles, and (later) streaming. It rides the existing Socket Mode afferent
  + the I3 engagement loop — an assistant thread is a directed 1:1 space, so messages route
  through `directed → may-respond → gated reply` unchanged. Manifest adds `features.
  assistant_view` (+ `assistant:write` scope, `assistant_thread_started` /
  `assistant_thread_context_changed` events). Built in slices: **A** — pane lifecycle
  (greet/prompts/title on open) [done]; **B** — conversation in the pane (status indicator;
  the honest-non-answer rule below); **C** — streaming replies (deferred).
- **Why.** It's the *native* home for a conversational agent in Slack — a threaded, 1:1,
  affordance-rich space where "addressed → may respond" actually fits, far better than
  @mentions scattered in channels. The Slack **MCP server is explicitly NOT adopted**: it's
  the inverse direction (external agents reaching *into* Slack) and using it as a reach-tool
  would breach meno's invite-as-consent boundary.
- **The pane-silence rule (operator choice).** In the dedicated pane a person has opened a
  conversation, so pure silence reads as broken. meno still never fabricates, but in the
  pane it gives a brief HONEST non-answer ("nothing specific comes to mind on that, but I've
  been turning over X") instead of nothing — may-not-must preserved, dedicated-surface
  expectation met. Outside the pane (channels, ordinary DMs) it may still stay fully silent.
- **Rules out / bounds.** The greeting is a posted message, so it respects the efferent
  `enabled` switch; the prompts/title/status are assistant-UI affordances (assistant:write),
  egress-gated. Requires a manifest reinstall (the new scope + feature). Streaming and a
  dynamic (musings-driven) prompt set are follow-ons.

### D38 — Reach (I4): meno speaks UNPROMPTED, on its own initiative
- **Decision.** meno can now reach OUT, not just respond — the highest-stakes capability
  (speech no one asked for). On a cadence in the quiet heartbeat, `Meno.reach()` gathers
  what's on its mind (a curiosity, a recent reflection, whether an impulse is pressing) and,
  ONLY when that state has changed (`_last_reach_digest` — no paid re-judgment of the same
  mind), asks `models.reach` whether it has something earned to say and to whom. The model's
  bar is HIGH (silence is the default). If it speaks, the mind enqueues a gated outbound
  intent carrying an ABSTRACT target ("voice" / "operator") — never a channel id; the adapter
  resolves the target to a Slack channel. Gated harder than replies: a SEPARATE `reach_enabled`
  toggle (off), its own `reach_dry_run` (on — watched-then-live), a per-DAY rate, egress,
  redaction, audit. Off at every layer by default.
- **Why.** The original design is "a default-mode loop and self-directed cognition" that
  "follows its own curiosities" (the roadmap's *reach*). Without an outward path meno only
  senses, reflects, and answers — quiescent. Reuse the gated effector; the new parts are the
  reach judgment, the abstract-target seam (kernel stays Slack-agnostic), and the tighter
  bounds. Targets: a "voice" channel (its own space), an "operator" DM; channels-it's-in (the
  riskiest) is a later slice.
- **Rules out / bounds.** Unprompted speech is contained by: default-off + dry-run-first + a
  per-day cap + the cost governor (a reach judgment is a deep op) + the digest gate (judges
  only on a new state of mind, so cost scales with cognitive change, not the clock) + the
  model's high bar. A reach post can't self-trigger (self-echo). The mind cannot post to an
  arbitrary channel — only configured targets resolve. Slices 2 (cadence/significance tuning,
  then go live) and 3 (channels-it's-in, with relevance routing) follow.
