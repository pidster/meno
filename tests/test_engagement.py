"""Phase I3 — engagement: meno reacts to being ADDRESSED (D35/D36).

Being addressed is a percept; reacting to it can flow outward. Meno is not a chatbot —
it weighs whether it has something earned to say and MAY stay silent. Addressed-ness is
graded: structural cues (an @mention) are 'directed' (certain); a lexical cue (its name +
a question) is a soft 'possibly'; everything else is 'ambient' (sensed, never replied).
A reply is an outward POST intent through the gated effector. Offline/deterministic.
"""
import tempfile

from meno import Config, Driver, Meno, StubModelProvider
from meno.home import EgressPolicy
from meno_adapters import SlackAdapter


def _mind(**kw):
    return Meno(config=Config(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_i3_"), name=kw.pop("name", "meno"))


class FakeDriver:
    def __init__(self):
        self.fed = []

    def feed(self, text, source="sensor", **payload):
        self.fed.append((text, source, payload))


def _adapter():
    ad = SlackAdapter(channels=(), bot_user_id="U_bot", name="meno")
    ad._driver = FakeDriver()
    return ad


# --- afferent: how directed at meno is a percept? (the three bands) ---------------- #
def test_an_at_mention_is_directed():
    ad = _adapter()
    ad._handle_event({"type": "app_mention", "channel": "C_t", "user": "U_a",
                      "text": "<@U_bot> what do you remember?", "ts": "1.0"})
    text, src, payload = ad._driver.fed[0]
    assert payload["addressed"] == "directed"
    assert payload["reply_to"]["channel"] == "C_t" and payload["reply_to"]["user"] == "U_a"


def test_a_named_question_without_an_at_is_possibly():
    ad = _adapter()
    ad._handle_event({"type": "message", "channel": "C_t", "user": "U_a",
                      "text": "meno, do you recall the otters?", "ts": "1.0"})
    assert ad._driver.fed[0][2]["addressed"] == "possibly"


def test_a_dm_is_directed_every_message():
    ad = _adapter()
    ad._handle_event({"type": "message", "channel": "D_99", "channel_type": "im",
                      "user": "U_a", "text": "no @ here, but it's a DM", "ts": "1.0"})
    assert ad._driver.fed[0][2]["addressed"] == "directed"


def test_a_one_to_one_channel_is_directed_every_message():
    # a channel whose only members are meno + one other is effectively a DM
    class FakeMembers:
        def conversations_members(self, channel, limit=100, cursor=None):
            return {"members": ["U_bot", "U_a"]}        # exactly two
    ad = SlackAdapter(client=FakeMembers(), channels=(), bot_user_id="U_bot", name="meno")
    ad._driver = FakeDriver()
    ad._handle_event({"type": "message", "channel": "C_pair", "user": "U_a",
                      "text": "just us two here", "ts": "1.0"})
    assert ad._driver.fed[0][2]["addressed"] == "directed"


def test_a_busy_channel_is_not_treated_as_one_to_one():
    class FakeMembers:
        def conversations_members(self, channel, limit=100, cursor=None):
            return {"members": ["U_bot", "U_a", "U_b", "U_c"]}   # many -> not 1:1
    ad = SlackAdapter(client=FakeMembers(), channels=(), bot_user_id="U_bot", name="meno")
    ad._driver = FakeDriver()
    ad._handle_event({"type": "message", "channel": "C_busy", "user": "U_a",
                      "text": "lovely weather", "ts": "1.0"})
    assert ad._driver.fed[0][2]["addressed"] == "ambient"


def test_plain_channel_chatter_is_ambient():
    ad = _adapter()
    ad._handle_event({"type": "message", "channel": "C_t", "user": "U_a",
                      "text": "lovely weather we're having", "ts": "1.0"})
    assert ad._driver.fed[0][2]["addressed"] == "ambient"


def test_a_message_that_at_mentions_us_is_skipped_so_we_dont_react_twice():
    # the @mention also arrives as an app_mention event; the message-event copy is dropped
    ad = _adapter()
    ad._handle_event({"type": "message", "channel": "C_t", "user": "U_a",
                      "text": "<@U_bot> hi there", "ts": "1.0"})
    assert ad._driver.fed == []


# --- the respond judgment (stub): may-not-must ------------------------------------ #
def test_stub_respond_turns_toward_a_direct_address_but_not_a_soft_one():
    p = StubModelProvider()
    assert p.respond({"addressed": "directed", "text": "hi", "actor": "U_a"})["speak"] is True
    assert p.respond({"addressed": "possibly", "text": "meno?", "actor": "U_a"})["speak"] is False
    # the base provider stays silent by default (engagement is opt-in cognition)
    from meno.models import ModelProvider
    assert ModelProvider().respond({"addressed": "directed"})["speak"] is False


# --- the engagement loop: a directed percept becomes a gated POST intent ----------- #
def _drain_outbox(mind):
    out = []
    while not mind.outbox.empty():
        out.append(mind.outbox.get_nowait())
    return out


def test_a_directed_percept_produces_a_post_intent():
    mind = _mind()
    mind.feed("hey meno", source="slack", addressed="directed",
              reply_to={"channel": "C_t", "user": "U_a", "thread_ts": "1.0"})
    mind.run_until_quiescent()
    posts = [p for p in _drain_outbox(mind) if p.get("action") == "post"]
    assert posts and posts[0]["channel"] == "C_t" and posts[0]["egress"] is True
    assert posts[0]["thread_ts"] == "1.0" and "U_a" in posts[0]["text"]   # threads + addresses


def test_a_possibly_percept_is_left_silent_by_the_stub():
    mind = _mind()
    mind.feed("meno?", source="slack", addressed="possibly",
              reply_to={"channel": "C_t", "user": "U_a", "thread_ts": "1.0"})
    mind.run_until_quiescent()
    assert [p for p in _drain_outbox(mind) if p.get("action") == "post"] == []


def test_ambient_percepts_never_engage():
    mind = _mind()
    mind.feed("just chatting", source="slack", addressed="ambient",
              reply_to={"channel": "C_t", "user": "U_a"})
    mind.run_until_quiescent()
    assert _drain_outbox(mind) == []


def test_per_cycle_engage_budget_bounds_the_reply_burst():
    # a burst of @mentions in one pass can't each fire a paid respond call (I3 review P1)
    mind = _mind()
    mind.engage_budget = 2                            # only two replies composable this pass
    for i in range(5):
        mind.feed(f"hey meno {i}", source="slack", addressed="directed",
                  reply_to={"channel": "C_t", "user": f"U_{i}", "thread_ts": f"{i}.0"})
    mind.run_until_quiescent()
    posts = [p for p in _drain_outbox(mind) if p.get("action") == "post"]
    assert len(posts) == 2                            # bounded to the budget, not all five


def test_engagement_is_withheld_while_throttled():
    mind = _mind()
    mind.throttled = True                            # the cost governor has tripped (D32)
    mind.feed("hey meno", source="slack", addressed="directed",
              reply_to={"channel": "C_t", "user": "U_a", "thread_ts": "1.0"})
    mind.run_until_quiescent()
    assert _drain_outbox(mind) == []                 # no reply composed while throttled


# --- end to end: addressed -> reply -> gated effector (dry-run, not posted) -------- #
def test_a_reply_flows_through_the_gated_effector_in_dry_run(tmp_path):
    import json
    mind = _mind()
    driver = Driver(mind, sleep=lambda _: None,
                    egress=EgressPolicy(allow=("slack.com", "*.slack.com")))
    audit = tmp_path / "sends.jsonl"
    ad = SlackAdapter(channels=(), name="meno", bot_user_id="U_bot",
                      enabled=True, post_channels=["C_t"], dry_run=True, audit_path=audit)
    driver.add_adapter(ad)
    driver.feed("slack #C_t: hey meno", source="slack", addressed="directed",
                reply_to={"channel": "C_t", "user": "U_a", "thread_ts": "1.0"})
    driver.run(max_cycles=4)
    recs = [json.loads(line) for line in audit.read_text().splitlines()]
    assert any(r["outcome"] == "dry-run" and r["channel"] == "C_t" for r in recs)  # composed, diverted
