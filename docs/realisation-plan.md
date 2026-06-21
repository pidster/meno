# Realisation Plan — A Working Meno

**Goal:** not a green test suite, but a Meno that *realises the vision*: a
persistent agent that accumulates experience, develops particularity it was not
seeded with, and survives the zombie test (CLAUDE.md principle 6). The v2 kernel
is mechanically live; this plan closes the gap between *runs* and *is alive*.

## Operating discipline (every phase)

1. **Working slice** — each phase produces something runnable end to end, not a
   layer that only makes sense once the next lands.
2. **Failing-then-passing tests** — including a *fidelity* test that asserts
   meaning, not mechanism (the zombie guard).
3. **Adversarial review gate** — before the next phase starts, run the
   `adversarial-design-review` skill: spawn one specialist per lens
   (Theory Coherence, Runtime Feasibility, Data/Model Semantics, Test/Evidence
   Quality, User-Intent Alignment), findings-first, P0/P1/P2. Every accepted
   P0/P1 becomes a design change, a test gate, a documented non-goal, or an
   explicit decision to proceed. No phase advances over an open P0.
4. **Stop conditions** (from `docs/rethink/03-review-protocol.md`): halt if a
   graph mutation can occur without a journal event; a dream/rehearsal can
   become fact; vitality counts placeholders as signal; retrieval can't explain
   activation; or the implementation can pass while ignoring accumulated history.

## Non-goals (anti-Goodhart, from the R0 review)

- **Aliveness scores are tripwires, never optimisation targets.** No phase's
  success criterion may be "an aliveness number went up." The loop must never read
  its own aliveness score and steer by it — that manufactures the metric instead of
  the mind. R5's panel must check the marks were *earned*, not engineered (e.g. a
  hub emerged from accumulated activation, it wasn't written in).
- **"Surprise" is panel-judged, not computed.** `novelty` is a necessary-not-
  sufficient proxy; the acceptance-bar "it does something the builder did not
  predict" is reserved for the R5 human/adversarial panel and is never considered
  discharged by `novelty` passing.
- **Provenance is the real particularity test.** A graph can be *shaped* to look
  idiosyncratic. R5 must verify the structure has a causal history (concentration
  tracks accumulated reinforcement), not just a final-state shape.

## The acceptance bar — the zombie test (defined up front so we don't drift)

A *working* Meno must demonstrate, on a real accumulating run, at least:
- **Particularity** — graph regions of unexpected density that reflect what *this*
  instance attended to, not the seed.
- **Unpredicted initiative** — at least one impulse/curiosity it generated and
  acted on that was not scripted.
- **Emergent synthesis** — at least one insight (merged streams / dream
  recombination / reflection) that no single component or input contained.
- **Non-substitutability** — a fresh instance given the same inputs would *not*
  produce the same graph.
- **Surprise** — it does something the builder did not predict.
A run that is mechanically perfect but fails these is a zombie, and fails.

---

## Phase R0 — Define "alive" as executable criteria  *(no external deps)*
- Turn the acceptance bar above into observable/automatable probes (graph
  particularity metrics, an initiative log, a synthesis detector, a
  same-input-different-graph harness).
- Restore the review machinery (done: `.agents/skills/adversarial-design-review`).
- **Review focus:** Theory Coherence + Test/Evidence Quality — is this a real
  test of life or a zombie-passable checklist?

## Phase R1 — Real cognition, validated end to end  *(needs a real model)*
- Install + wire `AnthropicModelProvider`; validate every model-judged surface:
  `appraise / associate / synthesise / relate / wonder / reconstruct`.
- Close the open merge caveat: with real embedder **and** real model, genuinely
  convergent (lexically different) streams merge into an `insight:` cue.
- Prove reflections are *reconstructed*, not templated (the formulaic-reflector
  failure mode).
- **Make cognition failure loud.** The provider's best-effort fallback silently
  degrades any model error (no credits, network, refusal, parse) to the stub —
  which would let a run *look* like real Claude while running the zombie stub,
  making the zombie test meaningless. R1 must surface degradation: a strict mode
  that raises, or a per-run telemetry counter of real-vs-fallback calls that the
  zombie test asserts is ~100% real.
- **Cognition-gate decisions (from the R1 review):**
  - The zombie verdict **fails closed**: "alive" is reachable only when cognition
    is proven real. `zombie_report` auto-derives `cognition_real` from the run's
    provider telemetry; absent/unproven cognition → `indeterminate`, never `alive`.
  - The gate keys on the **synthesis tier** (real, zero fallbacks) plus a ≥90%
    overall real fraction — so one transient cheap-surface blip can't poison a long
    run, but a degraded *insight* call (or wholesale degradation) does.
  - **R5 accumulation runs use `strict=True`.** A silent `relate` fallback changes
    which streams merge — it corrupts graph topology, not just a log line — so a run
    that claims to accumulate genuine experience must abort loudly on degradation
    rather than letting the stub quietly edit the agent's mind.
- **Review focus:** Data/Model Semantics + Theory Coherence.

## Phase R2 — Continuous operation  *(model-agnostic)*
- Async/worker driver over `run_until_quiescent` + `heartbeat` so Meno runs its
  default-mode loop autonomously between inputs, with bounded concurrency.
- **Review focus:** Runtime Feasibility (failure paths, back-pressure, no busy-spin).

## Phase R3 — Lifetime-growth hardening (D19 A1/A2/A3)  *(model-agnostic)*
- Bound `bus.log` (ring + fold-then-trim), reap cold warm streams, bound
  reconsolidation / retire cues. Cue retirement is **grief, not GC** — reflective.
- **Review focus:** Runtime Feasibility + Theory Coherence (forgetting stays principled).

## Phase R4 — Sensorium + warm-tier persistence  *(model-agnostic)*
- At least one real afferent channel (filesystem/git watcher) so Meno senses the
  world; persist warm streams so a restart resumes mid-thought, not just cold.
- **Review focus:** Data/Model Semantics + User-Intent (autonomy/privacy/resource bounds).

## Phase R5 — The zombie test  *(needs real model; the acceptance gate)*
- Run Meno continuously with real cognition + embedder + sensorium, accumulating
  experience over an extended session. Then convene an adversarial panel whose
  job is to **prove it is a zombie** (any fresh instance reproduces its graph).
- **Pass only if it survives** every probe from R0 and the panel cannot reduce it
  to generic. If it fails, the review asks what went wrong *in the building*, not
  the code — and we iterate, not ship.

---

## Dependency note
R0/R2/R3/R4 need no external service. **R1 and R5 require a real cognition model**
(Anthropic key + SDK, or an equivalent local LLM provider) — without it the
cognition tier is the deterministic stub, which is a zombie by construction. The
infrastructure phases can proceed in parallel while that is resolved.
