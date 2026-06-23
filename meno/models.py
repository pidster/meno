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

from .self_model import self_model

_STOP = {"the", "a", "an", "is", "are", "of", "to", "and", "in", "on", "it",
         "this", "that", "i", "you", "for", "with", "what", "why", "how"}


_FACTUAL_FRAMES = ("what is", "what are", "what does", "define ", "definition of",
                   "meaning of", "synonym for", "who is", "when did", "where is")


def looks_factual(text: str) -> bool:
    """A cheap heuristic: does a curiosity ask for a *fact* (look-up-able) rather than
    invite reflection? Distinguishes 'what is the definition of entropy' (lookup) from
    'how do i feel about forgetting' (reconstruct from the substrate). Used by the
    stub's wonder routing so the offline suite can exercise lookup; the real model
    makes the same call in prose."""
    low = (text or "").strip().lower()
    return any(low.startswith(f) or f in low for f in _FACTUAL_FRAMES)


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

    def respond(self, ctx: dict) -> dict:
        """Decide whether to turn toward an interlocutor who addressed meno, and compose a
        reply. ctx = {name, addressed, text, actor, memory}. Returns {speak: bool, text}.
        Default: stay SILENT — engagement is opt-in cognition, never an obligation (I3)."""
        return {"speak": False, "text": ""}

    def reach(self, ctx: dict) -> dict:
        """Self-directed INITIATIVE (I4): no one addressed meno — decide whether it has
        something earned to say UNPROMPTED, and to which target. ctx = {name, curiosity,
        reflection, impulse, targets}. Returns {speak, text, target}. Default: stay quiet
        — reaching out is the highest-stakes act, so the safe base never initiates."""
        return {"speak": False, "text": "", "target": ""}


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
        if looks_factual(text):
            # a factual curiosity -> look it up in the Library (K2). The runtime still
            # owns substrate-first: it only emits this intent when memory can't serve.
            return {"mode": "external", "thought": None,
                    "action": {"action": "lookup", "key": text}}
        if "/" in ref or ref.endswith((".txt", ".md", ".py", ".json", ".log")):
            # a world referent -> reach outward (the Effector will read it)
            return {"mode": "external", "thought": None,
                    "action": {"action": "fs_read", "path": ref}}
        return {"mode": "internal", "thought": f"I wonder: {text}", "action": None}

    def respond(self, ctx: dict) -> dict:
        # deterministic engagement: turn toward a DIRECT address (@mention / DM); stay
        # silent on the soft 'possibly' cue — so response is may-not-must even in the stub.
        # In a 1:1 pane (`must_respond`), never go silent: give a brief honest non-answer.
        who = ctx.get("actor") or "you"
        if ctx.get("addressed") != "directed":
            if ctx.get("must_respond"):
                return {"speak": True,
                        "text": f"I don't have anything earned to say on that yet, {who}, "
                                "but I'm here and listening."}
            return {"speak": False, "text": ""}
        msg = (ctx.get("text") or "").strip()
        return {"speak": True, "text": f"I heard you, {who} — you said: {msg[:120]}"}

    def reach(self, ctx: dict) -> dict:
        # deterministic initiative: voice the strongest thing on its mind to the first
        # available target. The cadence (how often reach is CONSIDERED) and the adapter's
        # reach-rate bound how often this actually goes out; a real model judges sparingly.
        targets = ctx.get("targets") or []
        thing = (ctx.get("curiosity") or ctx.get("reflection") or "").strip()
        if not targets or not thing:
            return {"speak": False, "text": "", "target": ""}
        return {"speak": True, "target": targets[0],
                "text": f"Something I've been turning over: {thing[:160]}"}


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

_RELATE_SYSTEM = ("Decide whether two trains of thought are fundamentally about "
                  "the same matter (and should merge).")

