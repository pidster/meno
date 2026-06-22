# Roadmap II — Self-Knowledge, Transactive Memory, and Reach

Realisation (R0–R5, merged to `main`) made Meno **particular**: it accumulates
experience and becomes a non-substitutable self, verified against the zombie test.
This chapter moves from *being* particular to **knowing itself**, **knowing what
it doesn't know**, and **reaching into the world** — sequenced so that what a Meno
*is* and *can do* is settled before it acts on others.

Each phase below is one `/goal` unit: a named working slice, failing-then-passing
fidelity tests with **assertable** outcomes, explicit entry/exit, and a 5-lens
adversarial review before advancing. Phases are sized like R0–R5 (one runnable
slice each), not like chapters.

## Principles (carried forward, non-negotiable)

- **Type ≠ identity.** A Meno is a *kind* of thing; the identity is an instance's
  and arises from the substrate. The prompt/config may describe the type; it must
  never assert instance identity.
- **Mechanics, not meaning.** Self-knowledge describes how a Meno *operates*. It
  never plants conclusions, values, affect, or dispositions — those are *earned* in
  the graph. A *stance* ("distrust faded memory") is not a mechanic even when
  phrased as procedure; it ships only once the capability it names is real, and
  only as mechanics ("a `lookup` route resolves a factual curiosity"), never as
  prescription. The denylist tests for **prescriptive mood** (should / prefer /
  distrust / matters-more / I-feel), not just affect vocabulary.
- **Episodic ≠ semantic.** The substrate is for experience (idiosyncratic,
  reconstructive, forgetful) — it is the self. Reference knowledge is the self's
  *self-managed, curated shelf* (stable, indexed, queryable; D25) — a tool the self
  manages, not the self, and not external-only. Don't confuse them (experience stays
  in the substrate, reference in the Library); don't let lookup supplant the self.
- **The gate.** Every phase: a runnable working slice + failing-then-passing
  fidelity tests + a 5-lens adversarial review before advancing. No advancing over
  an open P0. The `adversarial-design-review` skill is the review frame.

### The standing guard (two axes, two costs)

The zombie suite holds across every phase — but it measures the substrate, so a
**same-input twin diverging** is invariant to prompt/config changes and is *blind
to S and K* (where the leak risk is prompt-driven *convergence*, not substrate
divergence). The guard therefore has two axes:

- **Divergence (substrate).** `divergence(twin_a, twin_b) ≥ PASS['divergence']` —
  the inherited mark. Catches identity leaking into the *graph*.
- **Anti-convergence (prompt/config).** Two instances with **genuinely different
  graphs**, run over the *same* percepts with the full `_MENO_SELF`/Library
  installed, still produce divergent *outputs*:
  `divergence_under_self_model(meno_a[graph_X], meno_b[graph_Y], shared_percepts)
  ≥ threshold`. Catches a self-model or shared Library homogenising voice. This is
  the executable form of S's litmus ("would two different-graph instances sound the
  same?"). **New mark — add to `meno/aliveness.py`.**

And two costs:

- **Per-phase (offline, no key):** run `tests/test_aliveness.py` with
  `StubModelProvider` and `cognition_real=False`; assert `verdict != 'alive'`
  (stub still reads zombie) and both divergence axes hold. Cheap; runs on every
  `/goal`.
- **At gates (live, funded key):** the full `meno.zombie_run` real-cognition life
  runs **only at the K-exit and I-exit gates**, logged to evidence — not per
  sub-phase.

## Priority tree (8 phases)

```
NOW ── S    Self-Model (mechanics only; stance earned, not given)   small · foundational
          │
          ▼
P1 ──── K1  The Library (reference memory type)                     local · stdlib
          │
          ▼
        K2  Know-when-to-look-up (lookup = outward curiosity)       local · effector seam
          │   └─ K3 External authorities — DEFERRED into I (needs network)
          ▼
P2 ──── I0a Integration substrate (adapter seam; no network)        local · stdlib
          │
          ▼
        I0b Daemon + meno init + OCI image (D21, D22)               infra · container
          │
          ▼
        I1  Afferent channel (Slack/Discord — sense only)           network · inbound
          │
          ▼
        I2  Gated effector (act; confirm-first, audited)            network · outbound
          │
          ▼
        K3  External authorities (on the I0 network substrate)       network · lookup

⟂  B   Backlog / hardening (opportunistic, not phase-gated)
```

