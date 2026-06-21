"""The cognitive tiers behind a provider interface.

The cognitive layer is a cost-graded stack of models (redesign.md). Each *tier
method* names what that tier does — Tier 1 appraises, Tier 2 associates, Tier 3
synthesises. The default `StubModelProvider` is deterministic and offline so meno
runs with no API key (D4). `AnthropicModelProvider` maps the tiers onto the
Claude family and is selectable when a key and network are available (D13):

    Tier 1  claude-haiku-4-5    fast appraisal (structured JSON output)
    Tier 2  claude-sonnet-4-6   association across a stream
    Tier 3  claude-opus-4-8     synthesis (adaptive thinking + effort)

Every real call falls back to the stub on any error, so the kernel never blocks
on the network — faithful to the "graceful degradation" the design assumes.
"""
from __future__ import annotations

import json
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

    # --- model-routed judgments (F2 merge, F3 curiosity); safe base defaults ---
    def relate(self, summary_a: str, summary_b: str) -> bool:
        """Are two streams about the same thing? (merge decision)"""
        return False

    def wonder(self, text: str, referent: Optional[str] = None) -> dict:
        """Route a discharged curiosity across the internal/external matrix.
        Returns {mode: internal|external|both, thought: str|None, action: dict|None}."""
        return {"mode": "internal", "thought": f"I wonder: {text}", "action": None}


class StubModelProvider(ModelProvider):
    """Deterministic, offline stand-in. Good enough to exercise the whole loop."""

    name = "stub"

    def appraise(self, content: str, surprise: float) -> dict:
        kws = _keywords(content)
        label = kws[0] if kws else "stimulus"
        reaction = f"noted: {label}"
        question = None
        if surprise >= 0.5 and kws:
            question = f"what is the significance of {kws[0]}?"
        return {"label": label, "reaction": reaction, "question": question, "keywords": kws}

    def associate(self, stream_summary: str, related: List[str]) -> str:
        if not related:
            return f"{stream_summary} stands alone for now"
        return f"{stream_summary} connects to: {related[0]}"

    def synthesise(self, occasion: str, material: List[str]) -> str:
        kws: List[str] = []
        for m in material:
            kws.extend(_keywords(m, 2))
        uniq = list(dict.fromkeys(kws))[:5]
        theme = ", ".join(uniq) if uniq else "these fragments"
        return f"On {occasion}: a pattern across {theme} — they cohere into one concern."

    def relate(self, summary_a: str, summary_b: str) -> bool:
        # deterministic default: shared vocabulary = relatedness (candidates are
        # already pre-filtered by centroid cosine before this is asked)
        return len(set(_keywords(summary_a, 6)) & set(_keywords(summary_b, 6))) >= 1

    def wonder(self, text: str, referent: Optional[str] = None) -> dict:
        ref = str(referent or "")
        if "/" in ref or ref.endswith((".txt", ".md", ".py", ".json", ".log")):
            # a world referent -> reach outward (the Effector will read it)
            return {"mode": "external", "thought": None,
                    "action": {"action": "fs_read", "path": ref}}
        return {"mode": "internal", "thought": f"I wonder: {text}", "action": None}


_APPRAISE_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "reaction": {"type": "string"},
        "question": {"type": "string"},   # empty string when the percept raises none
    },
    "required": ["label", "reaction", "question"],
    "additionalProperties": False,
}

_APPRAISE_SYSTEM = (
    "You are the fast appraisal tier of a cognitive architecture. For each percept, "
    "give a one-line reflexive reaction (a few words), a short label, and — only if "
    "the percept is genuinely surprising or leaves something unresolved — a single "
    "short question it provokes. If it raises no question, return an empty string.")

_ASSOC_SYSTEM = "You connect ideas tersely. One line, no preamble."

_SYNTH_SYSTEM = (
    "You are the deep synthesis tier of a cognitive architecture. From the material, "
    "write a short, particular reflection (two or three sentences) that finds the "
    "pattern across it — a perspective, not a summary. First person is welcome. "
    "Respond with only the reflection, no preamble.")


