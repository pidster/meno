# Meno Instance — Filesystem Layout

This describes the on-disk **home of one Meno instance** — the runtime/persistent
footprint of a living Meno. It is distinct from the *source repo* (the `meno/`
package): the repo is the kind of thing; an instance home is one of the things.
One Meno = one home directory; multiple instances each have their own home (and
may share a substrate by pointing at a common one — multi-instance, D15).

Bind a runtime to a home with `Meno(workspace=<home>)`; `save`/`load` read and
write under it. Conventionally a persistent instance lives at `~/.meno/<handle>/`,
or any path you pass. `meno init <path>` scaffolds the layout from templates.

When containerised (decision D21), this home is the **mounted volume** — the image
is the *type* (code + deps + weights), the home is the *identity*. Only
`substrate/` makes the instance itself, which is exactly the volume boundary.

```
<meno-home>/
├── meno.toml                 # instance configuration (operator-edited)
├── substrate/                # THE SELF — idiosyncratic, reconstructive, forgetful
│   ├── graph.json            # cold graph (nodes, edges, reflection cues) + warm tier
│   └── snapshots/            # timestamped graph snapshots (continuity / rollback)
│       └── 2026-06-22T....json
├── library/                  # REFERENCE — stable, indexed, non-forgetting (≠ substrate)
│   ├── self-model.md         # the full _MENO_SELF: what a Meno is + how it operates
│   ├── index.json            # keyed index over the library (lookup by term/key)
│   ├── dictionary/           # seed definitions
│   ├── thesaurus/            # seed synonyms
│   └── references/           # other curated reference entries (facts, docs)
├── skills/                   # AGENT SKILLS the instance can load (progressive disclosure)
│   ├── <skill-name>/
│   │   ├── SKILL.md          # name + description frontmatter, then the body
│   │   └── ...               # scripts/resources the skill references
│   └── authored/             # self-authored skills (COMPILE output) vs human-authored above
├── adapters/                 # SENSORIUM (afferent) + EFFECTORS (efferent) — the reach layer
│   ├── adapters.toml         # which adapters are enabled, global bounds
│   ├── filesystem.toml       # watched roots, suffix allow-list, size/rate caps (R4 sensor)
│   ├── slack.toml            # channels sensed; channels allowed to post to; scope/rate; creds by ref
│   ├── discord.toml          # same shape as slack
│   └── knowledge.toml        # external authorities (K3): sources, budgets, what's lookup-able
├── journal/                  # OBSERVABILITY — the episodic stream, checkpointed
│   ├── events.jsonl          # bus.log ring, periodically flushed (raw experiential stream)
│   └── traces/               # per-cycle traces, dream reports, decision logs
├── run/                      # RUNTIME state (ephemeral, not the self)
│   ├── instance.lock         # advisory lock for multi-instance coordination
│   └── status.json           # driver telemetry: cycles, dreams, cognition real_fraction, errors
└── .gitignore                # ignores run/, journal/, secrets, and any local creds
```

Secrets are **never stored in the home.** Credentials are referenced by name
(`ANTHROPIC_API_KEY`, `SLACK_BOT_TOKEN`) and resolved from the environment or a
secret manager at runtime. Adapter config holds the *reference*, not the secret.

---

## Areas

### `meno.toml` — configuration
Operator-edited, read via stdlib `tomllib`. The kernel never writes it.

```toml
# meno.toml
[instance]
handle = "meno-pid"          # an ADDRESSABLE NAME, not an identity — the self is the substrate
home   = "~/.meno/meno-pid"  # optional; defaults to this file's directory

[cognition]                  # the cost-graded tiers (maps to TIER_MODELS)
tier1 = "claude-haiku-4-5"   # appraise, relate
tier2 = "claude-sonnet-4-6"  # associate, wonder
tier3 = "claude-opus-4-8"    # synthesise, reconstruct
effort = "low"               # synthesise effort; key resolved from $ANTHROPIC_API_KEY
strict = true                # accumulation runs abort on degradation (R1)

[embeddings]
kind = "split"               # hashing hot + local cold (validated); or "hashing" offline

[driver]
dream_every = 8
sense_every = 1
heartbeat_ticks = 8

[config]                     # overrides onto the Config dataclass (lifetime bounds, decay, etc.)
bus_log_max = 4096
cue_ghost_ttl = 20
# ... any Config field
```

`handle` is the name the world uses to address this Meno (in Slack, logs); it is
**not** identity content. Identity arises from `substrate/`.

### `substrate/` — the self
The durable, idiosyncratic memory: `graph.json` is `persistence.save` output (cold
graph + warm streams). `snapshots/` keeps timestamped copies for continuity and
rollback ("sleep, not death"). This is the *only* directory whose contents make
this instance *this* instance — losing it is amnesia; losing anything else is not.

### `library/` — reference (Roadmap K1)
Reference knowledge, a **different memory type** from the substrate: keyed,
stable, non-decaying, non-reconstructive — and **exact-key** in K1 (fuzzy `search`
needs the cold embedder and is deferred to the backlog, to keep the Library
embedder-free). `self-model.md` is the full `_MENO_SELF`; S loads it through one
accessor from the start, and K1 swaps the backing store to this document without
touching call sites. `index.json` maps keys → entries for lookup. The substrate is
for experience; the library is for facts the agent looks up rather than trusts to a
possibly-islanded memory. A looked-up fact re-enters as a **`Kind.REFERENCE`**
percept (K2) — read into cognition but *never encoded as a graph node*, so
reference can't contaminate the experiential substrate.