Sequence: `S → K1 → K2 → I0a → I0b → I1 → I2 → K3`. K3 is the only phase that
crosses chapters — it is *designed* in K2 (the lookup vocabulary + the discipline)
but *executed* after I0 gives it a network substrate.

---

## S — Self-Model

**Goal.** Each cognitive tier carries a true, mechanics-only description of what a
Meno *is* and how it *operates*, with zero instance-identity and zero earned
disposition — and the shared block is cacheable.

**Working slice.** `_MENO_SELF` (full) and `_MENO_SELF_BRIEF` (abridged) constants
in `meno/models.py`; a `_system(tier, role_line)` helper that returns the
block-list `[{type:text, text:<self>, cache_control:{type:ephemeral}}, {type:text,
text:<role_line>}]` (full self for deep tiers, brief for reflexive); the five
existing `system=` call sites routed through it.

**Design.**
- `_MENO_SELF` — a fulsome *type* description, **mechanics only**: associative,
  reconstructive memory; tiered forgetting → islanding → rediscovery; spreading
  activation; the mode repertoire + default-mode loop + dream; curiosities decay /
  impulses build pressure. It describes *how the machinery works*, never what to
  conclude from it. **The transactive stance is NOT here** — "look facts up rather
  than trust faded memory" is a disposition and names a capability that does not
  exist until K2; it is added, as mechanics, in K2 (see Open decisions / D-note).
- **Depth-scaled (static, per tier).** Reflexive tiers (`appraise`, `relate` —
  Haiku) get `_MENO_SELF_BRIEF` + a pointer ("your full self-model exists; if a
  percept needs it, that is a reason to escalate, not to reason here"). Deep tiers
  (`associate`, `synthesise`, `wonder`) get the full version. There is no *dynamic*
  load — the surfaces are single stateless calls; "full vs brief" is a per-tier
  constant choice, not runtime loading.
- **True to the implementation.** Sourced from the architecture docs +
  `reflection.md`, kept in sync with what the kernel actually does. A self-model
  that misdescribes the substrate makes the agent self-deluded; a self-model that
  claims a capability the current phase lacks is the same failure.
- **Cacheable prefix.** The full `_MENO_SELF` is one identical block across the
  deep surfaces — first, with `cache_control: {ephemeral}`, role line after. The
  deep tiers run on **Opus** (`synthesise`, 4096-token floor) and **Sonnet**
  (`wonder`, 2048); the reflexive tiers run on **Haiku** (4096). To cache on the
  deep tiers at all, `_MENO_SELF` must clear **≥4096 tokens** measured with
  `count_tokens` against Opus. *Cache value is not a reason to grow the block* —
  if real mechanics don't reach 4096 tokens, the deep-tier cache outcome is simply
  unmet; do not pad with filler (that reintroduces meaning-as-text).

**Outline.**
1. Draft `_MENO_SELF` (full) and `_MENO_SELF_BRIEF` (abridged), mechanics-only.
2. Add `_system(tier, role_line)` building the block-list; route all five
   `system=` sites (`appraise`, `relate`, `synthesise`, the inline `relate`,
   `wonder`) through it. (This restructures `system=` from plain string to content
   blocks — required for `cache_control`; it is not a one-line kwarg.)
3. Sync check: a `SELF_MODEL_CLAIMS` token list; a test asserts each claimed
   capability maps to a real kernel symbol available **in this phase**, and fails
   if `_MENO_SELF` references `lookup`/`define`/Library (absent until K2).
4. Token-floor gate: assert `count_tokens(_MENO_SELF, model=opus) >= 4096` (or the
   cache outcome is explicitly marked unmet and deferred, not silently passed).

**Outcomes (assertable).**
- *Content present.* For each of the five surfaces, the captured `system=` block
  list begins with the correct self block: `assert _MENO_SELF in deep_system` /
  `assert _MENO_SELF_BRIEF in reflexive_system and "escalate" in reflexive_system`
  (monkeypatch the SDK client; inspect the captured `system` argument).
- *No identity, no disposition.* `assert not any(tok in _MENO_SELF.lower() for tok
  in IDENTITY_DENYLIST)` where the denylist covers first-person preference verbs
  and **prescriptive mood** (should/prefer/distrust/value/matters-more/I-feel).
  The litmus "two different-graph instances sound the same?" is **panel-judged**
  (a named review lens), not machine-computed here — flag it as such so the run
  doesn't loop trying to compute it.
- *True-to-implementation.* The `SELF_MODEL_CLAIMS` sync test is green; a claim
  with no current-phase kernel referent fails the build.
- *Standing guard (offline).* Stub-with-self-model still reads `zombie`; both
  divergence axes hold (the anti-convergence mark is introduced here).
- *Caching (live, S-exit smoke).* The request built for each deep tier carries
  `cache_control:{type:ephemeral}` on the shared block (offline-assertable on the
  built payload). A funded-key smoke run logs `cache_read_input_tokens > 0` on the
  deep tiers to `run/status.json` — gated like R1's live tests, not a unit test.

**Entry.** Now (no deps). **Exit.** All five surfaces carry the correct self block;
denylist + sync-check + token-floor tests green; offline guard holds; S-exit cache
smoke logged (or cache explicitly deferred with reason).

**Review focus.** Theory Coherence (type≠identity, mechanics≠meaning, stance-not-
shipped) + Test/Evidence.

---

## K1 — The Library (reference memory type)

**Goal.** A reference store distinct from the graph: keyed, stable, non-decaying,
non-reconstructive — the anti-substrate.

**Working slice.** `meno/library.py` — `Reference{key, body, source, kind}`, a
`Library` with `get(key)` / `put(ref)` / save+load to `library/index.json`, seeded
with the self-model document + a small dictionary/thesaurus. **Exact-key lookup
only** (no fuzzy `search` — that needs the cold embedder and is deferred; see B).

**Design.**
- A different memory **type**, different dynamics: no edge decay, no islanding, no
  reconstruction. A Library entry recalled twice is byte-identical (the substrate's
  opposite).
- **The self's self-managed shelf (D25).** The Library is not the self (the substrate
  is) and not external-only — it is reference material the self *curates*. So the
  boundary is by **content kind, not authorship**: write-back accepts the reference
  kinds (`definition`/`fact`/`reference`) from any provenance, including the agent's
  own curation, and rejects only experience/reflection/perspective (those are the
  substrate). **Boundary enforced, not asserted:** the Library is never an entry point
  for spreading activation, its entries never appear in `graph.cues`, and the aliveness
  marks read the graph not the Library — so curating the shelf can never manufacture a
  self.
