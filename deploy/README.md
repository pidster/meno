# Deploying a meno instance

Two questions decide the shape: **where does the substrate live**, and **is there a DB**.

## The default: one container, file substrate

A single instance persists to a JSON file under its home volume — the volume *is* the
identity, and there's no database to run. This is the right default; reach for a DB only
when you outgrow it (concurrent readers, vector search at scale).

```bash
docker compose up            # or: podman-compose up
```

[`compose.yaml`](compose.yaml) runs the kernel image (built from the repo `Containerfile`,
a multi-stage uv build, D30) as the **egress safety boundary** that precedes any outward
action (I2): non-root (`10001`), read-only rootfs, `cap_drop: ALL`, `no-new-privileges`,
`/tmp` on tmpfs, the home on a named volume, `restart: on-failure` (a crashed cycle
restarts and the home resumes — sleep, not amnesia, D12).

**Secrets** are env-injected and resolved by *name* at runtime (D31) — never baked into
the image or committed. Put them in a gitignored `.env` beside `compose.yaml`:

```
ANTHROPIC_API_KEY=sk-ant-…
SLACK_BOT_TOKEN=xoxb-…
SLACK_APP_TOKEN=xapp-…        # Socket Mode only
```

## With a DB sidecar (when you outgrow the file store)

The substrate backend is selectable behind the `Store` interface (`meno/store.py`, D34).
Today only `file` ships; a SurrealDB / vector backend plugs in there and is provisioned as
a **sidecar** — a separate, digest-pinned container with its **own** volume, on an internal
network, never co-baked into the app image (that would break the distroless-style hardening
and couple their lifecycles).

```bash
docker compose --profile db up    # also starts the SurrealDB sidecar
```

The `surreal` service is gated behind the `db` compose profile, so it doesn't start by
default. When the `surreal` Store backend is implemented, meno reaches it over the internal
`meno-net` at `surreal:8000`; you then:

1. add `surreal` to `meno.toml [egress] allow` (the boundary gates the DB connection too),
2. set `meno.toml [storage] backend = "surreal"`,
3. provide `SURREAL_USER` / `SURREAL_PASS` in the env (resolved by name, D31).

Until then, setting `backend = "surreal"` fails loudly with a pointer here — an
unimplemented substrate must never look like it's persisting.

## Kubernetes (the sidecar pattern)

Same topology as a Pod with two containers sharing a lifecycle — meno + surreal — each with
its own `PersistentVolumeClaim`, the same hardening in `securityContext`
(`runAsNonRoot`, `readOnlyRootFilesystem`, `capabilities.drop: [ALL]`,
`allowPrivilegeEscalation: false`), and an `emptyDir` for `/tmp`. Pin images by digest.
Secrets come from a `Secret` mounted as env, not from the image. Network egress is
restricted with a `NetworkPolicy` matching `meno.toml [egress]`.