_WONDER_SYSTEM = ("A curiosity has arisen. Decide how to follow it. Respond inward "
                  "(a thought to think), or outward — either look a fact up in your "
                  "library (action 'lookup', target = the term/key) or read a file you "
                  "were given a referent for (action 'fs_read', target = the path) — or "
                  "both. Use 'lookup' for factual questions; think inward for matters of "
                  "perspective. Only propose a file path you were actually given.")

# The role lines above are *surface-specific* and short. Phase S (roadmap-ii.md)
# prepends the shared self-model — what a Meno is and how it operates — as a
# cache-controllable block before each. Deep tiers (associate, synthesise, wonder)
# carry the full self-model; reflexive tiers (appraise, relate) carry the brief one.
_RESPOND_SYSTEM = (
    "Someone has addressed you. You are not a chatbot — you do not owe a reply. Decide "
    "whether to TURN TOWARD them: speak only if you have something earned to say (drawn "
    "from your memory and perspective), otherwise stay silent (speak=false). When you do "
    "speak, be brief, particular, and in your own voice — not a generic assistant. Never "
    "fabricate; if you don't recall something, say so plainly or stay silent.")
_REACH_SYSTEM = (
    "This is your own INITIATIVE — no one addressed you. Reach out only if you have "
    "something genuinely earned to say right now: a curiosity worth voicing, a reflection "
    "worth sharing, an impulse that wants expression. The bar is HIGH and silence is the "
    "default — most of the time, stay quiet (speak=false); reaching out to fill space is a "
    "failure. When you do speak, be brief and in your own voice, and choose the target that "
    "fits: a shared 'voice' space for a thought meant for anyone, the 'operator' to confide "
    "something more personal. Pick a target only from the ones offered. Never fabricate.")
_DEPTH = {"appraise": False, "relate": False, "associate": True, "synthesise": True,
          "wonder": True, "respond": True, "reach": True}


