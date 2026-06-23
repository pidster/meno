"""Phase I3 — engagement: meno reacts to being ADDRESSED (D35/D36).

Being addressed is a percept; reacting to it can flow outward. Meno is not a chatbot —
it weighs whether it has something earned to say and MAY stay silent. Addressed-ness is
graded: structural cues (an @mention) are 'directed' (certain); a lexical cue (its name +
a question) is a soft 'possibly'; everything else is 'ambient' (sensed, never replied).
A reply is an outward POST intent through the gated effector. Offline/deterministic.
"""
import json
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


def test_a_directed_percept_resolves_the_speakers_display_name():
    class FakeUsers:
        def users_info(self, user):
            return {"user": {"profile": {"display_name": "Pid"}, "real_name": "Pidster"}}
    ad = SlackAdapter(client=FakeUsers(), channels=(), bot_user_id="U_bot", name="meno")
    ad._driver = FakeDriver()
    ad._handle_event({"type": "app_mention", "channel": "C_t", "user": "U01ABC",
                      "text": "<@U_bot> hi", "ts": "1.0"})
    assert ad._driver.fed[0][2]["reply_to"]["user_name"] == "Pid"   # name, not the raw id


def test_name_resolution_falls_back_to_the_mention_token_without_the_scope():
    class NoScope:
        def users_info(self, user):
            raise RuntimeError("missing_scope: users:read")
    ad = SlackAdapter(client=NoScope(), channels=(), bot_user_id="U_bot", name="meno")
    ad._driver = FakeDriver()
    ad._handle_event({"type": "app_mention", "channel": "C_t", "user": "U01ABC",
                      "text": "<@U_bot> hi", "ts": "1.0"})
    # <@id> renders as the person's name in Slack, so a reply still addresses a name
    assert ad._driver.fed[0][2]["reply_to"]["user_name"] == "<@U01ABC>"


def test_ambient_messages_do_not_trigger_a_name_lookup():
    calls = []
    class CountingUsers:
        def users_info(self, user):
            calls.append(user); return {"user": {"name": "x"}}
        def conversations_members(self, channel, limit=100, cursor=None):
            return {"members": ["U_bot", "U_a", "U_b"]}     # busy channel -> not 1:1
    ad = SlackAdapter(client=CountingUsers(), channels=(), bot_user_id="U_bot", name="meno")
    ad._driver = FakeDriver()
    ad._handle_event({"type": "message", "channel": "C_t", "user": "U01ABC",
                      "text": "just chatting", "ts": "1.0"})       # ambient
    assert calls == []                                # no lookup for ambient traffic


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


# --- App Home: a window INTO meno's state of mind (not a percept) ----------------- #
def test_home_view_renders_menos_state():
    mind = _mind()
    mind.feed("otters raft together", source="test")
    mind.run_until_quiescent()
    ad = SlackAdapter(channels=(), name="meno", bot_user_id="U_bot")
    driver = Driver(mind, sleep=lambda _: None)
    driver.add_adapter(ad)                            # gives the adapter its driver/mind
    view = ad._home_view()
    assert view["type"] == "home" and view["blocks"][0]["type"] == "header"
    blob = json.dumps(view)
    # the DISPLAY name is capitalized (Meno) though the handle slug is lowercase (meno)
    assert "Meno" in blob and "@Meno" in blob and "Memories" in blob and "Talk to me" in blob


def test_musings_digests_recent_reflections_and_curiosities():
    mind = _mind()
    mind.graph.store_cue([], "otters rafting in kelp", tone=0.5,
                         conclusion="they hold paws so they don't drift apart",
                         material=["x"], journal=True)          # journaled -> conclusion shows
    mind.graph.store_cue([], "the turning tide", tone=0.4, conclusion="patterns recur",
                         material=["y"])                        # reconstructive -> the topic shows
    mind.curiosities.register("why do otters hold paws?", source="top-down")
    m = mind.musings()
    assert any("hold paws" in r for r in m["reflections"])      # the journaled conclusion
    assert any("tide" in r for r in m["reflections"])           # the reconstructive occasion
    assert any("otters hold paws" in c for c in m["curiosities"])


