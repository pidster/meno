# Operating a Meno instance

How to **build**, **configure**, and **start** a running Meno — and the safety
posture that governs it. This is the operator's guide; for *what lives on disk* see
[`instance-layout.md`](instance-layout.md), and for *why* any choice was made see
[`decisions.md`](decisions.md).

A Meno is two things kept apart on purpose (decision **D21**):

- the **image / package** is the *type* — the code, pinned dependencies, baked model
  weights. Every instance of a given image is the same *kind* of thing.
- the **instance home** is the *identity* — `substrate/` (the self), plus the
  Library, config, journal, and runtime state. One home = one Meno.

Secrets are **never** stored in the home. Adapters name an environment variable
(`ANTHROPIC_API_KEY`, `SLACK_BOT_TOKEN`); the value is resolved at runtime.

> Requires **Python 3.11+** (stdlib `tomllib`; decision **D22**).

---

## 1 · Build / install

### From source (development)
```bash
git clone … meno && cd meno
uv sync --extra dev --extra anthropic --extra slack   # extras optional; uv.lock pins them (D30)
uv run python -m pytest -q                             # the offline suite
```
`uv` (the fast resolver/installer) is preferred — it reads the committed `uv.lock` for a
reproducible graph and resolves in milliseconds. Plain `pip` still works if you prefer:
`python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev,anthropic,slack]"`.

Extras (all optional — the core runs offline with no dependencies):

| extra | brings | needed for |
|---|---|---|
| *(none)* | stdlib only | the offline loop (stub cognition + hashing embedder) |
| `anthropic` | the Anthropic SDK | **real cognition** (Haiku/Sonnet/Opus) |
| `local` | `sentence-transformers` (pulls torch) | a **real local embedder** |
| `slack` | `slack_sdk` | the **Slack** channel |

Installing the package puts a `meno` command on the path (`[project.scripts]`).

### As a container (the deployment target, D21)
```bash
podman build -t meno:latest -f Containerfile .    # or: docker build …
```
The build is **multi-stage + uv** (D30): a uv builder resolves the frozen `uv.lock`
into a venv (the anthropic+slack install takes ~1s, where the old pip path timed out),
and only that venv is copied into a clean `python:3.13-slim` runtime — no uv, no build
tools, no caches in the final image. The image carries the code and dependencies (the
*type*); the home is a mounted volume (the *identity*). It runs **non-root**, with **no
instance identity baked in** (`.dockerignore` excludes `.env`, `*.key`, `*.pem`). To
bake the local embedder weights so a running instance never does a cold download,
uncomment the `[local]` block in the `Containerfile`.

### Try it without an instance (the offline demo)
```bash
python -m meno                 # a scripted run of the whole loop, offline
python -m meno --interactive   # feed stimuli; commands: dream | recall <q> | snapshot | quit
```

---

## 2 · Create an instance home

```bash
meno init ~/.meno/meno-pid --handle meno-pid
```

This scaffolds the home (idempotent — it never overwrites your `meno.toml`, a grown
library, or adapter config):

```
~/.meno/meno-pid/
├── meno.toml              # the config you edit (below)
├── substrate/             # THE SELF — the graph; the only identity-bearing dir
├── library/               # reference: self-model + seed dictionary/thesaurus
├── adapters/              # channel enable-flags
├── skills/  journal/  run/
└── .gitignore
```

`handle` is just an addressable name (for logs / Slack), **not** identity — the self
arises from `substrate/`.

---

## 3 · Configure (`meno.toml`)

Operator-edited, read with stdlib `tomllib`. The kernel never writes it. A typo in a
key or a wrong-typed value is a **loud startup error**, not a silent default.

```toml
[instance]
handle = "meno-pid"

[cognition]                  # the cost-graded tiers map to Haiku / Sonnet / Opus
provider = "stub"            # "stub" (offline, default) | "anthropic" (real)
effort   = "low"             # synthesise effort: low | medium | high
strict   = false             # if true, abort an accumulation run on cognition degradation

[embeddings]
kind = "hashing"             # "hashing" (offline) | "split" (cheap hot + local cold) | "local"

[driver]
dream_every     = 8          # consolidate every N cycles
sense_every     = 1          # poll channels every N cycles
heartbeat_ticks = 8          # quiet-phase initiative per cycle

[egress]                     # D21: deny-by-default outbound allowlist — gates ALL network
allow = []                   # e.g. ["slack.com", "*.slack.com"]

[config]                     # overrides onto any Config field (lifetime bounds, decay, …)
# bus_log_max = 4096
```

**Secrets** are supplied as environment variables, never in `meno.toml`:

```bash
export ANTHROPIC_API_KEY=…   # real cognition (with provider = "anthropic")
export SLACK_BOT_TOKEN=…     # the Slack channel
```

With `provider = "anthropic"` but **no key present**, Meno falls back to the offline
stub rather than failing — safe by default.

**Egress** is the network safety boundary: an empty `allow` denies all outbound; a
host (or `*.suffix`) must be listed for any adapter to reach it. This is enforced
**before** any send, on every path — it exists before Meno has any reach.

---

