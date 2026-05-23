"""Phase 1 journal: append-only evidence capture.

This module is intentionally standalone and stdlib-only. It does not import the
legacy SurrealDB-backed runtime.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1

EVENT_STATUS_MATRIX: dict[str, set[str]] = {
    "conversation": {"authored", "observed"},
    "tool_call": {"observed"},
    "observation": {"observed"},
    "reflection": {"authored", "inferred"},
    "graph_update_proposal": {"inferred"},
    "dream": {"hypothesis"},
    "dream_review": {"authored", "inferred"},
    "rehearsal": {"simulation"},
    "decision": {"authored"},
    "correction": {"correction", "retraction", "contradiction"},
    "outcome": {"observed"},
    "rest": {"authored"},
    "administrative_repair": {"administrative"},
    "retrieval_use_trace": {"observed"},
    "consolidation_run": {"authored"},
    "edge_decay_assessment": {"inferred"},
    "edge_archival": {"inferred"},
    "candidate_dormancy_mark": {"inferred"},
    "rediscovery": {"inferred"},
    "pruning_proposal": {"inferred"},
    "pruning_decision": {"authored"},
}

ALLOWED_EVENT_TYPES = set(EVENT_STATUS_MATRIX)
ALLOWED_EPISTEMIC_STATUSES = {
    status for statuses in EVENT_STATUS_MATRIX.values() for status in statuses
}
ALLOWED_LINK_TYPES = {
    "responds_to",
    "derived_from",
    "observed_during",
    "corrects",
    "supersedes",
    "invalidates",
    "contradicts",
    "caused_by",
    "proposes_from",
    "assesses",
    "archives",
    "marks_dormant",
    "rediscovers",
    "decides_pruning",
}

PAYLOAD_REQUIRED_KEYS: dict[str, set[str]] = {
    "conversation": {"speaker", "message", "channel", "turn_id"},
    "tool_call": {"tool_name", "arguments_summary", "result_boundary", "success"},
    "observation": {"subject", "evidence", "capture_method"},
    "reflection": {
        "cited_source_event_ids",
        "retrieval_result_hash",
        "cited_retrieval_paths",
        "interpretive_claims",
        "open_questions",
        "uncertainty_notes",
        "possible_self_deception",
        "rejected_interpretations",
        "changed_stance",
        "future_attention",
        "proposed_graph_updates",
        "deferred_graph_updates",
    },
    "graph_update_proposal": {
        "proposed_operation",
        "proposed_target_kind",
        "source_event_ids",
        "intended_status",
        "rationale",
    },
    "dream": {"residues_used", "generated_candidates", "uncertainty_notes"},
    "dream_review": {
        "dream_event_id",
        "fragment_id",
        "review_decision",
        "rationale",
        "observed_evidence_event_ids",
        "not_factual",
    },
    "rehearsal": {
        "policy_version",
        "target_refs",
        "problem_context",
        "current_or_failed_approach",
        "strategy_variants",
        "selected_variant_id",
        "improvement_hypothesis",
        "assumptions",
        "simulated_trace",
        "predicted_observations",
        "predicted_failure_modes",
        "validation_criteria",
        "falsification_criteria",
        "candidate_procedure_updates",
        "resource_scope_decision",
        "privacy_scope_decision",
        "review_status",
        "not_executed",
    },
    "decision": {"options_considered", "selected_option", "reason", "constraints"},
    "correction": {"target", "corrected_claim", "reason"},
    "outcome": {"expected_outcome_link", "observed_result", "match"},
    "rest": {"tensions_left_unresolved", "deliberate_non_action_reason", "consolidation_notes"},
    "administrative_repair": {"repair_target", "before_after_hash_evidence", "reason"},
    "retrieval_use_trace": {
        "retrieval_result_hash",
        "used_candidate_ids",
        "used_record_ids",
        "activated_path_ids",
        "retrieval_result_snapshot",
    },
    "consolidation_run": {
        "policy_version",
        "source_event_ids",
        "target_summary",
        "actions_taken",
        "no_action_reason",
    },
    "edge_decay_assessment": {
        "consolidation_event_id",
        "edge_id",
        "previous_lifecycle_state",
        "new_lifecycle_state",
        "previous_accessibility",
        "new_accessibility",
        "decay_basis",
        "source_event_ids",
    },
    "edge_archival": {
        "consolidation_event_id",
        "edge_id",
        "previous_lifecycle_state",
        "new_lifecycle_state",
        "previous_accessibility",
        "new_accessibility",
        "archive_reason",
        "source_event_ids",
        "rediscovery_recipe",
    },
    "candidate_dormancy_mark": {
        "consolidation_event_id",
        "candidate_id",
        "previous_lifecycle_state",
        "new_lifecycle_state",
        "previous_accessibility",
        "new_accessibility",
        "dormancy_reason",
        "source_event_ids",
        "rediscovery_recipe",
    },
    "rediscovery": {
        "consolidation_event_id",
        "dormant_candidate_id",
        "new_evidence_event_id",
        "bridge_edge_id",
        "source_event_ids",
        "reflection_event_id",
        "reflection_required",
        "rediscovery_reason",
    },
    "pruning_proposal": {
        "target_kind",
        "target_id",
        "source_event_ids",
        "affected_path_ids",
        "rejected_alternatives",
        "reversibility_check",
        "rediscovery_recipe",
        "release_rationale",
    },
    "pruning_decision": {
        "proposal_event_id",
        "selected_option",
        "reason",
        "constraints",
    },
}

RESIDUE_FIELDS = {
    "salience",
    "attention_target",
    "uncertainty",
    "open_tensions",
    "drive_refs",
    "importance_reason",
    "affect_valence",
    "expected_outcome",
}

DEFAULT_PRIVACY_SCOPE = {
    "retention": "local",
    "exposure": "local-only",
    "export_allowed": False,
}
DEFAULT_RESOURCE_SCOPE = {
    "external_contact": False,
    "network_access": False,
    "autonomous_spend": False,
    "compute_escalation": False,
}

FACTUAL_EVENT_TYPES = {
    "conversation",
    "tool_call",
    "observation",
    "decision",
    "correction",
    "outcome",
}
PROVISIONAL_EVENT_TYPES = {"reflection", "dream", "rehearsal"}

DREAM_FRAGMENT_KINDS = {
    "association",
    "metaphor",
    "question",
    "tension",
    "image",
    "counterfactual",
    "bridge",
}
DREAM_REVIEW_STATUSES = {
    "raw",
    "review_pending",
    "rejected",
    "deferred",
    "provisionally_useful",
    "corroborated_by_observation",
}
DREAM_RESIDUE_CATEGORIES = {
    "salience",
    "attention_target",
    "uncertainty",
    "open_tension",
    "drive",
    "importance_reason",
    "affect",
    "expected_outcome",
    "retrieval_use",
    "omitted_candidate",
    "ghost_signal",
    "dormant_memory",
    "archived_edge",
    "reflection_question",
    "rejected_interpretation",
    "future_attention",
    "deferred_graph_update",
    "conflict",
    "correction",
}
DREAM_REVIEW_DECISIONS = {
    "reject",
    "defer",
    "leave_raw",
    "propose_provisional",
    "corroborate_observation",
}
REHEARSAL_TARGET_CATEGORIES = {
    "failed_outcome",
    "repeated_workflow",
    "correction",
    "fragile_commitment",
    "reflection_deferred_action",
}
REHEARSAL_REVIEW_STATUSES = {
    "review_pending",
    "rejected",
    "deferred",
    "provisional",
    "validated",
    "falsified",
}
REHEARSAL_PREDICTION_RESULTS = {
    "confirmed",
    "falsified",
    "partially_matched",
    "inconclusive",
}


class JournalError(Exception):
    """Base journal exception."""


class JournalValidationError(JournalError):
    """Raised when an event or proposal violates the journal contract."""


class JournalIntegrityError(JournalError):
    """Raised when persisted journal integrity is broken."""


@dataclass(frozen=True)
class GraphProposal:
    proposed_operation: str
    proposed_target_kind: str
    source_event_ids: list[str]
    intended_status: str
    rationale: str
    requested_scope: dict[str, Any] | None = None


@dataclass(frozen=True)
class JournalReplayContext:
    ordered_recent_event_ids: list[str]
    salient_residues: list[dict[str, Any]]
    attention_targets: list[dict[str, Any]]
    uncertainty_markers: list[dict[str, Any]]
    open_tensions: list[dict[str, Any]]
    drive_refs: list[dict[str, Any]]
    importance_reasons: list[dict[str, Any]]
    affect_valence: list[dict[str, Any]]
    expected_outcomes: list[dict[str, Any]]
    rest_markers: list[dict[str, Any]]
    unresolved_decisions: list[dict[str, Any]]
    provisional_candidates: list[dict[str, Any]]
    privacy_resource_constraints: list[dict[str, Any]]
    evidence_anchors: list[dict[str, Any]]
    traces: list[dict[str, Any]]
    integrity_warnings: list[dict[str, Any]]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_timestamp(value: str | datetime | None) -> str:
    if value is None:
        return utc_now()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if not isinstance(value, str):
        raise JournalValidationError("timestamp must be a string, datetime, or None")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_hash(envelope: dict[str, Any]) -> str:
    hash_input = copy.deepcopy(envelope)
    hash_input.pop("content_hash", None)
    encoded = canonical_json(hash_input).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def unknown_residue(source: str = "unknown") -> dict[str, dict[str, Any]]:
    return {
        field: {"value": "unknown", "source": source, "epistemic_status": "unknown"}
        for field in sorted(RESIDUE_FIELDS)
    }


class JournalStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS journal_meta (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL
            );
            INSERT OR IGNORE INTO journal_meta (key, value) VALUES ('next_sequence', 1);

            CREATE TABLE IF NOT EXISTS journal_events (
                sequence INTEGER PRIMARY KEY,
                id TEXT NOT NULL UNIQUE,
                timestamp TEXT NOT NULL,
                actor TEXT NOT NULL,
                source TEXT NOT NULL,
                capture_method TEXT NOT NULL,
                event_type TEXT NOT NULL,
                epistemic_status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                context_json TEXT NOT NULL,
                residue_json TEXT NOT NULL,
                links_json TEXT NOT NULL,
                idempotency_key TEXT,
                privacy_scope_json TEXT NOT NULL,
                resource_scope_json TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                content_hash TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_journal_idempotency
                ON journal_events(idempotency_key)
                WHERE idempotency_key IS NOT NULL;

            CREATE TRIGGER IF NOT EXISTS journal_events_no_update
            BEFORE UPDATE ON journal_events
            BEGIN
                SELECT RAISE(ABORT, 'journal_events are append-only');
            END;

            CREATE TRIGGER IF NOT EXISTS journal_events_no_delete
            BEFORE DELETE ON journal_events
            BEGIN
                SELECT RAISE(ABORT, 'journal_events are append-only');
            END;
            """
        )
        self._conn.commit()

    def append_event(
        self,
        *,
        event_type: str,
        epistemic_status: str,
        actor: str,
        source: str,
        capture_method: str,
        payload: dict[str, Any],
        context: dict[str, Any],
        residue: dict[str, Any],
        links: list[dict[str, Any]] | None = None,
        privacy_scope: dict[str, Any] | None = None,
        resource_scope: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        timestamp: str | datetime | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        links = links or []
        privacy_scope = copy.deepcopy(privacy_scope or DEFAULT_PRIVACY_SCOPE)
        resource_scope = copy.deepcopy(resource_scope or DEFAULT_RESOURCE_SCOPE)
        normalized_timestamp = normalize_timestamp(timestamp)
        event_id = event_id or str(uuid.uuid4())

        if self.get_event(event_id) is not None:
            raise JournalValidationError(f"duplicate event id: {event_id}")

        self._validate_event_input(
            event_type=event_type,
            epistemic_status=epistemic_status,
            actor=actor,
            source=source,
            capture_method=capture_method,
            payload=payload,
            context=context,
            residue=residue,
            links=links,
            privacy_scope=privacy_scope,
            resource_scope=resource_scope,
            idempotency_key=idempotency_key,
        )

        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            sequence = self._reserve_sequence()
            envelope = {
                "id": event_id,
                "sequence": sequence,
                "timestamp": normalized_timestamp,
                "actor": actor,
                "source": source,
                "capture_method": capture_method,
                "event_type": event_type,
                "epistemic_status": epistemic_status,
                "payload": copy.deepcopy(payload),
                "context": copy.deepcopy(context),
                "residue": copy.deepcopy(residue),
                "links": copy.deepcopy(links),
                "idempotency_key": idempotency_key,
                "privacy_scope": privacy_scope,
                "resource_scope": resource_scope,
                "schema_version": SCHEMA_VERSION,
                "content_hash": None,
            }
            envelope["content_hash"] = content_hash(envelope)
            try:
                self._conn.execute(
                    """
                    INSERT INTO journal_events (
                        sequence, id, timestamp, actor, source, capture_method,
                        event_type, epistemic_status, payload_json, context_json,
                        residue_json, links_json, idempotency_key, privacy_scope_json,
                        resource_scope_json, schema_version, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sequence,
                        event_id,
                        normalized_timestamp,
                        actor,
                        source,
                        capture_method,
                        event_type,
                        epistemic_status,
                        canonical_json(payload),
                        canonical_json(context),
                        canonical_json(residue),
                        canonical_json(links),
                        idempotency_key,
                        canonical_json(privacy_scope),
                        canonical_json(resource_scope),
                        SCHEMA_VERSION,
                        envelope["content_hash"],
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise JournalValidationError(f"journal insert failed: {exc}") from exc
        return envelope

    def append_correction(
        self,
        *,
        target_event_id: str,
        corrected_claim: str,
        reason: str,
        actor: str,
        source: str,
        residue: dict[str, Any],
        target_field: str | None = None,
    ) -> dict[str, Any]:
        return self.append_event(
            event_type="correction",
            epistemic_status="correction",
            actor=actor,
            source=source,
            capture_method="journal_api",
            payload={
                "target": target_event_id,
                "corrected_claim": corrected_claim,
                "reason": reason,
            },
            context={"active_task": "correction", "source_channel": "journal_api"},
            residue=residue,
            links=[
                {
                    "type": "corrects",
                    "target_event_id": target_event_id,
                    "rationale": reason,
                    "target_field": target_field,
                }
            ],
        )

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM journal_events WHERE id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_event(row)

    def iter_events(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM journal_events ORDER BY sequence"
        ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def replay_context(
        self,
        *,
        limit: int = 50,
        requested_scope: dict[str, Any] | None = None,
    ) -> JournalReplayContext:
        events = self.iter_events()[-limit:]
        warnings = self._integrity_warnings(events)
        usable_events: list[dict[str, Any]] = []
        scope_warnings: list[dict[str, Any]] = []
        requested_scope = requested_scope or {}

        for event in events:
            if self._scope_allows(event, requested_scope):
                usable_events.append(event)
            else:
                scope_warnings.append(
                    {
                        "event_id": event["id"],
                        "kind": "scope_excluded",
                        "reason": "privacy/resource scope disallows requested context",
                    }
                )

        salient_residues = []
        attention_targets = []
        uncertainty_markers = []
        open_tensions = []
        drive_refs = []
        importance_reasons = []
        affect_valence = []
        expected_outcomes = []
        rest_markers = []
        unresolved_decisions = []
        provisional_candidates = []
        constraints = []
        anchors = []
        traces = []

        for event in usable_events:
            residue = event["residue"]
            salience = residue.get("salience", {})
            if self._known_value(salience):
                salient_residues.append(
                    {"event_id": event["id"], "field": "salience", "residue": salience}
                )
                traces.append(
                    {
                        "event_id": event["id"],
                        "event_type": event["event_type"],
                        "item": "salient_residues",
                        "residue_epistemic_status": salience.get("epistemic_status"),
                        "because": "known salience residue",
                    }
                )
            for field, bucket in (
                ("attention_target", attention_targets),
                ("uncertainty", uncertainty_markers),
                ("open_tensions", open_tensions),
                ("drive_refs", drive_refs),
                ("importance_reason", importance_reasons),
                ("affect_valence", affect_valence),
                ("expected_outcome", expected_outcomes),
            ):
                residue_value = residue.get(field, {})
                if not self._known_value(residue_value):
                    continue
                bucket.append(
                    {"event_id": event["id"], "field": field, "residue": residue_value}
                )
                traces.append(
                    {
                        "event_id": event["id"],
                        "event_type": event["event_type"],
                        "item": field,
                        "residue_epistemic_status": residue_value.get("epistemic_status"),
                        "because": f"known {field} residue",
                    }
                )
            if event["event_type"] == "decision" and not event["payload"].get("resolved", False):
                unresolved_decisions.append(
                    {"event_id": event["id"], "payload": event["payload"]}
                )
                traces.append(
                    {
                        "event_id": event["id"],
                        "event_type": event["event_type"],
                        "item": "unresolved_decisions",
                        "because": "decision has no resolved marker",
                    }
                )
            if event["event_type"] == "rest":
                rest_markers.append(
                    {
                        "event_id": event["id"],
                        "payload": event["payload"],
                        "epistemic_status": event["epistemic_status"],
                    }
                )
                traces.append(
                    {
                        "event_id": event["id"],
                        "event_type": event["event_type"],
                        "item": "rest_markers",
                        "because": "rest records deliberate non-action",
                    }
                )
            if event["event_type"] in {"dream", "rehearsal"}:
                provisional_candidates.append(
                    {
                        "event_id": event["id"],
                        "event_type": event["event_type"],
                        "epistemic_status": event["epistemic_status"],
                        "payload": event["payload"],
                    }
                )
                traces.append(
                    {
                        "event_id": event["id"],
                        "event_type": event["event_type"],
                        "item": "provisional_candidates",
                        "because": "dream/rehearsal remains provisional",
                    }
                )

            constraints.append(
                {
                    "event_id": event["id"],
                    "privacy_scope": event["privacy_scope"],
                    "resource_scope": event["resource_scope"],
                }
            )
            anchors.append(
                {
                    "event_id": event["id"],
                    "residue": event["residue"],
                    "epistemic_status": event["epistemic_status"],
                    "event_type": event["event_type"],
                }
            )

        return JournalReplayContext(
            ordered_recent_event_ids=[event["id"] for event in usable_events],
            salient_residues=salient_residues,
            attention_targets=attention_targets,
            uncertainty_markers=uncertainty_markers,
            open_tensions=open_tensions,
            drive_refs=drive_refs,
            importance_reasons=importance_reasons,
            affect_valence=affect_valence,
            expected_outcomes=expected_outcomes,
            rest_markers=rest_markers,
            unresolved_decisions=unresolved_decisions,
            provisional_candidates=provisional_candidates,
            privacy_resource_constraints=constraints,
            evidence_anchors=anchors,
            traces=traces,
            integrity_warnings=warnings + scope_warnings,
        )

    def verify_integrity(self) -> list[dict[str, Any]]:
        return self._integrity_warnings(self.iter_events(), full_journal=True)

    def validate_graph_proposal(self, proposal: GraphProposal) -> None:
        if not proposal.source_event_ids:
            raise JournalValidationError("graph proposal requires source event ids")
        if proposal.intended_status not in {"factual", "provisional"}:
            raise JournalValidationError("graph proposal status must be factual or provisional")
        if not proposal.proposed_operation or not proposal.proposed_target_kind:
            raise JournalValidationError("graph proposal operation and target kind are required")

        seen: set[str] = set()
        valid_sources = 0
        for event_id in proposal.source_event_ids:
            if event_id in seen:
                raise JournalValidationError("circular or duplicate provenance")
            seen.add(event_id)
            event = self.get_event(event_id)
            if event is None:
                raise JournalValidationError(f"unknown source event: {event_id}")
            if content_hash(event) != event["content_hash"]:
                raise JournalValidationError(f"source event hash mismatch: {event_id}")
            if not self._scope_allows(event, proposal.requested_scope or {}):
                raise JournalValidationError("privacy/resource scope disallows proposal")
            if event["event_type"] == "graph_update_proposal":
                raise JournalValidationError("proposal-only provenance is not valid evidence")
            if event["event_type"] == "administrative_repair":
                raise JournalValidationError("administrative repair cannot support semantic proposals")
            if proposal.intended_status == "factual":
                if event["event_type"] in FACTUAL_EVENT_TYPES and event["epistemic_status"] == "observed":
                    valid_sources += 1
                    continue
                raise JournalValidationError(
                    "factual proposal requires observed non-provisional evidence"
                )
            if event["event_type"] in FACTUAL_EVENT_TYPES | PROVISIONAL_EVENT_TYPES:
                valid_sources += 1
        if valid_sources == 0:
            raise JournalValidationError("graph proposal has no valid source evidence")

    def _reserve_sequence(self) -> int:
        row = self._conn.execute(
            "SELECT value FROM journal_meta WHERE key = 'next_sequence'"
        ).fetchone()
        sequence = int(row["value"])
        self._conn.execute(
            "UPDATE journal_meta SET value = ? WHERE key = 'next_sequence'",
            (sequence + 1,),
        )
        return sequence

    def _validate_event_input(
        self,
        *,
        event_type: str,
        epistemic_status: str,
        actor: str,
        source: str,
        capture_method: str,
        payload: dict[str, Any],
        context: dict[str, Any],
        residue: dict[str, Any],
        links: list[dict[str, Any]],
        privacy_scope: dict[str, Any],
        resource_scope: dict[str, Any],
        idempotency_key: str | None,
    ) -> None:
        if event_type not in ALLOWED_EVENT_TYPES:
            raise JournalValidationError(f"invalid event type: {event_type}")
        if epistemic_status not in EVENT_STATUS_MATRIX[event_type]:
            raise JournalValidationError(
                f"invalid epistemic status {epistemic_status} for {event_type}"
            )
        for label, value in {
            "actor": actor,
            "source": source,
            "capture_method": capture_method,
        }.items():
            if not isinstance(value, str) or not value:
                raise JournalValidationError(f"{label} is required")
        self._validate_payload(event_type, payload, links, capture_method)
        self._validate_context(context)
        self._validate_residue(residue)
        self._validate_scopes(privacy_scope, resource_scope)
        self._validate_idempotency(event_type, capture_method, idempotency_key)
        self._validate_links(links)
        self._validate_link_compatibility(event_type, epistemic_status, payload, links)

    def _validate_payload(
        self,
        event_type: str,
        payload: dict[str, Any],
        links: list[dict[str, Any]],
        capture_method: str,
    ) -> None:
        if not isinstance(payload, dict):
            raise JournalValidationError("payload must be an object")
        if event_type == "rehearsal" and capture_method != "rehearsal_workflow":
            raise JournalValidationError("rehearsal events must use rehearsal workflow")
        required = PAYLOAD_REQUIRED_KEYS[event_type]
        missing = sorted(required - payload.keys())
        if missing:
            raise JournalValidationError(f"payload missing required keys: {missing}")
        if event_type == "reflection" and not payload.get("cited_source_event_ids"):
            raise JournalValidationError("reflection requires cited source events")
        if event_type == "reflection" and not payload.get("cited_retrieval_paths"):
            raise JournalValidationError("reflection requires cited retrieval paths")
        if event_type == "reflection":
            if capture_method != "reflection_workflow":
                raise JournalValidationError("reflection events must use reflection workflow")
            self._validate_reflection_payload(payload)
            if payload.get("proposed_graph_updates"):
                raise JournalValidationError("reflection cannot embed graph update proposals")
            for claim in payload.get("interpretive_claims", []):
                if claim.get("epistemic_status") in {"observed", "accepted"}:
                    raise JournalValidationError("reflection claims cannot be observed or accepted")
        if event_type == "dream":
            if capture_method != "dream_workflow":
                raise JournalValidationError("dream events must use dream workflow")
            self._validate_dream_payload(payload)
        if event_type == "dream_review":
            self._validate_dream_review_payload(payload)
        if event_type == "rehearsal":
            self._validate_rehearsal_payload(payload)
        if event_type == "outcome":
            self._validate_outcome_payload(payload, links)
        if event_type == "graph_update_proposal" and not payload.get("source_event_ids"):
            raise JournalValidationError("graph update proposal requires source events")
        for source_event_id in payload.get("cited_source_event_ids", []):
            if self.get_event(source_event_id) is None:
                raise JournalValidationError(f"unknown cited source event: {source_event_id}")
        for source_event_id in payload.get("source_event_ids", []):
            if self.get_event(source_event_id) is None:
                raise JournalValidationError(f"unknown source event: {source_event_id}")
        for event_id_field in (
            "consolidation_event_id",
            "new_evidence_event_id",
            "proposal_event_id",
            "reflection_event_id",
        ):
            if payload.get(event_id_field) and self.get_event(payload[event_id_field]) is None:
                raise JournalValidationError(f"unknown {event_id_field}: {payload[event_id_field]}")
        if event_type == "graph_update_proposal":
            source_ids = set(payload["source_event_ids"])
            propose_link_targets = {
                link["target_event_id"] for link in links if link["type"] == "proposes_from"
            }
            if source_ids != propose_link_targets:
                raise JournalValidationError(
                    "graph update proposal requires proposes_from links for all source events"
                )
            self.validate_graph_proposal(
                GraphProposal(
                    proposed_operation=payload["proposed_operation"],
                    proposed_target_kind=payload["proposed_target_kind"],
                    source_event_ids=list(payload["source_event_ids"]),
                    intended_status=payload["intended_status"],
                    rationale=payload["rationale"],
                )
            )

    def _validate_dream_payload(self, payload: dict[str, Any]) -> None:
        residues = payload.get("residues_used")
        fragments = payload.get("generated_candidates")
        if not isinstance(residues, list) or not residues:
            raise JournalValidationError("dream requires structured residues_used")
        if not isinstance(fragments, list) or not fragments:
            raise JournalValidationError("dream requires structured generated_candidates")
        residue_ids: set[str] = set()
        for residue in residues:
            if not isinstance(residue, dict):
                raise JournalValidationError("dream residue refs must be objects")
            required = {
                "residue_ref_id",
                "source_event_id",
                "source_event_hash",
                "source_event_type",
                "source_epistemic_status",
                "scope_decision",
                "selection_reason",
                "selection_weight",
                "material_category",
            }
            missing = sorted(required - residue.keys())
            if missing:
                raise JournalValidationError(f"dream residue missing keys: {missing}")
            if residue["material_category"] not in DREAM_RESIDUE_CATEGORIES:
                raise JournalValidationError("dream residue has invalid material category")
            if residue.get("scope_decision", {}).get("decision") != "included":
                raise JournalValidationError("dream residue must record included scope decision")
            source = self.get_event(str(residue["source_event_id"]))
            if source is None:
                raise JournalValidationError("dream residue cites unknown source event")
            if source["content_hash"] != residue["source_event_hash"]:
                raise JournalValidationError("dream residue source hash mismatch")
            if source["event_type"] != residue["source_event_type"]:
                raise JournalValidationError("dream residue source type mismatch")
            if source["epistemic_status"] != residue["source_epistemic_status"]:
                raise JournalValidationError("dream residue source status mismatch")
            residue_ids.add(str(residue["residue_ref_id"]))
        for fragment in fragments:
            if not isinstance(fragment, dict):
                raise JournalValidationError("dream fragments must be objects")
            required = {
                "fragment_id",
                "label",
                "fragment_kind",
                "source_residue_refs",
                "association_rationale",
                "uncertainty_note",
                "useful_if",
                "review_status",
                "not_factual",
            }
            missing = sorted(required - fragment.keys())
            if missing:
                raise JournalValidationError(f"dream fragment missing keys: {missing}")
            if fragment["fragment_kind"] not in DREAM_FRAGMENT_KINDS:
                raise JournalValidationError("dream fragment has invalid kind")
            if fragment["review_status"] not in DREAM_REVIEW_STATUSES:
                raise JournalValidationError("dream fragment has invalid review status")
            if fragment["not_factual"] is not True:
                raise JournalValidationError("dream fragments must be explicitly not_factual")
            refs = fragment.get("source_residue_refs")
            if not isinstance(refs, list) or not refs:
                raise JournalValidationError("dream fragment requires source residue refs")
            if not set(str(ref) for ref in refs).issubset(residue_ids):
                raise JournalValidationError("dream fragment cites unknown residue ref")

    def _validate_dream_review_payload(self, payload: dict[str, Any]) -> None:
        if payload.get("review_decision") not in DREAM_REVIEW_DECISIONS:
            raise JournalValidationError("dream review has invalid decision")
        if payload.get("not_factual") is not True:
            raise JournalValidationError("dream review must remain not_factual")
        dream = self.get_event(str(payload.get("dream_event_id")))
        if dream is None or dream["event_type"] != "dream":
            raise JournalValidationError("dream review requires a dream event")
        fragment_ids = {
            fragment.get("fragment_id")
            for fragment in dream["payload"].get("generated_candidates", [])
            if isinstance(fragment, dict)
        }
        if payload.get("fragment_id") not in fragment_ids:
            raise JournalValidationError("dream review fragment is not in dream event")
        observed_ids = payload.get("observed_evidence_event_ids", [])
        if not isinstance(observed_ids, list):
            raise JournalValidationError("observed dream review evidence must be a list")
        if payload["review_decision"] == "corroborate_observation" and not observed_ids:
            raise JournalValidationError("dream corroboration requires later observed evidence")
        for event_id in observed_ids:
            event = self.get_event(str(event_id))
            if event is None:
                raise JournalValidationError("dream review cites unknown observed evidence")
            if event["event_type"] not in FACTUAL_EVENT_TYPES or event["epistemic_status"] != "observed":
                raise JournalValidationError("dream review observed evidence must be observed factual evidence")

    def _validate_rehearsal_payload(self, payload: dict[str, Any]) -> None:
        required = {
            "policy_version",
            "target_refs",
            "problem_context",
            "current_or_failed_approach",
            "strategy_variants",
            "selected_variant_id",
            "improvement_hypothesis",
            "assumptions",
            "simulated_trace",
            "predicted_observations",
            "predicted_failure_modes",
            "validation_criteria",
            "falsification_criteria",
            "candidate_procedure_updates",
            "resource_scope_decision",
            "privacy_scope_decision",
            "review_status",
            "not_executed",
        }
        missing = sorted(required - payload.keys())
        if missing:
            raise JournalValidationError(f"rehearsal payload missing keys: {missing}")
        if payload["not_executed"] is not True:
            raise JournalValidationError("rehearsal must be explicitly not_executed")
        if payload["review_status"] not in REHEARSAL_REVIEW_STATUSES:
            raise JournalValidationError("rehearsal has invalid review status")
        target_refs = payload.get("target_refs")
        if not isinstance(target_refs, list) or not target_refs:
            raise JournalValidationError("rehearsal requires structured target refs")
        target_ids: set[str] = set()
        for ref in target_refs:
            if not isinstance(ref, dict):
                raise JournalValidationError("rehearsal target refs must be objects")
            ref_required = {
                "target_ref_id",
                "source_event_id",
                "source_event_hash",
                "source_event_type",
                "source_epistemic_status",
                "target_field",
                "scope_decision",
                "target_category",
                "selection_reason",
                "selection_weight",
            }
            missing = sorted(ref_required - ref.keys())
            if missing:
                raise JournalValidationError(f"rehearsal target ref missing keys: {missing}")
            if ref["target_category"] not in REHEARSAL_TARGET_CATEGORIES:
                raise JournalValidationError("rehearsal target ref has invalid category")
            if ref.get("scope_decision", {}).get("decision") != "included":
                raise JournalValidationError("rehearsal target must record included scope decision")
            source = self.get_event(str(ref["source_event_id"]))
            if source is None:
                raise JournalValidationError("rehearsal target cites unknown source event")
            if source["content_hash"] != ref["source_event_hash"]:
                raise JournalValidationError("rehearsal target source hash mismatch")
            if source["event_type"] != ref["source_event_type"]:
                raise JournalValidationError("rehearsal target source type mismatch")
            if source["epistemic_status"] != ref["source_epistemic_status"]:
                raise JournalValidationError("rehearsal target source status mismatch")
            target_ids.add(str(ref["target_ref_id"]))
        variants = payload.get("strategy_variants")
        if not isinstance(variants, list) or not variants:
            raise JournalValidationError("rehearsal requires strategy variants")
        variant_ids = {variant.get("variant_id") for variant in variants if isinstance(variant, dict)}
        if payload["selected_variant_id"] not in variant_ids:
            raise JournalValidationError("selected rehearsal variant is unknown")
        step_ids: set[str] = set()
        for step in payload.get("simulated_trace", []):
            if not isinstance(step, dict):
                raise JournalValidationError("rehearsal simulated trace steps must be objects")
            if step.get("simulated") is not True:
                raise JournalValidationError("rehearsal trace steps must be simulated")
            if step.get("variant_id") not in variant_ids:
                raise JournalValidationError("rehearsal trace step cites unknown variant")
            if not step.get("step_id"):
                raise JournalValidationError("rehearsal trace step requires step id")
            step_ids.add(str(step["step_id"]))
        if not step_ids:
            raise JournalValidationError("rehearsal requires simulated trace steps")
        prediction_ids = self._rehearsal_prediction_ids(payload)
        if not prediction_ids:
            raise JournalValidationError("rehearsal requires predictions")
        for update in payload.get("candidate_procedure_updates", []):
            if not isinstance(update, dict):
                raise JournalValidationError("procedure updates must be objects")
            if update.get("source_variant_id") not in variant_ids:
                raise JournalValidationError("procedure update cites unknown variant")
            if update.get("review_status") not in {"provisional", "review_pending"}:
                raise JournalValidationError("procedure updates must remain provisional")
            if update.get("not_accepted") is not True:
                raise JournalValidationError("procedure updates must be explicitly not accepted")
        for criterion_key in ("validation_criteria", "falsification_criteria"):
            for criterion in payload.get(criterion_key, []):
                ids = criterion.get("prediction_ids", [])
                if not set(ids).issubset(prediction_ids):
                    raise JournalValidationError("rehearsal criterion cites unknown prediction")

    def _validate_outcome_payload(self, payload: dict[str, Any], links: list[dict[str, Any]]) -> None:
        target_id = payload.get("expected_outcome_link")
        if not target_id:
            raise JournalValidationError("outcome requires expected_outcome_link")
        target = self.get_event(str(target_id))
        if target is None:
            raise JournalValidationError("outcome target is unknown")
        derived_targets = {
            link.get("target_event_id")
            for link in links
            if link.get("type") == "derived_from"
        }
        if target_id not in derived_targets:
            raise JournalValidationError("outcome requires derived_from link to expected outcome")
        if target["event_type"] != "rehearsal":
            return
        prediction_results = payload.get("prediction_results")
        if not isinstance(prediction_results, list) or not prediction_results:
            raise JournalValidationError("rehearsal outcome requires prediction_results")
        prediction_ids = self._rehearsal_prediction_ids(target["payload"])
        for result in prediction_results:
            if not isinstance(result, dict):
                raise JournalValidationError("prediction result must be an object")
            if result.get("prediction_id") not in prediction_ids:
                raise JournalValidationError("outcome cites unknown rehearsal prediction")
            if result.get("result") not in REHEARSAL_PREDICTION_RESULTS:
                raise JournalValidationError("outcome has invalid prediction result")
            if not result.get("rationale"):
                raise JournalValidationError("prediction result requires rationale")

    def _rehearsal_prediction_ids(self, payload: dict[str, Any]) -> set[str]:
        prediction_ids: set[str] = set()
        for key in ("predicted_observations", "predicted_failure_modes"):
            for prediction in payload.get(key, []):
                if not isinstance(prediction, dict):
                    raise JournalValidationError("rehearsal predictions must be objects")
                if not prediction.get("prediction_id"):
                    raise JournalValidationError("rehearsal prediction requires id")
                if prediction.get("variant_id") != payload.get("selected_variant_id"):
                    raise JournalValidationError("rehearsal prediction must cite selected variant")
                prediction_ids.add(str(prediction["prediction_id"]))
        return prediction_ids

    def _validate_reflection_payload(self, payload: dict[str, Any]) -> None:
        snapshot = payload.get("retrieval_result_snapshot")
        if not isinstance(snapshot, dict):
            raise JournalValidationError("reflection requires retrieval result snapshot")
        stable = {
            key: value
            for key, value in snapshot.items()
            if key not in {"query_id", "timestamp"}
        }
        if payload.get("retrieval_result_hash") != hashlib.sha256(
            canonical_json(stable).encode("utf-8")
        ).hexdigest():
            raise JournalValidationError("reflection retrieval result hash mismatch")
        path_ids = {path.get("path_id") for path in payload.get("cited_retrieval_paths", [])}
        if not path_ids or None in path_ids:
            raise JournalValidationError("reflection cited paths require path ids")
        snapshot_path_ids = self._reflection_snapshot_path_ids(snapshot)
        if not path_ids.issubset(snapshot_path_ids):
            raise JournalValidationError("reflection cited path is not in retrieval snapshot")
        for claim in payload.get("interpretive_claims", []):
            for cite in claim.get("cites", []):
                if cite not in path_ids:
                    raise JournalValidationError("reflection claim cites unknown retrieval path")
        for path in payload.get("cited_retrieval_paths", []):
            if not path.get("source_refs"):
                raise JournalValidationError("reflection cited path requires source refs")
            if not path.get("scope_decision"):
                raise JournalValidationError("reflection cited path requires scope decision")
            if not path.get("activation_paths") and not path.get("steps"):
                raise JournalValidationError("reflection cited path requires path steps")
            if path.get("redacted") and path.get("label"):
                raise JournalValidationError("redacted reflection path leaks label")

    def _reflection_snapshot_path_ids(self, snapshot: dict[str, Any]) -> set[str]:
        path_ids: set[str] = set()
        for candidate in snapshot.get("activated_candidates", []):
            candidate_id = candidate.get("candidate_id")
            for path in candidate.get("activation_paths", []):
                path_ids.add(
                    "path_"
                    + hashlib.sha256(
                        canonical_json(
                            {
                                "candidate_id": candidate_id,
                                "entry_candidate_id": path.get("entry_candidate_id"),
                                "target_candidate_id": path.get("target_candidate_id"),
                                "steps": [
                                    {
                                        "record_type": step.get("record_type"),
                                        "record_id": step.get("record_id"),
                                        "hop_index": step.get("hop_index"),
                                    }
                                    for step in path.get("steps", [])
                                ],
                            }
                        ).encode("utf-8")
                    ).hexdigest()[:24]
                )
        for ghost in snapshot.get("ghost_signals", []):
            if ghost.get("ghost_id"):
                path_ids.add(ghost["ghost_id"])
        for omitted in snapshot.get("omitted_candidates", []):
            if omitted.get("candidate_id"):
                path_ids.add("omitted_" + str(omitted["candidate_id"]))
        return path_ids

    def _validate_context(self, context: dict[str, Any]) -> None:
        if not isinstance(context, dict):
            raise JournalValidationError("context must be an object")
        for key in ("active_task", "source_channel"):
            if not context.get(key):
                raise JournalValidationError(f"context missing {key}")

    def _validate_residue(self, residue: dict[str, Any]) -> None:
        if not isinstance(residue, dict):
            raise JournalValidationError("residue must be an object")
        missing = sorted(RESIDUE_FIELDS - residue.keys())
        if missing:
            raise JournalValidationError(f"residue missing required fields: {missing}")
        for field in RESIDUE_FIELDS:
            entry = residue[field]
            if not isinstance(entry, dict):
                raise JournalValidationError(f"residue {field} must be an object")
            for key in ("value", "source", "epistemic_status"):
                if key not in entry:
                    raise JournalValidationError(f"residue {field} missing {key}")
            if entry["value"] not in ("unknown", "not_applicable") and entry["source"] == "unknown":
                raise JournalValidationError(f"residue {field} needs a source")
            if entry["epistemic_status"] not in ALLOWED_EPISTEMIC_STATUSES | {"unknown"}:
                raise JournalValidationError(f"residue {field} has invalid epistemic status")

    def _validate_scopes(
        self, privacy_scope: dict[str, Any], resource_scope: dict[str, Any]
    ) -> None:
        for key in ("retention", "exposure", "export_allowed"):
            if key not in privacy_scope:
                raise JournalValidationError(f"privacy_scope missing {key}")
        for key in ("external_contact", "network_access", "autonomous_spend", "compute_escalation"):
            if key not in resource_scope:
                raise JournalValidationError(f"resource_scope missing {key}")

    def _validate_idempotency(
        self, event_type: str, capture_method: str, idempotency_key: str | None
    ) -> None:
        if event_type == "tool_call" or capture_method in {"tool", "import"}:
            if not idempotency_key:
                raise JournalValidationError(
                    "idempotency_key is required for tool/import captures"
                )

    def _validate_links(self, links: list[dict[str, Any]]) -> None:
        if not isinstance(links, list):
            raise JournalValidationError("links must be a list")
        for link in links:
            if not isinstance(link, dict):
                raise JournalValidationError("link must be an object")
            if link.get("type") not in ALLOWED_LINK_TYPES:
                raise JournalValidationError(f"invalid link type: {link.get('type')}")
            if not link.get("target_event_id"):
                raise JournalValidationError("link target_event_id is required")
            if not link.get("rationale"):
                raise JournalValidationError("link rationale is required")
            if self.get_event(link["target_event_id"]) is None:
                raise JournalValidationError(f"missing linked event: {link['target_event_id']}")
            if link["type"] == "corrects" and link.get("target_field") is None:
                raise JournalValidationError("corrects link requires target_field")

    def _validate_link_compatibility(
        self,
        event_type: str,
        epistemic_status: str,
        payload: dict[str, Any],
        links: list[dict[str, Any]],
    ) -> None:
        link_types = {link["type"] for link in links}
        if epistemic_status == "correction" and "corrects" not in link_types:
            raise JournalValidationError("correction event requires a corrects link")
        if epistemic_status == "retraction" and "invalidates" not in link_types:
            raise JournalValidationError("retraction event requires an invalidates link")
        if epistemic_status == "contradiction" and "contradicts" not in link_types:
            raise JournalValidationError("contradiction event requires a contradicts link")
        if event_type == "graph_update_proposal" and "proposes_from" not in link_types:
            raise JournalValidationError("graph update proposal requires proposes_from links")
        if event_type != "graph_update_proposal" and "proposes_from" in link_types:
            raise JournalValidationError("proposes_from links are only for graph proposals")

    def _row_to_event(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "sequence": row["sequence"],
            "timestamp": row["timestamp"],
            "actor": row["actor"],
            "source": row["source"],
            "capture_method": row["capture_method"],
            "event_type": row["event_type"],
            "epistemic_status": row["epistemic_status"],
            "payload": json.loads(row["payload_json"]),
            "context": json.loads(row["context_json"]),
            "residue": json.loads(row["residue_json"]),
            "links": json.loads(row["links_json"]),
            "idempotency_key": row["idempotency_key"],
            "privacy_scope": json.loads(row["privacy_scope_json"]),
            "resource_scope": json.loads(row["resource_scope_json"]),
            "schema_version": row["schema_version"],
            "content_hash": row["content_hash"],
        }

    def _integrity_warnings(
        self, events: list[dict[str, Any]], *, full_journal: bool = False
    ) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        all_event_ids = {event["id"] for event in self.iter_events()}
        event_ids = all_event_ids if full_journal else all_event_ids
        seen_idempotency: dict[str, str] = {}
        for event in events:
            if content_hash(event) != event["content_hash"]:
                warnings.append({"event_id": event["id"], "kind": "hash_mismatch"})
            idempotency_key = event.get("idempotency_key")
            if idempotency_key:
                if idempotency_key in seen_idempotency:
                    warnings.append(
                        {
                            "event_id": event["id"],
                            "kind": "duplicate_idempotency_key",
                            "other_event_id": seen_idempotency[idempotency_key],
                        }
                    )
                seen_idempotency[idempotency_key] = event["id"]
            if event["epistemic_status"] not in EVENT_STATUS_MATRIX.get(event["event_type"], set()):
                warnings.append({"event_id": event["id"], "kind": "invalid_event_status"})
            for link in event["links"]:
                if link.get("type") not in ALLOWED_LINK_TYPES:
                    warnings.append({"event_id": event["id"], "kind": "invalid_link_type"})
                if link.get("target_event_id") not in event_ids:
                    warnings.append(
                        {
                            "event_id": event["id"],
                            "kind": "missing_linked_event",
                            "target_event_id": link.get("target_event_id"),
                        }
                    )
        return warnings

    def _known_value(self, residue_entry: dict[str, Any]) -> bool:
        value = residue_entry.get("value")
        return value is not None and value not in ("unknown", "not_applicable", "") and value != []

    def _scope_allows(self, event: dict[str, Any], requested_scope: dict[str, Any]) -> bool:
        privacy = event["privacy_scope"]
        resource = event["resource_scope"]
        if requested_scope.get("export") and not privacy.get("export_allowed", False):
            return False
        if requested_scope.get("network") and not resource.get("network_access", False):
            return False
        if requested_scope.get("external_contact") and not resource.get("external_contact", False):
            return False
        if requested_scope.get("autonomous_spend") and not resource.get("autonomous_spend", False):
            return False
        if requested_scope.get("compute_escalation") and not resource.get("compute_escalation", False):
            return False
        return True
