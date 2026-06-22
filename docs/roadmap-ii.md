# Roadmap II — Self-Knowledge, Transactive Memory, and Reach

Realisation (R0–R5, merged to `main`) made Meno **particular**: it accumulates
experience and becomes a non-substitutable self, verified against the zombie test.
This chapter moves from *being* particular to **knowing itself**, **knowing what
it doesn't know**, and **reaching into the world** — sequenced so that what a Meno
*is* and *can do* is settled before it acts on others.

## Principles (carried forward, non-negotiable)

- **Type ≠ identity.** A Meno is a *kind* of thing; the identity is an instance's
  and arises from the substrate. The prompt/config may describe the type; it must
  never assert instance identity.
- **Mechanics, not meaning.** Self-knowledge describes how a Meno operates. It
  never plants conclusions, values, or affect — those are earned in the graph.
- **Episodic ≠ semantic.** The substrate is for experience (idiosyncratic,
  reconstructive, forgetful). Reference knowledge is external (stable, indexed,
  queryable). Don't confuse them; don't let lookup supplant the self.
- **The gate.** Every phase: a runnable working slice + failing-then-passing
  fidelity tests + a 5-lens adversarial review before advancing. No advancing over
  an open P0. The `adversarial-design-review` skill is the review frame.
- **The standing guard.** The zombie suite holds across every phase: a stub must
  still read *zombie*; a same-input twin must still *diverge*. Any change that
  narrows divergence has leaked identity into text/config — back it out.

## Priority tree

```
NOW ── S   Self-Model  (type, not identity)            small · foundational
          │
          ▼
P1 ──── K   Transactive Memory & Reference             identity-defining · local
          ├── K1  The Library (reference memory type)
          ├── K2  Know-when-to-look-up (lookup = outward curiosity)
          └── K3  External authorities ───┐ (needs network → executes in I)
          │
          ▼
P2 ──── I   Reach / Integrations                       network · outward action
          ├── I0  Async + integration substrate
          ├── I1  Afferent channels (Slack/Discord — sense)
          └── I2  Gated effectors (act; + K3 lookups)

⟂  B   Backlog / hardening (opportunistic, not phase-gated)
```

---

## S — Self-Model

**Goal.** Each tier knows what a Meno is and how it operates, with zero
instance-identity content.

