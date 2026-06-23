# Connecting a Meno instance to Slack

How to create the Slack app, what scopes it needs, and the two ways meno can receive
messages. The manifest is [`slack/manifest.yaml`](../slack/manifest.yaml).

## TL;DR

Meno's `SlackAdapter` has two afferent (receive) modes, both **outbound-only — no public
endpoint either way**:

- **Socket Mode** (`socket_mode = true`, the manifest default): real-time Events API over
  a WebSocket meno dials OUT to Slack. Needs a bot token **and** an app-level token.
- **Polling** (`socket_mode = false`): calls `conversations.history` on the driver's
  cadence. Needs only the bot token + read scopes.

The path:

1. Create an app from `slack/manifest.yaml`, install it → get a **bot token** (`xoxb-…`).
2. For Socket Mode, also generate an **app-level token** (`xapp-…`, scope
   `connections:write`) in *Basic Information → App-Level Tokens*.
3. Give meno the tokens as `$SLACK_BOT_TOKEN` (and `$SLACK_APP_TOKEN` for Socket Mode) —
   env only, never in the home.
4. `/invite @meno` to each channel it should sense/post in, put those channel IDs in
   `adapters/slack.toml`; add `slack.com` + `*.slack.com` to `meno.toml [egress]`.
5. `meno run` — sense-only by default; posting stays off until you enable + confirm it.

> **Socket Mode only takes effect in the `meno run` daemon** (which opens the WebSocket via
> `adapter.start()`). Bounded `meno run … --cycles N` runs stay on the poll path.

## How a Slack app maps to our adapter

A Slack app is a workspace-installed identity with a **bot user** and a **bot token**
scoped by OAuth permissions. Our adapter uses four Web API methods; each implies scopes:

| Adapter call | Slack method | Bot scopes (verified) | Used for |
|---|---|---|---|
| `auth_test()` | `auth.test` | *(none)* | learn the bot's user id (self-echo guard) |
| `SocketModeClient` | Socket Mode (`apps.connections.open`) | app-level `connections:write` | real-time event push (afferent) |
| `users_conversations(...)` | `users.conversations` | `channels:read`, `groups:read` | which channels the bot has joined (poll consent) |
| `conversations_history(...)` | `conversations.history` | `channels:history`, `groups:history` | read messages (poll afferent) |
| `chat_postMessage(...)` | `chat.postMessage` | `chat:write` | post (efferent — gated, off by default) |

(`app_mentions:read` is the bot scope behind the `app_mention` event; `message.channels`/
`message.groups` events ride the `channels:history`/`groups:history` scopes.)

