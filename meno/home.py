"""The instance home: scaffold, config, egress policy, and the home-bound daemon (I0b).

An instance's *home* is its identity-bearing footprint on disk (docs/instance-layout.md,
D21): `substrate/` is the self; `library/`, `skills/`, `adapters/`, `meno.toml` are
reference/config; `journal/`, `run/` are observability/runtime. `meno init <home>`
scaffolds it; `Meno(workspace=home)` binds to it; the daemon runs the loop and
persists the substrate so a restart is sleep, not amnesia.

Config (`meno.toml`) is READ with stdlib `tomllib` (D22, Python 3.11+); the kernel
only ever WRITES JSON/JSONL (machine state), never TOML. Secrets are never stored in
the home — adapters name a credential env var; the value is resolved at runtime.

The **egress policy** is the app-level half of D21's network boundary: a deny-by-
default allowlist of hosts the instance may reach. The integration layer consults it
before any outbound connection, so an outward action (I2/K3) to a non-allowlisted host
is refused — the boundary exists before any send capability does. (The container's
network policy is the other, infrastructural half.)
"""
from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import fcntl                       # POSIX advisory lock (the daemon runs on Linux/macOS)
except ImportError:                    # pragma: no cover - non-POSIX
    fcntl = None

from .config import Config
from .store import make_store

# Directories scaffolded under a home (instance-layout.md). substrate/ is the only
# identity-bearing one — it is the mounted volume's reason to exist (D21).
_DIRS = ("substrate/snapshots", "library/dictionary", "library/thesaurus",
         "library/references", "skills/authored", "adapters", "journal/traces", "run")

_MENO_TOML = """\
# meno.toml — instance configuration (operator-edited; read via stdlib tomllib).
# Secrets are NEVER stored here — adapters name an env var; the value is resolved
# at runtime.

[instance]
handle = "{handle}"          # an ADDRESSABLE NAME, not an identity — the self is the substrate

[cognition]                  # the cost-graded tiers (Haiku/Sonnet/Opus); key from $ANTHROPIC_API_KEY
provider = "stub"            # "stub" (offline, default) | "anthropic" (real, needs a key)
effort = "low"               # synthesise effort
strict = false               # if true, an accumulation run aborts on cognition degradation

[embeddings]
kind = "hashing"             # "hashing" (offline) | "split" (cheap hot + local cold) | "local"

[driver]
dream_every = 8
sense_every = 1
heartbeat_ticks = 8

[egress]                     # D21: deny-by-default outbound allowlist (gates I2/K3)
allow = []                   # e.g. ["slack.com", "www.slack.com"]

[storage]                    # D34: the substrate backend
backend = "file"             # "file" (default): the JSON substrate under this home — right
                             # for a single instance (the mounted volume IS the persistence).
                             # A SurrealDB/vector backend plugs in behind the Store interface,
                             # provisioned as a sidecar (deploy/compose.yaml). Not yet built.

[secrets]                    # D31: secrets are resolved by NAME (env-first), never stored
                             # in cognition or the substrate. Default is env-only.
# file = "secrets.env"       # OPTIONAL read-only dotenv fallback (env still wins). A
                             # relative path resolves against the home (gitignored); use
                             # an absolute path to keep secrets OUTSIDE the home entirely.

[config]                     # overrides onto the Config dataclass (any field)
# bus_log_max = 4096
"""

_GITIGNORE = "run/\njournal/\n*.lock\n.env\n*.env\n*.key\n*.pem\n"

_ADAPTERS_TOML = """\
# adapters.toml — which adapters are enabled. Each adapter has its own file.
[afferent]
filesystem = false
slack = false

[efferent]                   # outward action is opt-in, gated, and behind the egress allowlist
slack = false
knowledge = false            # K3: external lookup authority (network)
"""

_KNOWLEDGE_TOML = """\
# knowledge.toml — external lookup authority (Roadmap K3). Consulted when the Library
# misses a factual lookup. A network call, so it is behind the egress allowlist.
enabled = false              # off by default
kind    = "web"              # "web" | "dictionary" | "mcp"
hosts   = []                 # the authority's host(s) — MUST also be in meno.toml [egress]
# credential = "WEB_SEARCH_KEY"   # a REFERENCE; the secret is in the environment
"""

_SLACK_TOML = """\
# slack.toml — the Slack channel (Roadmap I1/I2). The bot token is in the
# environment ($SLACK_BOT_TOKEN), never here.
[afferent]                   # what it SENSES
enabled     = false
channels    = []             # leave EMPTY to sense every channel you /invite @meno to
                             # (auto-discovered — no need to collect IDs). A non-empty list
                             # of channel IDs is an OPTIONAL further restriction to a subset.
socket_mode = false          # false = poll; true = real-time Events API over a
                             # WebSocket (no public endpoint). Needs $SLACK_APP_TOKEN
                             # (xapp-…, scope connections:write); only active in the
                             # `meno run` daemon, not in bounded `--cycles` runs.

[efferent]                   # what it may DO — gated, off by default
enabled       = false        # the master switch; outward action is opt-in (a different risk class)
post_channels = []           # may post ONLY to these channel IDs (DMs are in scope already)
reply_in_dms  = true         # a DM is a 1:1 the person opened -> reply allowed without listing it
dry_run       = false        # true = compose but DIVERT to the audit (watched-then-live ramp)
rate          = "5/min"      # max posts/min — the runaway bound (no per-post approval, D35)
# slack.com MUST also be in meno.toml [egress] for any post to leave the box
"""


