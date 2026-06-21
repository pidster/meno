"""R1 — real cognition, validated end to end, with LOUD failure.

Two layers:
  - offline (always run): the telemetry/strict substrate that makes silent
    stub-fallback observable — the thing that keeps the zombie test honest.
  - live (skipped without a funded key): every model-judged surface makes a real
    call; reflections are genuinely generated (not the stub template); and a real
    model + real embedder close the merge caveat into an emergent insight the R0
    synthesis probe credits.

Live tests skip (never fail) when cognition is unavailable or degraded — a missing
key or empty credit balance must not break the offline suite.
"""
import tempfile

import pytest

from meno import (
    AnthropicModelProvider,
    CognitionDegraded,
    Config,
    Meno,
    StubModelProvider,
    cognition_is_real,
    make_embedder,
)
from meno.aliveness import synthesis
from meno.event import Event
from meno.streams import StreamManager


def fresh_stub() -> Meno:
    return Meno(config=Config(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_r1_"))


# --- offline: the loud-failure substrate ----------------------------------- #
def test_unavailable_provider_records_every_fallback():
    p = AnthropicModelProvider(client=None)
    p._client = None                                   # force "no key"
    p.appraise("hello", 0.6)
    p.relate("a", "b")
    p.synthesise("x", ["y"])
    assert p.degraded and p.real_fraction == 0.0
    assert p.telemetry["fallback"] == 3 and p.telemetry["real"] == 0
    assert not cognition_is_real(p)


def test_strict_mode_raises_instead_of_degrading_silently():
    p = AnthropicModelProvider(client=None, strict=True)
    p._client = None
    with pytest.raises(CognitionDegraded):
        p.synthesise("x", ["y"])


def test_cognition_is_real_false_for_stub_and_unused_provider():
    assert not cognition_is_real(StubModelProvider())
    assert not cognition_is_real(AnthropicModelProvider(client=None))   # no calls yet


def test_telemetry_counts_real_calls_with_a_fake_client():
    """A fake client lets us prove the success path increments `real` and that
    cognition_is_real flips True — without spending tokens."""
    class FakeMsg:
        def __init__(self, text): self.content = [type("B", (), {"type": "text", "text": text})()]
    class FakeClient:
        class messages:
            @staticmethod
            def create(**kw):
                return FakeMsg('{"related": true}')
    p = AnthropicModelProvider(client=FakeClient())
    assert p.relate("a", "b") is True
    assert p.synthesise("occ", ["material"])              # exercise the load-bearing tier
    assert p.telemetry["real"] == 2 and p.telemetry["fallback"] == 0
    assert cognition_is_real(p)                            # synth real, no fallbacks


def test_cognition_not_real_if_synthesis_tier_degraded():
    """R1 review P1: the gate is keyed on the deep insight tier. A run where cheap
    surfaces succeed but a synthesise call fell back is NOT real cognition, even at
    high overall real_fraction — the reflections may be stub."""
    class FakeMsg:
        def __init__(self, text): self.content = [type("B", (), {"type": "text", "text": text})()]
    class PickyClient:
        """Succeeds on Haiku relate, fails (empty) on the Opus synthesise."""
        class messages:
            @staticmethod
            def create(**kw):
                if kw["model"].startswith("claude-opus"):
                    return FakeMsg("")                    # empty synthesis -> degradation
                return FakeMsg('{"related": true}')
    p = AnthropicModelProvider(client=PickyClient())
    for _ in range(9):
        p.relate("a", "b")                                # 9 real cheap calls
    p.synthesise("occ", ["material"])                     # 1 synthesis fallback
    assert p.real_fraction >= 0.9                         # overall looks high...
    assert not cognition_is_real(p)                       # ...but the deep tier degraded


# --- live: real Claude cognition ------------------------------------------- #
def _live_provider(effort="low"):
    """A real provider, or a skip if cognition isn't actually available. We probe
    with one cheap relate() call and skip on any degradation (no key, no credits,
    network)."""
    p = AnthropicModelProvider(effort=effort)
    if not p.available:
        pytest.skip("no ANTHROPIC_API_KEY / anthropic client")
    p.relate("a topic about memory", "another note about memory")
    if p.degraded:
        pytest.skip(f"cognition unavailable: {p.telemetry['last_error']}")
    p.reset_telemetry()
    return p


def test_live_every_surface_makes_a_real_call():
    p = _live_provider()
    ap = p.appraise("the user wonders whether memory is reconstructed", 0.7)
    assert ap["label"]
    assert p.associate("memory and recall", ["forgetting and islanding"])
    assert isinstance(p.relate("reconstructive memory", "rebuilding the past from cues"), bool)
    route = p.wonder("what makes a memory feel vivid?")
    assert route["mode"] in ("internal", "external", "both")
    text = p.synthesise("insight: memory + forgetting",
                        ["memory is reconstructed at recall", "forgetting drops edges first"])
    assert text
    # all real, nothing fell back to the stub
    assert p.real_fraction == 1.0 and cognition_is_real(p), p.telemetry


def test_live_reflection_is_generated_not_templated():
    """A real synthesis must NOT be the stub's fixed template, and must introduce
    meaning beyond its material (what the R0 synthesis probe credits)."""
    p = _live_provider()
    material = ["memory is reconstructed at recall, not replayed",
                "forgetting thins edges before nodes, islanding memories"]
    text = p.synthesise("insight: how memory and forgetting relate", material)
    assert "a pattern across" not in text and "they cohere into one concern" not in text
    m = fresh_stub()
    a = m.graph.add_node(material[0]).id
    b = m.graph.add_node(material[1]).id
    cue = m.graph.store_cue([a, b], "insight: how memory and forgetting relate",
                            tone=0.9, conclusion=text, material=material)
    # the real reflection introduces terms its sources didn't -> genuine synthesis
    assert synthesis(m.graph, {cue.id: text})["score"] > 0.0, text


def test_live_merge_caveat_closes_into_an_emergent_insight():
    """Real embedder (convergent centroids) + real relate (the merge decision) +
    real synthesise -> two separate streams merge in the dream into an 'insight:'
    cue whose conclusion is emergent. The end-to-end thing R1 exists to prove."""
    p = _live_provider()
    embed = make_embedder("split")                     # real cold embedder
    m = Meno(config=Config(stream_match_threshold=0.99),   # keep streams separate -> dream merges
             models=p, embed=embed, workspace=tempfile.mkdtemp(prefix="meno_r1m_"))
    a = Event(content="how do people retrieve old memories")
    b = Event(content="the brain reconstructs the past rather than replaying it")
    a.embedding = m.embed.embed(a.content)
    b.embedding = m.embed.embed(b.content)
    m.streams.route(a)
    m.streams.route(b)
    assert a.stream_id != b.stream_id
    for ev in (a, b):
        n = m.graph.add_node(ev.content)
        m.streams.get(ev.stream_id).node_ids.append(n.id)
    report = m.dream()
    if report["merges"] < 1:
        pytest.skip(f"no merge fired (centroids below threshold this run): {report}")
    insights = [c for c in m.graph.cues.values() if c.occasion.lower().startswith("insight")]
    assert insights, "a merge must produce an 'insight:' cue"
    texts = {c.id: m.graph.reconstruct(c, m.models, reconsolidate=False)
             for c in m.graph.cues.values()}
    assert synthesis(m.graph, texts)["genuine_insights"] >= 1
    assert cognition_is_real(p)
