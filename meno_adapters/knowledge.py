"""KnowledgeAdapter — an external knowledge authority (Roadmap K3).

When the self's Library can't answer a factual curiosity, the lookup falls OUTWARD to
a real authority — a dictionary/definitions API, a web search, or an MCP server. This
adapter is that authority's edge, reusing the whole I-chapter substrate:

  - it runs as an OUTBOUND action on the I0a efferent contract — off the mind thread,
    so a slow network round-trip never blocks cognition;
  - it declares its `hosts`, so the D21 egress allowlist gates its reach BEFORE the
    call — an authority not on the allowlist is refused;
  - its result re-enters as a `Kind.REFERENCE` (read into cognition, NEVER encoded as
    experience) and is curated into the Library, so a repeat lookup is a local hit
    (the 'decide to retain' half of D25) — Meno learns what it looked up.

The authority client (an HTTP/MCP call) lives HERE in meno_adapters, never in the
kernel; with none configured the adapter is inert and a miss is honest. The client is
any object with `lookup(query) -> str | None`, so a dictionary API, a web search, or
an MCP tool all adapt behind one seam.
"""
from __future__ import annotations

from typing import Optional

from ._redact import redact as _redact
from .base import Adapter, DeliveryResult


class KnowledgeAdapter(Adapter):
    name = "knowledge"

    def __init__(self, *, client=None, hosts=(), kind: str = "web",
                 source: Optional[str] = None, max_chars: int = 2000) -> None:
        self.kind = kind                            # "web" | "dictionary" | "mcp" | ...
        self.hosts = tuple(hosts)                   # declared reach — gated by egress (D21)
        self.max_chars = max_chars
        # provenance names the ACTUAL authority host, not a generic kind — so an audit
        # can attribute a bad/poisoned fact to the source that supplied it (the
        # allowlist is the trust boundary; D28).
        self.source = source or f"authority:{kind}:{self.hosts[0] if self.hosts else '?'}"
        self.errors = 0
        self.last_error: Optional[str] = None
        self._client = client                       # any object with .lookup(query) -> str | None
        self.egress = None                          # handed in by the Driver (defense in depth)

    @property
    def available(self) -> bool:
        return self._client is not None

    def handles(self, action) -> bool:
        return action == "knowledge"

    def deliver(self, payload: dict) -> DeliveryResult:
        """Resolve a factual query against the authority. The egress boundary has
        already cleared `self.hosts` upstream (the Driver) — and is re-checked here for
        the same defense-in-depth as the Slack effector. A hit returns a `reference`
        (curated by the kernel); a miss/error is an honest refusal, never a crash."""
        if not self._egress_ok():
            return DeliveryResult("refused", f"egress to {list(self.hosts)} denied", "egress")
        if not self.available:
            return DeliveryResult("refused", "no knowledge authority configured", "unavailable")
        query = payload.get("key") or payload.get("query", "")
        curate_key = payload.get("curate_key") or query
        try:
            body = self._client.lookup(query)
        except Exception as exc:                     # an authority error must not be fatal
            self.errors += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            return DeliveryResult("refused", f"authority error: {type(exc).__name__}", "error")
        if not body:
            return DeliveryResult("refused", f"(no authority result for {query!r})", "miss")
        # an authority's response crosses the world boundary, so it gets the same
        # hygiene as an inbound percept: redact secrets/PII, then bound the size before
        # it is curated into the non-decaying Library (D26, P1: a hostile authority
        # must not write a credential or an unbounded blob into permanent reference).
        body = _redact(str(body))[:self.max_chars]
        return DeliveryResult("delivered", f"looked up {query!r} via {self.kind}",
                              reference={"key": curate_key, "body": body, "source": self.source})

    def _egress_ok(self) -> bool:
        if self.egress is None:
            return True
        try:
            for h in self.hosts:
                self.egress.check(h)
            return True
        except Exception:
            return False
