"""Phase S — the self-model, and its three disciplines (docs/roadmap-ii.md).

Offline and deterministic. The live cache-hit confirmation (cache_read_input_tokens
> 0 on the deep tiers) is the S-exit smoke, gated on a funded key — not here.
"""
import importlib
import tempfile

import pytest

from meno import Config, Meno, StubModelProvider
from meno.aliveness import PASS, output_divergence
from meno.models import AnthropicModelProvider, _DEPTH
from meno.self_model import (MENO_SELF, MENO_SELF_BRIEF, SELF_MODEL_CLAIMS,
                             IDENTITY_DENYLIST, EARNED_NOT_GIVEN, self_model)


def _live_available() -> bool:
    """A funded key + importable SDK — the live anti-convergence guard runs only then
    (like the S-exit cache smoke). Never fails the offline suite."""
    try:
        return AnthropicModelProvider().available
    except Exception:
        return False


# --- a client that captures the request kwargs (so we can inspect system=) ------ #
class _Block:
    def __init__(self, text): self.type = "text"; self.text = text


class _Msg:
    def __init__(self, text): self.content = [_Block(text)]


class _Messages:
    def __init__(self, calls): self.calls = calls

    def create(self, **kw):
        self.calls.append(kw)
        fmt = (kw.get("output_config") or {}).get("format")
        if fmt:                                   # a structured surface
            props = fmt["schema"]["properties"]
            if "related" in props:
                return _Msg('{"related": true}')
            if "mode" in props:
                return _Msg('{"mode": "internal", "thought": "t", "path": ""}')
            return _Msg('{"label": "x", "reaction": "y", "question": ""}')
        return _Msg("ok")                         # a free-text surface


class FakeClient:
    def __init__(self): self.calls = []; self.messages = _Messages(self.calls)


def _exercise_all_surfaces():
    """Drive every surface once, in a fixed order, returning the captured calls."""
    c = FakeClient()
    p = AnthropicModelProvider(client=c)
    p.appraise("hello", 0.6)              # reflexive (brief)
    p.relate("a", "b")                    # reflexive (brief)
    p.associate("s", ["r"])              # deep (full)
    p.synthesise("occ", ["m"])           # deep (full)
    p.wonder("w", referent=None)          # deep (full)
    return c.calls


_ORDER = ["appraise", "relate", "associate", "synthesise", "wonder"]


# --- the cache-control wiring + correct depth per surface ----------------------- #
def test_each_surface_carries_the_correct_self_block_with_the_breakpoint_on_deep_only():
    calls = _exercise_all_surfaces()
    assert len(calls) == len(_ORDER)
    for surface, call in zip(_ORDER, calls):
        blocks = call["system"]
        # system is a content-block LIST, not a plain string — required for cache_control
        assert isinstance(blocks, list) and len(blocks) == 2, surface
        deep = _DEPTH[surface]
        assert blocks[0]["text"] == (MENO_SELF if deep else MENO_SELF_BRIEF), surface
        # the cache breakpoint is on the deep path only: the ~180-token brief is below
        # every model's min-cacheable floor, so a breakpoint there could only no-op.
        if deep:
            assert blocks[0]["cache_control"] == {"type": "ephemeral"}, surface
        else:
            assert "cache_control" not in blocks[0], surface
        # the surface-specific role line follows, after any breakpoint, and is never
        # itself a breakpoint (that would split the cacheable prefix)
        assert blocks[1]["text"] and blocks[1]["text"] != blocks[0]["text"], surface
        assert "cache_control" not in blocks[1], surface


def test_deep_surfaces_share_one_identical_prefix_string():
    """Byte-identical prefixes are NECESSARY for cross-surface caching (this asserts
    that), but not SUFFICIENT: caches are model-scoped, so the realised hit is only
    associate<->wonder (both Sonnet); synthesise (Opus, below its 4096 floor) caches
    nothing yet. That is a property of the live API, confirmed at the S-exit smoke —
    not provable here. This test checks only the prefix STRING is shared."""
    calls = {s: c for s, c in zip(_ORDER, _exercise_all_surfaces())}
    deep_prefixes = {calls[s]["system"][0]["text"] for s in ("associate", "synthesise", "wonder")}
    reflexive_prefixes = {calls[s]["system"][0]["text"] for s in ("appraise", "relate")}
    assert deep_prefixes == {MENO_SELF}
    assert reflexive_prefixes == {MENO_SELF_BRIEF}


