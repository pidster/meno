"""SurrealDB connection utilities for meno."""

from surrealdb import Surreal

DEFAULT_URL = "ws://127.0.0.1:8000"
DEFAULT_NS = "meno"
DEFAULT_DB = "meno"


def connect(url=DEFAULT_URL, ns=DEFAULT_NS, db=DEFAULT_DB):
    """Create and return a connected SurrealDB client."""
    client = Surreal(url)
    client.use(ns, db)
    return client
