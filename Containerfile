# meno instance image (D21). OCI-neutral (build with podman or docker).
#
#   image  = the TYPE: Python + the meno package + pinned extras (+ baked weights)
#   volume = the IDENTITY: the instance home, mounted at /home/meno/.meno
#   secrets = env-injected at runtime, NEVER baked
#
# Build is multi-stage + uv (D30): a uv builder resolves the FROZEN lock (uv.lock) into
# a venv, and only that venv is copied into a clean slim runtime — no uv, no build
# tools, no caches in the final image. uv makes the install fast and reproducible (the
# pip path timed out on the anthropic layer); --frozen pins the exact dependency graph.
#
# The container is the egress safety boundary that precedes outward action (I2):
# run it non-root, read-only rootfs, dropped caps, and an egress allowlist — e.g.
#
#   podman run --rm \
#     --read-only --cap-drop=ALL --security-opt no-new-privileges \
#     -u 10001:10001 \
#     -v $HOME/.meno/meno-pid:/home/meno/.meno/meno-pid:Z \
#     --tmpfs /tmp \
#     -e ANTHROPIC_API_KEY -e SLACK_BOT_TOKEN -e SLACK_APP_TOKEN \
#     meno:latest run /home/meno/.meno/meno-pid
#
# (The host/network egress allowlist is enforced by the runtime/network policy AND,
# in-app, by meno.home.EgressPolicy from the home's meno.toml [egress].)

# --- builder: uv resolves the frozen lock into /app/.venv ------------------------- #
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

# copy=link-safe across the stage boundary; bytecode-compile for faster cold start;
# never fetch a managed interpreter — use the image's 3.13 (matches the runtime below).
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# install the package + pinned extras from the lock. Edit the --extra set to taste:
#   --extra anthropic   real cognition (needs ANTHROPIC_API_KEY at runtime)
#   --extra slack       the Slack adapter (needs SLACK_BOT_TOKEN[/SLACK_APP_TOKEN])
#   --extra local       local embedder (pulls torch — large; bake weights below)
COPY pyproject.toml uv.lock README.md ./
COPY meno ./meno
COPY meno_adapters ./meno_adapters
RUN uv sync --frozen --no-dev --extra anthropic --extra slack

# OPTIONAL: bake the local embedder weights so a running instance never does a cold
# Hugging Face download (the R1 gap, D21). Uncomment (adds torch + the model, ~100s MB):
#   RUN uv sync --frozen --no-dev --extra anthropic --extra slack --extra local \
#    && /app/.venv/bin/python -c "from sentence_transformers import SentenceTransformer as S; S('all-MiniLM-L6-v2')"

# --- runtime: a clean slim image carrying only the venv + source ------------------ #
FROM python:3.13-slim-bookworm AS runtime

# non-root by construction
RUN useradd --uid 10001 --create-home --home-dir /home/meno meno
WORKDIR /app

# the venv's interpreter resolves here because both stages are python:3.13-bookworm
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 HOME=/home/meno

USER meno
# the home is a mounted volume — the image must not carry instance identity
VOLUME ["/home/meno/.meno"]

# `meno run <home>` is the daemon; the home is supplied at runtime (the volume path)
ENTRYPOINT ["meno"]
CMD ["run", "/home/meno/.meno/instance"]
