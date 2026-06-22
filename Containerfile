# meno instance image (D21). OCI-neutral (build with podman or docker).
#
#   image  = the TYPE: Python + the meno package + pinned extras (+ baked weights)
#   volume = the IDENTITY: the instance home, mounted at /home/meno/.meno
#   secrets = env-injected at runtime, NEVER baked
#
# The container is the egress safety boundary that precedes outward action (I2):
# run it non-root, read-only rootfs, dropped caps, and an egress allowlist — e.g.
#
#   podman run --rm \
#     --read-only --cap-drop=ALL --security-opt no-new-privileges \
#     -u 10001:10001 \
#     -v $HOME/.meno/meno-pid:/home/meno/.meno/meno-pid:Z \
#     --tmpfs /tmp \
#     -e ANTHROPIC_API_KEY -e SLACK_BOT_TOKEN \
#     meno:latest run /home/meno/.meno/meno-pid
#
# (The host/network egress allowlist is enforced by the runtime/network policy AND,
# in-app, by meno.home.EgressPolicy from the home's meno.toml [egress].)

FROM python:3.13-slim AS base

# non-root by construction
RUN useradd --uid 10001 --create-home --home-dir /home/meno meno
WORKDIR /app

# install the package + extras. Edit the extras set to taste:
#   .[anthropic]            real cognition (needs ANTHROPIC_API_KEY at runtime)
#   .[local]                local embedder (pulls torch — large; baked weights below)
#   .[slack]                the Slack adapter
COPY pyproject.toml README.md ./
COPY meno ./meno
COPY meno_adapters ./meno_adapters
RUN pip install --no-cache-dir ".[anthropic,slack]"

# OPTIONAL: bake the local embedder weights so a running instance never does a
# cold Hugging Face download (the R1 gap, D21). Uncomment to include (adds torch +
# the model, ~hundreds of MB):
#   RUN pip install --no-cache-dir ".[local]" \
#    && python -c "from sentence_transformers import SentenceTransformer as S; S('all-MiniLM-L6-v2')"

USER meno
ENV PYTHONUNBUFFERED=1 HOME=/home/meno
# the home is a mounted volume — the image must not carry instance identity
VOLUME ["/home/meno/.meno"]

# `meno run <home>` is the daemon; the home is supplied at runtime (the volume path)
ENTRYPOINT ["meno"]
CMD ["run", "/home/meno/.meno/instance"]