def init_home(path, handle: Optional[str] = None) -> Path:
    """Scaffold an instance home from templates: the directory tree, a starter
    `meno.toml`, a seeded `library/` (self-model + a small dictionary/thesaurus), an
    empty `substrate/`, disabled adapter stubs, and a `.gitignore`. Idempotent-ish:
    never overwrites an existing `meno.toml` (won't clobber operator edits)."""
    from .library import seed_library

    home = Path(path).expanduser().resolve()
    home.mkdir(parents=True, exist_ok=True)
    for d in _DIRS:
        (home / d).mkdir(parents=True, exist_ok=True)
    handle = handle or home.name
    # CREATE-ONLY for every stateful/operator-edited file: re-running `meno init` on a
    # live home must NEVER clobber curated references (library/index.json) or operator
    # adapter config (adapters.toml). Only the self-model — the canonical TYPE (D24) —
    # is (re)written unconditionally, since it is re-derivable, not state.
    def _create(path: Path, text: str) -> None:
        if not path.exists():
            path.write_text(text)

    _create(home / "meno.toml", _MENO_TOML.format(handle=handle))
    _create(home / "adapters" / "adapters.toml", _ADAPTERS_TOML)
    _create(home / "adapters" / "knowledge.toml", _KNOWLEDGE_TOML)
    _create(home / "adapters" / "slack.toml", _SLACK_TOML)
    _create(home / ".gitignore", _GITIGNORE)
    if not (home / "library" / "index.json").exists():      # never wipe a grown/curated library
        seed_library().save(home / "library" / "index.json")
    from .self_model import MENO_SELF
    (home / "library" / "self-model.md").write_text(MENO_SELF)   # canonical type, re-derivable
    return home


def load_config(home) -> dict:
    """Read `meno.toml` (stdlib `tomllib`). Returns the raw config dict; missing
    sections default to empty. Raises if the home has no `meno.toml`."""
    home = Path(home).expanduser().resolve()
    toml_path = home / "meno.toml"
    if not toml_path.exists():
        raise FileNotFoundError(f"no meno.toml in {home} — run `meno init` first")
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def _apply_overrides(cfg: Config, overrides: dict) -> Config:
    """Apply [config] overrides LOUDLY: an unknown key (a typo in a hand-edited file)
    is an error, not a silent no-op; a value is coerced to the field's type with a
    message that names the offending key (D22 — the file exists to be hand-edited)."""
    for k, v in (overrides or {}).items():
        if not hasattr(cfg, k):
            raise ValueError(f"meno.toml [config]: unknown key {k!r} (typo?)")
        cur = getattr(cfg, k)
        try:
            setattr(cfg, k, type(cur)(v) if not isinstance(v, type(cur)) else v)
        except (TypeError, ValueError):
            raise ValueError(f"meno.toml [config] {k}={v!r}: expected {type(cur).__name__}")
    return cfg


def _int(conf: dict, key: str, default: int) -> int:
    v = conf.get(key, default)
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ValueError(f"meno.toml [driver] {key}={v!r} must be an integer")


@dataclass
class EgressPolicy:
    """Deny-by-default outbound allowlist (D21). The integration layer asks before any
    network connection; a host not on the list is refused. Empty list = no egress."""
    allow: tuple = ()

    @classmethod
    def from_config(cls, conf: dict) -> "EgressPolicy":
        return cls(tuple((conf.get("egress") or {}).get("allow", [])))

    def allows(self, host: str) -> bool:
        host = (host or "").lower().strip().rstrip(".")   # normalise the FQDN-absolute trailing dot
        if not host:
            return False
        for rule in self.allow:
            rule = rule.lower().strip()
            if host == rule or (rule.startswith("*.") and host.endswith(rule[1:])):
                return True
        return False

    def check(self, host: str) -> None:
        """Raise if `host` is not allowed — the enforcement point for outbound calls."""
        if not self.allows(host):
            raise PermissionError(
                f"egress to {host!r} denied — not in the allowlist {list(self.allow)} (D21)")


