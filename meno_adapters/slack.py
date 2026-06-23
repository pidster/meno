"""SlackAdapter — a real Slack channel: afferent (I1) + gated efferent (I2).

AFFERENT (sense). Percepts flow from listed-and-joined Slack channels into the loop,
bounded and consented exactly like R4's FilesystemSensor — the same discipline, a
different world:

  - **consent/scope**: a channel is read ONLY if it is both operator-listed
    (`channels`) AND one the bot has actually joined (membership checked live, then
    TTL-cached). A message from a non-listed or non-joined channel is never seen — the
    agent can't read uninvited. Membership lookup fails CLOSED (read nothing) and, on
    a transient API failure, falls back to last-known rather than going deaf.
  - **privacy**: obvious secrets/PII (tokens, AWS keys, private-key blocks, JWTs,
    `password=…`, emails, SSNs) are redacted BEFORE truncation so a secret can't
    survive by straddling the size cap; the bot's OWN messages are skipped (the
    afferent half of I2's self-echo guard). Redaction is deliberately blunt and
    best-effort (D26) — the operator must not list channels carrying regulated PII.
  - **resource**: text truncated to `max_chars`; at most `max_per_channel` messages
    fetched per channel and `max_per_poll` emitted per poll; only messages NEW since
    the last poll (per-channel ts cursor, compared numerically).

EFFERENT (act, I2/I3). Outward posting is a different risk class, so it is OPT-IN and
gated, every layer failing safe: `enabled=False` by default; `post_channels` scope
(distinct from the read list); a rate limit; the egress boundary; and an append-only
audit of every decision. There is NO per-post approval (D35) — the master `enabled`
toggle, the scope, the rate, the egress allowlist, and the audit ARE the controls;
`dry_run` diverts a post to the audit instead of the channel as a watched-then-live
tuning ramp. Own posts are skipped on re-read (self-echo guard) so Meno's voice never
re-enters as experience.

Concurrency: afferent `poll()` runs on the mind thread, efferent `deliver()` on the
single outbound worker — disjoint state except the advisory `errors` counter, so there
is no race that could send twice or open the gate.

The Slack SDK is imported HERE (meno_adapters), never in the kernel; with no SDK or
token the adapter is inert. With efferent disabled (the default) it is sense-only.
"""
from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path
from typing import List, Optional

from ._redact import redact as _redact
from .base import Adapter, DeliveryResult, Percept
from .secrets import SecretResolver, env_resolver