def test_accessor_returns_full_for_deep_and_brief_for_reflexive():
    assert self_model(True) == MENO_SELF
    assert self_model(False) == MENO_SELF_BRIEF
    assert "escalate" in MENO_SELF_BRIEF.lower()   # the brief points to escalation, not deep reasoning


# --- discipline 1: mechanics, not meaning (no planted disposition) -------------- #
def test_self_model_carries_no_identity_or_disposition():
    for name, text in (("MENO_SELF", MENO_SELF), ("MENO_SELF_BRIEF", MENO_SELF_BRIEF)):
        low = text.lower()
        hits = [t for t in IDENTITY_DENYLIST if t in low]
        assert not hits, f"{name} carries prescriptive/affective tokens: {hits}"


# --- discipline 3 (staging): no capability the current phase has not built ------- #
def test_self_model_claims_no_unbuilt_capability():
    low_full, low_brief = MENO_SELF.lower(), MENO_SELF_BRIEF.lower()
    hits = [t for t in EARNED_NOT_GIVEN if t in low_full or t in low_brief]
    assert not hits, f"self-model claims not-yet-built capabilities (earned, not given): {hits}"


# --- discipline 3: true to the implementation (every claim maps to a real symbol) - #
def _resolve(spec: str):
    mod, _, attr = spec.partition(":")
    obj = importlib.import_module(mod)
    for part in attr.split("."):
        obj = getattr(obj, part)
    return obj


def test_every_claimed_capability_appears_in_the_text_and_maps_to_a_kernel_symbol():
    for phrase, symbol in SELF_MODEL_CLAIMS:
        assert phrase in MENO_SELF, f"claim phrase absent from self-model: {phrase!r}"
        try:
            _resolve(symbol)
        except (ImportError, AttributeError) as exc:
            raise AssertionError(f"claim {phrase!r} -> {symbol} does not resolve: {exc}")


def test_directional_claims_match_the_kernel_values_not_just_names():
    """A name resolving proves only that an attribute exists — not that the text
    describes it TRUTHFULLY. For every claim that asserts a *direction*, check the
    kernel value actually points that way, so an inverted description ('edges decay
    slower than nodes') fails the build rather than passing on name-existence."""
    cfg = Config()
    # "Edges decay faster than nodes" / "decay far more slowly"
    assert cfg.edge_decay < cfg.node_decay, (cfg.edge_decay, cfg.node_decay)
    # "inherits only a fraction of its parent's activation" -> strictly damped
    assert 0.0 < cfg.activation_inherit < 1.0, cfg.activation_inherit
    # "accumulates pressure" -> pressure grows (positive increment)
    assert cfg.pressure_growth > 0.0, cfg.pressure_growth
    # "novelty against the recent run" -> a finite, positive window
    assert cfg.recency_window > 0, cfg.recency_window
    # "recoverable ghost before any release" -> a positive TTL window
    assert cfg.cue_ghost_ttl > 0, cfg.cue_ghost_ttl


# --- the cacheable-prefix floor (proxy; the real count is the S-exit live smoke) -- #
def _approx_tokens(text: str) -> int:
    return len(text) // 4   # conservative ~4 chars/token for clean English prose


# --- the standing guard's second axis: anti-convergence (introduced in S) -------- #
def _mind(contents):
    m = Meno(config=Config(), models=StubModelProvider(),
             workspace=tempfile.mkdtemp(prefix="meno_s_"))
    ids = [m.graph.add_node(c).id for c in contents]
    for a, b in zip(ids, ids[1:]):
        m.graph.link(a, b)
    cue = m.graph.store_cue(ids[:2], "the same shared occasion", tone=0.5,
                            conclusion="", material=contents[:2])
    return m, cue


def _outputs(m, cue):
    return [m.graph.reconstruct(cue, m.models, reconsolidate=False)]


