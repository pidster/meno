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


class CognitionDegraded(RuntimeError):
    """Raised (in strict mode) when a real model call fails and would otherwise
    silently fall back to the stub. The point of strict mode is that a run cannot
    pretend to be real cognition while secretly running the zombie (realisation
    plan R1: make cognition failure loud)."""


class AnthropicModelProvider(ModelProvider):
    """Maps the tiers onto the Claude family. By default best-effort: any error (no
    client, no key, network failure, refusal, parse failure) falls back to the stub
    so the loop never blocks (D13) — BUT every fallback is RECORDED in `telemetry`,
    so a caller can tell real cognition from silent degradation (the difference
    between a living run and a zombie). `strict=True` raises instead, for validation
    and for runs that must abort rather than degrade unnoticed."""

    name = "anthropic"
    TIER_MODELS = {1: "claude-haiku-4-5", 2: "claude-sonnet-4-6", 3: "claude-opus-4-8"}

    def __init__(self, client=None, fallback: Optional[ModelProvider] = None,
                 effort: str = "medium", strict: bool = False) -> None:
        self.fallback = fallback or StubModelProvider()
        self.effort = effort
        self.strict = strict
        self._client = client
        self.reset_telemetry()
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

    # --- cognition telemetry: the loud-failure substrate (R1) ---
    def reset_telemetry(self) -> None:
        self.telemetry = {"real": 0, "fallback": 0, "last_error": None,
                          "by_method": {}}

    @property
    def real_fraction(self) -> float:
        t = self.telemetry
        n = t["real"] + t["fallback"]
        return (t["real"] / n) if n else 0.0

    @property
    def degraded(self) -> bool:
        return self.telemetry["fallback"] > 0

    def _by(self, method: str) -> dict:
        return self.telemetry["by_method"].setdefault(method, {"real": 0, "fallback": 0})

    def _run(self, method: str, real_fn, fallback_fn, fb_args):
        """Run a real model call; on any failure record it and fall back (or, in
        strict mode, raise). Empty/invalid model output counts as a failure — a
        blank reflection is a degradation, not real cognition."""
        if self.available:
            try:
                result = real_fn()
                self.telemetry["real"] += 1
                self._by(method)["real"] += 1
                return result
            except Exception as exc:
                reason = f"{method}: {type(exc).__name__}: {exc}"
                if self.strict:
                    raise CognitionDegraded(reason) from exc
        elif self.strict:
            raise CognitionDegraded(f"{method}: no client/key")
        else:
            reason = f"{method}: no client/key"
        self.telemetry["fallback"] += 1
        self._by(method)["fallback"] += 1
        self.telemetry["last_error"] = reason
        return fallback_fn(*fb_args)

    @staticmethod
    def _text(msg) -> str:
        return "".join(b.text for b in msg.content
                       if getattr(b, "type", "") == "text").strip()

    def appraise(self, content: str, surprise: float) -> dict:
        def real():
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
        return self._run("appraise", real, self.fallback.appraise, (content, surprise))

    def associate(self, stream_summary: str, related: List[str]) -> str:
        def real():
            msg = self._client.messages.create(
                model=self.TIER_MODELS[2],
                max_tokens=200,
                system=_ASSOC_SYSTEM,
                messages=[{"role": "user",
                           "content": f"Thread: {stream_summary}\nRelated memory: {related}\n"
                                      "State the connection in one line."}],
            )
            text = self._text(msg)
            if not text:
                raise ValueError("empty association")
            return text
        return self._run("associate", real, self.fallback.associate, (stream_summary, related))

    def synthesise(self, occasion: str, material: List[str]) -> str:
        def real():
            prompt = f"Occasion: {occasion}\nMaterial:\n- " + "\n- ".join(material or ["(none)"])
            msg = self._client.messages.create(
                model=self.TIER_MODELS[3],
                max_tokens=1500,                       # room for adaptive thinking + a short reflection
                thinking={"type": "adaptive"},         # Opus 4.8: adaptive only (no budget_tokens)
                output_config={"effort": self.effort},  # low | medium | high | max
                system=_SYNTH_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            text = self._text(msg)
            if not text:
                raise ValueError("empty synthesis")
            return text
        return self._run("synthesise", real, self.fallback.synthesise, (occasion, material))

    def relate(self, summary_a: str, summary_b: str) -> bool:
        def real():
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
        return self._run("relate", real, self.fallback.relate, (summary_a, summary_b))

    def wonder(self, text: str, referent: Optional[str] = None) -> dict:
        def real():
            msg = self._client.messages.create(
                model=self.TIER_MODELS[2],
                max_tokens=512,        # the structured {mode,thought,path} JSON; 200 truncated
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
            mode = data.get("mode", "internal")
            thought = data.get("thought") or None
            path = (data.get("path") or "").strip()
            # a route must carry what its mode promises, else it is a no-op dressed
            # as cognition -> treat as degradation (R1 review, data lens P1.3)
            if mode in ("internal", "both") and not thought:
                raise ValueError("internal/both route with no thought")
            if mode in ("external", "both") and not path:
                raise ValueError("external/both route with no path")
            action = {"action": "fs_read", "path": path} if path else None
            return {"mode": mode, "thought": thought, "action": action}
        return self._run("wonder", real, self.fallback.wonder, (text, referent))


# The whole-run realness floor: a long, genuinely-alive run may suffer a rare
# transient blip on a cheap, frequent surface (a single relate 5xx); that must not
# poison the verdict. But the deep insight-bearing tier is gated hard below.
_REAL_FRACTION_FLOOR = 0.9


def cognition_is_real(provider) -> bool:
    """Is this run's cognition real enough to even ask whether it is alive?

    The zombie verdict depends on this (realisation plan R1): a run that silently
    degraded to the deterministic stub cannot be called 'alive'. Two conditions,
    chosen so the gate is neither hollow nor poisoned (R1 review):
      - the SYNTHESIS tier (the deep, insight-bearing cognition that produces the
        reflections the zombie test reads) must have run for real and NEVER fallen
        back — a single silent synthesise fallback means the reflections may be stub;
      - the run overall must be >=90% real, so wholesale degradation fails even if
        synthesise happened to succeed, while one cheap-surface blip does not.
    A pure StubModelProvider has no telemetry -> False (it IS the zombie)."""
    tel = getattr(provider, "telemetry", None)
    if not isinstance(tel, dict):
        return False
    synth = tel["by_method"].get("synthesise", {"real": 0, "fallback": 0})
    if synth["real"] == 0 or synth["fallback"] > 0:
        return False
    return provider.real_fraction >= _REAL_FRACTION_FLOOR


def make_models(name: str = "stub", **kwargs) -> ModelProvider:
    """Factory for selecting a provider by name (used by the runtime/CLI)."""
    if name == "anthropic":
        return AnthropicModelProvider(**kwargs)
    return StubModelProvider()
