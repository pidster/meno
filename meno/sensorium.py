"""Sensorium adapters: bridge the world to the bus (afferent) and intents to the
world (efferent). Concrete catalogue/schema are deferred (redesign.md); these are
the minimal afferent sources and the effector-intent helper for the bare loop.
"""
from __future__ import annotations

from .event import Event, Kind


class Sensor:
    """Afferent: normalise a source into events. Uncontrolled rate; the gate triages."""
    source = "sensor"

    def sense(self, text: str, **payload) -> Event:
        return Event(content=text, kind=Kind.SENSE, source=self.source, payload=payload)


class ChatSensor(Sensor):
    source = "chat"


class LogSensor(Sensor):
    source = "log"


def fs_read_intent(path: str) -> Event:
    return Event(content=f"intent: read {path}", kind=Kind.INTENT, source="self",
                 payload={"action": "fs_read", "path": path})


def fs_write_intent(path: str, data: str) -> Event:
    return Event(content=f"intent: write {path}", kind=Kind.INTENT, source="self",
                 payload={"action": "fs_write", "path": path, "data": data})
