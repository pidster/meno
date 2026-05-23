"""Phase 2 memory projection: typed interpretations over journal evidence.

This module is intentionally standalone and stdlib-only. It projects a narrow
fixture-first slice from journal evidence into auditable candidate records; it
does not implement retrieval, decay, traversal, or SurrealDB storage.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from journal import JournalStore, canonical_json, content_hash, utc_now


PROJECTION_VERSION = 1

EXPOSURE_RANK = {
    "public": 0,
    "team": 1,
    "local-only": 2,
    "internal-only": 3,
}


class ProjectionError(Exception):
    """Base projection exception."""


class ProjectionValidationError(ProjectionError):
    """Raised when projection records violate the evidence contract."""


@dataclass(frozen=True)
class EvidenceRef:
    event_id: str
    event_sequence: int
    event_hash: str
    event_type: str
    event_epistemic_status: str
    payload_path: str
    residue_field: str
    link_type: str
    replay_trace_item: str
    source_selector: str
    source_value_hash: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_sequence": self.event_sequence,
            "event_hash": self.event_hash,
            "event_type": self.event_type,
            "event_epistemic_status": self.event_epistemic_status,
            "payload_path": self.payload_path,
            "residue_field": self.residue_field,
            "link_type": self.link_type,
            "replay_trace_item": self.replay_trace_item,
            "source_selector": self.source_selector,
            "source_value_hash": self.source_value_hash,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class ConfidenceRecord:
    level: str
    evidence_class: str
    inference_distance: str
    corroboration_count: int
    contradiction_count: int
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "evidence_class": self.evidence_class,
            "inference_distance": self.inference_distance,
            "corroboration_count": self.corroboration_count,
            "contradiction_count": self.contradiction_count,
            "rationale": self.rationale,
        }


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_label(value: str) -> str:
    return " ".join(value.strip().lower().split())


def source_value_hash(value: Any) -> str:
    return stable_hash(value)


def candidate_id(kind: str, label: str, target_kind: str = "memory") -> str:
    return "cand_" + stable_hash(
        {
            "kind": kind,
            "label": normalize_label(label),
            "target_kind": target_kind,
        }
    )[:24]


def projection_record_id(
    run_id: str,
    candidate: str,
    decision: str,
    rule_id: str,
    evidence_refs: list[dict[str, Any]],
) -> str:
    return "proj_" + stable_hash(
        {
            "projection_version": PROJECTION_VERSION,
            "run_id": run_id,
            "candidate_id": candidate,
            "decision": decision,
            "rule_id": rule_id,
            "evidence_refs": evidence_refs,
        }
    )[:24]


def edge_id(
    source_candidate_id: str,
    target_candidate_id: str,
    edge_type: str,
    evidence_refs: list[dict[str, Any]],
) -> str:
    return "edge_" + stable_hash(
        {
            "source_candidate_id": source_candidate_id,
            "target_candidate_id": target_candidate_id,
            "edge_type": edge_type,
            "evidence_refs": evidence_refs,
        }
    )[:24]


def relation_id(
    relation_type: str,
    source_candidate_id: str,
    target_candidate_id: str,
    evidence_refs: list[dict[str, Any]],
) -> str:
    return "rel_" + stable_hash(
        {
            "relation_type": relation_type,
            "source_candidate_id": source_candidate_id,
            "target_candidate_id": target_candidate_id,
            "evidence_refs": evidence_refs,
        }
    )[:24]


class ProjectionStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._evidence_scopes: dict[str, dict[str, dict[str, Any]]] = {}
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projection_runs (
                id TEXT PRIMARY KEY,
                projection_key TEXT NOT NULL,
                projection_version INTEGER NOT NULL,
                source_sequence_start INTEGER,
                source_sequence_end INTEGER,
                source_event_hashes_json TEXT NOT NULL,
                created_candidate_ids_json TEXT NOT NULL,
                rejected_candidate_ids_json TEXT NOT NULL,
                warnings_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
                failure_reason TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS memory_candidates (
                candidate_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                label TEXT NOT NULL,
                epistemic_status TEXT NOT NULL,
                acceptance_status TEXT NOT NULL CHECK (
                    acceptance_status IN ('candidate', 'provisional', 'accepted', 'rejected')
                ),
                relation_status TEXT NOT NULL CHECK (
                    relation_status IN ('active', 'conflicted', 'superseded', 'invalidated')
                ),
                confidence_json TEXT NOT NULL,
                source_refs_json TEXT NOT NULL,
                privacy_scope_json TEXT NOT NULL,
                resource_scope_json TEXT NOT NULL,
                semantic_fingerprint TEXT NOT NULL,
                created_from_sequence_range_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memory_edges (
                id TEXT PRIMARY KEY,
                source_candidate_id TEXT NOT NULL,
                target_candidate_id TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                direction TEXT NOT NULL CHECK (direction IN ('directed', 'reverse', 'symmetric')),
                epistemic_status TEXT NOT NULL,
                confidence_json TEXT NOT NULL,
                source_refs_json TEXT NOT NULL,
                privacy_scope_json TEXT NOT NULL,
                resource_scope_json TEXT NOT NULL,
                semantic_fingerprint TEXT NOT NULL,
                projection_run_id TEXT NOT NULL,
                FOREIGN KEY (source_candidate_id) REFERENCES memory_candidates(candidate_id),
                FOREIGN KEY (target_candidate_id) REFERENCES memory_candidates(candidate_id),
                FOREIGN KEY (projection_run_id) REFERENCES projection_runs(id)
            );

            CREATE TABLE IF NOT EXISTS projection_decisions (
                projection_record_id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                acceptance_status_before TEXT,
                acceptance_status_after TEXT NOT NULL,
                relation_status_before TEXT,
                relation_status_after TEXT NOT NULL,
                projection_run_id TEXT NOT NULL,
                projection_rule_id TEXT NOT NULL,
                projection_version INTEGER NOT NULL,
                projection_fingerprint TEXT NOT NULL,
                source_refs_json TEXT NOT NULL,
                confidence_record_json TEXT NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (candidate_id) REFERENCES memory_candidates(candidate_id),
                FOREIGN KEY (projection_run_id) REFERENCES projection_runs(id)
            );

            CREATE TABLE IF NOT EXISTS candidate_transitions (
                id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                from_acceptance_status TEXT,
                to_acceptance_status TEXT NOT NULL,
                from_relation_status TEXT,
                to_relation_status TEXT NOT NULL,
                source_refs_json TEXT NOT NULL,
                projection_decision_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (candidate_id) REFERENCES memory_candidates(candidate_id),
                FOREIGN KEY (projection_decision_id)
                    REFERENCES projection_decisions(projection_record_id)
            );

            CREATE TABLE IF NOT EXISTS projection_relations (
                id TEXT PRIMARY KEY,
                relation_type TEXT NOT NULL,
                source_candidate_id TEXT NOT NULL,
                target_candidate_id TEXT NOT NULL,
                direction TEXT NOT NULL CHECK (direction IN ('directed', 'reverse', 'symmetric')),
                source_refs_json TEXT NOT NULL,
                privacy_scope_json TEXT NOT NULL,
                resource_scope_json TEXT NOT NULL,
                confidence_json TEXT NOT NULL,
                projection_run_id TEXT NOT NULL,
                projection_rule_id TEXT NOT NULL,
                projection_version INTEGER NOT NULL,
                projection_decision_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (source_candidate_id) REFERENCES memory_candidates(candidate_id),
                FOREIGN KEY (target_candidate_id) REFERENCES memory_candidates(candidate_id),
                FOREIGN KEY (projection_run_id) REFERENCES projection_runs(id),
                FOREIGN KEY (projection_decision_id)
                    REFERENCES projection_decisions(projection_record_id)
            );

            CREATE TABLE IF NOT EXISTS projection_rejections (
                id TEXT PRIMARY KEY,
                source_refs_json TEXT NOT NULL,
                candidate_kind TEXT NOT NULL,
                normalized_claim TEXT NOT NULL,
                epistemic_status TEXT NOT NULL,
                privacy_scope_json TEXT NOT NULL,
                resource_scope_json TEXT NOT NULL,
                rejection_reason TEXT NOT NULL,
                rejecting_rule_id TEXT NOT NULL,
                projection_run_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (projection_run_id) REFERENCES projection_runs(id)
            );

            CREATE TABLE IF NOT EXISTS projection_evidence_refs (
                id TEXT PRIMARY KEY,
                projection_record_id TEXT,
                record_type TEXT NOT NULL,
                record_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                event_sequence INTEGER NOT NULL,
                event_hash TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_epistemic_status TEXT NOT NULL,
                payload_path TEXT NOT NULL,
                residue_field TEXT NOT NULL,
                link_type TEXT NOT NULL,
                replay_trace_item TEXT NOT NULL,
                source_selector TEXT NOT NULL,
                source_value_hash TEXT NOT NULL,
                rationale TEXT NOT NULL,
                FOREIGN KEY (projection_record_id)
                    REFERENCES projection_decisions(projection_record_id)
            );

            CREATE TABLE IF NOT EXISTS candidate_lifecycle (
                candidate_id TEXT PRIMARY KEY,
                lifecycle_state TEXT NOT NULL CHECK (
                    lifecycle_state IN (
                        'active', 'dormant', 'rediscovered',
                        'pruning_proposed', 'tombstoned'
                    )
                ),
                accessibility REAL NOT NULL CHECK (accessibility >= 0.0 AND accessibility <= 1.0),
                last_reinforced_event_id TEXT,
                last_maintenance_event_id TEXT NOT NULL,
                decay_basis_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (candidate_id) REFERENCES memory_candidates(candidate_id)
            );

            CREATE TABLE IF NOT EXISTS edge_lifecycle (
                edge_id TEXT PRIMARY KEY,
                lifecycle_state TEXT NOT NULL CHECK (
                    lifecycle_state IN (
                        'active', 'weakened', 'archived',
                        'rediscovered_bridge', 'pruning_proposed',
                        'released', 'tombstoned'
                    )
                ),
                accessibility REAL NOT NULL CHECK (accessibility >= 0.0 AND accessibility <= 1.0),
                traversal_factor REAL NOT NULL CHECK (traversal_factor >= 0.0 AND traversal_factor <= 1.0),
                last_reinforced_event_id TEXT,
                last_maintenance_event_id TEXT NOT NULL,
                decay_basis_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (edge_id) REFERENCES memory_edges(id)
            );

            CREATE TABLE IF NOT EXISTS lifecycle_history (
                id TEXT PRIMARY KEY,
                target_type TEXT NOT NULL CHECK (target_type IN ('candidate', 'edge')),
                target_id TEXT NOT NULL,
                from_lifecycle_state TEXT,
                to_lifecycle_state TEXT NOT NULL,
                from_accessibility REAL,
                to_accessibility REAL NOT NULL,
                maintenance_event_id TEXT NOT NULL,
                basis_json TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TRIGGER IF NOT EXISTS memory_candidates_no_delete
            BEFORE DELETE ON memory_candidates
            BEGIN
                SELECT RAISE(ABORT, 'memory_candidates cannot be deleted without audited pruning');
            END;

            CREATE TRIGGER IF NOT EXISTS memory_edges_no_delete
            BEFORE DELETE ON memory_edges
            BEGIN
                SELECT RAISE(ABORT, 'memory_edges cannot be deleted without audited pruning');
            END;
            """
        )
        self._conn.commit()

    def required_tables(self) -> set[str]:
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        return {row["name"] for row in rows}

    def project_journal(
        self,
        journal: JournalStore,
        *,
        fail_after_run_start: bool = False,
        fail_after_first_write: bool = False,
    ) -> str:
        events = journal.iter_events()
        warnings = journal.verify_integrity()
        projection_key = "pkey_" + stable_hash(
            {
                "projection_version": PROJECTION_VERSION,
                "events": [(event["id"], event["content_hash"]) for event in events],
            }
        )[:24]
        run_id = "run_" + uuid.uuid4().hex[:24]
        sequence_start = events[0]["sequence"] if events else None
        sequence_end = events[-1]["sequence"] if events else None
        source_hashes = {event["id"]: event["content_hash"] for event in events}
        self._insert_run(
            run_id,
            projection_key,
            sequence_start,
            sequence_end,
            source_hashes,
            warnings,
            status="running",
            failure_reason=None,
        )

        if warnings:
            self._finish_run(
                run_id,
                status="failed",
                failure_reason="journal integrity warnings block projection",
            )
            raise ProjectionValidationError("journal integrity warnings block projection")

        if fail_after_run_start:
            self._finish_run(
                run_id,
                status="failed",
                failure_reason="injected failure",
            )
            raise ProjectionError("injected failure")

        created: set[str] = set()
        rejected: set[str] = set()
        try:
            with self._conn:
                self._project_events(
                    run_id,
                    events,
                    created,
                    rejected,
                    fail_after_first_write=fail_after_first_write,
                )
                self._conn.execute(
                    """
                    UPDATE projection_runs
                    SET status = 'succeeded',
                        failure_reason = NULL,
                        created_candidate_ids_json = ?,
                        rejected_candidate_ids_json = ?,
                        completed_at = ?
                    WHERE id = ?
                    """,
                    (
                        canonical_json(sorted(created)),
                        canonical_json(sorted(rejected)),
                        utc_now(),
                        run_id,
                    ),
                )
        except Exception as exc:
            self._finish_run(
                run_id,
                status="failed",
                failure_reason=str(exc),
            )
            raise
        return run_id

    def validate_evidence_ref(
        self,
        evidence_ref: dict[str, Any],
        journal: JournalStore,
    ) -> None:
        required = set(EvidenceRef.__annotations__)
        missing = sorted(required - evidence_ref.keys())
        if missing:
            raise ProjectionValidationError(f"evidence ref missing fields: {missing}")
        event = journal.get_event(evidence_ref["event_id"])
        if event is None:
            raise ProjectionValidationError("evidence ref event does not exist")
        if event["content_hash"] != evidence_ref["event_hash"]:
            raise ProjectionValidationError("evidence ref hash mismatch")
        if evidence_ref["event_hash"] != content_hash(event):
            raise ProjectionValidationError("evidence ref source event failed integrity")
        if evidence_ref["payload_path"] == "event" or evidence_ref["source_selector"] == "event":
            raise ProjectionValidationError("event-level-only evidence ref is not allowed")
        value = self._resolve_selector(event, evidence_ref["source_selector"])
        if source_value_hash(value) != evidence_ref["source_value_hash"]:
            raise ProjectionValidationError("evidence ref source value hash mismatch")

    def candidates(self) -> list[dict[str, Any]]:
        candidates = [self._row_candidate(row) for row in self._conn.execute(
            "SELECT * FROM memory_candidates ORDER BY kind, label"
        ).fetchall()]
        for candidate in candidates:
            candidate["lifecycle"] = self.candidate_lifecycle(candidate["candidate_id"])
        return candidates

    def candidate(self, kind: str, label: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM memory_candidates WHERE kind = ? AND label = ?",
            (kind, label),
        ).fetchone()
        if row is None:
            return None
        candidate = self._row_candidate(row)
        candidate["lifecycle"] = self.candidate_lifecycle(candidate["candidate_id"])
        return candidate

    def edges(self) -> list[dict[str, Any]]:
        edges = [self._row_json(row) for row in self._conn.execute(
            "SELECT * FROM memory_edges ORDER BY edge_type, id"
        ).fetchall()]
        for edge in edges:
            edge["lifecycle"] = self.edge_lifecycle(edge["id"])
        return edges

    def decisions(self) -> list[dict[str, Any]]:
        return [self._row_json(row) for row in self._conn.execute(
            "SELECT * FROM projection_decisions ORDER BY timestamp, projection_record_id"
        ).fetchall()]

    def relations(self) -> list[dict[str, Any]]:
        return [self._row_json(row) for row in self._conn.execute(
            "SELECT * FROM projection_relations ORDER BY relation_type, id"
        ).fetchall()]

    def rejections(self) -> list[dict[str, Any]]:
        return [self._row_json(row) for row in self._conn.execute(
            "SELECT * FROM projection_rejections ORDER BY id"
        ).fetchall()]

    def transitions(self) -> list[dict[str, Any]]:
        return [self._row_json(row) for row in self._conn.execute(
            "SELECT * FROM candidate_transitions ORDER BY id"
        ).fetchall()]

    def evidence_refs(self) -> list[dict[str, Any]]:
        return [self._row_json(row) for row in self._conn.execute(
            "SELECT * FROM projection_evidence_refs ORDER BY id"
        ).fetchall()]

    def candidate_lifecycle(self, candidate_id: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
        if candidate_id is None:
            return [
                self._row_json(row)
                for row in self._conn.execute(
                    "SELECT * FROM candidate_lifecycle ORDER BY candidate_id"
                ).fetchall()
            ]
        row = self._conn.execute(
            "SELECT * FROM candidate_lifecycle WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        if row is None:
            return {
                "candidate_id": candidate_id,
                "lifecycle_state": "active",
                "accessibility": 1.0,
                "last_reinforced_event_id": None,
                "last_maintenance_event_id": None,
                "decay_basis": {},
                "updated_at": None,
            }
        return self._row_json(row)

    def edge_lifecycle(self, edge_id: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
        if edge_id is None:
            return [
                self._row_json(row)
                for row in self._conn.execute(
                    "SELECT * FROM edge_lifecycle ORDER BY edge_id"
                ).fetchall()
            ]
        row = self._conn.execute(
            "SELECT * FROM edge_lifecycle WHERE edge_id = ?",
            (edge_id,),
        ).fetchone()
        if row is None:
            return {
                "edge_id": edge_id,
                "lifecycle_state": "active",
                "accessibility": 1.0,
                "traversal_factor": 1.0,
                "last_reinforced_event_id": None,
                "last_maintenance_event_id": None,
                "decay_basis": {},
                "updated_at": None,
            }
        return self._row_json(row)

    def lifecycle_history(self) -> list[dict[str, Any]]:
        return [
            self._row_json(row)
            for row in self._conn.execute(
                "SELECT * FROM lifecycle_history ORDER BY timestamp, id"
            ).fetchall()
        ]

    def record_candidate_lifecycle(
        self,
        *,
        journal: JournalStore,
        candidate_id: str,
        lifecycle_state: str,
        accessibility: float,
        maintenance_event: dict[str, Any],
        decay_basis: dict[str, Any],
        last_reinforced_event_id: str | None = None,
    ) -> None:
        self._validate_maintenance_event(
            journal,
            maintenance_event,
            allowed_types={"candidate_dormancy_mark", "rediscovery", "pruning_decision"},
            target_type="candidate",
            target_id=candidate_id,
            lifecycle_state=lifecycle_state,
        )
        if self._get_candidate_by_id(candidate_id) is None:
            raise ProjectionValidationError("candidate lifecycle target is missing")
        previous = self.candidate_lifecycle(candidate_id)
        now = utc_now()
        self._conn.execute(
            """
            INSERT INTO candidate_lifecycle (
                candidate_id, lifecycle_state, accessibility,
                last_reinforced_event_id, last_maintenance_event_id,
                decay_basis_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id) DO UPDATE SET
                lifecycle_state = excluded.lifecycle_state,
                accessibility = excluded.accessibility,
                last_reinforced_event_id = excluded.last_reinforced_event_id,
                last_maintenance_event_id = excluded.last_maintenance_event_id,
                decay_basis_json = excluded.decay_basis_json,
                updated_at = excluded.updated_at
            """,
            (
                candidate_id,
                lifecycle_state,
                float(accessibility),
                last_reinforced_event_id,
                maintenance_event["id"],
                canonical_json(decay_basis),
                now,
            ),
        )
        self._record_lifecycle_history(
            target_type="candidate",
            target_id=candidate_id,
            previous=previous,
            new_state=lifecycle_state,
            new_accessibility=float(accessibility),
            maintenance_event_id=maintenance_event["id"],
            basis=decay_basis,
        )
        self._conn.commit()

    def record_edge_lifecycle(
        self,
        *,
        journal: JournalStore,
        edge_id: str,
        lifecycle_state: str,
        accessibility: float,
        traversal_factor: float,
        maintenance_event: dict[str, Any],
        decay_basis: dict[str, Any],
        last_reinforced_event_id: str | None = None,
    ) -> None:
        self._validate_maintenance_event(
            journal,
            maintenance_event,
            allowed_types={"edge_decay_assessment", "edge_archival", "rediscovery", "pruning_decision"},
            target_type="edge",
            target_id=edge_id,
            lifecycle_state=lifecycle_state,
        )
        if self._conn.execute("SELECT 1 FROM memory_edges WHERE id = ?", (edge_id,)).fetchone() is None:
            raise ProjectionValidationError("edge lifecycle target is missing")
        previous = self.edge_lifecycle(edge_id)
        now = utc_now()
        self._conn.execute(
            """
            INSERT INTO edge_lifecycle (
                edge_id, lifecycle_state, accessibility, traversal_factor,
                last_reinforced_event_id, last_maintenance_event_id,
                decay_basis_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(edge_id) DO UPDATE SET
                lifecycle_state = excluded.lifecycle_state,
                accessibility = excluded.accessibility,
                traversal_factor = excluded.traversal_factor,
                last_reinforced_event_id = excluded.last_reinforced_event_id,
                last_maintenance_event_id = excluded.last_maintenance_event_id,
                decay_basis_json = excluded.decay_basis_json,
                updated_at = excluded.updated_at
            """,
            (
                edge_id,
                lifecycle_state,
                float(accessibility),
                float(traversal_factor),
                last_reinforced_event_id,
                maintenance_event["id"],
                canonical_json(decay_basis),
                now,
            ),
        )
        self._record_lifecycle_history(
            target_type="edge",
            target_id=edge_id,
            previous=previous,
            new_state=lifecycle_state,
            new_accessibility=float(accessibility),
            maintenance_event_id=maintenance_event["id"],
            basis=decay_basis,
        )
        self._conn.commit()

    def runs(self) -> list[dict[str, Any]]:
        return [self._row_json(row) for row in self._conn.execute(
            "SELECT * FROM projection_runs ORDER BY started_at, id"
        ).fetchall()]

    def _insert_run(
        self,
        run_id: str,
        projection_key: str,
        sequence_start: int | None,
        sequence_end: int | None,
        source_hashes: dict[str, str],
        warnings: list[dict[str, Any]],
        *,
        status: str,
        failure_reason: str | None,
    ) -> None:
        now = utc_now()
        self._conn.execute(
            """
            INSERT INTO projection_runs (
                id, projection_key, projection_version, source_sequence_start, source_sequence_end,
                source_event_hashes_json, created_candidate_ids_json,
                rejected_candidate_ids_json, warnings_json, status, failure_reason,
                started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                projection_key,
                PROJECTION_VERSION,
                sequence_start,
                sequence_end,
                canonical_json(source_hashes),
                canonical_json([]),
                canonical_json([]),
                canonical_json(warnings),
                status,
                failure_reason,
                now,
                now if status in {"succeeded", "failed"} else None,
            ),
        )
        self._conn.commit()

    def _finish_run(
        self,
        run_id: str,
        *,
        status: str,
        failure_reason: str | None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE projection_runs
            SET status = ?, failure_reason = ?, completed_at = ?
            WHERE id = ?
            """,
            (status, failure_reason, utc_now(), run_id),
        )
        self._conn.commit()

    def _project_events(
        self,
        run_id: str,
        events: list[dict[str, Any]],
        created: set[str],
        rejected: set[str],
        *,
        fail_after_first_write: bool = False,
    ) -> None:
        for event in events:
            if event["event_type"] == "conversation":
                self._project_conversation(run_id, event, created, rejected)
            elif event["event_type"] == "observation":
                self._project_observation(run_id, event, created)
            elif event["event_type"] == "dream":
                self._project_dream(run_id, event, created)
            elif event["event_type"] == "rehearsal":
                self._project_rehearsal(run_id, event, created)
            elif event["event_type"] == "outcome":
                self._project_outcome(run_id, event, created)
            elif event["event_type"] == "decision":
                self._project_decision(run_id, event, created)
            elif event["event_type"] == "correction":
                self._project_correction(run_id, event, created, rejected)
            elif event["event_type"] == "reflection":
                self._project_reflection(run_id, event, created)
            if fail_after_first_write and created:
                raise ProjectionError("injected failure after candidate write")

    def _project_conversation(
        self,
        run_id: str,
        event: dict[str, Any],
        created: set[str],
        rejected: set[str],
    ) -> None:
        message = str(event["payload"]["message"])
        utterance_ref = self._evidence_ref(
            event,
            payload_path="payload.message",
            source_selector="payload.message",
            rationale="conversation message is an authored utterance",
        )
        self._upsert_candidate(
            run_id=run_id,
            kind="experience",
            label=f"utterance:{event['id']}",
            epistemic_status=event["epistemic_status"],
            acceptance_status="accepted" if event["epistemic_status"] == "observed" else "provisional",
            relation_status="active",
            confidence=self._confidence(event["epistemic_status"], "direct utterance"),
            evidence_refs=[utterance_ref],
            rule_id="conversation_utterance",
            reason="conversation becomes an experience candidate",
            created=created,
        )

        truth_claim = self._extract_truth_claim(message)
        if truth_claim:
            rejected_id = self._record_rejection(
                run_id,
                candidate_kind="concept",
                normalized_claim=truth_claim,
                epistemic_status=event["epistemic_status"],
                evidence_refs=[utterance_ref],
                privacy_scope=event["privacy_scope"],
                resource_scope=event["resource_scope"],
                reason="conversation text cannot establish factual world truth",
                rule_id="conversation_claim_not_fact",
            )
            rejected.add(rejected_id)

        preference = self._extract_preference(message)
        if preference:
            self._upsert_candidate(
                run_id=run_id,
                kind="preference",
                label=preference,
                epistemic_status="authored",
                acceptance_status="provisional",
                relation_status="active",
                confidence=self._confidence("authored", "isolated self-report"),
                evidence_refs=[utterance_ref],
                rule_id="isolated_preference_self_report",
                reason="isolated preference self-report remains provisional",
                created=created,
            )

    def _project_observation(
        self,
        run_id: str,
        event: dict[str, Any],
        created: set[str],
    ) -> None:
        subject = str(event["payload"]["subject"])
        evidence = str(event["payload"]["evidence"])
        subject_ref = self._evidence_ref(
            event,
            payload_path="payload.subject",
            source_selector="payload.subject",
            rationale="observation subject supports factual memory",
        )
        evidence_ref = self._evidence_ref(
            event,
            payload_path="payload.evidence",
            source_selector="payload.evidence",
            rationale="observation evidence supports factual memory",
        )
        subject_id = self._upsert_candidate(
            run_id=run_id,
            kind="entity",
            label=subject,
            epistemic_status="observed",
            acceptance_status="accepted",
            relation_status="active",
            confidence=self._confidence("observed", "observed subject"),
            evidence_refs=[subject_ref],
            rule_id="observed_subject",
            reason="observed subject becomes factual entity candidate",
            created=created,
        )
        evidence_id = self._upsert_candidate(
            run_id=run_id,
            kind="concept",
            label=evidence,
            epistemic_status="observed",
            acceptance_status="accepted",
            relation_status="active",
            confidence=self._confidence("observed", "observed evidence"),
            evidence_refs=[evidence_ref],
            rule_id="observed_evidence",
            reason="observed evidence becomes factual concept candidate",
            created=created,
        )
        self._upsert_edge(
            run_id,
            subject_id,
            evidence_id,
            edge_type="observed_cooccurrence",
            direction="symmetric",
            epistemic_status="observed",
            confidence=self._confidence("observed", "same observation event"),
            evidence_refs=[subject_ref, evidence_ref],
            privacy_scope=event["privacy_scope"],
            resource_scope=event["resource_scope"],
        )

    def _project_dream(self, run_id: str, event: dict[str, Any], created: set[str]) -> None:
        candidates = event["payload"].get("generated_candidates", [])
        label = " | ".join(str(item) for item in candidates) or f"dream:{event['id']}"
        ref = self._evidence_ref(
            event,
            payload_path="payload.generated_candidates",
            residue_field="open_tensions",
            source_selector="payload.generated_candidates",
            rationale="dream candidate is a hypothesis from associative residue",
        )
        tension_ref = self._evidence_ref(
            event,
            payload_path="not_applicable",
            residue_field="open_tensions",
            source_selector="residue.open_tensions.value",
            rationale="dream projection retains the tension that shaped the association",
        )
        uncertainty_ref = self._evidence_ref(
            event,
            payload_path="payload.uncertainty_notes",
            source_selector="payload.uncertainty_notes",
            rationale="dream projection retains uncertainty notes",
        )
        salience_ref = self._evidence_ref(
            event,
            payload_path="not_applicable",
            residue_field="salience",
            source_selector="residue.salience.value",
            rationale="dream projection retains salience residue",
        )
        dream_id = self._upsert_candidate(
            run_id=run_id,
            kind="dream",
            label=label,
            epistemic_status="hypothesis",
            acceptance_status="provisional",
            relation_status="active",
            confidence=self._confidence("hypothesis", "dream association"),
            evidence_refs=[ref, tension_ref, uncertainty_ref, salience_ref],
            rule_id="dream_hypothesis",
            reason="dream remains hypothesis with residue rationale",
            created=created,
        )
        residue_label = str(event["residue"].get("open_tensions", {}).get("value", "not_applicable"))
        residue_id = self._upsert_candidate(
            run_id=run_id,
            kind="concept",
            label=f"dream residue:{residue_label}",
            epistemic_status="hypothesis",
            acceptance_status="provisional",
            relation_status="active",
            confidence=self._confidence("hypothesis", "source residue"),
            evidence_refs=[tension_ref, ref],
            rule_id="dream_source_residue",
            reason="dream retains source tension residue",
            created=created,
        )
        self._upsert_edge(
            run_id,
            dream_id,
            residue_id,
            edge_type="dream_association",
            direction="directed",
            epistemic_status="hypothesis",
            confidence=self._confidence("hypothesis", "associative dream link"),
            evidence_refs=[ref, tension_ref, uncertainty_ref, salience_ref],
            privacy_scope=event["privacy_scope"],
            resource_scope=event["resource_scope"],
        )

    def _project_rehearsal(self, run_id: str, event: dict[str, Any], created: set[str]) -> None:
        target = str(event["payload"]["target"])
        strategy = str(event["payload"]["strategy_variant"])
        label = f"{target} via {strategy}"
        ref = self._evidence_ref(
            event,
            payload_path="payload.strategy_variant",
            source_selector="payload.strategy_variant",
            rationale="rehearsal is a dry-run strategy simulation",
        )
        target_ref = self._evidence_ref(
            event,
            payload_path="payload.target",
            source_selector="payload.target",
            rationale="rehearsal projection retains target scenario",
        )
        trace_ref = self._evidence_ref(
            event,
            payload_path="payload.simulated_trace",
            source_selector="payload.simulated_trace",
            rationale="rehearsal projection retains simulated trace",
        )
        failure_ref = self._evidence_ref(
            event,
            payload_path="payload.predicted_failure_modes",
            source_selector="payload.predicted_failure_modes",
            rationale="rehearsal projection retains predicted failure modes",
        )
        self._upsert_candidate(
            run_id=run_id,
            kind="rehearsal",
            label=label,
            epistemic_status="simulation",
            acceptance_status="provisional",
            relation_status="active",
            confidence=self._confidence("simulation", "dry-run trace"),
            evidence_refs=[target_ref, ref, trace_ref, failure_ref],
            rule_id="rehearsal_simulation",
            reason="rehearsal remains simulation until outcome confirms it",
            created=created,
        )

    def _project_outcome(self, run_id: str, event: dict[str, Any], created: set[str]) -> None:
        result = str(event["payload"]["observed_result"])
        ref = self._evidence_ref(
            event,
            payload_path="payload.observed_result",
            source_selector="payload.observed_result",
            link_type="outcome_confirmation",
            rationale="observed outcome can confirm or disconfirm a rehearsal",
        )
        outcome_link_ref = self._evidence_ref(
            event,
            payload_path="not_applicable",
            source_selector="links.0.target_event_id",
            link_type="derived_from",
            rationale="outcome relation cites the rehearsal link target",
        )
        outcome_id = self._upsert_candidate(
            run_id=run_id,
            kind="concept",
            label=result,
            epistemic_status="observed",
            acceptance_status="accepted",
            relation_status="active",
            confidence=self._confidence("observed", "observed outcome"),
            evidence_refs=[ref],
            rule_id="observed_outcome",
            reason="outcome is observed evidence",
            created=created,
        )
        for link in event["links"]:
            if link.get("type") != "derived_from":
                continue
            target_event = {"id": link["target_event_id"]}
            rehearsal = self._find_candidate_by_event("rehearsal", target_event["id"])
            if rehearsal:
                self._upsert_edge(
                    run_id,
                    rehearsal["candidate_id"],
                    outcome_id,
                    edge_type="outcome_confirmation",
                    direction="directed",
                    epistemic_status="observed",
                    confidence=self._confidence("observed", "outcome linked to rehearsal"),
                    evidence_refs=[ref, outcome_link_ref],
                    privacy_scope=event["privacy_scope"],
                    resource_scope=event["resource_scope"],
                )
                self._upsert_relation(
                    run_id,
                    relation_type="outcome_confirms",
                    source_candidate_id=outcome_id,
                    target_candidate_id=rehearsal["candidate_id"],
                    direction="directed",
                    evidence_refs=[ref, outcome_link_ref],
                    reason="observed outcome confirms rehearsal result path",
                )

    def _project_decision(self, run_id: str, event: dict[str, Any], created: set[str]) -> None:
        selected = str(event["payload"]["selected_option"])
        ref = self._evidence_ref(
            event,
            payload_path="payload.selected_option",
            source_selector="payload.selected_option",
            rationale="decision evidence supports accepted preference",
        )
        self._upsert_candidate(
            run_id=run_id,
            kind="preference",
            label=selected,
            epistemic_status="authored",
            acceptance_status="accepted",
            relation_status="active",
            confidence=ConfidenceRecord(
                level="moderate",
                evidence_class="authored",
                inference_distance="one_step",
                corroboration_count=1,
                contradiction_count=0,
                rationale="decision evidence is stronger than isolated self-report",
            ),
            evidence_refs=[ref],
            rule_id="decision_preference",
            reason="decision evidence can support accepted preference",
            created=created,
        )

    def _project_correction(
        self,
        run_id: str,
        event: dict[str, Any],
        created: set[str],
        rejected: set[str],
    ) -> None:
        target_event_id = event["payload"]["target"]
        ref = self._evidence_ref(
            event,
            payload_path="payload.corrected_claim",
            source_selector="payload.corrected_claim",
            link_type=event["links"][0]["type"] if event["links"] else "not_applicable",
            rationale="correction/retraction/contradiction changes interpretation status",
        )
        corrected_label = str(event["payload"]["corrected_claim"])
        corrected_id = self._upsert_candidate(
            run_id=run_id,
            kind="concept",
            label=corrected_label,
            epistemic_status=event["epistemic_status"],
            acceptance_status="provisional",
            relation_status="active",
            confidence=self._confidence(event["epistemic_status"], "correction event"),
            evidence_refs=[ref],
            rule_id="correction_candidate",
            reason="correction creates explicit corrected interpretation",
            created=created,
        )
        target_candidate = self._find_candidate_by_event_any(target_event_id)
        if target_candidate is None:
            rejected_id = self._record_rejection(
                run_id,
                candidate_kind="correction",
                normalized_claim=corrected_label,
                epistemic_status=event["epistemic_status"],
                evidence_refs=[ref],
                privacy_scope=event["privacy_scope"],
                resource_scope=event["resource_scope"],
                reason="correction target had no projected candidate",
                rule_id="missing_correction_target",
            )
            rejected.add(rejected_id)
            return
        if event["epistemic_status"] == "contradiction":
            corrected_candidate = self._get_candidate_by_id(corrected_id)
            self._transition_candidate(
                run_id,
                target_candidate,
                new_relation_status="conflicted",
                evidence_refs=[ref],
                reason="contradiction marks prior candidate as contested",
            )
            if corrected_candidate is not None:
                self._transition_candidate(
                    run_id,
                    corrected_candidate,
                    new_relation_status="conflicted",
                    evidence_refs=[ref],
                    reason="contradiction marks competing candidate as contested",
                )
            self._upsert_relation(
                run_id,
                relation_type="conflicts_with",
                source_candidate_id=corrected_id,
                target_candidate_id=target_candidate["candidate_id"],
                direction="symmetric",
                evidence_refs=[ref],
                reason="contradiction preserves contested interpretations",
            )
        else:
            relation_type = "invalidates" if event["epistemic_status"] == "retraction" else "corrects"
            new_status = "invalidated" if event["epistemic_status"] == "retraction" else "superseded"
            self._transition_candidate(
                run_id,
                target_candidate,
                new_relation_status=new_status,
                evidence_refs=[ref],
                reason="correction changes prior candidate relation status without deletion",
            )
            self._upsert_relation(
                run_id,
                relation_type=relation_type,
                source_candidate_id=corrected_id,
                target_candidate_id=target_candidate["candidate_id"],
                direction="directed",
                evidence_refs=[ref],
                reason="correction keeps prior candidate queryable",
                )

    def _project_reflection(self, run_id: str, event: dict[str, Any], created: set[str]) -> None:
        payload = event["payload"]
        first_claim = next(
            (
                str(claim.get("claim"))
                for claim in payload.get("interpretive_claims", [])
                if claim.get("claim")
            ),
            f"reflection:{event['id']}",
        )
        label = str(payload.get("changed_stance") or first_claim)
        claim_ref = self._evidence_ref(
            event,
            payload_path="payload.interpretive_claims",
            source_selector="payload.interpretive_claims",
            rationale="reflection candidate is authored interpretation over cited retrieval paths",
        )
        retrieval_ref = self._evidence_ref(
            event,
            payload_path="payload.cited_retrieval_paths",
            source_selector="payload.cited_retrieval_paths",
            rationale="reflection retains retrieval path citations",
        )
        uncertainty_ref = self._evidence_ref(
            event,
            payload_path="payload.uncertainty_notes",
            source_selector="payload.uncertainty_notes",
            rationale="reflection preserves uncertainty rather than factual certainty",
        )
        stance_ref = self._evidence_ref(
            event,
            payload_path="payload.changed_stance",
            source_selector="payload.changed_stance",
            rationale="reflection records what changed because of this cognition",
        )
        reflection_id = self._upsert_candidate(
            run_id=run_id,
            kind="reflection",
            label=label,
            epistemic_status=event["epistemic_status"],
            acceptance_status="provisional",
            relation_status="active",
            confidence=self._confidence(event["epistemic_status"], "authored reflection"),
            evidence_refs=[claim_ref, retrieval_ref, uncertainty_ref, stance_ref],
            rule_id="authored_reflection",
            reason="reflection is authored meaning, not factual memory",
            created=created,
        )
        for path in payload.get("cited_retrieval_paths", []):
            candidate_id = path.get("candidate_id")
            if not candidate_id or self._get_candidate_by_id(candidate_id) is None:
                continue
            self._upsert_edge(
                run_id,
                reflection_id,
                candidate_id,
                edge_type="reflective_interpretation",
                direction="directed",
                epistemic_status=event["epistemic_status"],
                confidence=self._confidence(event["epistemic_status"], "reflection cites retrieval path"),
                evidence_refs=[claim_ref, retrieval_ref],
                privacy_scope=event["privacy_scope"],
                resource_scope=event["resource_scope"],
            )

    def _upsert_candidate(
        self,
        *,
        run_id: str,
        kind: str,
        label: str,
        epistemic_status: str,
        acceptance_status: str,
        relation_status: str,
        confidence: ConfidenceRecord,
        evidence_refs: list[EvidenceRef],
        rule_id: str,
        reason: str,
        created: set[str],
    ) -> str:
        refs = [ref.to_dict() for ref in evidence_refs]
        self._validate_refs(refs)
        cid = candidate_id(kind, label)
        semantic = stable_hash({"kind": kind, "label": normalize_label(label)})
        existing = self._conn.execute(
            "SELECT * FROM memory_candidates WHERE candidate_id = ?", (cid,)
        ).fetchone()
        before_acceptance = existing["acceptance_status"] if existing else None
        before_relation = existing["relation_status"] if existing else None
        after_acceptance = self._stronger_acceptance(before_acceptance, acceptance_status)
        after_relation = relation_status if before_relation in (None, "active") else before_relation
        existing_refs = json.loads(existing["source_refs_json"]) if existing else []
        combined_refs = self._merge_ref_dicts(existing_refs, refs)
        scope = self._merge_candidate_scopes(
            evidence_refs,
            existing_privacy=json.loads(existing["privacy_scope_json"]) if existing else None,
            existing_resource=json.loads(existing["resource_scope_json"]) if existing else None,
        )
        combined_confidence = self._merge_confidence(
            confidence,
            existing_confidence=json.loads(existing["confidence_json"]) if existing else None,
            ref_count=len(combined_refs),
        )
        unchanged = (
            existing is not None
            and before_acceptance == after_acceptance
            and before_relation == after_relation
            and all(ref in existing_refs for ref in refs)
        )
        self._conn.execute(
            """
            INSERT INTO memory_candidates (
                candidate_id, kind, label, epistemic_status, acceptance_status,
                relation_status, confidence_json, source_refs_json, privacy_scope_json,
                resource_scope_json, semantic_fingerprint,
                created_from_sequence_range_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id) DO UPDATE SET
                epistemic_status = excluded.epistemic_status,
                acceptance_status = excluded.acceptance_status,
                relation_status = excluded.relation_status,
                confidence_json = excluded.confidence_json,
                source_refs_json = excluded.source_refs_json,
                privacy_scope_json = excluded.privacy_scope_json,
                resource_scope_json = excluded.resource_scope_json,
                updated_at = excluded.updated_at
            """,
            (
                cid,
                kind,
                label,
                epistemic_status,
                after_acceptance,
                after_relation,
                canonical_json(combined_confidence.to_dict()),
                canonical_json(combined_refs),
                canonical_json(scope["privacy_scope"]),
                canonical_json(scope["resource_scope"]),
                semantic,
                canonical_json(
                    [
                        min(ref["event_sequence"] for ref in combined_refs),
                        max(ref["event_sequence"] for ref in combined_refs),
                    ]
                ),
                utc_now(),
            ),
        )
        if not unchanged:
            if existing is None:
                decision = "created"
            elif before_acceptance != after_acceptance:
                decision = "promoted"
            elif before_relation != after_relation:
                decision = after_relation
            else:
                decision = "retained"
            decision_id = self._record_decision(
                run_id=run_id,
                candidate=cid,
                decision=decision,
                acceptance_before=before_acceptance,
                acceptance_after=after_acceptance,
                relation_before=before_relation,
                relation_after=after_relation,
                rule_id=rule_id,
                refs=refs,
                confidence=combined_confidence,
                reason=reason,
            )
            if before_acceptance != after_acceptance or before_relation != after_relation:
                self._record_transition(
                    cid,
                    before_acceptance,
                    after_acceptance,
                    before_relation,
                    after_relation,
                    refs,
                    decision_id,
                    reason,
                )
        if existing is None:
            created.add(cid)
        return cid

    def _upsert_edge(
        self,
        run_id: str,
        source_candidate_id: str,
        target_candidate_id: str,
        *,
        edge_type: str,
        direction: str,
        epistemic_status: str,
        confidence: ConfidenceRecord,
        evidence_refs: list[EvidenceRef],
        privacy_scope: dict[str, Any],
        resource_scope: dict[str, Any],
    ) -> str:
        refs = [ref.to_dict() for ref in evidence_refs]
        eid = edge_id(source_candidate_id, target_candidate_id, edge_type, refs)
        self._conn.execute(
            """
            INSERT OR IGNORE INTO memory_edges (
                id, source_candidate_id, target_candidate_id, edge_type, direction,
                epistemic_status, confidence_json, source_refs_json,
                privacy_scope_json, resource_scope_json, semantic_fingerprint,
                projection_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eid,
                source_candidate_id,
                target_candidate_id,
                edge_type,
                direction,
                epistemic_status,
                canonical_json(confidence.to_dict()),
                canonical_json(refs),
                canonical_json(privacy_scope),
                canonical_json(resource_scope),
                stable_hash(
                    {
                        "source": source_candidate_id,
                        "target": target_candidate_id,
                        "edge_type": edge_type,
                    }
                ),
                run_id,
            ),
        )
        for ref in refs:
            self._record_evidence_ref(
                None,
                ref,
                record_type="edge",
                record_id=eid,
            )
        return eid

    def _record_decision(
        self,
        *,
        run_id: str,
        candidate: str,
        decision: str,
        acceptance_before: str | None,
        acceptance_after: str,
        relation_before: str | None,
        relation_after: str,
        rule_id: str,
        refs: list[dict[str, Any]],
        confidence: ConfidenceRecord,
        reason: str,
    ) -> str:
        did = projection_record_id(run_id, candidate, decision, rule_id, refs)
        projection_fingerprint = stable_hash(
            {
                "projection_version": PROJECTION_VERSION,
                "candidate_id": candidate,
                "source_refs": refs,
                "decision": decision,
            }
        )
        self._conn.execute(
            """
            INSERT INTO projection_decisions (
                projection_record_id, candidate_id, decision, acceptance_status_before,
                acceptance_status_after, relation_status_before, relation_status_after,
                projection_run_id, projection_rule_id, projection_version,
                projection_fingerprint, source_refs_json, confidence_record_json,
                reason, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                did,
                candidate,
                decision,
                acceptance_before,
                acceptance_after,
                relation_before,
                relation_after,
                run_id,
                rule_id,
                PROJECTION_VERSION,
                projection_fingerprint,
                canonical_json(refs),
                canonical_json(confidence.to_dict()),
                reason,
                utc_now(),
            ),
        )
        for ref in refs:
            self._record_evidence_ref(
                did,
                ref,
                record_type="decision",
                record_id=did,
            )
        return did

    def _record_transition(
        self,
        cid: str,
        before_acceptance: str | None,
        after_acceptance: str,
        before_relation: str | None,
        after_relation: str,
        refs: list[dict[str, Any]],
        decision_id: str,
        reason: str,
    ) -> None:
        tid = "trans_" + stable_hash(
            {
                "candidate_id": cid,
                "from_acceptance_status": before_acceptance,
                "to_acceptance_status": after_acceptance,
                "from_relation_status": before_relation,
                "to_relation_status": after_relation,
                "decision_id": decision_id,
            }
        )[:24]
        self._conn.execute(
            """
            INSERT OR REPLACE INTO candidate_transitions (
                id, candidate_id, from_acceptance_status, to_acceptance_status,
                from_relation_status, to_relation_status, source_refs_json,
                projection_decision_id, reason, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tid,
                cid,
                before_acceptance,
                after_acceptance,
                before_relation,
                after_relation,
                canonical_json(refs),
                decision_id,
                reason,
                utc_now(),
            ),
        )

    def _record_lifecycle_history(
        self,
        *,
        target_type: str,
        target_id: str,
        previous: dict[str, Any],
        new_state: str,
        new_accessibility: float,
        maintenance_event_id: str,
        basis: dict[str, Any],
    ) -> None:
        hid = "life_" + stable_hash(
            {
                "target_type": target_type,
                "target_id": target_id,
                "from_lifecycle_state": previous.get("lifecycle_state"),
                "to_lifecycle_state": new_state,
                "from_accessibility": previous.get("accessibility"),
                "to_accessibility": new_accessibility,
                "maintenance_event_id": maintenance_event_id,
                "basis": basis,
            }
        )[:24]
        self._conn.execute(
            """
            INSERT INTO lifecycle_history (
                id, target_type, target_id, from_lifecycle_state,
                to_lifecycle_state, from_accessibility, to_accessibility,
                maintenance_event_id, basis_json, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hid,
                target_type,
                target_id,
                previous.get("lifecycle_state"),
                new_state,
                previous.get("accessibility"),
                new_accessibility,
                maintenance_event_id,
                canonical_json(basis),
                utc_now(),
            ),
        )

    def _validate_maintenance_event(
        self,
        journal: JournalStore,
        event: dict[str, Any],
        *,
        allowed_types: set[str],
        target_type: str,
        target_id: str,
        lifecycle_state: str,
    ) -> None:
        if not isinstance(event, dict):
            raise ProjectionValidationError("maintenance event must be a journal event envelope")
        persisted = journal.get_event(event.get("id", ""))
        if persisted is None:
            raise ProjectionValidationError("maintenance event is not persisted in journal")
        if persisted["content_hash"] != event.get("content_hash"):
            raise ProjectionValidationError("maintenance event hash does not match journal")
        if event.get("event_type") not in allowed_types:
            raise ProjectionValidationError("maintenance event type is not valid for lifecycle update")
        if event.get("content_hash") != content_hash(event):
            raise ProjectionValidationError("maintenance event failed integrity check")
        if event.get("event_type") == "rediscovery" and not event.get("payload", {}).get("reflection_event_id"):
            raise ProjectionValidationError("rediscovery lifecycle updates require a reflection event")
        payload = event.get("payload", {})
        if target_type == "candidate":
            if event["event_type"] == "candidate_dormancy_mark":
                if payload.get("candidate_id") != target_id or payload.get("new_lifecycle_state") != lifecycle_state:
                    raise ProjectionValidationError("candidate lifecycle event target mismatch")
            elif event["event_type"] == "rediscovery":
                if payload.get("dormant_candidate_id") != target_id or lifecycle_state != "rediscovered":
                    raise ProjectionValidationError("candidate rediscovery event target mismatch")
        if target_type == "edge":
            if event["event_type"] in {"edge_decay_assessment", "edge_archival"}:
                if payload.get("edge_id") != target_id or payload.get("new_lifecycle_state") != lifecycle_state:
                    raise ProjectionValidationError("edge lifecycle event target mismatch")
            elif event["event_type"] == "rediscovery":
                if payload.get("bridge_edge_id") != target_id or lifecycle_state != "rediscovered_bridge":
                    raise ProjectionValidationError("edge rediscovery event target mismatch")

    def _transition_candidate(
        self,
        run_id: str,
        candidate: dict[str, Any],
        *,
        new_relation_status: str,
        evidence_refs: list[EvidenceRef],
        reason: str,
    ) -> None:
        refs = [ref.to_dict() for ref in evidence_refs]
        self._conn.execute(
            "UPDATE memory_candidates SET relation_status = ?, updated_at = ? WHERE candidate_id = ?",
            (new_relation_status, utc_now(), candidate["candidate_id"]),
        )
        decision_id = self._record_decision(
            run_id=run_id,
            candidate=candidate["candidate_id"],
            decision=new_relation_status,
            acceptance_before=candidate["acceptance_status"],
            acceptance_after=candidate["acceptance_status"],
            relation_before=candidate["relation_status"],
            relation_after=new_relation_status,
            rule_id="candidate_relation_transition",
            refs=refs,
            confidence=ConfidenceRecord(
                level="moderate",
                evidence_class="correction",
                inference_distance="direct",
                corroboration_count=1,
                contradiction_count=0,
                rationale=reason,
            ),
            reason=reason,
        )
        self._record_transition(
            candidate["candidate_id"],
            candidate["acceptance_status"],
            candidate["acceptance_status"],
            candidate["relation_status"],
            new_relation_status,
            refs,
            decision_id,
            reason,
        )

    def _upsert_relation(
        self,
        run_id: str,
        *,
        relation_type: str,
        source_candidate_id: str,
        target_candidate_id: str,
        direction: str,
        evidence_refs: list[EvidenceRef],
        reason: str,
    ) -> None:
        refs = [ref.to_dict() for ref in evidence_refs]
        rid = relation_id(relation_type, source_candidate_id, target_candidate_id, refs)
        source_candidate = self._get_candidate_by_id(source_candidate_id)
        if source_candidate is None:
            raise ProjectionValidationError("relation source candidate is missing")
        scope = self._merge_scopes(evidence_refs)
        confidence = ConfidenceRecord(
            level="moderate",
            evidence_class=evidence_refs[0].event_epistemic_status,
            inference_distance="one_step",
            corroboration_count=1 if evidence_refs[0].event_epistemic_status == "observed" else 0,
            contradiction_count=1 if relation_type == "conflicts_with" else 0,
            rationale=reason,
        )
        decision_id = self._record_decision(
            run_id=run_id,
            candidate=source_candidate_id,
            decision=relation_type,
            acceptance_before=source_candidate["acceptance_status"],
            acceptance_after=source_candidate["acceptance_status"],
            relation_before=source_candidate["relation_status"],
            relation_after=source_candidate["relation_status"],
            rule_id=f"relation_{relation_type}",
            refs=refs,
            confidence=confidence,
            reason=reason,
        )
        self._conn.execute(
            """
            INSERT OR IGNORE INTO projection_relations (
                id, relation_type, source_candidate_id, target_candidate_id, direction,
                source_refs_json, privacy_scope_json, resource_scope_json,
                confidence_json, projection_run_id, projection_rule_id,
                projection_version, projection_decision_id, reason, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rid,
                relation_type,
                source_candidate_id,
                target_candidate_id,
                direction,
                canonical_json(refs),
                canonical_json(scope["privacy_scope"]),
                canonical_json(scope["resource_scope"]),
                canonical_json(confidence.to_dict()),
                run_id,
                f"relation_{relation_type}",
                PROJECTION_VERSION,
                decision_id,
                reason,
                utc_now(),
            ),
        )
        for ref in refs:
            self._record_evidence_ref(
                decision_id,
                ref,
                record_type="relation",
                record_id=rid,
            )

    def _record_rejection(
        self,
        run_id: str,
        *,
        candidate_kind: str,
        normalized_claim: str,
        epistemic_status: str,
        evidence_refs: list[EvidenceRef],
        privacy_scope: dict[str, Any],
        resource_scope: dict[str, Any],
        reason: str,
        rule_id: str,
    ) -> str:
        refs = [ref.to_dict() for ref in evidence_refs]
        rid = "rej_" + stable_hash(
            {
                "candidate_kind": candidate_kind,
                "normalized_claim": normalize_label(normalized_claim),
                "refs": refs,
                "rule_id": rule_id,
            }
        )[:24]
        self._conn.execute(
            """
            INSERT OR IGNORE INTO projection_rejections (
                id, source_refs_json, candidate_kind, normalized_claim,
                epistemic_status, privacy_scope_json, resource_scope_json,
                rejection_reason, rejecting_rule_id, projection_run_id, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rid,
                canonical_json(refs),
                candidate_kind,
                normalize_label(normalized_claim),
                epistemic_status,
                canonical_json(privacy_scope),
                canonical_json(resource_scope),
                reason,
                rule_id,
                run_id,
                utc_now(),
            ),
        )
        for ref in refs:
            self._record_evidence_ref(
                None,
                ref,
                record_type="rejection",
                record_id=rid,
            )
        return rid

    def _record_evidence_ref(
        self,
        projection_record_id: str | None,
        ref: dict[str, Any],
        *,
        record_type: str,
        record_id: str,
    ) -> None:
        eid = "eref_" + stable_hash(
            {
                "projection_record_id": projection_record_id,
                "record_type": record_type,
                "record_id": record_id,
                **ref,
            }
        )[:24]
        self._conn.execute(
            """
            INSERT OR IGNORE INTO projection_evidence_refs (
                id, projection_record_id, record_type, record_id, event_id,
                event_sequence, event_hash, event_type, event_epistemic_status,
                payload_path, residue_field, link_type, replay_trace_item,
                source_selector, source_value_hash, rationale
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eid,
                projection_record_id,
                record_type,
                record_id,
                ref["event_id"],
                ref["event_sequence"],
                ref["event_hash"],
                ref["event_type"],
                ref["event_epistemic_status"],
                ref["payload_path"],
                ref["residue_field"],
                ref["link_type"],
                ref["replay_trace_item"],
                ref["source_selector"],
                ref["source_value_hash"],
                ref["rationale"],
            ),
        )

    def _evidence_ref(
        self,
        event: dict[str, Any],
        *,
        payload_path: str,
        source_selector: str,
        rationale: str,
        residue_field: str = "not_applicable",
        link_type: str = "not_applicable",
        replay_trace_item: str = "not_applicable",
    ) -> EvidenceRef:
        value = self._resolve_selector(event, source_selector)
        evidence_ref = EvidenceRef(
            event_id=event["id"],
            event_sequence=event["sequence"],
            event_hash=event["content_hash"],
            event_type=event["event_type"],
            event_epistemic_status=event["epistemic_status"],
            payload_path=payload_path,
            residue_field=residue_field,
            link_type=link_type,
            replay_trace_item=replay_trace_item,
            source_selector=source_selector,
            source_value_hash=source_value_hash(value),
            rationale=rationale,
        )
        self._evidence_scopes[self._evidence_scope_key(evidence_ref)] = {
            "privacy_scope": copy.deepcopy(event["privacy_scope"]),
            "resource_scope": copy.deepcopy(event["resource_scope"]),
        }
        return evidence_ref

    def _validate_refs(self, refs: list[dict[str, Any]]) -> None:
        for ref in refs:
            for key, value in ref.items():
                if value is None or value == "":
                    raise ProjectionValidationError(f"empty evidence ref field: {key}")
            if ref["payload_path"] == "event" or ref["source_selector"] == "event":
                raise ProjectionValidationError("event-level citation is not enough")

    def _resolve_selector(self, event: dict[str, Any], selector: str) -> Any:
        if not selector or selector == "event":
            raise ProjectionValidationError("selector must point below event level")
        current: Any = event
        for part in selector.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                raise ProjectionValidationError(f"source selector does not resolve: {selector}")
        return current

    def _confidence(self, evidence_class: str, rationale: str) -> ConfidenceRecord:
        if evidence_class == "observed":
            level = "strong"
            distance = "direct"
        elif evidence_class in {"hypothesis", "simulation"}:
            level = "weak"
            distance = "speculative"
        elif evidence_class in {"correction", "retraction", "contradiction"}:
            level = "moderate"
            distance = "direct"
        else:
            level = "weak"
            distance = "one_step"
        return ConfidenceRecord(
            level=level,
            evidence_class=evidence_class,
            inference_distance=distance,
            corroboration_count=1 if evidence_class == "observed" else 0,
            contradiction_count=1 if evidence_class == "contradiction" else 0,
            rationale=rationale,
        )

    def _merge_ref_dicts(
        self,
        existing_refs: list[dict[str, Any]],
        new_refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for ref in existing_refs + new_refs:
            key = stable_hash(ref)
            if key in seen:
                continue
            seen.add(key)
            merged.append(ref)
        return sorted(
            merged,
            key=lambda ref: (
                ref["event_sequence"],
                ref["event_id"],
                ref["source_selector"],
                ref["source_value_hash"],
            ),
        )

    def _merge_confidence(
        self,
        current: ConfidenceRecord,
        *,
        existing_confidence: dict[str, Any] | None,
        ref_count: int,
    ) -> ConfidenceRecord:
        if existing_confidence is None:
            return current
        rank = {"none": 0, "weak": 1, "moderate": 2, "strong": 3, "decisive": 4}
        current_rank = rank[current.level]
        existing_rank = rank.get(existing_confidence.get("level", "none"), 0)
        level = current.level if current_rank >= existing_rank else existing_confidence["level"]
        contradiction_count = max(
            current.contradiction_count,
            int(existing_confidence.get("contradiction_count", 0)),
        )
        return ConfidenceRecord(
            level=level,
            evidence_class="mixed"
            if existing_confidence.get("evidence_class") != current.evidence_class
            else current.evidence_class,
            inference_distance=current.inference_distance
            if current_rank >= existing_rank
            else existing_confidence.get("inference_distance", current.inference_distance),
            corroboration_count=ref_count,
            contradiction_count=contradiction_count,
            rationale=f"accumulated from {ref_count} evidence refs",
        )

    def _merge_candidate_scopes(
        self,
        evidence_refs: list[EvidenceRef],
        *,
        existing_privacy: dict[str, Any] | None,
        existing_resource: dict[str, Any] | None,
    ) -> dict[str, dict[str, Any]]:
        scope = self._merge_scopes(evidence_refs)
        if existing_privacy is None or existing_resource is None:
            return scope
        privacy = self._meet_privacy(existing_privacy, scope["privacy_scope"])
        resource = self._meet_resource(existing_resource, scope["resource_scope"])
        return {"privacy_scope": privacy, "resource_scope": resource}

    def _merge_scopes(self, evidence_refs: list[EvidenceRef]) -> dict[str, dict[str, Any]]:
        events = [self._event_from_ref(ref) for ref in evidence_refs]
        privacy = copy.deepcopy(events[0]["privacy_scope"])
        resource = copy.deepcopy(events[0]["resource_scope"])
        for event in events[1:]:
            other_privacy = event["privacy_scope"]
            other_resource = event["resource_scope"]
            privacy = self._meet_privacy(privacy, other_privacy)
            resource = self._meet_resource(resource, other_resource)
        return {"privacy_scope": privacy, "resource_scope": resource}

    def _meet_privacy(
        self,
        left: dict[str, Any],
        right: dict[str, Any],
    ) -> dict[str, Any]:
        privacy = copy.deepcopy(left)
        privacy["export_allowed"] = bool(
            left.get("export_allowed", False) and right.get("export_allowed", False)
        )
        privacy["exposure"] = max(
            [left.get("exposure", "internal-only"), right.get("exposure", "internal-only")],
            key=lambda item: EXPOSURE_RANK.get(item, max(EXPOSURE_RANK.values())),
        )
        if left.get("retention") != right.get("retention"):
            privacy["retention"] = "local"
        return privacy

    def _meet_resource(
        self,
        left: dict[str, Any],
        right: dict[str, Any],
    ) -> dict[str, Any]:
        resource = copy.deepcopy(left)
        for key in (
            "external_contact",
            "network_access",
            "autonomous_spend",
            "compute_escalation",
        ):
            resource[key] = bool(left.get(key, False) and right.get(key, False))
        return resource

    def _event_from_ref(self, ref: EvidenceRef) -> dict[str, Any]:
        key = self._evidence_scope_key(ref)
        return self._evidence_scopes[key]

    def _evidence_scope_key(self, ref: EvidenceRef) -> str:
        return stable_hash(
            {
                "event_id": ref.event_id,
                "source_selector": ref.source_selector,
                "source_value_hash": ref.source_value_hash,
            }
        )

    def _stronger_acceptance(self, before: str | None, after: str) -> str:
        rank = {"rejected": 0, "candidate": 1, "provisional": 2, "accepted": 3}
        if before is None:
            return after
        return after if rank[after] > rank[before] else before

    def _extract_truth_claim(self, message: str) -> str | None:
        match = re.search(r"\b(.+?)\s+is\s+true\b", message, re.IGNORECASE)
        if not match:
            return None
        return normalize_label(match.group(1))

    def _extract_preference(self, message: str) -> str | None:
        match = re.search(r"\bprefer\s+(.+)$", message, re.IGNORECASE)
        if not match:
            return None
        return normalize_label(match.group(1))

    def _find_candidate_by_event(self, kind: str, event_id: str) -> dict[str, Any] | None:
        for candidate in self.candidates():
            if candidate["kind"] != kind:
                continue
            for ref in candidate["source_refs"]:
                if ref["event_id"] == event_id:
                    return candidate
        return None

    def _find_candidate_by_event_any(self, event_id: str) -> dict[str, Any] | None:
        for candidate in self.candidates():
            for ref in candidate["source_refs"]:
                if ref["event_id"] == event_id:
                    return candidate
        return None

    def _get_candidate_by_id(self, cid: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM memory_candidates WHERE candidate_id = ?", (cid,)
        ).fetchone()
        if row is None:
            return None
        candidate = self._row_candidate(row)
        candidate["lifecycle"] = self.candidate_lifecycle(candidate["candidate_id"])
        return candidate

    def _row_candidate(self, row: sqlite3.Row) -> dict[str, Any]:
        return self._row_json(row)

    def _row_json(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        for key in list(data):
            if key.endswith("_json"):
                data[key[:-5]] = json.loads(data.pop(key))
        return data
