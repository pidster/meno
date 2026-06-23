"""The substrate store seam — where the persistent graph lives (D34).

Today the substrate is a JSON file under the home (`FileStore`), which is exactly right
for a single instance: the mounted volume IS the persistence, no service to run. When an
instance outgrows that — concurrent readers, vector search at scale — a graph/vector DB
(SurrealDB) plugs in HERE behind this same `Store` interface, provisioned as a SIDECAR
(see `deploy/compose.yaml`), never baked into the app image.

`make_store` selects the backend from `meno.toml [storage] backend` (default `"file"`).
A network backend, when implemented, lazily imports its client (like the Anthropic
provider does) — the seam stays kernel-pure; only the file store ships today. We do NOT
ship a stub SurrealDB backend: an unimplemented backend fails loudly with a pointer
rather than pretending to persist (a silent no-op store would be the worst zombie).
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Store(Protocol):
    def save(self, mind) -> None: ...
    def load(self, mind) -> bool: ...        # True if a prior substrate was restored
    def describe(self) -> str: ...


class FileStore:
    """The default: the substrate as a JSON file under the home (graph + library). The
    mounted volume is the identity; a restart reloads it (sleep, not amnesia — D12)."""

    def __init__(self, path) -> None:
        self.path = Path(path)

    def save(self, mind) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        mind.save(self.path)

    def load(self, mind) -> bool:
        if not self.path.exists():
            return False
        mind.load(self.path)
        return True

    def describe(self) -> str:
        return f"file:{self.path}"


def make_store(conf: dict, home) -> Store:
    """Pick the substrate backend from config. `file` (default) is the only backend that
    ships; any other value fails loudly with a pointer to the sidecar plan, rather than
    silently falling back (a substrate that doesn't persist must never look like it does)."""
    backend = ((conf.get("storage") or {}).get("backend") or "file").lower()
    graph_path = Path(home) / "substrate" / "graph.json"
    if backend == "file":
        return FileStore(graph_path)
    raise NotImplementedError(
        f"storage backend {backend!r} is not implemented. The JSON file store is the only "
        f"backend today (it is the right default for a single instance). A SurrealDB / "
        f"vector backend plugs in here behind the Store interface and is provisioned as a "
        f"sidecar (deploy/compose.yaml). Set [storage] backend = \"file\".")
