"""The Library — reference memory, the anti-substrate (Roadmap K1).

Wegner's transactive split, made structural: the **graph** is *episodic* memory —
idiosyncratic, reconstructive, forgetful, the thing that makes an instance
particular. The **Library** is *semantic* reference — keyed, stable, non-decaying,
non-reconstructive. They are opposite in every dynamic, and deliberately disjoint:

  - A graph edge left unused decays; a node can island; a reflection is rebuilt
    differently each recall. A Library entry does NONE of this — `get(key)` returns
    byte-identical text every time, forever.
  - The Library is never an entry point for spreading activation and its entries
    never appear in `graph.cues`. Reference cannot leak into the identity substrate,
    and the substrate's drift cannot corrupt reference. (`recall()` reads only
    `graph.cues`, so it can never return a Library entry — enforced by construction
    and asserted in tests.)
  - Lookup is **exact-key only** here (K1). Fuzzy `search` needs the cold embedder,
    which would pin the Library to that model (D20) — deferred to the backlog so the
    Library stays embedder-free.

The self-model document lives here as a reference copy so the agent can *look it up*
(K2). Its canonical home remains the code constant `self_model.MENO_SELF` — the
self-model is the **type** (D21: image = type), so it is baked into the image, not
served from the mutable instance home. The Library copy is seeded from the constant;
it never overrides it (D24).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

# The kinds of thing the Library may hold. A reference is external knowledge; it is
# NOT the agent's experience or perspective (those are the graph's). Write-back is
# restricted to these so an agent-authored reflection can never be filed as fact.
ALLOWED_KINDS = ("definition", "fact", "reference")

# Write-back is restricted to EXTERNAL provenance by an ALLOWLIST, not a denylist.
# A denylist (reject source=="self") is always one synonym behind — the K2 lookup
# caller could hand an innocent-looking `source="cognition"`/`"curiosity"`/`"meno"`
# and launder a self-authored reflection into "fact". Instead a reference's source
# MUST name a sanctioned external namespace; anything self-/agent-authored has none
# and is rejected. This is the episodic≠semantic boundary as a runtime check.
_EXTERNAL_SOURCE_PREFIXES = ("seed:", "dictionary:", "lookup:", "reference:",
                             "external:", "authority:", "meno:type")


@dataclass(frozen=True)
class Reference:
    """One reference entry, IMMUTABLE (frozen): the Library never rewrites a body,
    unlike a reflection cue which is regenerated each recall. `get` hands back this
    frozen object, so the byte-identical guarantee is structural, not a convention —
    a caller cannot mutate `body` in place and corrupt the store."""
    key: str
    body: str
    source: str          # provenance: a sanctioned external namespace (see allowlist)
    kind: str            # one of ALLOWED_KINDS


class WritebackRejected(ValueError):
    """A `put` that would file non-reference content (wrong kind, or self-authored
    provenance) into the Library. The boundary is enforced, not merely asserted."""


class Library:
    """A keyed reference store. Exact-key get/put, JSON save/load. No dynamics — no
    decay, no islanding, no reconstruction. The anti-substrate."""

    def __init__(self) -> None:
        self._refs: Dict[str, Reference] = {}

    # --- reads ---
    def get(self, key: str) -> Optional[Reference]:
        return self._refs.get(key)

    def __contains__(self, key: str) -> bool:
        return key in self._refs

    def __len__(self) -> int:
        return len(self._refs)

    def keys(self) -> List[str]:
        return list(self._refs)

    def bodies(self) -> List[str]:
        return [r.body for r in self._refs.values()]

    # --- writes (guarded) ---
    def put(self, ref: Reference) -> Reference:
        """Add or replace a reference. Rejects anything that isn't external reference
        knowledge: an unknown kind, an empty key/body, or self-authored provenance.
        This is the episodic≠semantic boundary as a runtime check (K1)."""
        if ref.kind not in ALLOWED_KINDS:
            raise WritebackRejected(
                f"kind {ref.kind!r} not in {ALLOWED_KINDS} — reflections/experience "
                "belong in the graph, not the Library")
        if not ref.key or not ref.body:
            raise WritebackRejected("a reference needs a non-empty key and body")
        if not ref.source or not ref.source.strip().lower().startswith(_EXTERNAL_SOURCE_PREFIXES):
            raise WritebackRejected(
                f"source {ref.source!r} is not a sanctioned external namespace "
                f"{_EXTERNAL_SOURCE_PREFIXES} — reference must be external, not "
                "self-authored")
        self._refs[ref.key] = ref
        return ref

    # --- persistence (its own home: <instance>/library/index.json) ---
    def save(self, path) -> None:
        # Atomic: write a temp file then os.replace, so a crash mid-write can never
        # leave a torn index.json that would crash the next load.
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1,
                   "references": [asdict(r) for r in self._refs.values()]}
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        os.replace(tmp, path)

    @classmethod
    def load(cls, path) -> "Library":
        lib = cls()
        path = Path(path)
        if not path.exists():
            return lib
        data = json.loads(path.read_text())
        for r in data.get("references", []):
            lib._refs[r["key"]] = Reference(key=r["key"], body=r["body"],
                                            source=r["source"], kind=r["kind"])
        return lib


def seed_library() -> Library:
    """A fresh instance's starting reference shelf: the self-model (a lookup-able copy
    of the type — D24), plus a tiny dictionary and thesaurus. Operators grow this; the
    agent will look entries up in K2. Kept deliberately small — a Meno's knowledge is
    meant to be *accumulated and looked up*, not pre-loaded."""
    from .self_model import MENO_SELF

    lib = Library()
    # the self-model as a reference copy — canonical home stays the code constant
    lib.put(Reference(key="self-model", body=MENO_SELF,
                      source="meno:type", kind="reference"))
    # a seed dictionary (definitions)
    for term, body in _SEED_DICTIONARY.items():
        lib.put(Reference(key=f"def:{term}", body=body,
                          source="seed:dictionary", kind="definition"))
    # a seed thesaurus (synonym sets, as reference)
    for term, syns in _SEED_THESAURUS.items():
        lib.put(Reference(key=f"syn:{term}", body=", ".join(syns),
                          source="seed:thesaurus", kind="reference"))
    return lib


_SEED_DICTIONARY = {
    "memory": "The retention and reconstruction of past experience. In a Meno, "
              "episodic memory is the graph (reconstructive, forgetful); semantic "
              "reference is the Library (stable, looked-up).",
    "reconstruction": "Rebuilding a memory from a cue and the current state of the "
                      "graph at the moment of recall, rather than replaying a stored "
                      "record — so the same memory recalled twice can differ.",
    "association": "A weighted link between two memories along which activation "
                   "spreads; the unit of relatedness in the graph.",
    "consolidation": "The dream: folding committed events into the graph, recombining "
                     "loosely, reconsolidating reflections, and forgetting.",
}

_SEED_THESAURUS = {
    "remember": ["recall", "reconstruct", "retrieve", "recollect"],
    "forget": ["decay", "island", "release", "let go"],
    "curiosity": ["wonder", "interest", "inquisitiveness", "pull"],
}
