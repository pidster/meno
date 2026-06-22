"""Phase I2 — Slack gated effector (outward action). The highest-stakes phase.

Every layer of the gate must REFUSE: disabled by default, out-of-scope channel,
rate limit, confirm-first. Every send is audited. Egress gates the adapter's reach.
The agent's own posts never re-enter as experience (self-echo). Offline/deterministic
with a fake client; the live post path is token+enable gated (deferred).
"""
import json
import tempfile
from pathlib import Path

from meno import (Config, Driver, Meno, StubModelProvider, self_echo_fraction,
                  zombie_report)
from meno.home import EgressPolicy
from meno_adapters import SlackAdapter
from meno_adapters.base import DeliveryResult


class FakeSlack:
    def __init__(self):
        self.posts = []

    def chat_postMessage(self, channel, text):
        self.posts.append((channel, text))
        return {"ok": True, "ts": "100"}

    # afferent stubs (so a combined adapter can also poll)
    def users_conversations(self, **kw):
        return {"channels": [{"id": "C_meno"}]}

    def conversations_history(self, channel, oldest="0", limit=10):
        return {"messages": []}


def _eff(fake, **kw):
    kw.setdefault("enabled", True)
    kw.setdefault("post_channels", ["C_meno"])
    kw.setdefault("confirm", False)
    return SlackAdapter(client=fake, **kw)


def _post(channel="C_meno", text="hello world", **extra):
    return {"action": "post", "channel": channel, "text": text, **extra}


# --- the gate: every layer fails SAFE (refuse) ----------------------------------- #
def test_disabled_by_default_posts_nothing():
    fake = FakeSlack()
    ad = SlackAdapter(client=fake, post_channels=["C_meno"])   # enabled defaults to False
    res = ad.deliver(_post())
    assert res.status == "refused" and res.reason == "disabled"
    assert fake.posts == []                                    # nothing sent


def test_a_post_to_an_out_of_scope_channel_is_refused():
    fake = FakeSlack()
    ad = _eff(fake, post_channels=["C_meno"])
    res = ad.deliver(_post(channel="C_secret"))
    assert res.status == "refused" and res.reason == "scope"
    assert fake.posts == []


def test_rate_limit_refuses_the_n_plus_first_send():
    fake = FakeSlack()
    ad = _eff(fake, rate_per_min=2)
    assert ad.deliver(_post(text="1")).status == "delivered"
    assert ad.deliver(_post(text="2")).status == "delivered"
    third = ad.deliver(_post(text="3"))
    assert third.status == "refused" and third.reason == "rate"
    assert len(fake.posts) == 2                                # the 3rd never went out


def test_confirm_first_sends_nothing_until_approved():
    fake = FakeSlack()
    ad = _eff(fake, confirm=True)
    res = ad.deliver(_post(text="awaiting"))
    assert res.status == "pending" and fake.posts == []        # NOT sent yet
    token = next(iter(ad._pending))
    done = ad.confirm_send(token)
    assert done.status == "delivered" and fake.posts == [("C_meno", "awaiting")]  # sent on approval


def test_the_mind_cannot_self_approve_a_confirm_first_post():
    """The security property: confirm-first is an OPERATOR gate. A `confirmed` flag in
    the mind-authored intent must be ignored — only confirm_send approves."""
    fake = FakeSlack()
    ad = _eff(fake, confirm=True)
    res = ad.deliver(_post(text="trying to self-approve", confirmed=True))   # mind sets the flag
    assert res.status == "pending" and fake.posts == []                      # still NOT sent


# --- confirm-first re-validates the gate (no back door around scope/rate/enabled) -- #
def test_confirm_send_revalidates_against_current_config():
    """A pending post must be re-gated at approval time — config that narrowed
    (disabled/scope/rate) between author and approve still blocks the stale post."""
    fake = FakeSlack()
    ad = _eff(fake, confirm=True)
    token = next(iter((ad.deliver(_post(text="queued")), ad._pending)[1]))
    ad.enabled = False                                  # operator disables before approving
    done = ad.confirm_send(token)
    assert done.status == "refused" and done.reason == "disabled"
    assert fake.posts == []                             # the stale pending post did NOT go out