class SlackAdapter(Adapter):
    name = "slack"
    source = "slack"

    # the network hosts this adapter reaches — declared so the egress boundary gates
    # its REAL reach before any post (D21), not a payload field the mind volunteers.
    hosts = ("slack.com", "*.slack.com")

    def __init__(self, *, client=None, channels=(), bot_user_id: Optional[str] = None,
                 name: str = "meno",        # meno's addressable name, for un-@'d self-recognition (I3)
                 max_chars: int = 2000, max_per_poll: int = 8, max_per_channel: int = 8,
                 membership_ttl: float = 120.0, token_env: str = "SLACK_BOT_TOKEN",
                 # --- afferent via Socket Mode (Events API, no public endpoint) ---
                 socket_mode: bool = False, app_token_env: str = "SLACK_APP_TOKEN",
                 # secrets are resolved by NAME through the composition root's resolver,
                 # never read from cognition; defaults to env-only (prior behaviour):
                 secrets: Optional[SecretResolver] = None,
                 # --- efferent (I2/I3): outward action is OPT-IN and gated ---
                 enabled: bool = False, post_channels=(), dry_run: bool = False,
                 rate_per_min: int = 5, audit_path=None) -> None:
        self._secrets = secrets or env_resolver()   # resolve token NAMES -> values here
        self.channels = tuple(channels)             # afferent allow-list (read)
        self.bot_user_id = bot_user_id              # skip our own posts (self-echo guard)
        self.agent_name = name                      # what meno answers to in un-@'d text (I3)
                                                    # (NOT `self.name` — that's the adapter id "slack")
        self.max_chars = max_chars
        self.max_per_poll = max_per_poll            # global cap on percepts emitted per poll
        self.max_per_channel = max_per_channel      # API fetch limit per channel
        self.membership_ttl = membership_ttl
        self.errors = 0                             # adapter-internal failures (observability)
        self.last_error: Optional[str] = None
        # efferent gate state — DISABLED by default; nothing posts until an operator opts in
        self.enabled = enabled
        self.post_channels = tuple(post_channels)   # efferent allow-list (write) — distinct from read
        self.dry_run = dry_run                      # divert posts to the audit, don't send (tuning ramp)
        self.rate_per_min = rate_per_min
        self.audit_path = Path(audit_path) if audit_path else None
        self.egress = None                          # set by the Driver; checked on the send path
        self._sent_at: deque = deque()              # send timestamps, for the rate window
        self.sent_texts: List[str] = []             # what we posted (self-echo detection)
        self._client = client
        if self._client is None:                    # build a real client only if SDK+token present
            try:  # pragma: no cover - depends on the optional dep + a token
                import slack_sdk  # type: ignore
                bot_token = self._secrets.resolve(token_env)
                if bot_token:
                    self._client = slack_sdk.WebClient(token=bot_token)
            except Exception:
                self._client = None
        if self._client is not None and self.bot_user_id is None:
            try:  # pragma: no cover - live: learn our own id so we reliably skip our echoes
                self.bot_user_id = (self._client.auth_test() or {}).get("user_id")
            except Exception:
                self.bot_user_id = None
        self._cursor: dict = {}                      # channel -> last ts emitted (string, for the API)
        self._joined_cache: Optional[set] = None
        self._joined_at = 0.0
        # Socket Mode (push afferent): real-time Events API over an OUTBOUND WebSocket —
        # no public Request URL. OFF by default; needs an app-level token ($SLACK_APP_TOKEN,
        # scope connections:write) distinct from the bot token. Supersedes polling when on.
        self.socket_mode = socket_mode
        self._app_token_env = app_token_env
        self._socket_client = None
        self._driver = None                          # set in start(); the thread-safe inbox
        self.events = 0                              # Socket Mode events fed (observability)
        self._seen_ids: deque = deque()              # bounded event_id dedup (reconnect resends)
        self._seen_set: set = set()
        self._seen_max = 512

    @property
    def available(self) -> bool:
        return self._client is not None

    def redact(self, text: str) -> str:
        return _redact(text)

    def _record(self, exc: Exception, where: str) -> None:
        self.errors += 1
        # redact the exception text: slack_sdk auth/handshake errors can echo the request
        # (URL, Authorization header, the app token) and last_error surfaces in telemetry.
        self.last_error = _redact(f"slack {where}: {type(exc).__name__}: {exc}")

    def _joined(self) -> set:
        """Channels the bot is a member of — consent: it cannot read a channel it was
        never invited to. TTL-cached (membership changes slowly; re-fetching every poll
        burns Slack's rate budget and would block the mind thread on a 429 retry).
        Paginated. On transient failure, keep last-known rather than going deaf; with no
        prior knowledge, fail CLOSED (empty)."""
        now = time.monotonic()
        if self._joined_cache is not None and now - self._joined_at < self.membership_ttl:
            return self._joined_cache
        try:
            chans: list = []
            cursor = ""
            while True:
                resp = self._client.users_conversations(
                    types="public_channel,private_channel", limit=1000, cursor=cursor or None)
                chans += (resp.get("channels") or [])
                cursor = ((resp.get("response_metadata") or {}).get("next_cursor") or "")
                if not cursor:
                    break
            self._joined_cache = {c["id"] for c in chans}
            self._joined_at = now
            return self._joined_cache
        except Exception as exc:                     # keep last-known; don't blank hearing on a blip
            self._record(exc, "users_conversations")
            return self._joined_cache if self._joined_cache is not None else set()

    def _shape(self, channel, user, subtype, text, bot_id=None) -> Optional[str]:
        """Turn a raw Slack message into a percept body, or None to drop it. Shared by the
        poll path and the Socket Mode push path so BOTH apply the same bounds: skip our
        own / ANY bot's posts (self-echo — `bot_id` catches bot-authored messages even
        when our own user id is unknown, e.g. auth_test failed), redact secrets/PII
        BEFORE truncating to max_chars."""
        if (bot_id or subtype == "bot_message"
                or (self.bot_user_id and user == self.bot_user_id)):
            return None                              # our own / any bot voice never re-enters
        return f"slack #{channel}: {self.redact(text or '')[:self.max_chars]}"

    def poll(self) -> List[Percept]:
        if not self.available or self.socket_mode:   # Socket Mode pushes; don't also poll
            return []
        joined = self._joined()
        # consent = the invite. With no explicit allow-list, sense EVERY channel the bot
        # was invited to (discovered dynamically); an allow-list, if given, further
        # restricts to a subset. Either way it can only read a channel it has joined.
        targets = self.channels or tuple(joined)
        out: List[Percept] = []
        for ch in targets:
            if ch not in joined:                     # joined is always required
                continue
            oldest = self._cursor.get(ch, "0")
            try:
                resp = self._client.conversations_history(
                    channel=ch, oldest=oldest, limit=self.max_per_channel)
                msgs = resp.get("messages") or []
            except Exception as exc:                 # one bad channel must not block the others
                self._record(exc, "conversations_history")
                continue
            cur_f = _ts_float(oldest)
            for m in sorted(msgs, key=lambda x: _ts_float(x.get("ts"))):   # numeric, oldest first
                ts = m.get("ts", "0")
                if _ts_float(ts) <= cur_f:           # new-only / dedup (numeric, width-safe)
                    continue
                self._cursor[ch] = ts                # advance past it (string, for the API)
                cur_f = _ts_float(ts)
                content = self._shape(ch, m.get("user"), m.get("subtype"),
                                      m.get("text"), m.get("bot_id"))
                if content is None:                  # skip our own / bot posts (self-echo)
                    continue
                out.append((content, self.source,
                            {"channel": ch, "ts": ts, "user": m.get("user")}))
                if len(out) >= self.max_per_poll:
                    return out
        return out

    # --- afferent via Socket Mode: real-time Events API over an outbound WebSocket ---
    def start(self, driver) -> None:
        """Open the Socket Mode WebSocket (the app dials OUT to Slack — Events API with no
        public Request URL; egress-only, gated by the same *.slack.com allowlist). Called
        by the Driver when the daemon starts (D27 unbounded mode). No-op unless socket
        mode is configured AND both tokens are present — an unconfigured instance stays
        poll/inert. Real-time push supersedes poll()."""
        self._driver = driver
        if not self.socket_mode or not self.available:
            return
        app_token = self._secrets.resolve(self._app_token_env)
        if not app_token:                            # fail loud-but-safe: stay deaf, don't crash
            self._record(RuntimeError(f"{self._app_token_env} unset"), "socket_mode")
            return
        try:  # pragma: no cover - live: needs slack_sdk + the app token + a network
            from slack_sdk.socket_mode import SocketModeClient
            self._socket_client = SocketModeClient(app_token=app_token, web_client=self._client)
            self._socket_client.socket_mode_request_listeners.append(self._on_request)
            self._socket_client.connect()            # background WS thread; returns immediately
        except Exception as exc:
            self._record(exc, "socket_mode")
            self._socket_client = None

    def stop(self) -> None:
        if self._socket_client is not None:
            try:  # pragma: no cover - live
                self._socket_client.disconnect()
            except Exception as exc:
                self._record(exc, "socket_mode_stop")
            self._socket_client = None

    def _dedup(self, event_id) -> bool:
        """True if this event_id was already handled. Socket Mode redelivers an event on
        reconnect or after a missed/slow ack, always with the SAME event_id — so a single
        bounded id cache makes 'ack-first then dispatch' safe: a transient ack failure
        costs neither a lost percept (we still dispatch) nor a doubled one (the resend is
        caught here). Bounded to the last `_seen_max` ids."""
        if not event_id:
            return False
        if event_id in self._seen_set:
            return True
        self._seen_set.add(event_id)
        self._seen_ids.append(event_id)
        if len(self._seen_ids) > self._seen_max:
            self._seen_set.discard(self._seen_ids.popleft())
        return False

    def _on_request(self, client, req) -> None:
        """Socket Mode listener (runs on the client's WS thread). ACK first — Slack
        re-sends an un-acked envelope — then dispatch events_api envelopes through the
        same bounds as poll(). A failed ack is recorded but NOT fatal: Slack will resend,
        and `_dedup` (same event_id) makes the resend a no-op, so we neither lose nor
        double the percept."""
        try:
            from slack_sdk.socket_mode.response import SocketModeResponse
            client.send_socket_mode_response(
                SocketModeResponse(envelope_id=getattr(req, "envelope_id", None)))
        except Exception as exc:                     # incl. SDK absent offline: record, still dispatch
            self._record(exc, "socket_ack")
        if getattr(req, "type", None) != "events_api":
            return                                   # only Events API envelopes carry percepts
        payload = getattr(req, "payload", None) or {}
        if self._dedup(payload.get("event_id")):     # reconnect / ack-resend -> handle once
            return
        self._handle_event(payload.get("event") or {})

    def _handle_event(self, event: dict) -> None:
        """Pure dispatch (no slack_sdk): apply consent (LISTED channel) + self-echo +
        redaction, then push a SENSE percept via the driver's thread-safe inbox. Tested
        directly; the WebSocket plumbing in start()/_on_request is live-gated.

        Consent IS the invite: Slack only delivers events for channels the bot was added
        to. With no explicit allow-list we sense all of them (dynamic — the operator never
        collects channel IDs); a non-empty `channels` further restricts to a subset. We
        accept only BARE messages and app_mentions — any `subtype` (edits, deletes, joins,
        file-shares, bot_message) is dropped: a `message_changed` carries its real author
        and edited body NESTED under `event['message']`, so the top-level self-echo guard
        can't see them; dropping subtyped events closes that bypass (documented in
        docs/slack-app.md)."""
        etype = event.get("type")
        if etype not in ("message", "app_mention"):
            return
        if event.get("subtype"):                     # bare messages/mentions only (see docstring)
            return
        channel = event.get("channel")
        if self.channels and channel not in self.channels:   # allow-list is an OPTIONAL restriction
            return
        text = event.get("text") or ""
        # a message that @-mentions us ALSO arrives as an app_mention event — let that one
        # carry it (as 'directed') and skip the duplicate, so we don't sense/reply twice.
        if etype == "message" and self.bot_user_id and f"<@{self.bot_user_id}>" in text:
            return
        content = self._shape(channel, event.get("user"), event.get("subtype"),
                              text, event.get("bot_id"))
        if content is None or self._driver is None:
            return
        band, reply_to = self._addressing(etype, channel, event)   # I3: how directed at me?
        self.events += 1
        self._driver.feed(content, source=self.source, channel=channel, ts=event.get("ts"),
                          user=event.get("user"), addressed=band, reply_to=reply_to)

    def _addressing(self, etype, channel, event):
        """How directed at meno is this percept? Returns (band, reply_to). Structural cues
        give certainty — an @mention is 'directed' (DM / 1:1 channel will be too, once the
        im scopes land); a lexical cue (our name + a question) is a soft 'possibly' that
        the may-respond loop weighs; everything else is 'ambient' (sensed, never replied)."""
        reply_to = {"channel": channel, "user": event.get("user"),
                    "thread_ts": event.get("thread_ts") or event.get("ts")}
        if etype == "app_mention":
            return "directed", reply_to
        text = (event.get("text") or "").lower()
        if self.agent_name and self.agent_name.lower() in text and "?" in text:
            return "possibly", reply_to
        return "ambient", reply_to

    # --- efferent (I2/I3): outward action, gated. Every layer is a refusal first. ---
    def handles(self, action) -> bool:
        return action == "post"

    def _gate(self, channel: str):
        """The channel-independent gate, each layer fail-safe. Returns a (reason, detail)
        refusal or None to proceed. Checked at the moment a post would go out, so config
        that has since narrowed (disabled / out-of-scope / rate / egress) still blocks it."""
        if not self.enabled:
            return ("disabled", "efferent disabled (outward action is opt-in)")
        if channel not in self.post_channels:
            return ("scope", f"channel {channel!r} not in post scope")
        now = time.monotonic()
        while self._sent_at and now - self._sent_at[0] > 60.0:
            self._sent_at.popleft()
        if len(self._sent_at) >= self.rate_per_min:
            return ("rate", f"rate limit ({self.rate_per_min}/min) reached")
        if not self._egress_ok():                    # the network boundary, on every send path
            return ("egress", f"egress to {list(self.hosts)} denied")
        return None

    def _egress_ok(self) -> bool:
        if self.egress is None:
            return True
        try:
            for h in self.hosts:
                self.egress.check(h)
            return True
        except Exception:
            return False

    def deliver(self, payload: dict) -> DeliveryResult:
        """Post to Slack, but only through the gate, fail-safe at every layer, so the
        default for an unconfigured instance is silence: disabled → scope → rate →
        egress → (dry-run?) → send. There is NO per-post approval (D35): the master
        `enabled` toggle, the `post_channels` scope, the rate limit, the egress boundary,
        and the audit ARE the controls; `dry_run` diverts a post to the audit (the mind
        still 'spoke', it just didn't reach the channel) as the tuning ramp. Every
        decision feeds back as FEEDBACK and is audited."""
        channel = payload.get("channel")
        # redact BEFORE truncating, on the SEND path (not just the audit): a reply is now
        # mind-composed from recalled memory, so a secret that entered the substrate via
        # another sensor must not egress through a Slack reply (I3 review P2).
        text = self.redact(payload.get("text") or "")[:self.max_chars]
        thread_ts = payload.get("thread_ts")
        refusal = self._gate(channel)
        if refusal:
            self._audit(channel, text, *refusal)
            return DeliveryResult("refused", refusal[1], refusal[0])
        if self.dry_run:                             # watched-then-live: divert, don't send
            self._audit(channel, text, "dry-run", "diverted (dry_run); not posted")
            return DeliveryResult("dry-run", f"[dry-run] would post to {channel}: {text[:60]}")
        return self._send(channel, text, thread_ts)

    def _send(self, channel: str, text: str, thread_ts=None) -> DeliveryResult:
        try:
            self._client.chat_postMessage(channel=channel, text=text, thread_ts=thread_ts)
        except Exception as exc:                     # an effector must not be blind/fatal
            self.errors += 1
            self._audit(channel, text, "error", f"{type(exc).__name__}: {exc}")
            return DeliveryResult("refused", f"post failed: {type(exc).__name__}: {exc}", "error")
        self._sent_at.append(time.monotonic())
        self.sent_texts.append(text)                 # remember our own voice (self-echo detection)
        self._audit(channel, text, "delivered", "")
        return DeliveryResult("delivered", f"posted to {channel}")

    def _audit(self, channel: str, text: str, outcome: str, detail: str) -> None:
        """Append-only record of every gate DECISION — delivered, refused, or pending —
        not just successes: 'Meno tried to post to #x and was blocked by scope' is the
        highest-value security event. Best-effort (a write failure doesn't block a send,
        which can't be un-sent); failures bump `errors`.

        The recorded `text`/`detail` are REDACTED before they touch disk: the mind may
        author a post quoting a secret/PII it recalled, and the at-rest audit is the wrong
        place for it to persist. Only the audit COPY is scrubbed — the actually-sent
        message (and the confirm-first operator preview) keep the real text, since the
        operator authored it deliberately and reviews it in the clear."""
        if self.audit_path is None:
            return
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            rec = {"ts": time.time(), "action": "post", "channel": channel,
                   "text": self.redact(text), "outcome": outcome,
                   "detail": self.redact(detail)}
            with open(self.audit_path, "a") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception as exc:
            self._record(exc, "audit")


def _ts_float(ts) -> float:
    """Slack ts as a number, for width-safe ordering ('1000' vs '999' compare wrong as
    strings). The string form is kept for the API's `oldest`/cursor."""
    try:
        return float(ts)
    except (TypeError, ValueError):
        return 0.0
