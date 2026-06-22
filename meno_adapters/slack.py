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

EFFERENT (act, I2). Outward posting is a different risk class, so it is OPT-IN and
gated, every layer failing safe: `enabled=False` by default; `post_channels` scope
(distinct from the read list); a rate limit; confirm-first (a post returns `pending`
and sends nothing until an out-of-band operator approves — the FULL gate re-applied at
approval); and an append-only audit record of every decision (delivered/refused/
pending), best-effort. The adapter declares its `hosts` so the egress allowlist gates
its real reach on BOTH send paths. Own posts are skipped on re-read (self-echo guard)
so Meno's voice never re-enters as experience.

Concurrency: afferent `poll()` runs on the mind thread, efferent `deliver()` on the
single outbound worker — disjoint state except the advisory `errors` counter, so there
is no race that could send twice or open the gate.

The Slack SDK is imported HERE (meno_adapters), never in the kernel; with no SDK or
token the adapter is inert. With efferent disabled (the default) it is sense-only.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import List, Optional

from .base import Adapter, DeliveryResult, Percept

# Redact obvious secrets/PII before a message becomes a percept. Blunt and best-effort
# by design (D26): a channel must not bleed a pasted credential or PII into the
# substrate, where it would be encoded as a near-permanent node. Over-redaction is the
# safe direction.
_SECRET_RE = re.compile(
    r"(xox[baprs]-[A-Za-z0-9-]{8,}"                                  # slack tokens
    r"|sk-[A-Za-z0-9_\-]{16,}"                                       # openai-style keys
    r"|AKIA[0-9A-Z]{16}"                                             # aws access key id
    r"|gh[posru]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"      # github tokens
    r"|eyJ[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}"  # jwt
    r"|(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+"    # key=value secrets
    r"|[\w.+-]+@[\w-]+\.[\w.-]+"                                     # email (PII)
    r"|\b\d{3}-\d{2}-\d{4}\b"                                        # us ssn (PII)
    r")", re.IGNORECASE)
# private-key blocks span lines, so they need their own DOTALL pass
_PRIVKEY_RE = re.compile(r"-----BEGIN[^-]*PRIVATE KEY-----.*?-----END[^-]*PRIVATE KEY-----",
                         re.DOTALL | re.IGNORECASE)