class AnthropicModelProvider(ModelProvider):
    """Maps the tiers onto the Claude family. Best-effort: any error (no client,
    no key, network failure, refusal, parse failure) falls back to the stub so the
    loop never blocks (D13)."""

    name = "anthropic"
    TIER_MODELS = {1: "claude-haiku-4-5", 2: "claude-sonnet-4-6", 3: "claude-opus-4-8"}

    def __init__(self, client=None, fallback: Optional[ModelProvider] = None,
                 effort: str = "medium") -> None:
        self.fallback = fallback or StubModelProvider()
        self.effort = effort
        self._client = client
        if self._client is None:
            try:  # pragma: no cover - depends on the optional dep + a key
                import anthropic  # type: ignore

                if os.environ.get("ANTHROPIC_API_KEY"):
                    self._client = anthropic.Anthropic()
            except Exception:
                self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    @staticmethod
    def _text(msg) -> str:
        return "".join(b.text for b in msg.content
                       if getattr(b, "type", "") == "text").strip()

    def appraise(self, content: str, surprise: float) -> dict:
        if not self.available:
            return self.fallback.appraise(content, surprise)
        try:
            msg = self._client.messages.create(
                model=self.TIER_MODELS[1],
                max_tokens=256,
                system=_APPRAISE_SYSTEM,
                messages=[{"role": "user",
                           "content": f"Percept (surprise={surprise:.2f}): {content}"}],
                output_config={"format": {"type": "json_schema", "schema": _APPRAISE_SCHEMA}},
            )
            data = json.loads(self._text(msg))
            question = (data.get("question") or "").strip() or None
            return {"label": data.get("label", "stimulus"),
                    "reaction": data.get("reaction", ""),
                    "question": question, "keywords": []}
        except Exception:
            return self.fallback.appraise(content, surprise)

    def associate(self, stream_summary: str, related: List[str]) -> str:
        if not self.available:
            return self.fallback.associate(stream_summary, related)
        try:
            msg = self._client.messages.create(
                model=self.TIER_MODELS[2],
                max_tokens=200,
                system=_ASSOC_SYSTEM,
                messages=[{"role": "user",
                           "content": f"Thread: {stream_summary}\nRelated memory: {related}\n"
                                      "State the connection in one line."}],
            )
            return self._text(msg) or self.fallback.associate(stream_summary, related)
        except Exception:
            return self.fallback.associate(stream_summary, related)

    def synthesise(self, occasion: str, material: List[str]) -> str:
        if not self.available:
            return self.fallback.synthesise(occasion, material)
        try:
            prompt = f"Occasion: {occasion}\nMaterial:\n- " + "\n- ".join(material or ["(none)"])
            msg = self._client.messages.create(
                model=self.TIER_MODELS[3],
                max_tokens=1500,                       # room for adaptive thinking + a short reflection
                thinking={"type": "adaptive"},         # Opus 4.8: adaptive only (no budget_tokens)
                output_config={"effort": self.effort},  # low | medium | high | max
                system=_SYNTH_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._text(msg) or self.fallback.synthesise(occasion, material)
        except Exception:
            return self.fallback.synthesise(occasion, material)

    def relate(self, summary_a: str, summary_b: str) -> bool:
        if not self.available:
            return self.fallback.relate(summary_a, summary_b)
        try:
            msg = self._client.messages.create(
                model=self.TIER_MODELS[1],
                max_tokens=64,
                system="Decide whether two trains of thought are fundamentally about "
                       "the same matter (and should merge).",
                messages=[{"role": "user",
                           "content": f"A: {summary_a}\nB: {summary_b}"}],
                output_config={"format": {"type": "json_schema", "schema": {
                    "type": "object",
                    "properties": {"related": {"type": "boolean"}},
                    "required": ["related"], "additionalProperties": False}}},
            )
            return bool(json.loads(self._text(msg)).get("related", False))
        except Exception:
            return self.fallback.relate(summary_a, summary_b)

    def wonder(self, text: str, referent: Optional[str] = None) -> dict:
        if not self.available:
            return self.fallback.wonder(text, referent)
        try:
            msg = self._client.messages.create(
                model=self.TIER_MODELS[2],
                max_tokens=200,
                system="A curiosity has arisen. Decide how to follow it. Respond inward "
                       "(a thought to think) or outward (read a file you're curious about) "
                       "or both — whatever fits. Only propose a file path you were actually "
                       "given a referent for.",
                messages=[{"role": "user",
                           "content": f"Curiosity: {text}\nReferent: {referent or '(none)'}"}],
                output_config={"format": {"type": "json_schema", "schema": {
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": ["internal", "external", "both"]},
                        "thought": {"type": "string"},
                        "path": {"type": "string"}},
                    "required": ["mode", "thought", "path"], "additionalProperties": False}}},
            )
            data = json.loads(self._text(msg))
            path = (data.get("path") or "").strip()
            action = {"action": "fs_read", "path": path} if path else None
            return {"mode": data.get("mode", "internal"),
                    "thought": data.get("thought") or None, "action": action}
        except Exception:
            return self.fallback.wonder(text, referent)


def make_models(name: str = "stub", **kwargs) -> ModelProvider:
    """Factory for selecting a provider by name (used by the runtime/CLI)."""
    if name == "anthropic":
        return AnthropicModelProvider(**kwargs)
    return StubModelProvider()
