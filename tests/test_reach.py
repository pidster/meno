"""Phase I4 — reach: meno speaking UNPROMPTED, on its own initiative (D38).

The highest-stakes capability — speech no one asked for — so it is quiet by default and
gated harder than replies: its own toggle (off), its own dry-run, abstract targets the
adapter resolves to channels (the mind never holds channel ids), and a per-DAY rate.
Offline/deterministic.
"""
import json
import tempfile

from meno import Config, Driver, Meno, StubModelProvider
from meno.event import Kind
from meno.home import EgressPolicy
from meno.models import ModelProvider
from meno_adapters import SlackAdapter


def _mind(**kw):
    return Meno(config=Config(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_i4_"), name="meno")


class FakeSlack:
    def __init__(self):
        self.posts = []
    def chat_postMessage(self, channel, text, thread_ts=None):
        self.posts.append((channel, text))
        return {"ok": True}


def _reach_payload(target="operator", text="a thought"):
    return {"action": "reach", "target": target, "text": text}


# --- models.reach: quiet by default, voices something when it has it -------------- #
def test_the_base_provider_never_reaches_out():
    assert ModelProvider().reach({"targets": ["voice"], "curiosity": "x"})["speak"] is False


def test_stub_reaches_only_with_something_to_say_and_somewhere_to_say_it():
    p = StubModelProvider()
    d = p.reach({"targets": ["operator"], "curiosity": "why do otters hold paws?"})
    assert d["speak"] is True and d["target"] == "operator" and "otters" in d["text"]
    assert p.reach({"targets": [], "curiosity": "x"})["speak"] is False          # nowhere
    assert p.reach({"targets": ["voice"], "curiosity": "", "reflection": ""})["speak"] is False  # nothing


# --- Meno.reach(): inert unless armed; emits a gated intent ----------------------- #
def test_reach_is_inert_without_configured_targets():
    mind = _mind()
    mind.curiosities.register("why X?", source="top-down")
    assert mind.reach() is False and mind.outbox.empty()   # no targets -> never reaches


def test_reach_emits_an_outbound_intent_to_a_target():
    mind = _mind()
    mind.reach_targets = ["operator"]
    mind.curiosities.register("why do otters raft together?", source="top-down")
    assert mind.reach() is True
    p = mind.outbox.get_nowait()
    assert p["action"] == "reach" and p["target"] == "operator" and p["text"]


def test_reach_is_withheld_while_throttled():
    mind = _mind()
    mind.reach_targets = ["operator"]
    mind.throttled = True
    mind.curiosities.register("why?", source="top-down")
    assert mind.reach() is False and mind.outbox.empty()   # cost breaker withholds initiative too


def test_reach_with_nothing_on_its_mind_stays_quiet():
    mind = _mind()
    mind.reach_targets = ["voice"]
    assert mind.reach() is False                            # no curiosity/reflection/impulse


# --- the adapter reach gate: own toggle, target resolution, per-day rate, dry-run - #
def test_reach_is_disabled_by_default():
    ad = SlackAdapter(client=FakeSlack(), operator_dm="U_op")   # reach_enabled defaults False
    res = ad.deliver(_reach_payload())
    assert res.status == "refused" and res.reason == "disabled"


def test_reach_resolves_targets_and_refuses_unconfigured_ones():
    fake = FakeSlack()
    ad = SlackAdapter(client=fake, reach_enabled=True, reach_dry_run=False, operator_dm="U_op")
    assert ad.deliver(_reach_payload("operator")).status == "delivered"
    assert fake.posts == [("U_op", "a thought")]               # 'operator' -> the DM user id
    assert ad.deliver(_reach_payload("voice")).reason == "no-target"   # voice not configured


def test_reach_dry_run_diverts_to_the_audit(tmp_path):
    audit = tmp_path / "sends.jsonl"
    fake = FakeSlack()
    ad = SlackAdapter(client=fake, reach_enabled=True, reach_dry_run=True,
                      voice_channel="C_voice", audit_path=audit)
    res = ad.deliver(_reach_payload("voice"))
    assert res.status == "dry-run" and fake.posts == []        # composed, not sent
    rec = json.loads(audit.read_text().strip())
    assert rec["outcome"] == "reach-dry-run" and rec["channel"] == "C_voice"


def test_reach_per_day_rate_keeps_unprompted_speech_sparse():
    fake = FakeSlack()
    ad = SlackAdapter(client=fake, reach_enabled=True, reach_dry_run=False,
                      operator_dm="U_op", reach_per_day=2)
    assert ad.deliver(_reach_payload()).status == "delivered"
    assert ad.deliver(_reach_payload()).status == "delivered"
    third = ad.deliver(_reach_payload())
    assert third.status == "refused" and third.reason == "rate" and len(fake.posts) == 2


def test_reach_redacts_the_outbound_text():
    fake = FakeSlack()
    ad = SlackAdapter(client=fake, reach_enabled=True, reach_dry_run=False, operator_dm="U_op")
    ad.deliver(_reach_payload(text="fyi password=hunter2secret"))
    assert "[redacted]" in fake.posts[0][1] and "hunter2secret" not in fake.posts[0][1]


# --- the loop fix: meno does NOT reflect on its own actions (no re-voicing) -------- #
def test_proprioceptive_action_feedback_is_not_encoded_as_memory():
    mind = _mind()
    n0 = len(mind.graph.nodes)
    # proprioception of its OWN outbound action -> appraised, NOT encoded (else it reflects
    # on its own posts and re-voices them: the reach feedback loop)
    mind.feed("(reach to voice held back — dry-run)", source="slack",
              kind=Kind.FEEDBACK, proprioceptive=True)
    mind.run_until_quiescent()
    assert len(mind.graph.nodes) == n0                # encoded nothing
    # a normal WORLD feedback still DOES become a memory
    mind.feed("the deploy finished cleanly", source="ci", kind=Kind.FEEDBACK)
    mind.run_until_quiescent()
    assert len(mind.graph.nodes) > n0


# --- the loader arms reach from config (adapter + mind targets + driver cadence) -- #
def test_loader_arms_reach_from_config(tmp_path):
    from meno.home import build_instance, init_home
    from meno_adapters.loader import load_adapters
    home = init_home(tmp_path / "inst")
    (home / "adapters" / "slack.toml").write_text(
        '[reach]\nenabled = true\ndry_run = true\noperator_dm = "U_op"\n'
        'voice_channel = "C_voice"\nper_day = 2\nevery = 10\n')
    inst = build_instance(home)
    load_adapters(inst)
    ad = inst.driver.adapters[0]
    assert ad.reach_enabled and ad.operator_dm == "U_op" and ad.voice_channel == "C_voice"
    assert ad.reach_dry_run is True and ad.reach_per_day == 2
    assert set(inst.mind.reach_targets) == {"voice", "operator"} and inst.driver.reach_every == 10


# --- end to end: meno reaches out unprompted through the gated effector (dry-run) -- #
def test_meno_reaches_out_end_to_end_in_dry_run(tmp_path):
    mind = _mind()
    mind.reach_targets = ["operator"]
    mind.curiosities.register("what makes a habit stick?", source="top-down")
    audit = tmp_path / "sends.jsonl"
    driver = Driver(mind, sleep=lambda _: None, reach_every=1,
                    egress=EgressPolicy(allow=("slack.com", "*.slack.com")))
    ad = SlackAdapter(client=FakeSlack(), reach_enabled=True, reach_dry_run=True,
                      operator_dm="U_op", audit_path=audit)
    driver.add_adapter(ad)
    driver.run(max_cycles=2)
    recs = [json.loads(line) for line in audit.read_text().splitlines()]
    assert any(r["outcome"] == "reach-dry-run" for r in recs)   # it reached, diverted to audit