class SlackAdapter(Adapter):
    name = "slack"
    source = "slack"

    # the network hosts this adapter reaches — declared so the egress boundary gates
    # its REAL reach before any post (D21), not a payload field the mind volunteers.
    hosts = ("slack.com", "*.slack.com")

    def __init__(self, *, client=None, channels=(), bot_user_id: Optional[str] = None,
                 max_chars: int = 2000, max_per_poll: int = 8, max_per_channel: int = 8,
                 membership_ttl: float = 120.0, token_env: str = "SLACK_BOT_TOKEN",
                 # --- efferent (I2): outward action is OPT-IN and gated ---
                 enabled: bool = False, post_channels=(), confirm: bool = True,
                 rate_per_min: int = 5, audit_path=None) -> None:
        self.channels = tuple(channels)             # afferent allow-list (read)
        self.bot_user_id = bot_user_id              # skip our own posts (self-echo guard)
        self.max_chars = max_chars
        self.max_per_poll = max_per_poll            # global cap on percepts emitted per poll
        self.max_per_channel = max_per_channel      # API fetch limit per channel
        self.membership_ttl = membership_ttl
        self.errors = 0                             # adapter-internal failures (observability)
        self.last_error: Optional[str] = None
        # efferent gate state — DISABLED by default; nothing posts until an operator opts in
        self.enabled = enabled
        self.post_channels = tuple(post_channels)   # efferent allow-list (write) — distinct from read
        self.confirm = confirm                      # confirm-first: a post waits for approval
        self.rate_per_min = rate_per_min
        self.audit_path = Path(audit_path) if audit_path else None
        self.max_pending = 256                      # bound the confirm-first backlog
        self.egress = None                          # set by the Driver; checked on BOTH send paths
        self._sent_at: deque = deque()              # send timestamps, for the rate window
        self._pending: dict = {}                    # confirm-first: token -> {channel,text}
        self._pending_seq = 0
        self.sent_texts: List[str] = []             # what we posted (self-echo detection)
        self._client = client
        if self._client is None:                    # build a real client only if SDK+token present
            try:  # pragma: no cover - depends on the optional dep + a token
                import slack_sdk  # type: ignore
                if os.environ.get(token_env):
                    self._client = slack_sdk.WebClient(token=os.environ[token_env])
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

    @property
    def available(self) -> bool:
        return self._client is not None

    def redact(self, text: str) -> str:
        return _SECRET_RE.sub("[redacted]", _PRIVKEY_RE.sub("[redacted-key]", text))

    def _record(self, exc: Exception, where: str) -> None:
        self.errors += 1
        self.last_error = f"slack {where}: {type(exc).__name__}: {exc}"

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

    def poll(self) -> List[Percept]:
        if not self.available:
            return []
        joined = self._joined()
        out: List[Percept] = []
        for ch in self.channels:
            if ch not in joined:                     # consent: listed AND joined
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
                if m.get("subtype") == "bot_message" or (
                        self.bot_user_id and m.get("user") == self.bot_user_id):
                    continue                         # skip our own / bot posts (self-echo)
                text = self.redact(m.get("text") or "")[:self.max_chars]   # redact BEFORE truncate
                out.append((f"slack #{ch}: {text}", self.source,
                            {"channel": ch, "ts": ts, "user": m.get("user")}))
                if len(out) >= self.max_per_poll:
                    return out
        return out

    # --- efferent (I2): outward action, gated. Every layer is a refusal first. ---
    def handles(self, action) -> bool:
        return action == "post"

    def _gate(self, channel: str):
        """The channel-independent gate, each layer fail-safe. Returns a (reason, detail)
        refusal or None to proceed. Applied on BOTH the deliver and confirm paths — a
        post is re-validated at the moment it would actually go out, so config that
        narrowed (disabled/scope/rate) between authoring and approval still blocks it."""
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
        egress → confirm-first → send. A delivered or refused post feeds back as
        FEEDBACK (with the reason); a pending one does not (and does not block the
        worker). Every decision is audited."""
        channel = payload.get("channel")
        text = (payload.get("text") or "")[:self.max_chars]
        refusal = self._gate(channel)
        if refusal:
            self._audit(channel, text, *refusal)
            return DeliveryResult("refused", refusal[1], refusal[0])
        if self.confirm:
            # confirm-first: the MIND authors this payload, so it can NEVER self-approve
            # (a `confirmed` flag in the intent is ignored). The post is stashed and sends
            # NOTHING until confirm_send(token) — an out-of-band operator step — fires.
            if len(self._pending) >= self.max_pending:   # bounded backlog (don't grow unbounded)
                self._audit(channel, text, "pending-overflow", "pending store full")
                return DeliveryResult("refused", "pending store full", "pending-overflow")
            self._pending_seq += 1
            token = f"pending-{self._pending_seq}"
            self._pending[token] = {"channel": channel, "text": text}
            self._audit(channel, text, "pending", token)
            return DeliveryResult("pending", f"awaiting confirmation [{token}]")
        return self._send(channel, text)

    def confirm_send(self, token: str) -> DeliveryResult:
        """Approve a confirm-first post (the out-of-band operator step). The FULL gate
        is re-applied against CURRENT config — a post authored when scope/rate/egress
        were fine but since narrowed is still refused. Until this fires, the post has
        sent NOTHING."""
        payload = self._pending.pop(token, None)
        if payload is None:
            return DeliveryResult("refused", f"no pending post {token!r}", "unknown")
        channel, text = payload["channel"], payload["text"]
        refusal = self._gate(channel)
        if refusal:
            self._audit(channel, text, refusal[0], f"on confirm: {refusal[1]}")
            return DeliveryResult("refused", refusal[1], refusal[0])
        return self._send(channel, text)

    def _send(self, channel: str, text: str) -> DeliveryResult:
        try:
            self._client.chat_postMessage(channel=channel, text=text)
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
        which can't be un-sent); failures bump `errors`."""
        if self.audit_path is None:
            return
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            rec = {"ts": time.time(), "action": "post", "channel": channel,
                   "text": text, "outcome": outcome, "detail": detail}
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
