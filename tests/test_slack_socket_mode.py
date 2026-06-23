"""Phase I1+ — Slack afferent via Socket Mode (real-time Events API, no public endpoint).

Socket Mode dials an OUTBOUND WebSocket from the app to Slack, so events arrive in
real time with no public Request URL — the same egress-only shape as the rest of meno
(D21). It supersedes polling. The WebSocket plumbing (start/_on_request) needs
slack_sdk + the app-level token + a network, so it's live-gated; the dispatch logic
(_handle_event) is pure and tested directly with the SAME bounds as the poll path:
consent (operator-listed channel), self-echo (skip our own/bot posts), redaction.
"""
import tempfile

import pytest

from meno import Config, Driver, Meno, StubModelProvider
from meno.event import Kind
from meno_adapters import SlackAdapter


class FakeDriver:
    """Stand-in for the Driver's thread-safe inbox: records what Socket Mode pushed."""
    def __init__(self):
        self.fed = []

    def feed(self, text, source="sensor", **payload):
        self.fed.append((text, source, payload))


def _event(text, channel="C_meno", user="U_alice", type="message", **extra):
    return {"type": type, "channel": channel, "user": user, "text": text, "ts": "100.5", **extra}


def _socket_adapter(channels=("C_meno",), **kw):
    # No client needed: _handle_event is pure dispatch. bot_user_id given so __init__
    # never calls auth_test. socket_mode on so poll() steps aside for the push path.
    ad = SlackAdapter(channels=channels, socket_mode=True, bot_user_id="U_bot", **kw)
    return ad


# --- consent: only operator-listed channels are ever fed -------------------------- #
def test_socket_event_in_a_listed_channel_is_fed_as_a_percept():
    ad, drv = _socket_adapter(), FakeDriver()
    ad._driver = drv
    ad._handle_event(_event("hello over the websocket"))
    assert len(drv.fed) == 1
    text, source, payload = drv.fed[0]
    assert source == "slack" and "hello over the websocket" in text
    assert payload["channel"] == "C_meno" and payload["ts"] == "100.5"
    assert payload["user"] == "U_alice" and ad.events == 1


def test_socket_event_from_an_unlisted_channel_is_dropped():
    ad, drv = _socket_adapter(channels=("C_meno",)), FakeDriver()
    ad._driver = drv
    ad._handle_event(_event("off-limits", channel="C_random"))   # joined upstream, not listed
    assert drv.fed == [] and ad.events == 0


# --- self-echo: our own / bot posts never re-enter (matches the poll path) -------- #
def test_socket_skips_our_own_posts_and_bot_messages():
    ad, drv = _socket_adapter(), FakeDriver()
    ad._driver = drv
    ad._handle_event(_event("i am meno speaking", user="U_bot"))          # our own id
    ad._handle_event(_event("a different bot", subtype="bot_message"))    # any bot
    ad._handle_event(_event("a human speaks", user="U_alice"))
    assert len(drv.fed) == 1 and "human" in drv.fed[0][0]


# --- privacy: redaction runs on the push path too --------------------------------- #
def test_socket_redacts_secrets_before_they_become_a_percept():
    ad, drv = _socket_adapter(), FakeDriver()
    ad._driver = drv
    ad._handle_event(_event("the key is password=hunter2secret ok"))
    text = drv.fed[0][0]
    assert "[redacted]" in text and "hunter2secret" not in text


def test_socket_redacts_before_truncating_so_a_straddling_secret_cannot_leak():
    ad, drv = _socket_adapter(max_chars=30), FakeDriver()
    ad._driver = drv
    ad._handle_event(_event("x" * 20 + " password=supersecretvalue12345"))
    text = drv.fed[0][0]
    assert "password=" not in text and "supersecret" not in text


# --- which events we act on: messages + mentions; nothing else -------------------- #
def test_app_mention_events_are_handled():
    ad, drv = _socket_adapter(), FakeDriver()
    ad._driver = drv
    ad._handle_event(_event("@meno what do you think?", type="app_mention"))
    assert len(drv.fed) == 1 and "what do you think" in drv.fed[0][0]


