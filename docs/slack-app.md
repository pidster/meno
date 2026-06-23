# Connecting a Meno instance to Slack

How to create the Slack app, what scopes it needs, and the gaps between what we've
built and a fully real-time integration. The manifest is [`slack/manifest.yaml`](../slack/manifest.yaml).

## TL;DR

Meno's `SlackAdapter` is **poll-based**: it calls `conversations.history` (and
`users.conversations` for membership) on the driver's cadence. That means **v1 needs
only a bot token + read scopes — no public endpoint, no Events API, no Socket Mode.**
So the path is short:

1. Create an app from `slack/manifest.yaml`, install it → get a **bot token** (`xoxb-…`).
2. Give meno the token as `$SLACK_BOT_TOKEN` (env — never in the home).
3. `/invite @meno` to each channel it should sense/post in, and put those channel IDs
   in `adapters/slack.toml`; add `slack.com` to `meno.toml [egress]`.
4. `meno run` — sense-only by default; posting stays off until you enable + confirm it.

## How a Slack app maps to our adapter

A Slack app is a workspace-installed identity with a **bot user** and a **bot token**
scoped by OAuth permissions. Our adapter uses four Web API methods; each implies scopes:

| Adapter call | Slack method | Bot scopes (verified) | Used for |
|---|---|---|---|
| `auth_test()` | `auth.test` | *(none)* | learn the bot's user id (self-echo guard) |
| `users_conversations(...)` | `users.conversations` | `channels:read`, `groups:read` | which channels the bot has joined (consent) |
| `conversations_history(...)` | `conversations.history` | `channels:history`, `groups:history` | read messages (afferent) |
| `chat_postMessage(...)` | `chat.postMessage` | `chat:write` | post (efferent — gated, off by default) |

(`im:*` / `mpim:*` scopes are only needed if you want it to sense DMs; the adapter
requests public+private channels today, so they're omitted.) The bot reads/posts
**only in channels it is a member of**, which is exactly our consent model
("listed AND joined").

## The two ways to receive messages — and why v1 polls

Slack offers two receive models. This is the main architectural choice, and the one
real gap:

**A. Polling (`conversations.history`) — what we built.**
- ✅ Needs only the bot token + read scopes. No public ingress, no Request URL, no
  app-level token. Fits the container/egress-only model perfectly (outbound calls only).
- ✅ Already implemented, bounded, consented, redacted, rate-aware (membership is
  TTL-cached; per-poll caps).
- ⚠️ **Latency**: a message is seen on the next poll (`sense_every` × cycle), not
  instantly. Fine for a reflective agent; not for a snappy chatbot.
- ⚠️ **Rate budget**: `conversations.history` is Tier-3 (~50 req/min). Polling many
  channels frequently eats it — our caching helps, but it's the ceiling.

**B. Events API via Socket Mode — the upgrade, NOT yet built.**
- Slack **pushes** events (`message.channels`, `app_mention`) over a WebSocket using an
  **app-level token** (`xapp-…`, scope `connections:write`). Real-time, no public URL
  (Socket Mode tunnels it), no polling, no rate-budget burn for reads.
- This is the right model for an interactive "@meno, …" bot.
- **Gap**: it needs (1) a new afferent adapter using `slack_sdk`'s `SocketModeClient`
  (async — lives in `meno_adapters`, not the kernel), (2) `socket_mode_enabled: true`
  + `event_subscriptions.bot_events` in the manifest, and (3) a second token
  (`SLACK_APP_TOKEN`). The manifest has these lines commented in, ready.

**Recommendation:** ship v1 on polling (it works with what we have), and treat Socket
Mode as a follow-on once we want real-time / mention-driven interaction.

## Gaps & what to create

| Gap | Severity | What's needed |
|---|---|---|
| **The Slack app** | required | Create from the manifest; install; capture the `xoxb-` token. *(You do this; I made the manifest.)* |
| **Channel IDs** | minor | The adapter takes channel **IDs** (`C…`), not names. Get them from the channel's "View details" or `conversations.list`. *(Could add name→ID resolution as a convenience.)* |
| **Bot must be invited** | required | `/invite @meno` per channel — our consent requires "joined". |
| **Real-time / mentions** | optional (v2) | Build the Socket Mode afferent adapter + `app_mention` handling. The current adapter reads channel history indiscriminately; it has no "reply when mentioned" behaviour. |
| **DMs / group DMs** | optional | Add `im:*`/`mpim:*` scopes + sense those conversation types. |
| **Egress** | required | `slack.com` (and `*.slack.com`, which covers `www.slack.com` and the Socket Mode `wss-*.slack.com`) must be in `meno.toml [egress]`, or every call is refused at the boundary. |
| **Token rotation** | optional | A single-workspace internal app uses a static bot token (fine). Distributed/rotating tokens (`token_rotation_enabled`) would need refresh handling we don't have. |

None of these block v1. The two **required** non-app steps are: invite the bot, and
allowlist `slack.com` in egress.

## Step-by-step setup (v1)

1. **Create the app.** https://api.slack.com/apps → *Create New App* → *From an app
   manifest* → pick the workspace → paste [`slack/manifest.yaml`](../slack/manifest.yaml).
2. **Install to Workspace** (Settings → Install App). Approve the scopes. Copy the
   **Bot User OAuth Token** (`xoxb-…`).
3. **Give meno the token** (never store it in the home):
   ```bash
   export SLACK_BOT_TOKEN=xoxb-…
   ```
4. **Invite the bot** to each channel: `/invite @meno`. Note each channel's **ID**.
5. **Configure the instance** (`<home>/adapters/slack.toml`):
   ```toml
   [afferent]
   enabled  = true
   channels = ["C0123ABC", "C0456DEF"]   # the channel IDs you invited it to

   [efferent]                            # leave OFF until you want it to post
   enabled       = false
   post_channels = ["C0123ABC"]
   confirm       = true                  # confirm-first: each post needs approval
   rate          = "5/min"
   ```
   and `<home>/meno.toml`:
   ```toml
   [egress]
   allow = ["slack.com", "*.slack.com"]
   ```
6. **Run:** `meno run <home>`. It reports `adapters=['slack']`. With `[efferent].enabled
   = false`, Meno *hears* the channels and posts nothing — the safe first step. To let
   it post, enable the efferent side and approve each post (confirm-first); every
   send/refusal is audited to `journal/traces/`.

## Security recap

- The token lives in **`$SLACK_BOT_TOKEN`**, resolved at runtime — never written to the
  home (`.gitignore` covers it).
- Inbound messages are **redacted** (secrets/PII) before they ever become a percept (D26).
- Outbound posting is a **different risk class**: disabled by default, scoped to
  `post_channels`, rate-limited, **confirm-first**, audited, and behind the **egress**
  allowlist — and the bot's own posts are dropped on re-read (self-echo guard).
