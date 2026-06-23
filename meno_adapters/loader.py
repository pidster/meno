"""Construct channel/authority adapters from an instance's `adapters/*.toml` and wire
them into the driver (Roadmap I — the config-driven composition step).

This lives in meno_adapters, NOT the kernel: the kernel stays adapter-blind (`meno/`
never imports `meno_adapters`). The CLI calls `load_adapters` as an `on_build` hook.
Each adapter is OFF unless its config explicitly enables it — default is silence.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from .knowledge import KnowledgeAdapter
from .secrets import DotenvBackend, EnvBackend, SecretResolver
from .slack import SlackAdapter


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _rate_per_min(rate, default: int = 5) -> int:
    # "5/min" -> 5 ; an int -> itself
    try:
        return int(str(rate).split("/")[0])
    except (TypeError, ValueError):
        return default


def _secret_resolver(home: Path) -> SecretResolver:
    """Env-first secret resolution for the composition root (D31). Always reads the
    process environment; OPTIONALLY also a read-only dotenv file declared in
    `meno.toml [secrets] file = …` (a relative path resolves against the home; an
    absolute path lets the operator keep secrets OUTSIDE the home — the default posture
    is env-only, no file). Env wins over the file. Never materialises a secret to disk
    and never reaches the kernel or the mind."""
    backends = [EnvBackend()]
    path = _read(home / "meno.toml").get("secrets", {}).get("file")
    if path:
        p = Path(path).expanduser()
        backends.append(DotenvBackend(p if p.is_absolute() else home / p))
    return SecretResolver(backends)


def load_adapters(inst) -> list:
    """Attach the adapters an instance's config enables. Returns the names attached.
    A Slack adapter is added if its afferent OR efferent side is enabled; the efferent
    (posting) stays gated regardless. A knowledge authority is added if enabled.
    Audit trails land under the home's `journal/traces/`."""
    home = Path(inst.home)
    traces = home / "journal" / "traces"
    secrets = _secret_resolver(home)                 # resolve token NAMES -> values here
    attached = []

    slack = _read(home / "adapters" / "slack.toml")
    aff, eff = slack.get("afferent", {}), slack.get("efferent", {})
    if aff.get("enabled") or eff.get("enabled"):
        inst.driver.add_adapter(SlackAdapter(
            channels=tuple(aff.get("channels", ())) if aff.get("enabled") else (),
            secrets=secrets,                          # tokens resolved by name, off the loop
            # afferent receive model: poll (default) or Socket Mode (real-time, needs
            # $SLACK_APP_TOKEN). Socket Mode only takes effect in the unbounded daemon,
            # which calls adapter.start(); bounded `--cycles` runs stay on poll.
            socket_mode=bool(aff.get("socket_mode", False)) and bool(aff.get("enabled")),
            enabled=bool(eff.get("enabled", False)),
            post_channels=tuple(eff.get("post_channels", ())),
            dry_run=bool(eff.get("dry_run", False)),
            rate_per_min=_rate_per_min(eff.get("rate", "5/min")),
            audit_path=traces / "slack-sends.jsonl"))
        attached.append("slack")

    know = _read(home / "adapters" / "knowledge.toml")
    if know.get("enabled"):
        inst.driver.add_adapter(KnowledgeAdapter(
            kind=know.get("kind", "web"),
            hosts=tuple(know.get("hosts", ()))))
        attached.append("knowledge")

    return attached