- Holds a **lookup-able copy** of the full `_MENO_SELF` so the agent can look up its
  own self-model (K2). Its canonical home stays the **code constant** — the
  self-model is the *type* (D21: image = type), so it is baked in the image, never
  served from the mutable instance home; the Library copy is seeded from the constant
  and never overrides it (**D24**). On load the copy is re-derived from the constant
  so it can't go stale across an image upgrade.

**Outline.**
1. `meno/library.py`: the keyed store + save/load + seed (incl. the self-model copy).
2. Seed the Library from the `MENO_SELF` constant; `self_model()` keeps reading the
   constant (the type). The accessor stays the single read-seam.
3. Boundary tests (below).

**Outcomes (assertable).**
- *Non-decay contrast.* After N decay cycles a Library entry is byte-identical; a
  graph edge of the same age has decayed. `assert library.get(k).body == seed_body`
  after N cycles `and graph.edge(a,b).weight < initial`.
- *Not a memory.* `recall(q)` can never return a Library entry as `reconstructed`
  or `ghost`; `assert all(e not in graph.cues for e in library)`.
- *Write-back guarded.* `library.put(ref_with_kind='reflection')` is rejected;
  `kind ∈ {definition, fact, reference}` with external provenance is accepted.
- *Standing guard (offline).* Both divergence axes hold with the Library present.

**Entry.** After S (self-model accessor exists). **Exit.** Library store +
boundary tests green; the Library holds a re-derivable copy of the self-model (the
constant stays canonical, D24); offline guard holds.