def test_pending_store_is_bounded():
    fake = FakeSlack()
    ad = _eff(fake, confirm=True)
    ad.max_pending = 3
    for i in range(3):
        assert ad.deliver(_post(text=f"m{i}")).status == "pending"
    overflow = ad.deliver(_post(text="one too many"))
    assert overflow.status == "refused" and overflow.reason == "pending-overflow"


# --- every gate DECISION is audited, not just successes -------------------------- #
def test_every_send_is_audited(tmp_path):
    fake = FakeSlack()
    audit = tmp_path / "journal" / "traces" / "sends.jsonl"
    ad = _eff(fake, audit_path=audit)
    ad.deliver(_post(text="for the record"))
    rec = json.loads(audit.read_text().strip())
    assert rec["channel"] == "C_meno" and rec["text"] == "for the record"
    assert rec["action"] == "post" and rec["outcome"] == "delivered" and "ts" in rec


def test_refused_attempts_are_audited_too(tmp_path):
    """The highest-value security event — 'Meno tried to post out of scope' — must
    leave a durable trace, not only successful sends."""
    fake = FakeSlack()
    audit = tmp_path / "sends.jsonl"
    ad = _eff(fake, post_channels=["C_meno"], audit_path=audit)
    ad.deliver(_post(channel="C_secret"))               # out of scope -> refused
    rec = json.loads(audit.read_text().strip())
    assert rec["outcome"] == "scope" and rec["channel"] == "C_secret" and fake.posts == []


