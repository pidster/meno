"""Secret resolution for the composition root — NOT the kernel, NEVER the mind.

Secrets (model and channel tokens, and later DB credentials) are referenced by NAME in
config and resolved HERE, at adapter-construction time, to values that live only inside
the adapter object — outside cognition and outside the substrate. This is the formalised
indirection the architecture already implied: the kernel and the graph never see a
credential, and there is deliberately NO secret store the mind can read or write. A
percept that quotes a secret is still redacted before it can become a memory; this layer
ensures the *operator's* secrets are never materialised into the home or the loop either.

Backends are pluggable and tried in order; the default is the process environment
(12-factor). A read-only dotenv-file backend is available but OFF by default — the
standard posture stays env-only, nothing kept in the instance home (D31). The
`SecretBackend` protocol (`get(name) -> str | None`) is the seam for an external manager
(Vault, SOPS, a cloud secrets API) later, without touching the kernel.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Protocol, runtime_checkable


@runtime_checkable
class SecretBackend(Protocol):
    def get(self, name: str) -> Optional[str]: ...


class EnvBackend:
    """Resolve a secret from the process environment (the default, 12-factor)."""

    def get(self, name: str) -> Optional[str]:
        return os.environ.get(name) or None


class DotenvBackend:
    """Resolve from a read-only `KEY=VALUE` file. The path is EXPLICIT and may live
    outside the instance home — secrets are not committed and, by default, not kept in
    the home at all (D31). Parsed lazily and cached; a missing/unreadable file is inert
    (yields nothing) rather than an error. This backend only ever READS — it never
    writes a secret anywhere."""

    def __init__(self, path) -> None:
        self.path = Path(path)
        self._cache: Optional[dict] = None

    def _load(self) -> dict:
        if self._cache is None:
            data: dict = {}
            try:
                for raw in self.path.read_text().splitlines():
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    if line.startswith("export "):
                        line = line[len("export "):]
                    key, _, val = line.partition("=")
                    data[key.strip()] = val.strip().strip('"').strip("'")
            except OSError:
                pass
            self._cache = data
        return self._cache

    def get(self, name: str) -> Optional[str]:
        return self._load().get(name) or None


class SecretResolver:
    """Resolve a named secret through an ordered backend chain. Holds NO values itself
    (resolves on demand) and never logs them — its repr deliberately hides the chain's
    contents so a resolver can't leak a credential through a stack trace or a log line."""

    def __init__(self, backends: Optional[List[SecretBackend]] = None) -> None:
        self._backends: List[SecretBackend] = list(backends) if backends else [EnvBackend()]

    def resolve(self, name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        for backend in self._backends:
            value = backend.get(name)
            if value:
                return value
        return None

    def has(self, name: Optional[str]) -> bool:
        return self.resolve(name) is not None

    def __repr__(self) -> str:                       # never the values, only the shape
        return f"SecretResolver(backends={len(self._backends)})"


def env_resolver() -> SecretResolver:
    """The default resolver: environment only. Used when no composition root supplies one,
    so an adapter constructed bare behaves exactly as before (read its token from env)."""
    return SecretResolver([EnvBackend()])