def _system_blocks(role_line: str, deep: bool) -> list:
    """System prompt as content blocks: the self-model first, the surface's role line
    after. A plain `system=` string cannot carry `cache_control`, so the block list
    is what lets the shared self-model prefix be prompt-cached (S).

    Caching is MODEL-SCOPED and has a per-model minimum-cacheable-prefix floor, so the
    realised benefit is narrower than 'one cache across all deep surfaces':
      - associate + wonder run on Sonnet (2048-token floor) and the full self-model
        (~3.4k tokens) clears it — they share ONE Sonnet cache entry. This is the win.
      - synthesise runs on Opus (4096-token floor); the self-model is *below* it, so
        its breakpoint is currently a silent no-op (it caches nothing until the text
        clears 4096 on Opus — confirmed at the S-exit live smoke, never by padding).
      - reflexive tiers carry the ~180-token brief, far below Haiku's 4096 floor, so a
        breakpoint there could only ever no-op — we omit it rather than imply intent.
    The breakpoint is therefore attached only on the deep path."""
    block = {"type": "text", "text": self_model(deep)}
    if deep:
        block["cache_control"] = {"type": "ephemeral"}
    return [block, {"type": "text", "text": role_line}]


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
                system=_system_blocks(_APPRAISE_SYSTEM, _DEPTH["appraise"]),
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
                system=_system_blocks(_ASSOC_SYSTEM, _DEPTH["associate"]),
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
                system=_system_blocks(_SYNTH_SYSTEM, _DEPTH["synthesise"]),
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
                system=_system_blocks(_RELATE_SYSTEM, _DEPTH["relate"]),
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
                max_tokens=512,        # the structured {mode,thought,action,target} JSON; 200 truncated
                system=_system_blocks(_WONDER_SYSTEM, _DEPTH["wonder"]),
                messages=[{"role": "user",
                           "content": f"Curiosity: {text}\nReferent: {referent or '(none)'}"}],
                output_config={"format": {"type": "json_schema", "schema": {
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": ["internal", "external", "both"]},
                        "thought": {"type": "string"},
                        "action": {"type": "string", "enum": ["none", "lookup", "fs_read"]},
                        "target": {"type": "string"}},
                    "required": ["mode", "thought", "action", "target"],
                    "additionalProperties": False}}},
            )
            data = json.loads(self._text(msg))
            mode = data.get("mode", "internal")
            thought = data.get("thought") or None
            act_kind = data.get("action", "none")
            target = (data.get("target") or "").strip()
            # a route must carry what its mode promises, else it is a no-op dressed
            # as cognition -> treat as degradation (R1 review, data lens P1.3)
            if mode in ("internal", "both") and not thought:
                raise ValueError("internal/both route with no thought")
            if mode in ("external", "both") and (act_kind == "none" or not target):
                raise ValueError("external/both route with no action+target")
            action = None
            if act_kind == "lookup" and target:
                action = {"action": "lookup", "key": target}
            elif act_kind == "fs_read" and target:
                action = {"action": "fs_read", "path": target}
            return {"mode": mode, "thought": thought, "action": action}
        return self._run("wonder", real, self.fallback.wonder, (text, referent))

    def respond(self, ctx: dict) -> dict:
        def real():
            mem = ctx.get("memory") or "(nothing specific comes to mind)"
            system = _RESPOND_SYSTEM
            if ctx.get("must_respond"):               # a 1:1 pane the person opened (D37)
                system += (" You are in a 1:1 conversation the person opened, so do NOT stay "
                           "silent: if you have nothing substantive, briefly and honestly say "
                           "so (you may note what is on your mind) — never fabricate. speak=true.")
            msg = self._client.messages.create(
                model=self.TIER_MODELS[2],
                max_tokens=600,
                system=_system_blocks(system, _DEPTH["respond"]),
                messages=[{"role": "user",
                           "content": f"You are {ctx.get('name','meno')}. "
                                      f"{ctx.get('actor','someone')} addressed you "
                                      f"({ctx.get('addressed','directed')}): "
                                      f"{ctx.get('text','')}\n\nWhat you recall:\n{mem}"}],
                output_config={"format": {"type": "json_schema", "schema": {
                    "type": "object",
                    "properties": {"speak": {"type": "boolean"},
                                   "text": {"type": "string"}},
                    "required": ["speak", "text"],
                    "additionalProperties": False}}},
            )
            data = json.loads(self._text(msg))
            speak = bool(data.get("speak"))
            text = (data.get("text") or "").strip()
            if speak and not text:                     # "speak" with nothing to say is a degradation
                raise ValueError("respond=speak with empty text")
            return {"speak": speak, "text": text}
        return self._run("respond", real, self.fallback.respond, (ctx,))

    def reach(self, ctx: dict) -> dict:
        def real():
            targets = ctx.get("targets") or []
            msg = self._client.messages.create(
                model=self.TIER_MODELS[2],
                max_tokens=600,
                system=_system_blocks(_REACH_SYSTEM, _DEPTH["reach"]),
                messages=[{"role": "user", "content":
                           f"You are {ctx.get('name', 'meno')}. Right now —\n"
                           f"a curiosity pulling at you: {ctx.get('curiosity') or '(none)'}\n"
                           f"a recent reflection: {ctx.get('reflection') or '(none)'}\n"
                           f"impulse pressure: {ctx.get('impulse') or '(none)'}\n\n"
                           f"Targets you may reach: {targets}. Is there something earned "
                           "worth saying unprompted right now, and to whom — or stay quiet?"}],
                output_config={"format": {"type": "json_schema", "schema": {
                    "type": "object",
                    "properties": {"speak": {"type": "boolean"}, "text": {"type": "string"},
                                   "target": {"type": "string"}},
                    "required": ["speak", "text", "target"],
                    "additionalProperties": False}}},
            )
            data = json.loads(self._text(msg))
            speak = bool(data.get("speak"))
            text = (data.get("text") or "").strip()
            target = (data.get("target") or "").strip()
            if speak and (not text or target not in targets):
                speak = False                        # invalid target / empty -> stay quiet
            return {"speak": speak, "text": text, "target": target}
        return self._run("reach", real, self.fallback.reach, (ctx,))


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