# --- egress gates the adapter's declared reach (slack.com) before any post -------- #
def test_egress_refuses_the_post_before_the_adapter_runs():
    fake = FakeSlack()
    mind = Meno(config=Config(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_i2_"))
    driver = Driver(mind, sleep=lambda _: None, egress=EgressPolicy(allow=()))  # deny all
    ad = _eff(fake)
    driver.add_adapter(ad)
    mind.outbox.put(_post())                                    # no host field — egress checks ad.hosts
    assert driver.drain_outbox_once() is False
    assert fake.posts == [] and driver.egress_denied == 1       # refused before deliver()
    assert ad.hosts == ("slack.com", "*.slack.com")


def test_egress_allows_the_post_when_slack_is_allowlisted():
    fake = FakeSlack()
    mind = Meno(config=Config(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_i2_"))
    driver = Driver(mind, sleep=lambda _: None, egress=EgressPolicy(allow=("*.slack.com", "slack.com")))
    driver.add_adapter(_eff(fake))
    mind.outbox.put(_post(text="cleared"))
    driver.drain_outbox_once()
    assert fake.posts == [("C_meno", "cleared")] and driver.egress_denied == 0


# --- self-echo: the agent's own voice must not re-enter as experience ------------- #
def test_own_posts_are_skipped_on_re_read():
    fake = FakeSlack()
    ad = SlackAdapter(client=fake, channels=["C_meno"], bot_user_id="U_bot")
    fake.conversations_history = lambda channel, oldest="0", limit=10: {"messages": [
        {"ts": "100", "text": "a thing meno posted", "user": "U_bot"},
        {"ts": "200", "text": "a human reply", "user": "U_alice"}]}
    out = ad.poll()
    assert len(out) == 1 and "human" in out[0][0]               # our own post dropped


def test_short_own_output_does_not_false_flag_external_percepts():
    """A 1–3 word ack must not substring-match a genuinely external message (the
    false-positive the min-length guard closes)."""
    m = Meno(config=Config(), models=StubModelProvider(), workspace=tempfile.mkdtemp())
    m.graph.add_node("the weather is bad and the harbour is rough tonight",
                     meta={"source": "slack", "external": True})
    r = self_echo_fraction(m, ["ok", "thanks", "yes the weather"])   # short -> ignored
    assert r["echoed"] == 0 and r["score"] == 0.0


def test_self_echo_fraction_detects_own_output_in_the_graph():
    m = Meno(config=Config(), models=StubModelProvider(), workspace=tempfile.mkdtemp())
    m.graph.add_node("the weather turned cold over the harbour",
                     meta={"source": "slack", "external": True})        # genuinely external
    m.graph.add_node("slack #C_meno: I am not the water but the shape I keep making",
                     meta={"source": "slack", "external": True})        # an echo of our own post
    own = ["I am not the water but the shape I keep making"]
    r = self_echo_fraction(m, own)
    assert r["external_nodes"] == 2 and r["echoed"] == 1 and r["score"] == 0.5


def test_zombie_verdict_flags_echo_inflated_particularity():
    """If most 'external' experience is the agent's own echo, particularity is
    manufactured — the verdict must NOT read alive even with cognition real."""
    m = Meno(config=Config(), models=StubModelProvider(), workspace=tempfile.mkdtemp())
    for i in range(4):
        m.graph.add_node(f"echo number {i} of my own voice",
                         meta={"source": "self:slack", "external": True})
    own = [f"echo number {i} of my own voice" for i in range(4)]
    report = zombie_report(m, own_outputs=own, cognition_real=True)
    assert report["marks"]["self_echo"]["score"] > 0.20
    assert "self_echo" in report["failed_marks"] and report["verdict"] != "alive"


def test_clean_run_passes_the_self_echo_guard():
    m = Meno(config=Config(), models=StubModelProvider(), workspace=tempfile.mkdtemp())
    m.graph.add_node("a genuinely external thought from the world",
                     meta={"source": "slack", "external": True})
    report = zombie_report(m, own_outputs=["nothing the agent ever said"], cognition_real=True)
    assert report["marks"]["self_echo"]["score"] == 0.0
    assert "self_echo" not in report["failed_marks"]


# --- the slow post runs OFF the mind thread (cognition isn't blocked) ------------- #
def test_a_slow_post_runs_off_the_mind_thread_and_does_not_block_cognition():
    import threading
    import time as _t
    gate = threading.Event()
    fake = FakeSlack()
    _orig = fake.chat_postMessage
    fake.chat_postMessage = lambda channel, text: (gate.wait(timeout=5), _orig(channel, text))[1]
    mind = Meno(config=Config(), models=StubModelProvider(), workspace=tempfile.mkdtemp())
    driver = Driver(mind, sleep=_t.sleep, idle_backoff=0.001, max_backoff=0.01,
                    egress=EgressPolicy(allow=("slack.com", "*.slack.com")))
    driver.add_adapter(_eff(fake))
    driver.start()
    try:
        mind.outbox.put(_post(text="slow post"))
        c0 = driver.cycles                              # worker now blocked in chat_postMessage
        deadline = _t.time() + 2.0
        while _t.time() < deadline and driver.cycles < c0 + 2:
            _t.sleep(0.005)
        assert driver.cycles >= c0 + 2, "the slow post blocked the mind loop"
    finally:
        gate.set()
        driver.stop()
    assert fake.posts == [("C_meno", "slow post")]      # it did go out, off-thread


# --- the SDK stays out of the kernel; inert without a client --------------------- #
def test_effector_is_inert_without_a_client():
    ad = SlackAdapter(channels=["C_meno"], enabled=True, post_channels=["C_meno"], confirm=False)
    assert ad.available is False
    res = ad.deliver({"action": "post", "channel": "C_meno", "text": "x"})
    # no client -> the send raises inside _send and is caught as a refusal, never a crash
    assert isinstance(res, DeliveryResult) and res.status == "refused"
