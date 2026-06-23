"""Token / cost accounting (D39): meno tracks what its real cognition spends.

Every real model call is metered (input/output + prompt-cache tokens, dollar cost at the
model's rate); the cumulative total is surfaced in status.json `health.usage` and persisted
so it survives restarts. Offline providers spend nothing. No network — fake usage objects.
"""
import json
from types import SimpleNamespace

from meno.models import AnthropicModelProvider, StubModelProvider, _call_cost


def _usage(inp, out, cr=0, cw=0):
    return SimpleNamespace(usage=SimpleNamespace(
        input_tokens=inp, output_tokens=out,
        cache_read_input_tokens=cr, cache_creation_input_tokens=cw))


# --- the cost function: per-model rates, cache discounts ---------------------------- #
def test_call_cost_uses_per_model_rates_and_cache_pricing():
    assert abs(_call_cost("claude-sonnet-4-6", 1000, 500, 0, 0) - 0.0105) < 1e-9   # 3+7.5 /1k
    assert abs(_call_cost("claude-opus-4-8", 1000, 1000, 0, 0) - 0.030) < 1e-9     # 5+25
    assert abs(_call_cost("claude-haiku-4-5", 0, 0, 1000, 0) - 0.0001) < 1e-9      # cache read 0.1x
    assert abs(_call_cost("claude-haiku-4-5", 0, 0, 0, 1000) - 0.00125) < 1e-9     # cache write 1.25x


# --- metering accumulates tokens + cost, attributed by model ----------------------- #
def test_meter_accumulates_tokens_and_cost_by_model():
    p = AnthropicModelProvider()                      # no key -> no client, but _meter is pure
    p._meter("claude-sonnet-4-6", _usage(1000, 500))
    p._meter("claude-haiku-4-5", _usage(200, 100, cr=50))
    s = p.usage_summary()
    assert s["input_tokens"] == 1200 and s["output_tokens"] == 600
    assert s["cache_read_tokens"] == 50 and s["cost_usd"] > 0
    assert set(s["by_model"]) == {"claude-sonnet-4-6", "claude-haiku-4-5"}
    assert s["by_model"]["claude-sonnet-4-6"]["calls"] == 1


def test_meter_is_safe_when_a_response_has_no_usage():
    p = AnthropicModelProvider()
    p._meter("claude-sonnet-4-6", SimpleNamespace())  # no .usage at all
    assert p.usage_summary()["input_tokens"] == 0     # never breaks cognition


def test_offline_providers_report_zero_spend():
    s = StubModelProvider().usage_summary()
    assert s["cost_usd"] == 0.0 and s["input_tokens"] == 0 and s["output_tokens"] == 0


# --- persistence: cumulative cost survives a restart ------------------------------- #
def test_usage_persists_and_is_seeded_across_a_restart(tmp_path, monkeypatch):
    from meno.home import build_instance, init_home
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-dummy")   # selects the anthropic provider
    home = init_home(tmp_path / "inst")
    (home / "meno.toml").write_text('[cognition]\nprovider = "anthropic"\n')

    inst = build_instance(home)
    inst.mind.models._meter("claude-sonnet-4-6", _usage(1000, 500))   # simulate spend this run
    inst.write_status()
    saved = json.loads((home / "run" / "usage.json").read_text())
    assert saved["input"] == 1000 and saved["cost_usd"] > 0

    # a fresh process binds the same home and resumes the cumulative total
    woken = build_instance(home)
    assert woken.mind.models.usage["input"] == 1000          # seeded from disk
    woken.mind.models._meter("claude-sonnet-4-6", _usage(500, 0))
    assert woken.mind.models.usage["input"] == 1500          # accumulates on top


def test_status_health_carries_the_usage_summary(tmp_path, monkeypatch):
    from meno.home import build_instance, init_home
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-dummy")
    home = init_home(tmp_path / "inst")
    (home / "meno.toml").write_text('[cognition]\nprovider = "anthropic"\n')
    inst = build_instance(home)
    inst.mind.models._meter("claude-opus-4-8", _usage(2000, 800))
    inst.write_status()
    data = json.loads(inst.status_path.read_text())
    u = data["health"]["usage"]
    assert u["input_tokens"] == 2000 and u["output_tokens"] == 800 and u["cost_usd"] > 0