**Design.**
- `_MENO_SELF` — a fulsome *type* description: associative, reconstructive memory;
  tiered forgetting → islanding → rediscovery; the mode repertoire + default-mode
  loop + dream; curiosities decay / impulses build pressure; and the transactive
  stance ("your graph is for experience and may have islanded a fact — look facts
  up rather than trust a faded memory"). Mechanics only.
- **Depth-scaled** (decided): reflexive tiers (`appraise`, `relate` — Haiku) get
  `_MENO_SELF_BRIEF` + a pointer ("your full self-model exists; if a percept needs
  it, that is a reason to escalate, not to reason here"). Deep tiers (`associate`,
  `synthesise`, `wonder`) get the full version.
- **True to the implementation.** Sourced from the architecture docs +
  `reflection.md`, kept in sync with what the kernel actually does. A self-model
  that misdescribes the substrate makes the agent self-deluded.
- **Cacheable prefix.** The full `_MENO_SELF` is one identical block across the
  deep surfaces — put it first with `cache_control: {ephemeral}`, role line after.
  Caches across a continuous run (clears Sonnet's 2048-token floor; Opus too at
  ≥4096). This is the large shared prefix that finally makes caching worth it.

**Outline.**
1. Draft `_MENO_SELF` (full) and `_MENO_SELF_BRIEF` (abridged), mechanics-not-meaning.
2. Prepend to the five role lines (full vs brief per tier).
3. Add `cache_control` on the shared block; confirm `cache_read_input_tokens > 0`.
4. Sync check: a test/checklist that every capability `_MENO_SELF` claims is one
   the kernel actually has.

**Outcomes.**
- Each surface's system = self-model (full/brief) + role line.
- A test asserts `_MENO_SELF` carries **no identity content** (denylist of
  values/conclusions/affect + the litmus: "would this make two instances with
  different graphs sound the same?").
- Zombie guard holds: stub-with-self-model still scores 0 on synthesis / reads
  zombie; same-input twin still diverges above threshold.
- A live run shows cache hits on the deep tiers.

**Review focus.** Theory Coherence (type≠identity, mechanics≠meaning) + Test/Evidence.

---

## K — Transactive Memory & Reference

**Goal.** Separate reference knowledge from the experiential substrate; let a Meno
know it can look things up, and decide when to.

**Design.**
- **K1 The Library** — a reference store *distinct from the graph*: keyed, stable,
  non-decaying, non-reconstructive (the anti-substrate). Different memory **type**,
  different dynamics — no edge decay, no islanding. Holds the self-model document
  and a seed dictionary/thesaurus. (Long-term home of the full `_MENO_SELF`.)
- **K2 Know-when-to-look-up** — the metacognition "my memory is insufficient /
  this is a fact I shouldn't trust to a possibly-islanded node" routes a curiosity
  **outward**. `wonder()` already returns `{mode: external, action}`; extend the
  action vocabulary from `fs_read` to `define`/`lookup`/`search`. An effector
  resolves the lookup against the Library and re-enters the result as a percept
  tagged `source="reference"` (provenance, like R4's `external` flag) — the
  refreshed fact flows back into cognition.
- **K3 External authorities** — real outside lookups (dictionary API, web,
  MCP). Deferred onto the network substrate in **I**; until then the Library +
  local seed is the authority.
- **Discipline.** Facts/reference → external; experience/perspective/association →
  substrate. The self-model (S) carries this awareness. Guard against becoming a
  lookup machine: substrate-first for experiential prompts; lookup only when the
  percept is factual or memory signals islanded/uncertain (a budget/ratio).

**Outline.**
1. K1: `meno/library.py` — a keyed reference store (`Reference{key, body, source,
   kind}`); save/load; seed with the self-model + a small dictionary/thesaurus.
2. K2: a `lookup` effector + extend `wonder()`/`appraise()` to emit lookup intents
   when warranted; resolve against the Library; re-enter as a provenance-tagged
   percept.
3. Update `_MENO_SELF` (S) with the transactive stance.
4. Tests: an islanded fact gets refreshed via lookup; reference percepts carry
   provenance; the agent prefers substrate for experiential vs lookup for factual
   prompts (discrimination); lookup never becomes the default (budget assertion).

**Outcomes.**
- A Library separate from the graph, with its own non-forgetting dynamics.
- Lookups happen as outward-routed curiosity, returning provenance-tagged facts.
- The agent demonstrably distinguishes "reconstruct from experience" from "look up
  a fact."
- Zombie guard: external knowledge does not flatten particularity — the twin still
  diverges; a Meno's *perspective* still comes from its graph, not the shared library.

**Review focus.** Theory Coherence (episodic≠semantic; transactive memory;
don't-become-a-lookup-machine) + Data/Model Semantics (provenance; the Library's
distinct dynamics; no reference leakage into the identity substrate).

---

## I — Reach / Integrations

**Goal.** Meno senses and acts in real channels, safely.

**Design.**
- **I0 Runtime, async & integration substrate** — the live async driver (the
  long-deferred chunk) + an integration layer **outside** the stdlib kernel
  (network lives there; the kernel stays stdlib and step-driven). MCP is a
  candidate substrate (Slack/Discord MCP are available). Hosts K3's lookups too.
  **Packaging (decision D21):** the instance ships as an OCI image (the type) with
  the home as a mounted volume (the identity), secrets env-injected, healthcheck +
  restart, and the egress policy that gates I2 — landing before I1/I2 so the
  boundary precedes outward action. Rationale and bounds live in `decisions.md` D21.
- **I1 Afferent channels** — Slack/Discord sensors (poll/subscribe → percepts),
  bounded and consented like R4's `FilesystemSensor`: only joined channels;
  rate/size caps; provenance `source="slack"/"discord"`; secret/PII handling.
- **I2 Gated effectors** — the agent's `Kind.INTENT` → real outward actions (post
  a message, answer a DM). **Outward action is a different risk class than
  reading**: confirm-first by default, rate-limited, scoped (which channels it may
  post to), audited. Never autonomous outward action without an explicit,
  scoped allow. K3 external lookups also execute here (they are outward calls).

**Outline** (each a separately-reviewed sub-phase).
1. I0: the integration/async substrate + live driver; run K3 lookups on it.
2. I1: one channel, **sense-only** first; bounds + provenance.
3. I2: gated send on that channel (approval/rate/scope/audit); then the second.

**Outcomes.**
- Percepts flow from a real Slack/Discord channel into the loop.
- Meno can look up external facts (K3) on the network substrate.
- Meno acts outward only through gated, rate-limited, audited effectors with
  confirm-first.
- The kernel stays stdlib; all network/async lives in the integration layer.

**Review focus.** User-Intent/Safety (consent, outward-action gating, rate/scope,
audit trail) weighted highest + Runtime Feasibility (async, failure paths, no
busy-spin, bounded). Sending into the world is the highest-stakes thing Meno does.

---

## B — Backlog / hardening (opportunistic, not gated)

- **Indexing/ANN** for `spread`/`similar` once a measured profile says the O(nodes)
  cost bites (the deferred scale trigger; embedder-before-DB satisfied).
- **Vector/graph DB** selectable behind the existing graph interface, at a scale
  trigger (D14 — only after a profile says the in-process store is the bottleneck).
- **API embedder** — another `EmbeddingModel`, if a hosted cold model is wanted.
- **R4 sensor**: a content-aware secret scan (not just name-based); a
  trust-meaningful `external` provenance (operator-chat vs ingested world-text).
- **novelty mark**: replace the curiosity-text proxy with reflection-text novelty
  on live runs (non-core, but the proxy is thin).
- **Merges rarely fire naturally** (single-stream synthesis carries it): decide
  whether to tune toward more cross-stream convergence or accept it.
- **Live-embedder threshold tuning** against real sentence-transformer weights.

---

## Open decisions (for Pid)

- **Self-model home long-term:** inline constant (S) vs Library entry (K1).
  *Recommend: inline now in S, relocate to the Library in K1.*
- **First external authority:** local dictionary/thesaurus seed vs a web/definitions
  API vs MCP. *Recommend: local seed first (no network); real authorities on I0.*
- **First integration:** Slack or Discord — and **sense-only before any send**.
- Depth-scaling — *already decided* (abridged+pointer reflexive, full deep).

## Non-goals / guards

- No instance-identity in any prompt or config (type only).
- No autonomous outward action without an explicit, scoped allow.
- Reference lookup augments the experiential substrate; it never supplants the self.
- The zombie suite remains the standing acceptance guard across all phases.