def test_home_view_shows_the_live_narrative():
    mind = _mind()
    mind.graph.store_cue([], "the shape of a habit", tone=0.5,
                         conclusion="repetition wears a groove", material=["x"], journal=True)
    mind.curiosities.register("what makes a memory stick?", source="top-down")
    driver = Driver(mind, sleep=lambda _: None)
    ad = SlackAdapter(channels=(), name="meno", bot_user_id="U_bot")
    driver.add_adapter(ad)
    ad._driver = driver                               # what start() wires live
    blob = json.dumps(ad._home_view())
    assert "reflecting on" in blob and "repetition wears a groove" in blob   # narrative present
    assert "curious about" in blob and "what makes a memory stick" in blob


def test_home_view_degrades_gracefully_with_no_driver():
    ad = SlackAdapter(channels=(), name="meno")       # no driver attached
    view = ad._home_view()                            # must still render (no crash)
    assert view["type"] == "home"
    assert "—" in json.dumps(view, ensure_ascii=False)   # state fields degrade to a dash


def test_app_home_opened_publishes_the_home_view_and_is_not_a_percept():
    published = {}

    class _Client:
        available = True
        def views_publish(self, user_id, view):
            published["user"], published["view"] = user_id, view
    ad = SlackAdapter(client=_Client(), channels=("C_t",), name="meno", bot_user_id="U_bot")
    drv = FakeDriver()
    ad._driver = drv

    class _Req:
        type = "events_api"; envelope_id = "e1"
        payload = {"event_id": "Ev1",
                   "event": {"type": "app_home_opened", "user": "U_a", "tab": "home"}}

    class _Ack:
        def send_socket_mode_response(self, resp): pass
    ad._on_request(_Ack(), _Req())
    assert published.get("user") == "U_a" and published["view"]["type"] == "home"
    assert drv.fed == []                              # the home-open is NOT sensed as a message


# --- the Assistant pane (I3.5): greet + prompts + title on open ------------------- #
class _AssistantClient:
    def __init__(self):
        self.calls = []
    def assistant_threads_setTitle(self, **kw):           self.calls.append(("title", kw))
    def assistant_threads_setSuggestedPrompts(self, **kw): self.calls.append(("prompts", kw))
    def chat_postMessage(self, **kw):                      self.calls.append(("post", kw))


_ASSIST_EVENT = {"type": "assistant_thread_started",
                 "assistant_thread": {"user_id": "U_a", "channel_id": "D0XYZ",
                                      "thread_ts": "1729.0001"}}


def test_opening_the_assistant_pane_sets_title_and_prompts_and_greets():
    cli = _AssistantClient()
    ad = SlackAdapter(client=cli, channels=(), name="meno", bot_user_id="U_bot",
                      enabled=True, post_channels=[])   # efferent on -> greeting posts
    ad._assistant_started(_ASSIST_EVENT)
    kinds = [c[0] for c in cli.calls]
    assert "title" in kinds and "prompts" in kinds and "post" in kinds
    prompts = next(kw for k, kw in cli.calls if k == "prompts")["prompts"]
    assert any("reflecting" in p["title"].lower() for p in prompts)
    greet = next(kw for k, kw in cli.calls if k == "post")["text"]
    assert "Meno" in greet and greet  # in-voice, names itself
    assert all(kw.get("channel_id") == "D0XYZ" or kw.get("channel") == "D0XYZ"
               for _, kw in cli.calls)                  # all scoped to the pane thread


def test_the_greeting_respects_the_efferent_switch():
    cli = _AssistantClient()
    ad = SlackAdapter(client=cli, channels=(), name="meno", bot_user_id="U_bot")  # enabled=False
    ad._assistant_started(_ASSIST_EVENT)
    kinds = [c[0] for c in cli.calls]
    assert "prompts" in kinds and "title" in kinds       # UI affordances still set...
    assert "post" not in kinds                           # ...but no greeting posted (efferent off)


def test_on_request_dispatches_assistant_thread_started():
    cli = _AssistantClient()
    ad = SlackAdapter(client=cli, channels=(), name="meno", bot_user_id="U_bot", enabled=True)
    drv = FakeDriver()
    ad._driver = drv

    class _Req:
        type = "events_api"; envelope_id = "e1"
        payload = {"event_id": "Ev1", "event": _ASSIST_EVENT}

    class _Ack:
        def send_socket_mode_response(self, resp): pass
    ad._on_request(_Ack(), _Req())
    assert any(k == "prompts" for k, _ in cli.calls)     # the pane was set up
    assert drv.fed == []                                 # opening the pane is NOT a sensed message


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