# --- the home-bound daemon ------------------------------------------------------- #
@dataclass
class Instance:
    """A home-bound Meno: the mind, its driver, the egress policy, and the home paths.
    Persists the substrate under the home so a restart resumes (D12)."""
    mind: object
    driver: object
    egress: EgressPolicy
    home: Path
    conf: dict
    store: object = None                       # the substrate backend (D34); FileStore by default
    _lock_fh: object = field(default=None, repr=False)

    @property
    def graph_path(self) -> Path:
        return self.home / "substrate" / "graph.json"

    @property
    def status_path(self) -> Path:
        return self.home / "run" / "status.json"

    @property
    def lock_path(self) -> Path:
        return self.home / "run" / "instance.lock"

    def acquire_lock(self) -> bool:
        """Take the home's advisory lock so two daemons can't race on one substrate
        (last-writer-wins would silently corrupt the identity). Returns False if another
        live process already holds it. A no-op (True) where fcntl is unavailable."""
        if fcntl is None:
            return True
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.lock_path, "w")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        fh.write(str(os.getpid()))
        fh.flush()
        self._lock_fh = fh
        return True

    def release_lock(self) -> None:
        if self._lock_fh is not None:
            try:
                fcntl.flock(self._lock_fh, fcntl.LOCK_UN)
                self._lock_fh.close()
            except Exception:
                pass
            self._lock_fh = None

    def save(self) -> None:
        try:
            from .store import FileStore
            (self.store or FileStore(self.graph_path)).save(self.mind)   # substrate backend (D34)
        except Exception as exc:                      # a failed save must not crash shutdown silently
            self.driver.last_error = f"save failed: {type(exc).__name__}: {exc}"

    def write_status(self) -> None:
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        models = getattr(self.mind, "models", None)
        status = {
            "handle": (self.conf.get("instance") or {}).get("handle", self.home.name),
            "cycles": getattr(self.driver, "cycles", 0),
            "dreams": getattr(self.driver, "dreams", 0),
            "nodes": len(self.mind.graph.nodes),
            "reflections": len(self.mind.graph.cues),
            # name the provider so 0.0 on a real provider (degraded — alarm) is
            # distinguishable from the stub (offline by design; real_fraction is None)
            "cognition_provider": getattr(models, "name", "?"),
            "cognition_real_fraction": getattr(models, "real_fraction", None),
            "errors": getattr(self.driver, "errors", 0),
            "health": self._health(models),
        }
        tmp = self.status_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(status, indent=2))
        os.replace(tmp, self.status_path)

    def _health(self, models) -> dict:
        """The operational health surface (D32): the signals an operator watches to SEE
        pathology — load and backpressure, degraded cognition, and the cost breaker.
        Pulled from the driver's counters and the mind's snapshot (both already
        maintained); additive, so older readers that only read the top-level fields are
        unaffected."""
        tel = self.driver.telemetry() if hasattr(self.driver, "telemetry") else {}
        snap = self.mind.snapshot() if hasattr(self.mind, "snapshot") else {}
        cycles = tel.get("cycles", 0) or 0
        return {
            "idle_fraction": round(tel.get("idle_cycles", 0) / cycles, 3) if cycles else None,
            "pending_input": tel.get("pending_input", 0),
            "dropped_input": tel.get("dropped_input", 0),
            "dropped_outbound": tel.get("dropped_outbound", 0),
            "egress_denied": tel.get("egress_denied", 0),
            "hot": snap.get("hot"),                       # working-set depth
            "streams_active": snap.get("streams_active"),
            "streams_warm": snap.get("streams_warm"),
            "curiosities": snap.get("curiosities"),
            "impulses_fixated": snap.get("fixations"),   # forced take-ups past the TTL (D33)
            "edges": snap.get("edges"),
            "node_ceiling": self.mind.cfg.node_ceiling or None,
            "cognition_degraded": getattr(models, "degraded", False),
            "throttled": tel.get("throttled", False),
            "cost": tel.get("cost"),
            "last_error": tel.get("last_error"),
        }


def build_instance(home) -> Instance:
    """Bind a Meno to a home from its `meno.toml`: select the cognition provider and
    embedder, apply Config overrides + driver settings, restore the substrate if one
    exists. Offline-safe — defaults to the stub provider + hashing embedder."""
    from .driver import Driver
    from .embeddings import make_embedder
    from .models import AnthropicModelProvider, StubModelProvider
    from .runtime import Meno

    home = Path(home).expanduser().resolve()
    conf = load_config(home)
    cognition = conf.get("cognition") or {}
    embeddings = conf.get("embeddings") or {}
    driver_conf = conf.get("driver") or {}

    cfg = _apply_overrides(Config(), conf.get("config") or {})
    embed = make_embedder(embeddings.get("kind", "hashing"))
    provider = cognition.get("provider", "stub")
    if provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
        models = AnthropicModelProvider(effort=cognition.get("effort", "low"),
                                        strict=bool(cognition.get("strict", False)))
    else:
        models = StubModelProvider()

    handle = (conf.get("instance") or {}).get("handle", home.name)
    mind = Meno(config=cfg, models=models, embed=embed, workspace=home, name=handle)
    store = make_store(conf, home)                    # the substrate backend (D34); file by default
    store.load(mind)                                  # sleep, not amnesia (D12) — no-op on a fresh home

    egress = EgressPolicy.from_config(conf)
    driver = Driver(mind, dream_every=_int(driver_conf, "dream_every", 8),
                    heartbeat_ticks=_int(driver_conf, "heartbeat_ticks", 8),
                    sense_every=_int(driver_conf, "sense_every", 1),
                    egress=egress,                    # the boundary is enforced on the outbound path
                    audit_path=home / "journal" / "traces" / "outbound.jsonl")   # the outward-action trail
    return Instance(mind=mind, driver=driver, egress=egress, home=home, conf=conf, store=store)
