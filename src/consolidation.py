"""Phase 5 consolidation and forgetting workflow.

Consolidation is journal-first maintenance over projected memory. It weakens
access paths, marks dormancy, and records rediscovery without deleting evidence
or editing confidence records.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from journal import JournalStore, canonical_json, unknown_residue
from memory_projection import ProjectionStore, normalize_label, stable_hash
from reflection import append_reflection_event, cite_retrieval_path
from typed_retrieval import RetrievalQuery, retrieve


POLICY_VERSION = 1
RECENT_USE_SEQUENCE_WINDOW = 25

PROVISIONAL_EDGE_TYPES = {"dream_association", "rehearsal_candidate"}
CONFLICT_EDGE_TYPES = {"contradiction"}
IDENTITY_BEARING_KINDS = {"preference", "reflection"}


class ConsolidationError(Exception):
    """Base consolidation exception."""


class ConsolidationValidationError(ConsolidationError):
    """Raised when consolidation would violate Phase 5 invariants."""


@dataclass(frozen=True)
class ConsolidationResult:
    run_event_id: str
    action_event_ids: list[str] = field(default_factory=list)
    edge_actions: list[dict[str, Any]] = field(default_factory=list)
    candidate_actions: list[dict[str, Any]] = field(default_factory=list)
    rediscoveries: list[dict[str, Any]] = field(default_factory=list)
    no_action_reason: str | None = None


def retrieval_result_hash(retrieval_result: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in retrieval_result.items()
        if key not in {"query_id", "timestamp"}
    }
    return hashlib.sha256(canonical_json(stable).encode("utf-8")).hexdigest()


def append_retrieval_use_trace(
    journal: JournalStore,
    *,
    retrieval_result: dict[str, Any],
    used_candidate_ids: list[str] | None = None,
    used_record_ids: list[str] | None = None,
    actor: str = "codex",
    source: str = "consolidation",
) -> dict[str, Any]:
    snapshot_candidate_ids = set(_activated_candidate_ids(retrieval_result))
    snapshot_record_ids = set(_activated_record_ids(retrieval_result))
    used_candidate_ids = sorted(set(used_candidate_ids or snapshot_candidate_ids))
    used_record_ids = sorted(set(used_record_ids or snapshot_record_ids))
    if not set(used_candidate_ids).issubset(snapshot_candidate_ids):
        raise ConsolidationValidationError("retrieval use candidates must come from retrieval snapshot")
    if not set(used_record_ids).issubset(snapshot_record_ids):
        raise ConsolidationValidationError("retrieval use records must come from retrieval snapshot")
    activated_path_ids = sorted(set(_activated_path_ids(retrieval_result)))
    return journal.append_event(
        event_type="retrieval_use_trace",
        epistemic_status="observed",
        actor=actor,
        source=source,
        capture_method="retrieval_use_trace",
        payload={
            "retrieval_result_hash": retrieval_result_hash(retrieval_result),
            "used_candidate_ids": used_candidate_ids,
            "used_record_ids": used_record_ids,
            "activated_path_ids": activated_path_ids,
            "retrieval_result_snapshot": retrieval_result,
        },
        context={"active_task": "phase-5-consolidation", "source_channel": source},
        residue=unknown_residue("consolidation"),
    )


def consolidate(
    journal: JournalStore,
    projection: ProjectionStore,
    *,
    actor: str = "codex",
    source: str = "consolidation",
) -> ConsolidationResult:
    retrieval_use_events = [
        event for event in journal.iter_events() if event["event_type"] == "retrieval_use_trace"
    ]
    used_records = _recent_use_index(retrieval_use_events, "used_record_ids")
    used_candidates = _recent_use_index(retrieval_use_events, "used_candidate_ids")
    candidates = {candidate["candidate_id"]: candidate for candidate in projection.candidates()}
    edges = projection.edges()
    degree = _degree(edges)
    source_event_ids = [event["id"] for event in retrieval_use_events]
    run_event = journal.append_event(
        event_type="consolidation_run",
        epistemic_status="authored",
        actor=actor,
        source=source,
        capture_method="consolidation_workflow",
        payload={
            "policy_version": POLICY_VERSION,
            "source_event_ids": source_event_ids,
            "target_summary": {
                "candidate_count": len(candidates),
                "edge_count": len(edges),
                "retrieval_use_trace_count": len(retrieval_use_events),
            },
            "actions_taken": ["assess_edges", "mark_dormancy", "check_rediscovery"],
            "no_action_reason": "record quiet run if no edge, dormancy, or rediscovery action is justified",
        },
        context={"active_task": "phase-5-consolidation", "source_channel": source},
        residue=unknown_residue("consolidation"),
    )

    result = ConsolidationResult(run_event_id=run_event["id"])
    for edge in edges:
        action = _edge_action(edge, candidates, degree, used_records)
        if action["new_lifecycle_state"] == edge["lifecycle"]["lifecycle_state"] and (
            action["new_accessibility"] == edge["lifecycle"]["accessibility"]
        ):
            continue
        event_type = "edge_archival" if action["new_lifecycle_state"] == "archived" else "edge_decay_assessment"
        event = _append_edge_action_event(
            journal,
            event_type=event_type,
            run_event_id=run_event["id"],
            edge=edge,
            action=action,
            actor=actor,
            source=source,
        )
        projection.record_edge_lifecycle(
            journal=journal,
            edge_id=edge["id"],
            lifecycle_state=action["new_lifecycle_state"],
            accessibility=action["new_accessibility"],
            traversal_factor=action["new_traversal_factor"],
            maintenance_event=event,
            decay_basis=action["decay_basis"],
            last_reinforced_event_id=action.get("last_reinforced_event_id"),
        )
        result.action_event_ids.append(event["id"])
        result.edge_actions.append({"edge_id": edge["id"], **action})

    for candidate in candidates.values():
        action = _candidate_action(candidate, edges, used_candidates)
        if action is None:
            continue
        event = journal.append_event(
            event_type="candidate_dormancy_mark",
            epistemic_status="inferred",
            actor=actor,
            source=source,
            capture_method="consolidation_workflow",
            payload={
                "consolidation_event_id": run_event["id"],
                "candidate_id": candidate["candidate_id"],
                "previous_lifecycle_state": candidate["lifecycle"]["lifecycle_state"],
                "new_lifecycle_state": "dormant",
                "previous_accessibility": candidate["lifecycle"]["accessibility"],
                "new_accessibility": action["accessibility"],
                "dormancy_reason": action["reason"],
                "source_event_ids": action["source_event_ids"],
                "rediscovery_recipe": action["rediscovery_recipe"],
            },
            context={"active_task": "phase-5-consolidation", "source_channel": source},
            residue=unknown_residue("consolidation"),
        )
        projection.record_candidate_lifecycle(
            journal=journal,
            candidate_id=candidate["candidate_id"],
            lifecycle_state="dormant",
            accessibility=action["accessibility"],
            maintenance_event=event,
            decay_basis=action["decay_basis"],
        )
        result.action_event_ids.append(event["id"])
        result.candidate_actions.append({"candidate_id": candidate["candidate_id"], **action})

    for rediscovery in _rediscovery_actions(journal, projection):
        reflection_event = _append_rediscovery_reflection(
            journal,
            projection,
            rediscovery=rediscovery,
            actor=actor,
            source=source,
        )
        event = journal.append_event(
            event_type="rediscovery",
            epistemic_status="inferred",
            actor=actor,
            source=source,
            capture_method="consolidation_workflow",
            payload={
                "consolidation_event_id": run_event["id"],
                "dormant_candidate_id": rediscovery["dormant_candidate_id"],
                "new_evidence_event_id": rediscovery["new_evidence_event_id"],
                "bridge_edge_id": rediscovery["bridge_edge_id"],
                "source_event_ids": rediscovery["source_event_ids"],
                "reflection_event_id": reflection_event["id"],
                "reflection_required": True,
                "rediscovery_reason": rediscovery["reason"],
            },
            context={"active_task": "phase-5-consolidation", "source_channel": source},
            residue=unknown_residue("consolidation"),
        )
        projection.record_candidate_lifecycle(
            journal=journal,
            candidate_id=rediscovery["dormant_candidate_id"],
            lifecycle_state="rediscovered",
            accessibility=0.75,
            maintenance_event=event,
            decay_basis=rediscovery,
            last_reinforced_event_id=rediscovery["new_evidence_event_id"],
        )
        projection.record_edge_lifecycle(
            journal=journal,
            edge_id=rediscovery["bridge_edge_id"],
            lifecycle_state="rediscovered_bridge",
            accessibility=0.80,
            traversal_factor=0.80,
            maintenance_event=event,
            decay_basis=rediscovery,
            last_reinforced_event_id=rediscovery["new_evidence_event_id"],
        )
        result.action_event_ids.append(event["id"])
        result.rediscoveries.append(rediscovery)

    if not result.action_event_ids:
        object.__setattr__(result, "no_action_reason", "no maintenance action justified")
    return result


def propose_pruning(
    journal: JournalStore,
    *,
    target_kind: str,
    target_id: str,
    source_event_ids: list[str],
    affected_path_ids: list[str],
    rejected_alternatives: list[str],
    reversibility_check: str,
    rediscovery_recipe: str,
    release_rationale: str,
    actor: str = "codex",
    source: str = "consolidation",
) -> dict[str, Any]:
    if not source_event_ids:
        raise ConsolidationValidationError("pruning proposal requires source events")
    if not affected_path_ids:
        raise ConsolidationValidationError("pruning proposal requires affected paths")
    if not rejected_alternatives:
        raise ConsolidationValidationError("pruning proposal requires rejected alternatives")
    if not release_rationale or not reversibility_check or not rediscovery_recipe:
        raise ConsolidationValidationError("pruning proposal requires grief, reversibility, and rediscovery rationale")
    return journal.append_event(
        event_type="pruning_proposal",
        epistemic_status="inferred",
        actor=actor,
        source=source,
        capture_method="consolidation_workflow",
        payload={
            "target_kind": target_kind,
            "target_id": target_id,
            "source_event_ids": source_event_ids,
            "affected_path_ids": affected_path_ids,
            "rejected_alternatives": rejected_alternatives,
            "reversibility_check": reversibility_check,
            "rediscovery_recipe": rediscovery_recipe,
            "release_rationale": release_rationale,
        },
        context={"active_task": "phase-5-consolidation", "source_channel": source},
        residue=unknown_residue("consolidation"),
    )


def _append_edge_action_event(
    journal: JournalStore,
    *,
    event_type: str,
    run_event_id: str,
    edge: dict[str, Any],
    action: dict[str, Any],
    actor: str,
    source: str,
) -> dict[str, Any]:
    source_event_ids = action["source_event_ids"]
    payload = {
        "consolidation_event_id": run_event_id,
        "edge_id": edge["id"],
        "previous_lifecycle_state": edge["lifecycle"]["lifecycle_state"],
        "new_lifecycle_state": action["new_lifecycle_state"],
        "previous_accessibility": edge["lifecycle"]["accessibility"],
        "new_accessibility": action["new_accessibility"],
        "decay_basis": action["decay_basis"],
        "source_event_ids": source_event_ids,
    }
    if event_type == "edge_archival":
        payload = {
            "consolidation_event_id": run_event_id,
            "edge_id": edge["id"],
            "previous_lifecycle_state": edge["lifecycle"]["lifecycle_state"],
            "new_lifecycle_state": action["new_lifecycle_state"],
            "previous_accessibility": edge["lifecycle"]["accessibility"],
            "new_accessibility": action["new_accessibility"],
            "archive_reason": action["reason"],
            "source_event_ids": source_event_ids,
            "rediscovery_recipe": action["rediscovery_recipe"],
        }
    return journal.append_event(
        event_type=event_type,
        epistemic_status="inferred",
        actor=actor,
        source=source,
        capture_method="consolidation_workflow",
        payload=payload,
        context={"active_task": "phase-5-consolidation", "source_channel": source},
        residue=unknown_residue("consolidation"),
    )


def _edge_action(
    edge: dict[str, Any],
    candidates: dict[str, dict[str, Any]],
    degree: dict[str, int],
    used_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    used = used_records.get(edge["id"])
    source = candidates.get(edge["source_candidate_id"], {})
    target = candidates.get(edge["target_candidate_id"], {})
    edge_type = edge["edge_type"]
    idiosyncratic = any(
        "idiosyncratic" in str(ref.get("rationale", "")).lower()
        for ref in edge["source_refs"]
    )
    identity_bearing = source.get("kind") in IDENTITY_BEARING_KINDS or target.get("kind") in IDENTITY_BEARING_KINDS
    provisional = edge_type in PROVISIONAL_EDGE_TYPES or edge["epistemic_status"] in {"hypothesis", "simulation"}
    conflict = edge_type in CONFLICT_EDGE_TYPES or target.get("relation_status") == "conflicted"
    source_event_ids = sorted({ref["event_id"] for ref in edge["source_refs"]})

    if used:
        return {
            "new_lifecycle_state": "active",
            "new_accessibility": 1.0,
            "new_traversal_factor": 1.0,
            "last_reinforced_event_id": used["event_id"],
            "source_event_ids": sorted(set(source_event_ids + [used["event_id"]])),
            "reason": "recent retrieval use resists decay",
            "rediscovery_recipe": "reuse the retrieval path that reinforced this edge",
            "decay_basis": {
                "used": True,
                "policy": "recently used paths resist decay",
                "material_type": _material_type(edge),
            },
        }

    if provisional:
        state = "weakened"
        accessibility = 0.35
        reason = "provisional dream/rehearsal material weakens without becoming fact"
    elif conflict:
        state = "weakened"
        accessibility = 0.70
        reason = "conflict material remains accessible as unresolved tension"
    elif idiosyncratic or identity_bearing:
        state = "weakened"
        accessibility = 0.65
        reason = "weak idiosyncratic or identity-bearing path is preserved"
    elif edge["confidence"].get("level") == "weak":
        state = "archived"
        accessibility = 0.0
        reason = "weak unused non-identity edge archived before node dormancy"
    else:
        state = "weakened"
        accessibility = 0.45
        reason = "unused ordinary path weakens before any candidate dormancy"

    return {
        "new_lifecycle_state": state,
        "new_accessibility": accessibility,
        "new_traversal_factor": accessibility,
        "last_reinforced_event_id": None,
        "source_event_ids": source_event_ids,
        "reason": reason,
        "rediscovery_recipe": "new observed evidence must bridge this edge or one of its endpoint fingerprints",
        "decay_basis": {
            "used": False,
            "material_type": _material_type(edge),
            "idiosyncratic": idiosyncratic,
            "identity_bearing": identity_bearing,
            "confidence_level": edge["confidence"].get("level"),
        },
    }


def _candidate_action(
    candidate: dict[str, Any],
    edges: list[dict[str, Any]],
    used_candidates: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if candidate["candidate_id"] in used_candidates:
        return None
    if candidate["lifecycle"]["lifecycle_state"] in {"dormant", "rediscovered", "tombstoned"}:
        return None
    incident = [
        edge
        for edge in edges
        if candidate["candidate_id"] in {edge["source_candidate_id"], edge["target_candidate_id"]}
    ]
    if not incident:
        return None
    if any(edge["lifecycle"]["lifecycle_state"] == "active" for edge in incident):
        return None
    if max(edge["lifecycle"]["accessibility"] for edge in incident) > 0.45:
        return None
    source_event_ids = sorted({ref["event_id"] for ref in candidate["source_refs"]})
    return {
        "accessibility": 0.25,
        "reason": "all access paths weakened or archived; evidence remains preserved",
        "source_event_ids": source_event_ids,
        "rediscovery_recipe": "match new observed evidence against the candidate semantic fingerprint",
        "decay_basis": {
            "incident_edge_count": len(incident),
            "incident_lifecycle_states": sorted({edge["lifecycle"]["lifecycle_state"] for edge in incident}),
            "evidence_preserved": True,
        },
    }


def _rediscovery_actions(journal: JournalStore, projection: ProjectionStore) -> list[dict[str, Any]]:
    observed_events = [
        event
        for event in journal.iter_events()
        if event["event_type"] == "observation" and event["epistemic_status"] == "observed"
    ]
    dormant = [
        candidate
        for candidate in projection.candidates()
        if candidate["lifecycle"]["lifecycle_state"] == "dormant"
    ]
    edges = projection.edges()
    actions: list[dict[str, Any]] = []
    for candidate in dormant:
        dormancy_event = journal.get_event(candidate["lifecycle"]["last_maintenance_event_id"])
        if dormancy_event is None:
            continue
        original_event_ids = {ref["event_id"] for ref in candidate["source_refs"]}
        for event in observed_events:
            if event["sequence"] <= dormancy_event["sequence"]:
                continue
            if event["id"] in original_event_ids:
                continue
            text = canonical_json(event["payload"]).lower()
            if normalize_label(candidate["label"]) not in text:
                continue
            bridge = next(
                (
                    edge
                    for edge in edges
                    if candidate["candidate_id"] in {edge["source_candidate_id"], edge["target_candidate_id"]}
                    and any(ref["event_id"] == event["id"] for ref in edge["source_refs"])
                ),
                None,
            )
            if bridge is None:
                continue
            actions.append(
                {
                    "dormant_candidate_id": candidate["candidate_id"],
                    "new_evidence_event_id": event["id"],
                    "bridge_edge_id": bridge["id"],
                    "entry_candidate_id": (
                        bridge["target_candidate_id"]
                        if bridge["source_candidate_id"] == candidate["candidate_id"]
                        else bridge["source_candidate_id"]
                    ),
                    "source_event_ids": sorted(
                        {
                            event["id"],
                            *[ref["event_id"] for ref in candidate["source_refs"]],
                            *[ref["event_id"] for ref in bridge["source_refs"]],
                        }
                    ),
                    "reason": "new observed evidence matched dormant candidate and bridge edge",
                    "semantic_fingerprint": candidate["semantic_fingerprint"],
                }
            )
            break
    return actions


def _append_rediscovery_reflection(
    journal: JournalStore,
    projection: ProjectionStore,
    *,
    rediscovery: dict[str, Any],
    actor: str,
    source: str,
) -> dict[str, Any]:
    result = retrieve(
        projection,
        RetrievalQuery(
            entry_candidate_ids=[rediscovery["entry_candidate_id"]],
            max_hops=1,
        ),
    )
    path = cite_retrieval_path(result, rediscovery["dormant_candidate_id"])
    payload = {
        "cited_source_event_ids": rediscovery["source_event_ids"],
        "retrieval_result_hash": retrieval_result_hash(result),
        "retrieval_result_snapshot": result,
        "cited_retrieval_paths": [path],
        "interpretive_claims": [
            {
                "type": "tension",
                "claim": "New observed evidence reopened access to a dormant memory without making the old interpretation factual by default.",
                "cites": [path["path_id"]],
                "epistemic_status": "authored",
            }
        ],
        "open_questions": ["What later evidence should decide whether this rediscovered path deserves stronger access?"],
        "uncertainty_notes": ["Rediscovery changes accessibility, not source confidence."],
        "possible_self_deception": ["The bridge may overfit a matching label rather than a meaningful renewed association."],
        "rejected_interpretations": ["The dormant memory was not proven newly true merely because it resurfaced."],
        "changed_stance": "Treat rediscovered material as accessible again but still dependent on its original evidence.",
        "future_attention": [
            {
                "target": rediscovery["dormant_candidate_id"],
                "reason": "new observed evidence created a bridge to dormant material",
                "resource_scope": {
                    "external_contact": False,
                    "network_access": False,
                    "autonomous_spend": False,
                    "compute_escalation": False,
                },
            }
        ],
        "proposed_graph_updates": [],
        "deferred_graph_updates": [
            {
                "reason": "Rediscovery requires later evidence before stronger promotion.",
                "source_event_ids": rediscovery["source_event_ids"],
            }
        ],
    }
    return append_reflection_event(
        journal,
        payload=payload,
        retrieval_result=result,
        actor=actor,
        source=source,
        context={"active_task": "phase-5-consolidation", "source_channel": source},
        residue=unknown_residue("consolidation"),
    )


def _activated_candidate_ids(retrieval_result: dict[str, Any]) -> list[str]:
    return [
        candidate["candidate_id"]
        for candidate in retrieval_result.get("activated_candidates", [])
        if candidate.get("candidate_id")
    ]


def _activated_record_ids(retrieval_result: dict[str, Any]) -> list[str]:
    record_ids: list[str] = []
    for candidate in retrieval_result.get("activated_candidates", []):
        for path in candidate.get("activation_paths", []):
            for step in path.get("steps", []):
                if step.get("record_id"):
                    record_ids.append(step["record_id"])
    return record_ids


def _activated_path_ids(retrieval_result: dict[str, Any]) -> list[str]:
    path_ids: list[str] = []
    for candidate in retrieval_result.get("activated_candidates", []):
        candidate_id = candidate.get("candidate_id")
        for path in candidate.get("activation_paths", []):
            path_ids.append(
                "path_"
                + stable_hash(
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
                )[:24]
            )
    return path_ids


def _recent_use_index(events: list[dict[str, Any]], payload_field: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    latest_sequence = max((event["sequence"] for event in events), default=0)
    oldest_recent_sequence = max(0, latest_sequence - RECENT_USE_SEQUENCE_WINDOW)
    for event in events:
        if event["sequence"] < oldest_recent_sequence:
            continue
        for item_id in event["payload"].get(payload_field, []):
            index[item_id] = {"event_id": event["id"], "sequence": event["sequence"]}
    return index


def _degree(edges: list[dict[str, Any]]) -> dict[str, int]:
    degree: dict[str, set[str]] = {}
    for edge in edges:
        degree.setdefault(edge["source_candidate_id"], set()).add(edge["target_candidate_id"])
        degree.setdefault(edge["target_candidate_id"], set()).add(edge["source_candidate_id"])
    return {candidate_id: len(neighbors) for candidate_id, neighbors in degree.items()}


def _material_type(edge: dict[str, Any]) -> str:
    if edge["edge_type"] == "dream_association":
        return "dream"
    if edge["edge_type"] == "rehearsal_candidate":
        return "rehearsal"
    if edge["edge_type"] == "contradiction":
        return "conflict"
    if edge["edge_type"] == "reflective_interpretation":
        return "reflection"
    return edge["epistemic_status"]
