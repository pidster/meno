"""Prompt text, externalised to markdown files behind a loader seam.

Every piece of text meno sends to a cognitive model — the self-model prefix, each
surface's role line, and each surface's user-content template — lives as a `.md`
file in this package, not inline in Python. `models.py` and `self_model.py` read
through `load()` / `render()`; the text itself is data, editable without touching
the logic that consumes it (the same discipline `config.py` applies to constants).

Two readers:
  - `load(name)`  -> the raw text of `<name>.md` (system role lines, the self-model).
  - `render(name, **kw)` -> `load(name).format(**kw)` (user-content templates).

A template `.md` carries only simple ``{placeholder}`` fields and never a literal
brace; the caller prepares the values (so there are no expressions in the text). The
read is cached — the hot path (appraise, per event) must never touch disk twice.

This realises the relocation `self_model.py` always anticipated ("the backing store
to a file… `self_model()` is the seam"). Loading is stdlib-only (`importlib`), so the
kernel-purity guard still holds.
"""
from __future__ import annotations

from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=None)
def load(name: str) -> str:
    """The text of prompt `name`, read from `meno/prompts/<name>.md`.

    A trailing newline (every well-formed text file has one) is stripped, so the
    loaded prompt matches the inline string it replaced byte-for-byte. Cached per
    process: a prompt file is read from disk at most once."""
    text = files(__package__).joinpath(f"{name}.md").read_text(encoding="utf-8")
    return text.rstrip("\n")


def render(name: str, **kwargs: object) -> str:
    """A user-content template (`<name>.md`) with its ``{placeholder}`` fields filled.
    The caller supplies already-prepared values — the template holds no expressions."""
    return load(name).format(**kwargs)