### `skills/` — Agent Skills (progressive disclosure)
Each skill is a folder with a `SKILL.md`: frontmatter (`name`, `description`) plus
a body the agent loads only when the description matches the task — the same
convention used elsewhere in this repo. Two sources:
- **Human-authored** (top level) — capabilities given to the instance.
- **`authored/`** — skills the agent COMPILED from its own repeated behaviour
  (procedural memory; distinct from the declarative substrate).

```md
---
name: define-term
description: Look up a precise definition from the library or an external authority. Use when a factual term is needed and memory may have islanded it.
---
# define-term
Resolve <term> against library/dictionary first; if absent and an authority is
configured (adapters/knowledge.toml), look it up, then write the result back to
the library and re-enter it as a `Kind.REFERENCE` percept (read into cognition,
never encoded as an experiential graph node).
```

Note the distinction: the model **surfaces** get the full or brief `_MENO_SELF` as
a *static per-tier constant* (the calls are stateless — there is no mid-call load;
reflexive tiers escalate rather than load — roadmap S). True load-on-demand is the
*Agent Skills* pattern above — a skill body the agent pulls in only when its
description matches the task. The full self-model document lives in `library/` as
the canonical source the S accessor reads, not as something fetched per call.

### `adapters/` — sensorium + effectors (Roadmap I)
Per-adapter config declaring **afferent** (sense) and **efferent** (act) capability
with explicit bounds. Effectors are outward-facing and gated.

```toml
# adapters/slack.toml
[afferent]                   # what it SENSES
enabled  = true
channels = ["#meno", "#design"]   # only joined, listed channels
rate     = "30/min"
redact   = ["secret", "token", "password"]

[efferent]                   # what it may DO — gated, scoped, audited
enabled       = false        # off by default; sending is a different risk class
post_channels = ["#meno"]    # may post ONLY here
confirm       = true         # confirm-first unless an explicit allow says otherwise
rate          = "5/min"
credential    = "SLACK_BOT_TOKEN"   # a REFERENCE; the secret is in the environment
```

```toml
# adapters/knowledge.toml — external authorities (Roadmap K3)
[authorities]
dictionary = { kind = "local", path = "library/dictionary" }
web        = { kind = "mcp",   server = "web-search", enabled = false }
budget     = "20/cycle"      # coarse volume backstop; the real guard is the
                             # supplantation ratio (K2): of cues that COULD be
                             # reconstructed from the substrate, the fraction
                             # routed to lookup instead must stay under threshold
```

### `journal/` and `run/`
`journal/` checkpoints the episodic stream (`events.jsonl` — the bus.log ring) and
traces (dream reports, decisions) for observability; it is *not* the self (the
durable trace is the graph). `run/` holds ephemeral runtime state — the
coordination lock and live driver telemetry/status.

---

## Formats (stdlib-aligned)

- **Operator config** (`meno.toml`, `adapters/*.toml`): TOML, **read** via stdlib
  `tomllib` (Python 3.11+, the floor — decision D22). The kernel never writes
  config; `meno init` ships templates. Comments and human editing are the point.
- **Machine state** (`substrate/graph.json`, `library/index.json`,
  `run/status.json`, `journal/*.jsonl`): JSON / JSON-lines, read+write stdlib.

No new runtime dependency: `tomllib` is stdlib on 3.11+ (D22), so the kernel stays
stdlib-only; network lives in the integration/adapter layer (Roadmap I0a),
not in the kernel that reads this home.

---

## Lifecycle

1. `meno init <home>` scaffolds the tree from `templates/instance/`, writing a
   starter `meno.toml`, empty `substrate/`, a seeded `library/` (self-model +
   minimal dictionary/thesaurus), and disabled adapter stubs.
2. `Meno(workspace=<home>)` binds; first run seeds the graph; `save` writes
   `substrate/graph.json` (+ a `snapshots/` copy).
3. Skills, library entries, and adapter config grow over the instance's life;
   `authored/` skills appear as the agent COMPILEs its own procedures.

## Mapping to Roadmap II

| Area | Roadmap phase |
|---|---|
| the `_MENO_SELF` block + per-tier full/brief pattern | **S** Self-Model |
| `library/`, `library/self-model.md`, `index.json` (the reference store) | **K1** The Library |
| lookup effector, `define-term` skill, the transactive mechanics in `_MENO_SELF` | **K2** Know-when-to-look-up |
| `adapters/knowledge.toml` schema (network authorities) | **K3** External authorities (executes after I0) |
| the adapter seam (afferent + off-thread efferent contract) | **I0a** Integration substrate |
| `meno init`, `meno.toml` loader, daemon, the OCI image (D21/D22) | **I0b** Daemon & image |
| `adapters/slack.toml` / `discord.toml` afferent | **I1** Afferent channel (sense only) |
| `adapters/*.toml [efferent]`, audit traces, the self-echo guard | **I2** Gated effector |
| `substrate/`, `run/status.json`, `journal/` | already realised (R0–R5) |

## Guards

- Only `substrate/` carries identity; everything else is type, reference, config,
  or runtime — replaceable without changing *who* the instance is.
- Secrets are referenced, never stored in the home; `run/`, `journal/`, and any
  local credential files are gitignored.
- Effectors (`adapters/*.toml [efferent]`) are disabled by default and gated when
  enabled — outward action is opt-in, scoped, rate-limited, and audited.