## 4 · Start

```bash
meno run    ~/.meno/meno-pid           # the daemon — runs until SIGINT/SIGTERM
meno run    ~/.meno/meno-pid --cycles 50   # bounded, deterministic (a one-shot)
meno status ~/.meno/meno-pid           # print run/status.json (cycles, nodes, real_fraction…)
```

The daemon:

- **persists the substrate** to `substrate/graph.json` periodically and on shutdown —
  a restart resumes where it left off (*sleep, not amnesia*; D12);
- holds an **advisory lock** (`run/instance.lock`) so two daemons can't corrupt one
  substrate;
- writes telemetry to `run/status.json`.

`meno run` (unbounded) uses the background loop with an off-thread worker so a slow
outward call never blocks cognition; `--cycles` uses a deterministic single-thread
loop for one-shots and tests (decision **D27**).

### In a container
```bash
podman run --rm \
  --read-only --cap-drop=ALL --security-opt no-new-privileges \
  -u 10001:10001 --tmpfs /tmp \
  -v $HOME/.meno/meno-pid:/home/meno/.meno/meno-pid:Z \
  -e ANTHROPIC_API_KEY -e SLACK_BOT_TOKEN \
  meno:latest run /home/meno/.meno/meno-pid
```
Read-only rootfs, dropped capabilities, non-root user, the home as the only writable
mount, secrets injected as env. The container's network policy is the infrastructural
half of the egress boundary; `meno.toml [egress]` is the in-app half.

---

## 5 · Channels — Slack

> **Creating the Slack app** (manifest, scopes, setup): see [`slack-app.md`](slack-app.md).

Meno reaches the world through **adapters** (the `meno_adapters` package; the network
SDKs live there, never in the kernel). Slack is the first channel, in two halves:

- **Afferent (listen)** — messages from *listed-and-joined* channels become percepts,
  bounded and consented: only channels the bot has joined *and* you listed; secrets/PII
  redacted before they enter memory; the bot's own posts skipped; size/rate caps.
- **Efferent (post)** — outward action is a different risk class, so it is **opt-in and
  gated** at every layer: `enabled = false` by default; a `post_channels` scope; a rate
  limit; the egress allowlist; and **confirm-first** — Meno cannot self-approve, an
  out-of-band operator step approves each post. Every decision is audited to
  `journal/traces/`.

> **Default = silence.** Nothing is posted until *all* of: `SLACK_BOT_TOKEN` is set,
> the efferent is `enabled = true` with a `post_channels` scope, and (unless you turn
> it off) each post is confirmed.

### Status of the wiring (read this)
`meno run` attaches the channel from `adapters/slack.toml` automatically — it is OFF
until you enable it there:

```toml
# adapters/slack.toml
[afferent]                            # what it SENSES
enabled  = true
channels = ["C_MENO", "C_DESIGN"]     # channel IDs — must be joined too

[efferent]                            # what it may DO — gated, off by default
enabled       = false                 # outward action is opt-in
post_channels = ["C_MENO"]            # may post ONLY here
confirm       = true                  # confirm-first: each post needs operator approval
rate          = "5/min"
# slack.com MUST also be in meno.toml [egress] for any post to leave the box
```

Then `meno run <home>` builds the instance and wires the enabled adapters; it reports
what it attached (`adapters=['slack']`). Sense-only is the safe first step —
`[afferent].enabled = true` with `[efferent].enabled = false` lets Meno *hear* Slack
and post nothing. The bot token is supplied as `$SLACK_BOT_TOKEN`; with no token the
adapter is inert.

> **The kernel stays adapter-blind.** `meno/` never imports the integration layer;
> the `meno` entrypoint is a *composition root* (`meno_adapters/cli.py`) that wires the
> kernel and the adapters together. A test enforces that no kernel module imports
> `meno_adapters`.

### External knowledge authorities (K3)
`adapters/knowledge.toml` enables a network lookup authority consulted when the
Library misses a factual lookup. Its `hosts` must also be in `meno.toml [egress]`; the
result re-enters as reference (never encoded as experience) and is curated back so a
repeat is a local hit. The live web/MCP client is the one deferred piece — with none
configured, a miss is honest.

---

## 6 · Safety model, at a glance

| Control | Where | Default |
|---|---|---|
| Outward action (posting) | `adapters/slack.toml [efferent] enabled` | **off** |
| Per-post approval | confirm-first; `confirm = true` | **on** |
| Where it may post | `post_channels` scope | empty (refuse all) |
| Outbound network | `meno.toml [egress] allow` + container netpolicy | deny all |
| Secrets | env vars only, never in the home | — |
| World-text hygiene | redaction of secrets/PII before a percept (best-effort, D26) | on |
| Self-echo | own posts dropped on re-read; `self_echo_fraction` guard | on |
| Single writer | `run/instance.lock` | enforced |
| Continuity | substrate persisted; restart resumes (D12) | always |

Real cognition needs `ANTHROPIC_API_KEY`; real Slack needs `SLACK_BOT_TOKEN`; the
container path needs a runtime (podman/docker). Without them, Meno runs offline and
silent by design.
