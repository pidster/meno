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

    def __init__(self, root, *, max_bytes: int = 64_000, max_chars: int = 2000,
                 max_per_poll: int = 8, suffixes=None) -> None:
        self.root = Path(root).resolve()
        self.max_bytes = max_bytes
        self.max_chars = max_chars
        self.max_per_poll = max_per_poll
        self.suffixes = frozenset(suffixes) if suffixes else self._TEXT_SUFFIXES
        self._seen: dict = {}              # resolved path -> mtime, for change detection

    def _eligible(self, p: Path) -> bool:
        if not p.is_file() or p.suffix.lower() not in self.suffixes:
            return False
        try:
            rp = p.resolve()
            rel = rp.relative_to(self.root)    # within root? (rejects symlink escapes)
        except (ValueError, OSError):
            return False
        if any(part.startswith(".") for part in rel.parts):
            return False                   # hidden file or anything under a dotdir
        try:
            return p.stat().st_size <= self.max_bytes
        except OSError:
            return False

    def poll(self) -> List[Percept]:
        out: List[Percept] = []
        try:
            candidates = sorted(self.root.rglob("*"))
        except OSError:
            return out
        for p in candidates:
            if len(out) >= self.max_per_poll:
                break
            if not self._eligible(p):
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            rp = p.resolve()
            if self._seen.get(rp) == mtime:
                continue                   # unchanged since last poll
            self._seen[rp] = mtime
            try:
                text = p.read_text(errors="ignore")[:self.max_chars]
            except OSError:
                continue
            rel = rp.relative_to(self.root)
            out.append((f"file {rel}: {text}", self.source, {"path": str(rp)}))
        return out


def fs_read_intent(path: str) -> Event:
    return Event(content=f"intent: read {path}", kind=Kind.INTENT, source="self",
                 payload={"action": "fs_read", "path": path})


def fs_write_intent(path: str, data: str) -> Event:
    return Event(content=f"intent: write {path}", kind=Kind.INTENT, source="self",
                 payload={"action": "fs_write", "path": path, "data": data})