def test_substrate_vocabulary_survives_a_shared_occasion():
    """The MECHANISM behind anti-convergence, offline: two minds over the SAME
    occasion but DIFFERENT graphs produce divergent output, while same-graph minds
    converge. This proves substrate drives voice — necessary, but NOT the full guard.

    What it does NOT test (and must not be read as testing): whether the shared
    *self-model prompt* homogenises voice. The stub ignores `system=` entirely, so the
    Phase-S artifact never enters this path; the divergence here is pure node
    vocabulary. The real anti-convergence guard — does MENO_SELF make two
    different-graph minds *sound* alike under real cognition — is the panel-judged
    litmus (roadmap-ii.md) and the key-gated live test below. Do not certify the
    prompt-homogenisation risk on this test's green."""
    otters = ["otters raft together while sleeping", "kelp anchors the floating raft"]
    aqueduct = ["roman aqueducts moved water by gradient", "concrete set underwater in harbours"]
    ma, ca = _mind(otters)
    mb, cb = _mind(aqueduct)
    different = output_divergence(_outputs(ma, ca), _outputs(mb, cb))
    assert different["score"] >= PASS["anti_convergence"], different

    mc, cc = _mind(otters)                       # same substrate as ma
    same = output_divergence(_outputs(ma, ca), _outputs(mc, cc))
    assert same["score"] < PASS["anti_convergence"], same


def test_self_model_does_not_animate_the_stub():
    """Standing guard (offline): wiring the self-model must not make a stub-driven mind
    read as alive. Cognition is not real (stub) -> the verdict is at most
    'indeterminate', never 'alive'. If this ever returns 'alive', the self-model has
    smuggled the appearance of life into the prompt — the exact Phase-S failure."""
    from meno.aliveness import zombie_report
    m, cue = _mind(["a memory of the sea", "a memory of stone"])
    m.graph.reconstruct(cue, m.models, reconsolidate=False)
    report = zombie_report(m, cognition_real=False)
    assert report["verdict"] != "alive", report


@pytest.mark.skipif(not _live_available(), reason="no funded ANTHROPIC_API_KEY")
def test_shared_self_model_does_not_homogenise_voice_live():
    """The REAL anti-convergence guard (key-gated, like the cache smoke). Two minds
    with genuinely different graphs, the SAME percept, both carrying the full
    self-model: their generated reflections must still diverge. A low score here means
    the shared self-model flattened two substrates into one voice — identity leaking
    into the prompt. This is the binding check the offline test cannot perform."""
    from meno import AnthropicModelProvider
    p = AnthropicModelProvider()
    occasion = "what stays when much is forgotten"
    sea = ["otters raft together while sleeping", "kelp anchors the floating raft"]
    rome = ["roman aqueducts moved water by gradient", "concrete set underwater in harbours"]
    out_a = [p.synthesise(occasion, sea)]
    out_b = [p.synthesise(occasion, rome)]
    if p.degraded:
        pytest.skip(f"cognition degraded mid-test: {p.telemetry['last_error']}")
    div = output_divergence(out_a, out_b)
    assert div["score"] >= PASS["anti_convergence"], div


def test_full_self_model_clears_the_sonnet_cache_floor():
    """A PROXY (len//4), and deliberately a weaker bar than the roadmap's S outline
    (which targets count_tokens >= 4096 on Opus). We can only assert the Sonnet floor
    (2048) offline: the real BPE count needs the API, and len//4 tends to over-count
    clean prose, so the true Opus margin is unknown and plausibly still under 4096.
    What that means concretely: associate + wonder (Sonnet) cache; synthesise (Opus)
    does NOT yet (model-scoped, sub-floor). The binding check is the S-exit live smoke
    (real count_tokens + cache_read_input_tokens>0), not this proxy. The Opus 4096
    target is NOT met by padding — only by genuine mechanism, or it stays deferred.
    The brief is deliberately tiny (reflexive tiers are cheap; no cache needed)."""
    assert _approx_tokens(MENO_SELF) >= 2048
    assert _approx_tokens(MENO_SELF_BRIEF) < 512