**Review focus.** Data/Model Semantics (the Library's distinct dynamics; no
reference leakage into the identity substrate) + Theory Coherence (episodic≠semantic).

---

## K2 — Know-when-to-look-up (lookup as outward curiosity)

**Goal.** A Meno routes a factual/uncertain curiosity **outward** to the Library,
re-enters the result as reference, and demonstrably distinguishes
reconstruct-from-experience from look-up-a-fact — without becoming a lookup machine.

**Working slice.** Extend the existing effector seam (it already exists —
`Effector` in `meno/processors.py:183` consumes `Kind.INTENT`): add a `lookup`
branch resolving against the Library and re-entering the result; extend `wonder()`'s
action vocabulary from `fs_read` to `{define, lookup, search}`; add the transactive
*mechanics* paragraph to `_MENO_SELF` (now that the capability is real).

**Design.**
- **The substrate-contamination guard is the core work, not an afterthought.** A
  looked-up fact re-entered as `Kind.FEEDBACK` is encoded as a graph node by
  `Appraiser.ENCODE = (SENSE, FEEDBACK)` (processors.py:37), mislabeled as the
  agent's own thought (`external=False`). That violates episodic≠semantic on the
  *default* path. Fix: a new **`Kind.REFERENCE`** excluded from `ENCODE` (preferred)
  *or* a `source=="reference"` encode-skip in `Appraiser`. A reference may *inform*
  cognition (be read in the working set) without being *encoded* as experience.
- **Action vocabulary.** *As-built:* the real `wonder()` returns
  `{mode, thought, action, target}` where `action ∈ {none, lookup, fs_read}` and
  `target` is the key (lookup) or path (fs_read); it builds the dispatch dict
  `{action: "lookup", key}` / `{action: "fs_read", path}`. Validation: an
  external/both route needs `action != none` and a `target`. `Effector.triggers`
  extended to `fs_read/fs_write/lookup/define` so a lookup intent is dispatched, not
  dropped (`define` is dispatch-capable; the model emits `lookup`).
- **Stub routing.** The offline stub routes `wonder` by sniffing for `/`
  (models.py:96); top-down curiosities never look like paths, so `lookup` never
  fires offline. Add a "looks-factual" heuristic to the stub so the offline suite
  can exercise K2.
