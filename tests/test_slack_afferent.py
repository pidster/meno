"""Phase I1 — Slack afferent channel (sense-only).

Percepts flow from listed-and-joined Slack channels into the loop, bounded and
consented like R4's FilesystemSensor. Offline/deterministic via a fake Slack client;
the real slack_sdk path is live-gated (no token here). NO send path exists in I1.
"""
import tempfile

import pytest

from meno import Config, Driver, Meno, StubModelProvider
from meno.event import Kind
from meno_adapters import SlackAdapter


def _tsf(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


class FakeSlack:
    """Minimal stand-in for slack_sdk.WebClient: membership + channel history. Filters
    `oldest` NUMERICALLY, as the real API does (ts are unix timestamps)."""
    def __init__(self, joined, history):
        self._joined = list(joined)              # channel ids the bot has joined
        self._history = dict(history)            # {channel_id: [message dicts]}
        self.membership_calls = 0
        self.calls = []

    def users_conversations(self, **kw):
        self.membership_calls += 1
        return {"channels": [{"id": c} for c in self._joined]}

    def conversations_history(self, channel, oldest="0", limit=10):
        self.calls.append((channel, oldest, limit))
        msgs = [m for m in self._history.get(channel, []) if _tsf(m.get("ts", "0")) > _tsf(oldest)]
        return {"messages": list(reversed(msgs))[:limit]}   # Slack returns newest-first


def _msg(ts, text, user="U_alice", **extra):
    return {"ts": ts, "text": text, "user": user, **extra}


def _adapter(joined, history, **kw):
    return SlackAdapter(client=FakeSlack(joined, history), **kw)


# --- consent/scope: only listed AND joined channels are ever read ----------------- #
def test_message_from_a_listed_and_joined_channel_becomes_a_percept():
    ad = _adapter(["C_meno"], {"C_meno": [_msg("100", "hello team")]}, channels=["C_meno"])
    out = ad.poll()
    assert len(out) == 1
    text, source, payload = out[0]
    assert source == "slack" and "hello team" in text
    assert payload["channel"] == "C_meno" and payload["ts"] == "100"


def test_a_listed_but_not_joined_channel_yields_nothing():
    # operator listed C_secret, but the bot was never invited (not in joined)
    ad = _adapter(["C_meno"], {"C_secret": [_msg("100", "should never be read")]},
                  channels=["C_meno", "C_secret"])
    assert ad.poll() == []


def test_a_joined_but_not_listed_channel_yields_nothing():
    ad = _adapter(["C_meno", "C_random"], {"C_random": [_msg("100", "off-limits")]},
                  channels=["C_meno"])   # C_random joined but not listed
    assert ad.poll() == []


# --- privacy: secrets redacted; the bot's own posts skipped (self-echo) ----------- #
def test_secrets_in_a_message_are_redacted_before_becoming_a_percept():
    ad = _adapter(["C_meno"], {"C_meno": [_msg("100", "the key is password=hunter2secret ok")]},
                  channels=["C_meno"])
    text = ad.poll()[0][0]
    assert "[redacted]" in text and "hunter2secret" not in text


def test_the_bots_own_messages_are_skipped():
    hist = {"C_meno": [_msg("100", "i am the bot", user="U_bot"),
                       _msg("200", "a human speaks", user="U_alice")]}
    ad = _adapter(["C_meno"], hist, channels=["C_meno"], bot_user_id="U_bot")
    out = ad.poll()
    assert len(out) == 1 and "human" in out[0][0]


def test_a_secret_straddling_the_size_cap_is_still_redacted():
    """Redaction runs BEFORE truncation, so a secret that begins inside max_chars but
    extends past it cannot survive as a leaked fragment."""
    body = "x" * 20 + " password=supersecretvalue12345"   # secret straddles a 30-char cap
    ad = _adapter(["C_meno"], {"C_meno": [_msg("100", body)]}, channels=["C_meno"], max_chars=30)
    text = ad.poll()[0][0]
    assert "password=" not in text and "supersecret" not in text


def test_redacts_aws_keys_private_keys_jwts_and_pii():
    cases = {
        "aws": "deploy with AKIAIOSFODNN7EXAMPLE now",
        "pk": "key:\n-----BEGIN RSA PRIVATE KEY-----\nMIIabc123\n-----END RSA PRIVATE KEY-----",
        "jwt": "bearer eyJhbGciOi.eyJzdWIiOi.SflKxwRJSM here",
        "email": "ping me at alice.smith@example.com please",
        "ssn": "ssn is 123-45-6789 ok",
    }
    hist = {"C_meno": [_msg(str(100 + i), t) for i, t in enumerate(cases.values())]}
    ad = _adapter(["C_meno"], hist, channels=["C_meno"], max_chars=4000, max_per_poll=20)
    blob = " ".join(p[0] for p in ad.poll())
    for leak in ("AKIAIOSFODNN7EXAMPLE", "MIIabc123", "SflKxwRJSM",
                 "alice.smith@example.com", "123-45-6789"):
        assert leak not in blob, leak


def test_ts_width_crossing_is_ordered_numerically_not_lexically():
    """'100' > '99' numerically but '100' < '99' as strings — the cursor must use
    numbers, or a message after a width boundary is silently dropped."""
    hist = {"C_meno": [_msg("99", "earlier")]}
    ad = _adapter(["C_meno"], hist, channels=["C_meno"])
    assert len(ad.poll()) == 1                    # reads "99", cursor -> 99
    hist["C_meno"].append(_msg("100", "later, across the width boundary"))
    out = ad.poll()
    assert len(out) == 1 and "later" in out[0][0]  # 100 > 99 numerically -> delivered


def test_membership_is_ttl_cached_not_refetched_every_poll():
    fake = FakeSlack(["C_meno"], {"C_meno": [_msg("100", "a"), _msg("200", "b")]})
    ad = SlackAdapter(client=fake, channels=["C_meno"], membership_ttl=120.0)
    ad.poll(); ad.poll(); ad.poll()
    assert fake.membership_calls == 1             # one lookup, not one per poll (rate-budget)


def test_membership_lookup_failure_fails_closed_then_keeps_last_known():
    class Flaky(FakeSlack):
        fail = False
        def users_conversations(self, **kw):
            if self.fail:
                raise RuntimeError("429 rate limited")
            return super().users_conversations(**kw)
    fake = Flaky(["C_meno"], {"C_meno": [_msg("100", "hi")]})
    fake.fail = True
    ad = SlackAdapter(client=fake, channels=["C_meno"], membership_ttl=0.0)
    assert ad.poll() == [] and ad.errors >= 1     # no prior knowledge -> fail CLOSED
    fake.fail = False
    assert len(ad.poll()) == 1                     # recovers once the API is back


# --- resource: size + per-poll bounds; new-only (cursor dedup) -------------------- #
def test_oversized_message_is_truncated():
    long = "x" * 500
    ad = _adapter(["C_meno"], {"C_meno": [_msg("100", long)]}, channels=["C_meno"], max_chars=20)
    text = ad.poll()[0][0]
    assert text.count("x") <= 20


def test_at_most_max_per_poll_messages_are_emitted():
    hist = {"C_meno": [_msg(str(100 + i), f"m{i}") for i in range(20)]}
    ad = _adapter(["C_meno"], hist, channels=["C_meno"], max_per_poll=3)
    assert len(ad.poll()) == 3


def test_a_message_is_not_re_emitted_on_the_next_poll():
    hist = {"C_meno": [_msg("100", "first")]}
    ad = _adapter(["C_meno"], hist, channels=["C_meno"])
    assert len(ad.poll()) == 1
    assert ad.poll() == []                       # cursor advanced; nothing new
    hist["C_meno"].append(_msg("200", "second"))
    out = ad.poll()
    assert len(out) == 1 and "second" in out[0][0]


# --- I1 is SENSE-ONLY: there is no send path ------------------------------------- #
def test_no_efferent_send_path_exists():
    ad = _adapter(["C_meno"], {}, channels=["C_meno"])
    assert ad.handles("post") is False and ad.handles("anything") is False
    with pytest.raises(NotImplementedError):     # no deliver() — posting is I2, behind the gate
        ad.deliver({"action": "post"})


def test_adapter_is_inert_without_a_client():
    ad = SlackAdapter(channels=["C_meno"])       # no client, no token -> not available
    assert ad.available is False and ad.poll() == []


def test_source_has_no_slack_write_call():
    """A static guard: until I2's gate exists, no write/post API call may sneak into the
    afferent adapter. The only Slack methods used are reads."""
    import pathlib
    import meno_adapters.slack as mod
    src = pathlib.Path(mod.__file__).read_text().lower()
    for write_method in ("postmessage", "chat_post", "files_upload", "conversations_open",
                         "chat_update", "chat.post"):
        assert write_method not in src, write_method


# --- integration: a Slack message flows into the loop as a SENSE percept ---------- #
def test_slack_percept_flows_into_the_mind_through_the_driver():
    mind = Meno(config=Config(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_i1_"))
    driver = Driver(mind, sleep=lambda _: None)
    driver.add_adapter(_adapter(["C_meno"], {"C_meno": [_msg("100", "a thought from the channel")]},
                                channels=["C_meno"]))
    driver.run(max_cycles=1)
    hits = [e for e in mind.bus.log if e.source == "slack"]
    assert hits and hits[0].kind == Kind.SENSE and "channel" in hits[0].content