def test_non_message_events_are_ignored():
    ad, drv = _socket_adapter(), FakeDriver()
    ad._driver = drv
    ad._handle_event(_event("👍", type="reaction_added"))
    ad._handle_event({"type": "channel_joined", "channel": "C_meno"})
    assert drv.fed == []


def test_a_malformed_event_does_not_crash_the_listener():
    ad, drv = _socket_adapter(), FakeDriver()
    ad._driver = drv
    ad._handle_event({})                       # no type/channel/text
    assert drv.fed == []


# --- self-echo robustness: edits and any bot-authored post never re-enter ---------- #
def test_socket_drops_subtyped_events_so_an_edit_cannot_bypass_self_echo():
    """A `message_changed` edit carries the real author/body NESTED under event['message'],
    so the top-level self-echo guard can't see them — meno editing its own message could
    otherwise re-enter. Dropping all subtyped events closes that bypass."""
    ad, drv = _socket_adapter(), FakeDriver()
    ad._driver = drv
    ad._handle_event({"type": "message", "subtype": "message_changed", "channel": "C_meno",
                      "message": {"user": "U_bot", "text": "edited by meno"}})
    ad._handle_event({"type": "message", "subtype": "channel_join", "channel": "C_meno",
                      "user": "U_alice", "text": "has joined"})
    assert drv.fed == [] and ad.events == 0


def test_socket_skips_any_bot_authored_message_even_when_our_own_id_is_unknown():
    """If auth_test failed, bot_user_id is None and meno's own posts arrive WITHOUT the
    bot_message subtype — but every bot-authored message carries a `bot_id`, which the
    self-echo guard now also honours. So the echo is dropped without knowing our id."""
    ad = SlackAdapter(channels=["C_meno"], socket_mode=True)   # no client -> bot_user_id None
    assert ad.bot_user_id is None
    drv = FakeDriver()
    ad._driver = drv
    ad._handle_event(_event("posted by a bot", bot_id="B999"))
    assert drv.fed == []


def test_poll_and_socket_emit_identical_content_for_the_same_message():
    """The two afferent paths share `_shape`, so the SAME raw message must yield a
    byte-identical percept body either way — redaction, truncation, formatting alike.
    This pins the parity rather than trusting that both happen to work."""
    raw = "leak password=hunter2secret then " + "x" * 40

    class FakeSlack:
        def users_conversations(self, **kw):
            return {"channels": [{"id": "C_meno"}]}
        def conversations_history(self, channel, oldest="0", limit=10):
            return {"messages": [{"ts": "100", "text": raw, "user": "U_alice"}]}
    poll_ad = SlackAdapter(client=FakeSlack(), channels=["C_meno"], bot_user_id="U_bot", max_chars=25)
    poll_body = poll_ad.poll()[0][0]

    sock_ad = SlackAdapter(channels=["C_meno"], socket_mode=True, bot_user_id="U_bot", max_chars=25)
    drv = FakeDriver()
    sock_ad._driver = drv
    sock_ad._handle_event({"type": "message", "channel": "C_meno", "user": "U_alice", "text": raw})
    sock_body = drv.fed[0][0]

    assert poll_body == sock_body
    assert "[redacted]" in sock_body and "hunter2secret" not in sock_body


def test_an_event_arriving_before_start_wires_the_driver_is_dropped_safely():
    ad = _socket_adapter()                       # _driver is None until start()
    ad._handle_event(_event("arrived before start()"))
    assert ad.events == 0                         # no crash, nothing fed


# --- the listener wrapper: ack/dispatch/dedup, tested offline (no slack_sdk needed) - #
class _Req:
    def __init__(self, payload, type="events_api", envelope_id="e1"):
        self.type, self.payload, self.envelope_id = type, payload, envelope_id