(`im:*` / `mpim:*` scopes are only needed if you want it to sense DMs; the adapter
requests public+private channels today, so they're omitted.) The bot reads/posts
**only in channels it is a member of**, which is exactly our consent model
("listed AND joined").

## The two ways to receive messages — both built

Slack offers two receive models. The `SlackAdapter` supports **both**, selected by
`socket_mode` in `adapters/slack.toml`; neither needs a public endpoint.

**A. Socket Mode (Events API over a WebSocket) — `socket_mode = true` (default).**
- Slack **pushes** events (`message.channels`, `message.groups`, `app_mention`) over a
  WebSocket that meno dials OUT to Slack, using an **app-level token** (`xapp-…`, scope
  `connections:write`) alongside the bot token. Real-time; no public Request URL (the
  WebSocket replaces it); no rate-budget burn for reads.
- The right model for an interactive "@meno, …" bot.
- Built on `slack_sdk`'s built-in `SocketModeClient` (no extra deps), in `meno_adapters`
  (never the kernel). The adapter opens the socket in `adapter.start(driver)` and pushes
  each event through the **same bounds as polling** — consent (operator-listed channel),
  self-echo skip, redaction-before-truncation — then `driver.feed(…, kind=SENSE)`.
- ⚠️ Active only in the long-running `meno run` daemon (which calls `start()`); bounded
  `--cycles` runs fall back to polling.

Socket-Mode-specific behaviour (D29), each a deliberate bound:
- **Bare messages and mentions only.** Subtyped `message` events (edits, deletes, joins,
  file-shares, `bot_message`) are dropped — a `message_changed` carries its real author
  and edited body *nested*, where the top-level self-echo guard can't see it, so an edit
  of meno's own post could otherwise re-enter. Conservative: it also means threaded
  broadcasts / file-share captions aren't sensed in real time (poll still sees them).
- **`bot_id` self-echo.** Any bot-authored message (including meno's own) is dropped via
  its `bot_id`, so the guard holds even if `auth_test` failed and meno's user id is unknown.
- **Idempotent.** Events are de-duplicated by Slack's `event_id` (bounded cache), so a
  reconnect or post-ack redelivery is handled exactly once.
- **Ack-first, lossy under flood.** The adapter acks each envelope before dispatch (Slack
  re-sends un-acked ones). Percepts the bounded driver inbox drops under backpressure are
  *not* recoverable — unlike the poll path, which self-heals via its per-channel cursor.
  The drop is counted (`dropped_input`); a reflective agent isn't obliged to read faster
  than it thinks. Tokens never reach disk; SDK exception text is redacted before telemetry.

**B. Polling (`conversations.history`) — `socket_mode = false`.**
- ✅ Needs only the bot token + read scopes — no app-level token. Also outbound-only.
- ✅ Bounded, consented, redacted, rate-aware (membership TTL-cached; per-poll caps).
- ⚠️ **Latency**: a message is seen on the next poll, not instantly.
- ⚠️ **Rate budget**: `conversations.history` is Tier-3 (~50 req/min); polling many
  channels frequently eats it — caching helps, but it's the ceiling.

**Recommendation:** use Socket Mode for real-time / mention-driven interaction (it's the
manifest default); keep polling for the simplest possible setup (one token, no app-level
token) or where a WebSocket is undesirable.

## Gaps & what to create

| Gap | Severity | What's needed |
|---|---|---|
| **The Slack app** | required | Create from the manifest; install; capture the `xoxb-` bot token. |
| **App-level token** | required for Socket Mode | Generate in *Basic Information → App-Level Tokens* (scope `connections:write`); give it as `$SLACK_APP_TOKEN`. Not needed for polling. |
| **Channel IDs** | none | Not needed — leave `channels = []` and meno senses every channel it's invited to (discovered via `users.conversations`; Socket Mode only delivers joined-channel events). An explicit ID list is an optional restriction. |
| **Bot must be invited** | required | `/invite @meno` per channel — the invite is the consent (Socket Mode only delivers events for channels it's in; polling checks membership). |
| **Mention-reply behaviour** | optional | Socket Mode now *receives* `app_mention` as a SENSE percept, but meno has no special "always reply when mentioned" reflex — a mention enters cognition like any percept, and any reply goes through the gated efferent path. |
| **DMs / group DMs** | optional | Add `im:*`/`mpim:*` scopes + `message.im`/`message.mpim` events to sense those conversation types. |
| **Egress** | required | `slack.com` and `*.slack.com` (covers `www.slack.com` and the Socket Mode `wss-*.slack.com`) must be in `meno.toml [egress]`, or every call — including the WebSocket open — is refused at the boundary. |
| **Token rotation** | optional | A single-workspace internal app uses static tokens (fine). Rotating tokens (`token_rotation_enabled`) would need refresh handling we don't have. |

The **required** non-app steps are: invite the bot, allowlist `slack.com`/`*.slack.com`
in egress, and (for Socket Mode) provide the app-level token.

## Step-by-step setup

1. **Create the app.** https://api.slack.com/apps → *Create New App* → *From an app
   manifest* → pick the workspace → paste [`slack/manifest.yaml`](../slack/manifest.yaml).
   The manifest enables Socket Mode and subscribes the bot events.
2. **Install to Workspace** (Settings → Install App). Approve the scopes. Copy the
   **Bot User OAuth Token** (`xoxb-…`).
3. **(Socket Mode) Create an app-level token.** *Basic Information → App-Level Tokens →
   Generate Token and Scopes* → add scope `connections:write` → copy the token (`xapp-…`).
4. **Give meno the tokens** (never store them in the home):
   ```bash
   export SLACK_BOT_TOKEN=xoxb-…
   export SLACK_APP_TOKEN=xapp-…          # Socket Mode only
   ```
5. **Invite the bot** to each channel it should sense: `/invite @meno`. That invite **is the
   consent** — you don't collect channel IDs.
6. **Configure the instance** (`<home>/adapters/slack.toml`):
   ```toml
   [afferent]
   enabled     = true
   channels    = []                       # empty = sense EVERY channel you invited it to
                                           # (auto-discovered). A list restricts to a subset.
   socket_mode = true                     # real-time; false = poll (no app token needed)

   [efferent]                             # leave OFF until you want it to post
   enabled       = false
   post_channels = ["C0123ABC"]
   confirm       = true                   # confirm-first: each post needs approval
   rate          = "5/min"
   ```
   and `<home>/meno.toml`:
   ```toml
   [egress]
   allow = ["slack.com", "*.slack.com"]
   ```
7. **Run:** `meno run <home>` (the unbounded daemon — Socket Mode opens its WebSocket
   here; a bounded `--cycles` run would stay on the poll path). It reports
   `adapters=['slack']`. With `[efferent].enabled = false`, Meno *hears* the channels and
   posts nothing — the safe first step. To let it post, enable the efferent side and
   approve each post (confirm-first); every send/refusal is audited to `journal/traces/`.

## Security recap

- The token lives in **`$SLACK_BOT_TOKEN`**, resolved at runtime — never written to the
  home (`.gitignore` covers it).
- Inbound messages are **redacted** (secrets/PII) before they ever become a percept (D26).
- Outbound posting is a **different risk class**: disabled by default, scoped to
  `post_channels`, rate-limited, **confirm-first**, audited, and behind the **egress**
  allowlist — and the bot's own posts are dropped on re-read (self-echo guard).
