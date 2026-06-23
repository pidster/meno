"""Shared best-effort redaction (D26) for text crossing the world boundary — applied
to BOTH inbound Slack percepts and outbound knowledge-authority results before they
enter the substrate or the Library. Blunt by design; over-redacts rather than under.
"""
from __future__ import annotations

import re

_SECRET_RE = re.compile(
    r"(xox[baprs]-[A-Za-z0-9-]{8,}"                                  # slack bot/user tokens
    r"|xapp-[A-Za-z0-9-]{8,}"                                        # slack app-level token (Socket Mode)
    r"|sk-[A-Za-z0-9_\-]{16,}"                                       # openai-style keys
    r"|AKIA[0-9A-Z]{16}"                                             # aws access key id
    r"|gh[posru]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"      # github tokens
    r"|eyJ[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}"  # jwt
    r"|(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+"    # key=value secrets
    r"|[\w.+-]+@[\w-]+\.[\w.-]+"                                     # email (PII)
    r"|\b\d{3}-\d{2}-\d{4}\b"                                        # us ssn (PII)
    r")", re.IGNORECASE)
_PRIVKEY_RE = re.compile(r"-----BEGIN[^-]*PRIVATE KEY-----.*?-----END[^-]*PRIVATE KEY-----",
                         re.DOTALL | re.IGNORECASE)


def redact(text: str) -> str:
    return _SECRET_RE.sub("[redacted]", _PRIVKEY_RE.sub("[redacted-key]", text or ""))