class _Client:
    def __init__(self, fail=False):
        self.acked, self._fail = [], fail

    def send_socket_mode_response(self, resp):
        if self._fail:
            raise RuntimeError("ack boom")
        self.acked.append(resp)


def test_on_request_dispatches_an_events_api_envelope():
    ad, drv = _socket_adapter(), FakeDriver()
    ad._driver = drv
    ad._on_request(_Client(), _Req({"event_id": "Ev1", "event": _event("pushed via on_request")}))
    assert len(drv.fed) == 1 and "pushed via on_request" in drv.fed[0][0]


def test_on_request_ignores_non_events_api_envelopes():
    ad, drv = _socket_adapter(), FakeDriver()
    ad._driver = drv
    ad._on_request(_Client(), _Req({"event_id": "Ev2", "event": _event("nope")}, type="slash_commands"))
    assert drv.fed == []


def test_on_request_dedups_a_redelivered_event_id():
    ad, drv = _socket_adapter(), FakeDriver()
    ad._driver = drv
    req = _Req({"event_id": "Ev3", "event": _event("delivered twice")})
    ad._on_request(_Client(), req)
    ad._on_request(_Client(), req)               # Slack resends same event_id on reconnect/ack-resend
    assert len(drv.fed) == 1                      # handled exactly once


def test_on_request_ack_failure_is_recorded_but_the_event_still_dispatches():
    ad, drv = _socket_adapter(), FakeDriver()
    ad._driver = drv
    ad._on_request(_Client(fail=True), _Req({"event_id": "Ev4", "event": _event("survives ack failure")}))
    assert len(drv.fed) == 1 and ad.errors >= 1  # not lost; a resend would dedup, not double


# --- Socket Mode supersedes polling: the two afferent paths don't double-read ----- #
def test_socket_mode_suppresses_polling():
    class FakeSlack:
        def users_conversations(self, **kw):
            return {"channels": [{"id": "C_meno"}]}
        def conversations_history(self, channel, oldest="0", limit=10):
            return {"messages": [{"ts": "100", "text": "would be polled", "user": "U_a"}]}
    ad = SlackAdapter(client=FakeSlack(), channels=["C_meno"],
                      socket_mode=True, bot_user_id="U_bot")
    assert ad.available is True                 # a real client is present...
    assert ad.poll() == []                      # ...yet poll() steps aside for the push path


# --- start()/stop(): inert and safe when unconfigured ----------------------------- #
def test_start_is_a_noop_when_socket_mode_is_off():
    ad = SlackAdapter(channels=["C_meno"])      # socket_mode defaults off
    drv = FakeDriver()
    ad.start(drv)                               # must not raise, must not open a socket
    assert ad._driver is drv and ad._socket_client is None and ad.errors == 0


def test_start_without_an_app_token_stays_deaf_but_does_not_crash(monkeypatch):
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)

    class FakeSlack:                            # available, but no app-level token to dial out
        def auth_test(self):
            return {"user_id": "U_bot"}
    ad = SlackAdapter(client=FakeSlack(), channels=["C_meno"], socket_mode=True)
    drv = FakeDriver()
    ad.start(drv)                               # records the gap, does not raise
    assert ad._socket_client is None and ad.errors >= 1 and ad._driver is drv
    ad.stop()                                   # idempotent / safe with nothing open


# --- integration: a Socket Mode event flows into the loop as a SENSE percept ------ #
def test_socket_event_flows_into_the_mind_through_the_driver():
    mind = Meno(config=Config(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_socket_"))
    driver = Driver(mind, sleep=lambda _: None)
    ad = _socket_adapter()
    driver.add_adapter(ad)
    ad.start(driver)                            # socket_mode on, no token -> sets _driver, stays deaf
    ad._handle_event(_event("a thought arriving in real time"))   # simulate the WS push
    driver.run(max_cycles=1)
    hits = [e for e in mind.bus.log if e.source == "slack"]
    assert hits and hits[0].kind == Kind.SENSE and "real time" in hits[0].content
