"""The cognitive tiers behind a provider interface.

The cognitive layer is a cost-graded stack of models (redesign.md). Here each
*tier method* names what that tier does — Tier 1 appraises, Tier 2 associates,
Tier 3 synthesises. The default `StubModelProvider` is deterministic and offline
so meno runs with no API key (D4). `AnthropicModelProvider` maps the tiers onto
the Claude family (Haiku / Sonnet / Opus) and is selectable when a key and
network are available.
"""
from __future__ import annotations

import os
import re
from typing import List, Optional

_STOP = {"the", "a", "an", "is", "are", "of", "to", "and", "in", "on", "it",
         "this", "that", "i", "you", "for", "with", "what", "why", "how"}


def _keywords(text: str, n: int = 4) -> List[str]:
    seen, out = set(), []
    for tok in re.findall(r"[a-zA-Z0-9]+", text.lower()):
        if tok in _STOP or len(tok) < 3 or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
        if len(out) >= n:
            break
    return out


class ModelProvider:
    """Interface for the cognitive tiers."""

    def appraise(self, content: str, surprise: float) -> dict:  # Tier 1
        raise NotImplementedError

    def associate(self, stream_summary: str, related: List[str]) -> str:  # Tier 2
        raise NotImplementedError

    def synthesise(self, occasion: str, material: List[str]) -> str:  # Tier 3
        raise NotImplementedError


class StubModelProvider(ModelProvider):
    """Deterministic, offline stand-in. Good enough to exercise the whole loop."""

    name = "stub"

    def appraise(self, content: str, surprise: float) -> dict:
        kws = _keywords(content)
        label = kws[0] if kws else "stimulus"
        # a reflexive echo; and, only if surprising, a residual question that may climb
        reaction = f"noted: {label}"
        question = None
        if surprise >= 0.5 and kws:
            question = f"what is the significance of {kws[0]}?"
        return {"label": label, "reaction": reaction, "question": question, "keywords": kws}

    def associate(self, stream_summary: str, related: List[str]) -> str:
        if not related:
            return f"{stream_summary} stands alone for now"
        link = related[0]
        return f"{stream_summary} connects to: {link}"

    def synthesise(self, occasion: str, material: List[str]) -> str:
        kws: List[str] = []
        for m in material:
            kws.extend(_keywords(m, 2))
        uniq = list(dict.fromkeys(kws))[:5]
        theme = ", ".join(uniq) if uniq else "these fragments"
        return f"On {occasion}: a pattern across {theme} — they cohere into one concern."


class AnthropicModelProvider(ModelProvider):
    """Maps the tiers onto the Claude family. Best-effort; falls back to the stub
    on any error so the loop never blocks on the network (D4)."""

    name = "anthropic"
    TIER_MODELS = {1: "claude-haiku-4-5", 2: "claude-sonnet-4-6", 3: "claude-opus-4-8"}

    def __init__(self, fallback: Optional[ModelProvider] = None) -> None:
        self.fallback = fallback or StubModelProvider()
        self._client = None
        try:  # pragma: no cover - exercised only when the dep + key exist
            import anthropic  # type: ignore

            if os.environ.get("ANTHROPIC_API_KEY"):
                self._client = anthropic.Anthropic()
        except Exception:
            self._client = None

    def _ask(self, tier: int, system: str, prompt: str) -> Optional[str]:  # pragma: no cover
        if self._client is None:
            return None
        try:
            msg = self._client.messages.create(
                model=self.TIER_MODELS[tier],
                max_tokens=256,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        except Exception:
            return None

    def appraise(self, content: str, surprise: float) -> dict:
        return self.fallback.appraise(content, surprise)  # routing stays cheap/deterministic

    def associate(self, stream_summary: str, related: List[str]) -> str:  # pragma: no cover
        out = self._ask(2, "You connect ideas tersely.",
                        f"Thread: {stream_summary}\nRelated: {related}\nState the connection in one line.")
        return out or self.fallback.associate(stream_summary, related)

    def synthesise(self, occasion: str, material: List[str]) -> str:  # pragma: no cover
        out = self._ask(3, "You synthesise a short, particular reflection.",
                        f"Occasion: {occasion}\nMaterial:\n- " + "\n- ".join(material))
        return out or self.fallback.synthesise(occasion, material)
