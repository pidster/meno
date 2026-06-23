"""meno_adapters — the integration layer (Roadmap I0a).

This package, NOT the `meno/` kernel, is where the world is reached: network, async,
channel SDKs all live here. The kernel stays stdlib-only and step-driven (D7); an
adapter runs its own I/O and talks to the mind only through the Driver's thread-safe
seam — `driver.feed(...)` inbound, and the outbox/`deliver` hand-off outbound, so a
slow network call never blocks cognition.
"""
from .base import Adapter, DeliveryResult
from .knowledge import KnowledgeAdapter
from .loopback import LoopbackAdapter
from .secrets import DotenvBackend, EnvBackend, SecretResolver, env_resolver
from .slack import SlackAdapter

__all__ = ["Adapter", "DeliveryResult", "DotenvBackend", "EnvBackend", "KnowledgeAdapter",
           "LoopbackAdapter", "SecretResolver", "SlackAdapter", "env_resolver"]
