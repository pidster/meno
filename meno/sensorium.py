"""Sensorium adapters: bridge the world to the bus (afferent) and intents to the
world (efferent). Concrete catalogue/schema are deferred (redesign.md); these are
the minimal afferent sources and the effector-intent helper for the bare loop.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from .event import Event, Kind

# a percept the driver will feed: (text, source, payload)
Percept = Tuple[str, str, dict]


class Sensor:
    """Afferent: normalise a source into events. Uncontrolled rate; the gate triages.

    A live sensor also implements ``poll() -> list[Percept]``: the driver calls it
    each sense-cycle and feeds whatever it returns. ``poll`` must be cheap, return
    only what is NEW since the last call, and bound how much it emits per call."""
    source = "sensor"

    def sense(self, text: str, **payload) -> Event:
        return Event(content=text, kind=Kind.SENSE, source=self.source, payload=payload)

    def poll(self) -> List[Percept]:
        return []


class ChatSensor(Sensor):
    source = "chat"


class LogSensor(Sensor):
    source = "log"


class FilesystemSensor(Sensor):
    """A real afferent channel: watch ONE explicitly-given directory and emit a
    percept when a text file appears or changes. Bounded by design (the consent and
    resource boundary the review lens cares about):

      - **consent/scope**: only the given `root`; a path that resolves outside it
        (a symlink escape) is skipped — the sensor can never wander the filesystem.
      - **privacy**: hidden files/dirs (dotfiles like `.env`, `.git/…`) are skipped,
        and only an allow-list of text-ish suffixes is read.
      - **resource**: files over `max_bytes` are skipped; content is truncated to
        `max_chars`; at most `max_per_poll` changes are emitted per call.

    It is AFFERENT ONLY — it never writes. The agent senses the directory; it does
    not touch it.
    """

    source = "filesystem"
    _TEXT_SUFFIXES = frozenset(
        ".txt .md .rst .py .js .ts .json .yaml .yml .toml .cfg .ini .csv .log .html".split())
    # never read these, even with an allowed suffix (e.g. 'credentials.txt') — a
    # blunt secret guard so a watched project dir can't bleed obvious secrets in.
    _SECRET_MARKERS = ("credential", "secret", "password", "passwd", "id_rsa",
                       "id_ed25519", "id_dsa", "htpasswd", "private_key", ".pem", ".key")

    def __init__(self, root, *, max_bytes: int = 64_000, max_chars: int = 2000,
                 max_per_poll: int = 8, suffixes=None) -> None:
        self.root = Path(root).resolve()
        self.max_bytes = max_bytes
        self.max_chars = max_chars
        self.max_per_poll = max_per_poll
        self.suffixes = frozenset(suffixes) if suffixes else self._TEXT_SUFFIXES
        try:
            self._root_dev = self.root.stat().st_dev      # confine to the root's device
        except OSError:
            self._root_dev = None
        self._seen: dict = {}              # resolved path -> mtime, for change detection
        self._cursor = 0                   # round-robins the per-poll window (anti-starvation)

    def _eligible(self, p: Path) -> bool:
        if not p.is_file() or p.suffix.lower() not in self.suffixes:
            return False
        if any(m in p.name.lower() for m in self._SECRET_MARKERS):
            return False                   # obvious secret by name -> never read
        try:
            rp = p.resolve()
            rel = rp.relative_to(self.root)    # within root? (rejects symlink escapes)
        except (ValueError, OSError):
            return False
        if any(part.startswith(".") for part in rel.parts):
            return False                   # hidden file or anything under a dotdir
        try:
            st = p.stat()
        except OSError:
            return False
        # confine to root's filesystem and reject hardlinks (a 2nd name with no link
        # target that resolve() can't see through — the symlink guard misses them).
        if self._root_dev is not None and st.st_dev != self._root_dev:
            return False
        if st.st_nlink > 1:
            return False
        return st.st_size <= self.max_bytes

    def poll(self) -> List[Percept]:
        out: List[Percept] = []
        try:
            candidates = sorted(self.root.rglob("*"))
        except OSError:
            return out
        present, changed = set(), []
        for p in candidates:
            if not self._eligible(p):
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            rp = p.resolve()
            present.add(rp)
            if self._seen.get(rp) != mtime:
                changed.append((p, rp, mtime))
        # prune change-detection state of files that have gone (no unbounded _seen leak)
        self._seen = {k: v for k, v in self._seen.items() if k in present}
        if not changed:
            return out
        # round-robin the window so a few constantly-changing files can't permanently
        # starve the rest; mark a file seen ONLY once actually read.
        start = self._cursor % len(changed)
        ordered = changed[start:] + changed[:start]
        for p, rp, mtime in ordered[:self.max_per_poll]:
            try:
                text = p.read_text(errors="ignore")[:self.max_chars]
            except OSError:
                continue
            self._seen[rp] = mtime
            out.append((f"file {rp.relative_to(self.root)}: {text}", self.source, {"path": str(rp)}))
        self._cursor += len(out)
        return out


def fs_read_intent(path: str) -> Event:
    return Event(content=f"intent: read {path}", kind=Kind.INTENT, source="self",
                 payload={"action": "fs_read", "path": path})


def fs_write_intent(path: str, data: str) -> Event:
    return Event(content=f"intent: write {path}", kind=Kind.INTENT, source="self",
                 payload={"action": "fs_write", "path": path, "data": data})
