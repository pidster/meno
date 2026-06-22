# meno v2 — Roadmap  ·  ARCHIVED / SUPERSEDED

> **This is the historical v2-kernel build roadmap.** Its "immediate next" and
> deferred items are now done or carried forward: the embedder, lifetime-growth
> (D19), and the sensorium were realised in `docs/realisation-plan.md` (R0–R5,
> merged); everything still open lives in `docs/roadmap-ii.md`. Kept for the
> record of how the v2 kernel was planned; not a live plan.

Where the build is, and what's next. The *why* behind each choice lives in
`decisions.md`; the mechanism lives in `redesign.md` / `system-design.md`. This
file is the planning view: status, next steps, and open risks.

Newest status at the top.

---

## Status — June 2026

**The v2 kernel is live and replaces v1 on `main`.** v1 (the tick simulation) is
preserved in `archive/tick-simulation` (and `backup/main-pre-redesign`).

Working end to end, offline and deterministic by default:

- event bus → Tier-0 gate (annotator) → bounded working set → self-selecting
  processors (Tier 1 appraise / Tier 2 associate / Tier 3 synthesise) → effector;
- streams (born / route / merge=insight / suspend / resume), worker budget;
- cold associative graph: spreading activation, embedding similarity, edge-before-
  node decay (islanding), rediscovery;
- reconstructive reflection: cues regenerated at recall (full / partial / ghost),
  reconsolidation drift, deliberate verbatim journaling;
- curiosity (decays, pulls) vs impulse (builds pressure, pushes); model-routed
  curiosity discharge across the internal/external matrix; impulses-first;
- the dream: promote → rediscover → recombine → merge → reconsolidate → forget;
- continuity: `save`/`load` the cold graph (sleep, not death).

Pluggable real backends, all falling back to the offline default:

- **cognition** — `--anthropic` (Haiku/Sonnet/Opus behind `AnthropicModelProvider`);
- **embeddings** — `--split-embed` / `--local-embed` (hot/cold split; local
  sentence-transformers cold adapter; D20).

Tests: 48 pass + 1 skip (the real local embedder, skipped unless the package
*and* its weights are available). The kernel-fidelity suite pins the theory's
meaning so the "zombie" failure mode can't return.

---

## Immediate next — validate the local embedder against real weights

P3 (D20) shipped the hot/cold split and the local cold adapter, and the contract
is fully proven offline by different-dimensioned stub tests. **What's left is a
live run against real sentence-transformer weights**, which this remote
environment's network policy blocks (`huggingface.co` unreachable for the weight
download). Continue on a machine where Hugging Face is reachable:

```bash
pip install -e '.[local]'        # sentence-transformers + torch
python -m pytest -q              # test_local_embedder_loads_if_installed now runs
python -m meno --split-embed     # watch recall/merge/rediscovery on real semantics
```

What to look for (the P3 motivation — the stub embedder throttled these):
- **merge** actually fires in the dream (convergent streams → an `insight:` cue);
- **rediscovery** bridges genuinely-related islanded nodes, not lexical overlaps;
- **recall** distinguishes meaning, not shared tokens (e.g. paraphrase probes hit;
  unrelated-but-overlapping probes don't);
- tune `merge_threshold`, `loose_link_sim`, `rediscovery_threshold`,
  `stream_match_threshold`, and the recall floors in `config.py` for the real
  embedding distribution (the current values were set against the hashing space).

A persisted graph is tied to the cold embedder that built it (the gist space):
loading it under a different cold model mismatches. Pin the model name when you
save anything you want to keep.

---

## Deferred — continuous operation (the next substantial chunk)

The kernel core is synchronous and step-driven (D7) for reproducibility. Real
sensors and concurrent model calls need a live driver, and a long-running process
exposes lifetime-growth that the step-driven demo never hits.

- **Async/worker driver** — a thin wrapper over `run_until_quiescent`; the kernel
  only needs *bounded* concurrency (the worker budget already models it). Run
  model calls (cognition + cold embeddings) concurrently off the hot path.
- **Lifetime-growth fixes (D19 — A1/A2/A3).** Only bite in a long-lived process:
  - **A1 `bus.log`** retains every event ever (with embeddings). Bound it — ring
    buffer + fold-then-trim once consolidation has projected the committed subset.
  - **A2 `streams.warm`** has no reaper; warm-deferred `pressure` grows unbounded.
    Age out cold warm streams; cap/relax pressure.
  - **A3 `graph.cues`** never pruned; reconsolidation re-spreads *all* cues each
    dream (O(lifetime·cues)). Bound reconsolidation to a recent/relevant working
    set; consider cue retirement (with grief, not GC).
- **Warm-tier persistence** — suspended streams currently live only in memory;
  persist them so a restart resumes mid-thought, not just from the cold graph.

## Deferred — scale & reach

- **Indexing** — adjacency map + ANN over embeddings, so spread/similar stop being
  O(nodes). The trigger is a measured profile, not a guess (D14: Python until a
  profile says otherwise; a Rust/PyO3 hot-path core is the escape hatch).
- **Vector/graph DB** — selectable behind the existing graph interface, at a scale
  trigger (D14: embedder before DB — now satisfied).
- **API embedder** — another `EmbeddingModel`, if a hosted cold model is wanted.
- **Sensorium** — the afferent sensor catalogue + efferent intent set, an event
  wire-schema, and an ingress API (chat, logs, network, filesystem).
- **Skills / procedural memory** — how-to that consolidates from repeated action,
  distinct from the associative (declarative) graph.

## Always

- Keep `decisions.md` current; tune `config.py` empirically.
- Guard against the zombie (CLAUDE.md principle 6): if it never surprises you,
  something is wrong. New behaviour gets a fidelity test that asserts *meaning*,
  not mechanism.
