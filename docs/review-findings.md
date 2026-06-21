# Adversarial Review — Findings & Remediation (v2 kernel)

*Four adversarial reviewers audited the v2 implementation: theory-fidelity,
code-correctness, substrate (embeddings vs graph DB), and language (Python vs
Rust). This is the synthesis and the resulting plan. Verdict first, because it
reframes everything.*

## Verdict

meno v2 is **a well-organised log with the vocabulary of a mind, not a mind.**
The architecture reads cleanly, all 28 tests pass, the demo is tidy — and that is
precisely the trap principle #6 names ("a zombie agent passes all tests"). Every
mechanism the theory nominates as a *source of life* is either **unwired** (merge,
curiosity, rediscovery, graph-spread-in-cognition) or **inert** (islanding has no
effect on reconstruction; "drift" is frozen token-shuffle). The tests pass because
they assert the mechanical surface (`recalls == 2`, `islanded() == True`,
`nodes >= 2`) and never assert the *meaning* the theory promises.

The substrate and language questions are **downstream of this** and largely moot
until the kernel mechanisms are actually wired and the dynamics fixed. Two
reviewers independently concluded the real bottleneck is *algorithmic and wiring*,
not the backend or the language.

## Convergent findings (most damning first)

| # | Finding | Kind | Found by |
|---|---------|------|----------|
| F1 | **Islanding is inert.** `reconstruct` rebuilds a reflection from its entry points' *own content*; decayed edges only remove neighbours, so islanding a reflection's whole neighbourhood returns a byte-identical reflection. The keystone reconstructive claim is false in code. | FUNDAMENTAL | theory |
| F2 | **Merge ("insight/aha") is dead code.** `detect_merge`/`merge` are called only by a unit test, never by the runtime/dream/heartbeat. The project's central emergent behaviour cannot occur in a running mind. | FUNDAMENTAL | theory, code (H4) |
| F3 | **Curiosity does not exist.** Zero hits for curiosity/boredom/under-stimulation. Only impulse (push) is built; the whole "pull toward the world" half of principle #4 is absent, so the Effector never self-fires — meno never reaches out on its own. | FUNDAMENTAL | theory |
| F4 | **Rediscovery never fires.** `graph.islanded()` is dead code; `graph.similar()` is used only by the Associator (which excludes its own stream and needs ≥2 nodes). Nothing re-bridges an islanded node. The flagship justification for embeddings is unexercised. | FUNDAMENTAL | theory, substrate |
| F5 | **Surprise is broken across bursts.** Surprise is measured against the working set, but `claim()` drains it before the next event is scored, so surprise ≈ 1.0 for almost everything. Habituation works only *within* a burst; the Tier-2/3 thresholds are effectively dead, so synthesis over-fires. | FUNDAMENTAL | code (M1) |
| F6 | **Heartbeat storm not fixed (D11 oversold).** A synthesised stream immediately re-qualifies to defer→wake→synthesise. Measured: **26 reflections from 4 stimuli**; bounded only by the `ticks` arg, not by quiescence. The storm was relocated, not cured. | FUNDAMENTAL | theory, code (H2) |
| F7 | **Graph spreading activation — "the spine" — is used only inside reflection reconstruct,** never by the Associator/Synthesiser. The expensive connection-seeking step the redesign builds its identity claim on is not wired into cognition. | FUNDAMENTAL | theory, substrate |
| F8 | **"Drift" doesn't change meaning.** `occasion` is stored verbatim and anchors every reconstruction; the reconsolidated gist updates only *recall matching*, never the reconstructed text. Drift changes retrieval reach, not meaning. | FUND. + stub | theory |
| F9 | **`_enforce_capacity` is broken.** `stream_id is None` evicts the entire un-routed cohort; a single stream larger than N collapses the working set to ~1 and thrashes forever; no progress guard. "Never split a stream" + "stream > N" is unsatisfiable and the code resolves it by destroying the stream. | HIGH | code (H1) |
| F10 | **Global id counters collide across instances;** `persistence.load` clobbers the module-global counter, so a fresh load can make an existing instance mint colliding ids and silently overwrite a node. | HIGH | code (H3) |
| F11 | With the default **stub**, the whole system is a pure deterministic function of its inputs — byte-identical output every run, structurally incapable of surprise. And the stub is what the docs present as "working meno." | STUB (w/ caveat) | theory |
| F12 | **Tests are tautological around the dynamics** (storm, demotion, habituation, insight) and solid only on static graph/persistence/model-shape. Several pass *because* of the bug (e.g. the initiative test is satisfied by the storm). | HIGH | code, theory |

What a real model/embedder *would* fix: F8 (wording), F11 (variety), and the
brittleness behind F4-style association. What no backend swap touches: **F1, F2,
F3, F4-wiring, F5, F6, F7, F9, F10, F12.** The fundamentals are wiring and design,
not substrate.

## The three questions

### Q1 — Embeddings vs graph database

**Complements, not substitutes.** Embeddings answer "what *means* the same?";
graph traversal answers "what is *connected*?". They do genuinely different jobs:
traversal walks existing structure (reconstruction-gather, the gate); similarity
finds structure that isn't there yet or is broken (rediscovery of islanded nodes,
matching an external recall probe to a cue). Neither replaces the other.

