"""SlackAdapter — a real afferent channel (Roadmap I1). SENSE-ONLY.

Percepts flow from listed-and-joined Slack channels into the loop, bounded and
consented exactly like R4's FilesystemSensor — the same discipline, a different
world:

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

It is AFFERENT ONLY. There is no send path in I1 — `handles()` is False and there is
no `deliver()`; outward posting is I2, behind the gate. The Slack SDK is imported
HERE (meno_adapters), never in the kernel; with no SDK or token the adapter is inert.
"""
from __future__ import annotations

import os
import re
import time
from typing import List, Optional

from .base import Adapter, Percept

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

    def __init__(self, *, client=None, channels=(), bot_user_id: Optional[str] = None,
                 max_chars: int = 2000, max_per_poll: int = 8, max_per_channel: int = 8,
                 membership_ttl: float = 120.0, token_env: str = "SLACK_BOT_TOKEN") -> None:
        self.channels = tuple(channels)             # operator allow-list
        self.bot_user_id = bot_user_id              # skip our own posts (self-echo guard)
        self.max_chars = max_chars
        self.max_per_poll = max_per_poll            # global cap on percepts emitted per poll
        self.max_per_channel = max_per_channel      # API fetch limit per channel
        self.membership_ttl = membership_ttl
        self.errors = 0                             # adapter-internal failures (observability)
        self.last_error: Optional[str] = None
        self._client = client
        if self._client is None:                    # build a real client only if SDK+token present
            try:  # pragma: no cover - depends on the optional dep + a token
                import slack_sdk  # type: ignore
                if os.environ.get(token_env):
                    self._client = slack_sdk.WebClient(token=os.environ[token_env])
            except Exception:
                self._client = None
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

    # --- efferent: NONE in I1. Sense-only; posting is I2, behind the gate. ---
    def handles(self, action) -> bool:
        return False


def _ts_float(ts) -> float:
    """Slack ts as a number, for width-safe ordering ('1000' vs '999' compare wrong as
    strings). The string form is kept for the API's `oldest`/cursor."""
    try:
        return float(ts)
    except (TypeError, ValueError):
        return 0.0
