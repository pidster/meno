"""Service-free Phase 10 cognition smoke path."""

from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(__file__)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from cognition import build_cognition_packet  # noqa: E402
from journal import JournalStore, unknown_residue  # noqa: E402
from memory_projection import ProjectionStore  # noqa: E402


def _residue(label: str) -> dict[str, dict[str, object]]:
    data = unknown_residue("cognition-smoke")
    for field, value in {
        "salience": 0.7,
        "attention_target": label,
        "uncertainty": 0.3,
        "open_tensions": label,
        "drive_refs": ["smoke"],
        "importance_reason": f"smoke fixture: {label}",
        "affect_valence": "neutral",
        "expected_outcome": "preview packet only",
    }.items():
        data[field] = {
            "value": value,
            "source": "cognition-smoke",
            "epistemic_status": "authored",
        }
    return data


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        journal = JournalStore(os.path.join(tmp, "journal.sqlite3"))
        projection = ProjectionStore(os.path.join(tmp, "projection.sqlite3"))
        try:
            journal.append_event(
                event_type="observation",
                epistemic_status="observed",
                actor="smoke",
                source="cognition_smoke",
                capture_method="manual",
                payload={
                    "subject": "cognition preview",
                    "evidence": "projection and retrieval must shape attention",
                    "capture_method": "fixture",
                },
                context={"active_task": "phase-10-smoke", "source_channel": "local"},
                residue=_residue("projection retrieval attention chain"),
            )
            projection.project_journal(journal)
            entry = projection.candidate("entity", "cognition preview")
            if entry is None:
                raise RuntimeError("smoke projection did not create entry candidate")
            packet = build_cognition_packet(
                journal,
                projection,
                entry_candidate_ids=[entry["candidate_id"]],
                immediate_context={"prompt": "what comes to mind now"},
            )
            print(packet["packet_status"])
            print(packet["selected_next_step"]["class"])
            return 0 if packet["packet_status"] == "accepted" else 1
        finally:
            projection.close()
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