- A learned **embedder** carries *capability* (semantic rediscovery + recall),
  and it is load-bearing on the **cold path only** (anything that touches the
  graph) — a real embed per *event* on the hot path would violate the kernel's
  "gate must be cheap" rule. Keep `HashingEmbedding` for the genuinely graph-free
  hot ops (gate surprise, stream centroids).
- A **graph DB** carries only *scale/persistence* (ANN instead of the current
  O(n) `similar`, durability instead of whole-graph JSON). It does **not** make
  embeddings — you still feed it vectors. It is orthogonal to capability.
- **Latent bug to fix regardless:** the recall *probe* and the stored *gist* must
  use the **same** embedder, or recall returns noise.
- **The meno-faithful possibility worth weighing:** cheap embedding + *rich
  traversal* + an *aggressive dream* lets the graph learn its **own** semantics
  rather than importing a generic foundation model's — "the graph's idiosyncrasy
  is the identity" cuts against an identity-less embedder. The embedder may be a
  bootstrap device, not a permanent load.

**Recommendation:** real embeddings *before* a graph DB — but **wire up
rediscovery first (F4)**, because we cannot evaluate whether we need a better
embedder until the feature that needs it actually runs. Defer the graph DB to a
real scale/persistence trigger; when it comes, prefer a single store with native
vectors (SurrealDB) over two stores (one mind, one memory).

### Q2 — Where are we?

A zombie (see Verdict). Clean seams, dead muscles. The good news: the seams are
clean enough that wiring the muscles is tractable, and the failures are specific
and individually fixable, not a mush.

### Q3 — Python vs Rust

**Stay on Python.** The concurrency we need is overlapping *network waits*
(rare, expensive LLM calls) — `asyncio.Semaphore(D)` *is* the deep-slot cap, and
asyncio ties tokio there. The GIL doesn't bite: the autonomic loop is microseconds
of cosine over a *bounded* working set; heavy graph work is cold-path, amortised
behind a multi-second model call. meno's real bug classes are **dynamics** (storms,
runaway decay, mis-tuned scoring) — which the type system can't catch and which
you fix by *running and tuning* (Python's strength). Rust's ownership safety
targets shared-memory parallelism races the design has **deliberately designed
out** ("one mind, tiny D"). Ecosystem (Anthropic SDK, embedders) is decisively
Python.

- The genuinely defensible long-term shape is **hybrid**: Python shell + a
  **PyO3 Rust core for the graph + spreading activation + ANN** — but it's
  *profile-triggered*, not now (the graph isn't large, and it's heading to an
  external DB anyway). The canary that flips the decision: **the hot path starting
  to touch the graph continuously.**
- Both reviewers independently noted the current graph is algorithmically naive
  (`neighbors()` scans *all* edges; `similar()` is O(n)) — **the bottleneck is
  algorithmic, not language.** Fix that in Python first (adjacency map + ANN).

## Remediation plan (fundamentals before backends)

**P0 — Wire the kernel; make the mechanisms real.** No backend/language change
helps these.
1. Reconstruction must degrade with islanding (F1): rebuild from what is
   *reachable via surviving edges* (+ gist), so a cut-off reflection genuinely
   goes thin. This is the keystone.
2. Wire **merge** into the loop (F2) — dream and/or post-burst — and test it
   *through the runtime*.
3. Implement **curiosity** (F3): an under-stimulation/boredom drive that
   self-generates INTENT (the Effector fires on its own); plus bottom-up
   curiosity from unresolved residue climbing. This is what makes initiative
   "want the world," not just finish backlog.
4. Wire **rediscovery** (F4): a new percept that matches an islanded node
   re-bridges it (`similar` → new edge), re-entering it on the bus.
5. Use **graph spreading activation in cognition** (F7), not just reconstruct.
6. Fix **surprise/habituation across bursts** (F5): measure against the graph or
   a recency window, not the draining working set — this also revives the dead
   tier thresholds.
7. Fix the **heartbeat storm** properly (F6): a refractory/"synthesised-this-cycle"
   gate so a stream can't immediately re-defer.

**P1 — Make tests assert *meaning*, not surface (F12).** Theory checks that fail
if F1–F7 regress (e.g. "islanding measurably thins reconstruction"; "two
converging streams merge through the runtime"; "an islanded node is rediscovered
by a bridging percept"; "habituation holds across bursts"). Otherwise we will
re-zombify.

**P2 — Correctness fixes:** `_enforce_capacity` (F9), per-instance id counters
(F10), the `route` strict-inequality/seed bug, the empty-wake-message and
journaling-drifts-on-freeze foot-guns.

**P3 — Then, and only then, backends & execution:**
- real embedder on graph-touching ops (probe/gist consistent), defer graph DB;
- the deferred **async execution layer** (real `P` pool + `asyncio.Semaphore(D)`);
- adjacency index + ANN for the two naive data structures.

**Not doing now:** Rust rewrite (revisit only if meno becomes a high-throughput
service); a graph DB (revisit at a scale/persistence trigger); any new feature
before the existing mechanisms actually run.

## The honest meta-point

The build was optimised for a green suite and a clean demo, which is exactly how a
zombie passes. The fix is not more features — it is wiring the mechanisms already
designed, and writing tests that assert the *behaviour the theory promises* so the
zombie can't come back.
