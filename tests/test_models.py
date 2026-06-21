import json
import tempfile

from meno import AnthropicModelProvider, Config, Meno, StubModelProvider


# --- a minimal fake of the Anthropic client (no network) ---
class _Block:
    def __init__(self, type, text=""):
        self.type = type
        self.text = text


class _Msg:
    def __init__(self, blocks):
        self.content = blocks


class _Messages:
    def __init__(self, handler):
        self._handler = handler
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._handler(kwargs)


class FakeClient:
    def __init__(self, handler):
        self.messages = _Messages(handler)


def _tiered_handler(kwargs):
    """Route by model id, mimicking each tier's response shape."""
    model = kwargs["model"]
    if model == "claude-haiku-4-5":      # Tier 1 — structured appraisal JSON
        return _Msg([_Block("text", json.dumps(
            {"label": "topic", "reaction": "noted topic", "question": "what does it mean?"}))])
    if model == "claude-sonnet-4-6":     # Tier 2 — association text
        return _Msg([_Block("text", "this connects to the earlier idea")])
    if model == "claude-opus-4-8":       # Tier 3 — thinking block (empty) + reflection text
        return _Msg([_Block("thinking", ""), _Block("text", "a synthesised reflection about it")])
    raise AssertionError(f"unexpected model {model}")


def test_tier_model_ids_are_current():
    assert AnthropicModelProvider.TIER_MODELS == {
        1: "claude-haiku-4-5", 2: "claude-sonnet-4-6", 3: "claude-opus-4-8"}


def test_unavailable_provider_falls_back_to_stub():
    p = AnthropicModelProvider(client=None)
    # no injected client and (in test env) no key -> not available -> stub behaviour
    if not p.available:
        assert p.appraise("hello world", 0.9) == StubModelProvider().appraise("hello world", 0.9)


def test_appraise_parses_structured_json():
    p = AnthropicModelProvider(client=FakeClient(_tiered_handler))
    res = p.appraise("the database dropped", 0.9)
    assert res["reaction"] == "noted topic"
    assert res["question"] == "what does it mean?"
    assert res["label"] == "topic"
    call = p._client.messages.calls[0]
    assert call["model"] == "claude-haiku-4-5"
    assert "format" in call["output_config"]          # structured output requested


def test_appraise_empty_question_becomes_none():
    def handler(kwargs):
        return _Msg([_Block("text", json.dumps(
            {"label": "x", "reaction": "noted", "question": ""}))])
    p = AnthropicModelProvider(client=FakeClient(handler))
    assert p.appraise("x", 0.1)["question"] is None


def test_synthesise_uses_adaptive_thinking_and_extracts_text():
    p = AnthropicModelProvider(client=FakeClient(_tiered_handler))
    out = p.synthesise("an occasion", ["one", "two"])
    assert out == "a synthesised reflection about it"   # thinking block ignored
    call = p._client.messages.calls[0]
    assert call["model"] == "claude-opus-4-8"
    assert call["thinking"] == {"type": "adaptive"}     # no budget_tokens
    assert "effort" in call["output_config"]


def test_associate_returns_text_from_sonnet():
    p = AnthropicModelProvider(client=FakeClient(_tiered_handler))
    assert p.associate("a thread", ["a memory"]) == "this connects to the earlier idea"
    assert p._client.messages.calls[0]["model"] == "claude-sonnet-4-6"


def test_any_error_falls_back_to_stub():
    def boom(kwargs):
        raise RuntimeError("network down")
    p = AnthropicModelProvider(client=FakeClient(boom))
    # falls back to deterministic stub rather than raising
    assert p.appraise("hello world", 0.9)["reaction"].startswith("noted")
    assert isinstance(p.synthesise("o", ["m"]), str)


def test_meno_runs_end_to_end_with_real_shaped_provider():
    provider = AnthropicModelProvider(client=FakeClient(_tiered_handler))
    mind = Meno(config=Config(stream_match_threshold=0.2), models=provider,
                workspace=tempfile.mkdtemp(prefix="meno_anthropic_"))
    for s in ["memory reconstruction recall idea one",
              "memory reconstruction recall idea two",
              "memory reconstruction recall idea three"]:
        mind.feed(s)
        mind.run_until_quiescent()
    mind.heartbeat()
    assert mind.snapshot()["reflections"] >= 1
    r = mind.recall("memory reconstruction recall")
    assert r["mode"] in ("reconstructed", "ghost")
    # a reflection reconstructed through the real-shaped provider carries its text
    if r["mode"] == "reconstructed":
        assert "reflection" in r["text"].lower()