- **Don't-become-a-lookup-machine — measured as supplantation, not volume.** *As-
  built:* substrate-first routing in `_discharge_curiosity`. A factual curiosity
  consults memory first (`recall()` band): a **reconstructed** result (≥0.33) is
  reconstructed, not looked up (suppressed); a **ghost** (0.18–0.33) is reconstructed
  AND corroborated by lookup (mode `both`); only `none` looks up alone. The
  `supplantation_ratio` = of curiosities a genuine reconstruction could serve, the
  fraction looked up anyway — ~0 with the guard on, and **falsifiable** (toggle
  `cfg.substrate_first_lookup` off → it spikes to 1, so the metric isn't a tautology).
  Ghost-corroboration is not counted as supplantation (memory was reconstructed too).
- **Transactive stance enters here, as mechanics.** Append to `_MENO_SELF`: "a
  `lookup` route resolves a factual curiosity against the Library and re-enters the
  result tagged `reference`" — describing the capability, never prescribing distrust.

**Outline.**
1. `Kind.REFERENCE` (or encode-skip) so re-entered facts are not encoded as
   experience.
2. `lookup` branch in `Effector.run`; extend `Effector.triggers`.
3. Extend `wonder()` action vocabulary + validation; add the stub "looks-factual"
   branch.
4. Append the transactive mechanics paragraph to `_MENO_SELF`; re-run S's
   sync-check (the `lookup` claim now has a referent).
5. Tests (below).

**Outcomes (assertable).**
- *Discrimination (the keystone).* Fixture — `experiential="how do i feel about
  forgetting"`, `factual="what is the definition of entropy"`. After the factual
  curiosity: an INTENT with `payload['action'] == 'lookup'` is emitted (the action is
  a string, dispatched by the Effector) and graph reconstruction is not the primary
  path. After the experiential curiosity: no lookup INTENT — the path is an internal
  thought / substrate reconstruction. (`define` is dispatch-capable but the model
  emits `lookup`; `search` is deferred to the backlog — needs the cold embedder.)
  *As-built (shipped):* the discrimination is exercised offline via the stub's
  `looks_factual` heuristic (the routing seam); the real-cognition judgment is the
  K-exit live gate.
- *Provenance.* The re-entered percept has `kind == Kind.REFERENCE` (or
  `payload['source']=='reference'`) and `external is True`; a second lookup of the
  same key is a Library hit (`assert library_get_call_count == 1` across two
  lookups).
- *No contamination.* The looked-up fact does **not** become a `graph` node:
  `assert fact_text not in {n.content for n in graph.nodes}`.
- *Not a lookup machine.* `assert lookup_when_reconstructable_fraction < threshold`
  over a mixed run; `assert no lookup fires on a purely experiential percept`.
- *Standing guard.* External knowledge does not flatten particularity — shared-
  Library twins still diverge on both axes; a Meno's perspective still comes from
  its graph, not the Library.

**Entry.** After K1 (Library exists). **Exit.** Discrimination + provenance +
no-contamination + supplantation tests green; `_MENO_SELF` sync-check green with the
new claim; offline guard holds. **K-exit gate:** the full live `meno.zombie_run`
runs once with real cognition; evidence logged; verdict must not be `zombie`.

**Review focus.** Theory Coherence (episodic≠semantic; transactive memory;
don't-become-a-lookup-machine as supplantation) + Data/Model Semantics (provenance;
the encode-skip; no reference leakage into the substrate).

> **K3 (External authorities) is explicitly NOT built here.** Its only K-era
> deliverable is the `adapters/knowledge.toml` schema (`kind = local|mcp`) and the
> local dictionary/thesaurus as the authority. Network lookups are an I0-gated
> follow-on — do not attempt network in the K chapter.

---

## I0a — Integration substrate (adapter seam; no network)

**Goal.** A clean seam by which an external source feeds percepts into the loop,
with the network/async kept *out* of the stdlib kernel — provable before any real
channel exists.

**Working slice.** An `Adapter` base class + an in-memory **loopback adapter** that
pushes a canned percept into the live driver *through the seam* (not via a direct
`driver.feed`). Lives outside the `meno/` kernel package (e.g. `meno_adapters/`).

**Design.**
- The afferent boundary is already clean: `Driver.feed` is thread-safe
  (driver.py:73), sensors poll on the driver thread through a bounded queue. I0a
  formalises that into an `Adapter` contract so I1 (Slack/Discord) is a drop-in.
- **The efferent boundary is the harder half and must be designed now.** The
  existing `Effector` runs *synchronously on the single mind thread*
  (processors.py:192). A network post there would **block the whole mind** for the
  HTTP round-trip. So the outbound contract is hand-off: an `INTENT` enqueues an
  outbound action to an adapter worker; the worker performs the network call off
  the mind thread and returns a `FEEDBACK` via `Driver.feed`. I0a defines this
  contract (with a loopback effector) even though the real network lands in I2.
- **Kernel-purity test.** No module under `meno/` imports a non-stdlib
  network/async package; those imports appear only in the adapter layer.

**Outline.**
1. `Adapter` base (afferent `poll`/`subscribe` → percept; efferent `submit`
   intent → off-thread → `FEEDBACK`).
2. A loopback afferent adapter + a loopback efferent adapter.
3. Kernel-purity import test.

**Outcomes (assertable).**
- *Seam works.* A canned percept enters the loop *through the loopback adapter*;
  `assert it appears in bus.log with the adapter's provenance`.
- *Off-thread efferent.* A loopback `INTENT` is handled without blocking the mind
  thread; `assert the mind processed ≥1 other event during the (simulated) delay`.
- *Kernel stays stdlib.* Walk `meno/*.py` imports; `assert intersection with
  {aiohttp, httpx, requests, websockets, slack_sdk, discord, mcp} == ∅`; assert
  those imports live in the adapter package.

**Entry.** After K2. **Exit.** Seam + off-thread-efferent + kernel-purity tests
green.

**Review focus.** Runtime Feasibility (threading boundary; no busy-spin; bounded;
the efferent hand-off) + Theory Coherence (kernel stays stdlib & step-driven).

---

## I0b — Daemon, `meno init`, and the OCI image (D21, D22)

**Goal.** An instance runs as a home-bound daemon, scaffolded by `meno init`,
packaged as an OCI image with the home as a mounted volume.

**Working slice.** `meno init <home>` (scaffolds the D21 layout from templates); a
`meno.toml` loader (stdlib `tomllib`, D22); a daemon entrypoint
(`[project.scripts]` `meno = ...`) bound to `workspace=<home>` that persists
`substrate/graph.json`, writes `run/status.json`, and checkpoints `journal/`; a
`Containerfile` building the image.

**Design.**
- Today `python -m meno --live` builds an **ephemeral** `tempfile` workspace
  (`__main__.py:155`) and never persists to a home — that is demo, not daemon. I0b
  is the bulk of the I-chapter work and is *non-network* (it precedes I1/I2).
- Per D22: floor is 3.11; `tomllib` reads config; the kernel writes only
  JSON/JSONL. Per D21: image = type (code + pinned extras + baked embedder
  weights); home = mounted volume (the only identity-bearing thing); secrets
  env-injected; non-root, read-only rootfs, dropped caps, and the **egress policy**
  that gates I2 — so the network boundary exists *before* any outward action.

**Outline.**
1. `meno init` + `templates/instance/`.
2. `meno.toml` loader → `Config` overrides; `[project.scripts]` entrypoint; the
   home-bound daemon loop (status.json, journal flush, snapshot on save).
3. `Containerfile`; weights baked; a `podman/docker run` smoke with the home as a
   volume.

**Outcomes (assertable).**
- *Scaffold.* `meno init <tmp>` produces the D21 tree; `assert the expected files
  exist and meno.toml parses via tomllib`.
- *Sleep, not amnesia.* Start the daemon on a home, feed percepts, stop, restart;
  `assert the substrate resumes from the volume` (D12) and `run/status.json`
  reflects cycles/real_fraction.
- *Container boundary.* The image builds; the daemon starts non-root with a
  read-only rootfs; substrate writes land on the **host volume** (restart resumes);
  a connection to a non-allowlisted host is refused by the egress policy.

**Entry.** After I0a. **Exit.** init + loader + daemon + image-smoke tests green.
**External deps flagged (like R1's "needs a model"):** a container runtime +
network are required for the image smoke; skip-not-fail without them.

**Review focus.** Runtime Feasibility + User-Intent/Safety (egress boundary,
non-root, secret handling).

---

## I1 — Afferent channel (Slack/Discord — sense only)

**Goal.** Percepts flow from one real channel into the loop, bounded and consented;
**no effector code merged.**

**Working slice.** One channel's afferent adapter (Slack *or* Discord — sense
first), modelled on R4's `FilesystemSensor` bounds, plugged into the I0a seam.

**Design.** Only joined, listed channels; rate/size caps; provenance
`source="slack"/"discord"`; secret/PII redaction. Mirrors `tests/test_sensorium_r4.py`
assertion shapes (non-joined → no percept; oversized → skipped; secret-pattern →
redacted).

**Outcomes (assertable).** A message in a joined channel becomes a percept with the
right provenance; a non-joined channel yields nothing; oversized is skipped; a
secret pattern is redacted. `assert no efferent/INTENT-send code path is reachable`
in this phase.

**Entry.** After I0b. **Exit.** Afferent bounds tests green (R4 template); no
outbound path exists.

**Review focus.** User-Intent/Safety (consent, bounds, redaction) + Runtime
Feasibility.

---

## I2 — Gated effector (act; confirm-first, audited)

**Goal.** Meno acts outward only through a gated, rate-limited, scoped, audited
effector — and self-authored output cannot masquerade as experience.

**Working slice.** The efferent half of one channel adapter (the I0a off-thread
contract made real): `Kind.INTENT` → a real post, behind the gate.

**Design.**
- **Outward action is a different risk class.** Disabled by default; confirm-first;
  scoped to `post_channels`; rate-limited; every send audited to `journal/traces/`.
  Never autonomous outward action without an explicit, scoped allow.
- **The self-echo guard (new mark).** Once I2 posts, the I1 sensor will read the
  channel *including Meno's own post* and could re-enter it as `source="slack"`
  experience — and `particularity()`/`divergence()` would *reward* the self-echo as
  identity. Tag effector output `source="self:slack"` (or `echo=true`) so the
  afferent sensor recognises and drops/marks it; add a **self-echo-fraction** mark
  to `meno/aliveness.py` that flags echo-inflated particularity rather than
  crediting it.

**Outcomes (assertable).**
- *Default-safe.* With `[efferent] enabled=false`, an `INTENT` to post no-ops:
  `assert no outbound call made`.
- *Confirm-first.* With `enabled=true, confirm=true`, an intent enters a pending
  state and does not send until confirmed: `assert send_called is False before
  confirm, True after`.
- *Scoped & rate-limited.* A post to a channel outside `post_channels` is refused;
  the N+1th send in the window is refused.
- *Audited.* Every send appends a record (channel, content, timestamp) to
  `journal/traces/`.
- *No self-echo inflation.* The agent's own re-read post is dropped/marked;
  `assert self_echo_fraction below the inflation threshold` over a post-then-sense
  cycle.

**Entry.** After I1 (sense-only proven on the channel). **Exit.** All safety
assertions green; self-echo mark green. **I-exit gate:** the full live
`meno.zombie_run` runs once; particularity must not be echo-inflated; verdict not
`zombie`.

**Review focus.** User-Intent/Safety (gating, scope, rate, audit, self-echo)
weighted highest + Runtime Feasibility (the off-thread send, failure paths).

---

## K3 — External authorities (on the I0 network substrate)

**Goal.** Real outside lookups (dictionary API, web, MCP) resolve a factual
curiosity, on the I0 network substrate, through the I2 egress gate.

**Working slice.** A network authority adapter behind `adapters/knowledge.toml`
(`kind = mcp|web`), invoked by the K2 `lookup` action when the Library misses,
executing as an outbound call on the I0a efferent contract.

**Design.** K3's vocabulary and discipline are already built (K2); K3 only swaps the
*local* authority for a *network* one, reusing I2's egress policy and audit. MCP is
a candidate substrate (Slack/Discord/web MCP) — async client in the adapter layer
(≥3.11), never in the kernel.

**Outcomes (assertable).** A Library miss on a factual key routes to the network
authority; the result re-enters as `Kind.REFERENCE` (not encoded as experience),
audited like any outbound call; egress to a non-allowlisted authority is refused;
the supplantation ratio (K2) still holds with network lookups counted.

**Entry.** After I2 (egress gate + off-thread efferent exist). **Exit.** Network
lookup + provenance + egress + supplantation tests green.

**Review focus.** User-Intent/Safety (egress, audit) + Data/Model Semantics
(reference provenance unchanged from K2).

---

## B — Backlog / hardening (opportunistic, not gated)

- **Fuzzy `search` over the Library** — the third lookup verb; needs the cold
  embedder, which pins the Library to that model (D20). Deferred from K1 (which is
  exact-key only) precisely to keep the Library embedder-free until wanted.
- **Indexing/ANN** for `spread`/`similar` once a measured profile says the
  O(nodes) cost bites (the deferred scale trigger; embedder-before-DB satisfied).
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

- **First integration channel:** Slack or Discord — and **sense-only before any
  send** (I1 before I2 is fixed; which channel first is open).
- **First network authority (K3):** dictionary/definitions API vs web vs MCP.
  *Recommend: an MCP authority, reusing the I2 egress gate.*

*Resolved:* depth-scaling (abridged+pointer reflexive, full deep) — decided.
Self-model home — **D24**: canonical in the code constant (the type, baked in the
image); the Library holds a re-derivable copy for lookup, never overriding it.
Config loader / Python floor — **D22** (3.11 + `tomllib`). Self-model scope —
**mechanics only; the transactive stance is earned, added as mechanics in K2.**

## Non-goals / guards

- No instance-identity, and no earned disposition, in any prompt or config (type
  and mechanics only).
- No autonomous outward action without an explicit, scoped allow.
- Reference lookup augments the experiential substrate; it never supplants the self
  (measured as the supplantation ratio, not a volume cap).
- The zombie suite remains the standing acceptance guard across all phases — both
  axes (substrate divergence and prompt/config anti-convergence), cheap offline
  per-phase and live at the K-exit and I-exit gates.
