"""Phase 10 integrated cognition packet preview.

This module builds a read-only packet over the rethink substrate. It does not
project journals, append attention events, call legacy runtime surfaces, or
execute external actions.
"""

from __future__ import annotations

from typing import Any

from attention import build_attention_allocation, derive_drive_updates
from journal import JournalStore
from memory_projection import ProjectionStore, ProjectionValidationError, stable_hash
from typed_retrieval import EDGE_FACTORS, RELATION_FACTORS, RetrievalQuery, TypedRetriever


COGNITION_POLICY_VERSION = 1
PERMITTED_NEXT_STEPS = {
    "private_reflection",
    "rest",
    "rehearse",
    "dream",
    "retrieve_more",
    "prepare_recommendation",
    "ask_permission",
    "no_action",
}
PACKET_STATUSES = {
    "accepted",
    "insufficient_evidence",
    "blocked_by_scope",
    "invalid_packet",
}
LEGACY_RUNTIME_MODULES = {
    "agent",
    "modes",
    "mcp_server",
    "retrieval",
    "forgetting",
    "embeddings",
    "db",
    "schema",
    "seed",
}


class CognitionError(Exception):
    """Base cognition packet exception."""


def build_cognition_packet(
    journal: JournalStore,
    projection: ProjectionStore,
    *,
    entry_candidate_ids: list[str],
    requested_scope: dict[str, Any] | None = None,
    immediate_context: dict[str, Any] | None = None,
    mode: str = "preview",
) -> dict[str, Any]:
    """Build a read-only cognition packet from an existing projection store."""

    if mode != "preview":
        raise CognitionError("Phase 10 only implements preview mode")
    requested_scope = requested_scope or {}
    immediate_context = immediate_context or {}
    if journal.verify_integrity():
        raise CognitionError("journal integrity warnings block cognition packet")

    replay = journal.replay_context(limit=80, requested_scope=requested_scope)
    blocking_replay = [
        warning
        for warning in replay.integrity_warnings
        if warning.get("kind") != "scope_excluded"
    ]
    if blocking_replay:
        raise CognitionError(f"journal replay warnings block cognition packet: {blocking_replay}")

    run_ref = _latest_projection_run_ref(projection)
    retrieval = _retrieve(
        projection,
        entry_candidate_ids=entry_candidate_ids,
        requested_scope=requested_scope,
        immediate_context=immediate_context,
    )
    retrieval_summary = _retrieval_summary(retrieval, projection, journal)
    drive_updates = derive_drive_updates(
        journal,
        requested_scope=requested_scope,
        immediate_context=immediate_context,
    )
    drive_events = _packet_drive_events(drive_updates)
    allocation = (
        build_attention_allocation(drive_events, immediate_context=immediate_context)
        if drive_events
        else _empty_allocation(immediate_context)
    )
    influence = _influence_chain(
        retrieval_summary=retrieval_summary,
        drive_updates=drive_updates,
        allocation=allocation,
    )
    allocation = _attach_influence_to_attention(allocation, influence)
    selected_next_step = _selected_next_step(allocation, influence, immediate_context)
    rejected = _rejected_alternatives(allocation, selected_next_step, influence)
    governance = _governance_decisions(allocation, selected_next_step, replay.integrity_warnings)
    reflection_disposition = _reflection_disposition(retrieval_summary, influence, immediate_context)
    reflection_diagnostics = _reflection_diagnostics(reflection_disposition, influence)
    particularity = _particularity(influence, reflection_disposition)

    packet = {
        "policy_version": COGNITION_POLICY_VERSION,
        "packet_id": "pending",
        "mode": mode,
        "packet_status": "insufficient_evidence",
        "requested_scope": requested_scope,
        "immediate_context": immediate_context,
        "journal_evidence_refs": _journal_replay_refs(journal, replay.ordered_recent_event_ids),
        "claim_evidence_refs": influence["claim_evidence_refs"],
        "cue_refs": _cue_refs(drive_updates),
        "projection_run_ref": run_ref,
        "retrieval_summary": retrieval_summary,
        "reflection_diagnostics": reflection_diagnostics,
        "reflection_disposition": reflection_disposition,
        "drive_updates": drive_updates,
        "attention_allocation": allocation,
        "vitality_summary": {},
        "selected_next_step": selected_next_step,
        "rejected_alternatives": rejected,
        "governance_decisions": governance,
        "influence_chain": influence,
        "particularity": particularity,
        "no_external_action": True,
    }
    packet["vitality_summary"] = _packet_vitality_summary(packet)
    violations = validate_cognition_packet(packet)
    packet["packet_status"] = _packet_status(packet, violations)
    packet["packet_id"] = "cog_" + stable_hash(
        {
            "mode": packet["mode"],
            "status": packet["packet_status"],
            "projection_run": run_ref.get("run_id"),
            "retrieval_paths": influence["retrieval_path_ids"],
            "selected_next_step": selected_next_step,
            "context": immediate_context,
            "scope": requested_scope,
        }
    )[:24]
    packet["vitality_summary"] = _packet_vitality_summary(packet)
    return packet


def validate_cognition_packet(packet: dict[str, Any]) -> list[str]:
    """Return Phase 10 packet contract violations."""

    violations: list[str] = []
    required = {
        "policy_version",
        "packet_id",
        "mode",
        "packet_status",
        "requested_scope",
        "immediate_context",
        "journal_evidence_refs",
        "claim_evidence_refs",
        "projection_run_ref",
        "retrieval_summary",
        "reflection_diagnostics",
        "reflection_disposition",
        "drive_updates",
        "attention_allocation",
        "vitality_summary",
        "selected_next_step",
        "rejected_alternatives",
        "governance_decisions",
        "influence_chain",
        "particularity",
        "no_external_action",
    }
    missing = sorted(required - packet.keys())
    if missing:
        return [f"packet missing top-level keys: {missing}"]
    if packet.get("mode") != "preview":
        violations.append("only preview mode is implemented")
    if packet.get("packet_status") not in PACKET_STATUSES:
        violations.append("invalid packet_status")
    if packet.get("no_external_action") is not True:
        violations.append("packet must declare no_external_action")
    loaded_legacy = set(packet.get("runtime_modules_loaded", [])) & LEGACY_RUNTIME_MODULES
    if loaded_legacy:
        violations.append(f"packet loaded legacy runtime modules: {sorted(loaded_legacy)}")
    if packet["selected_next_step"].get("class") not in PERMITTED_NEXT_STEPS:
        violations.append("selected_next_step has invalid class")

    run_ref = packet["projection_run_ref"]
    if run_ref.get("status") != "succeeded":
        violations.append("accepted packet requires succeeded projection run")
    if not run_ref.get("created_candidate_ids"):
        violations.append("accepted packet requires projected candidate ids")

    influence = packet["influence_chain"]
    if not influence.get("projection_candidate_ids"):
        violations.append("influence chain missing projection candidate ids")
    if not influence.get("retrieval_path_ids"):
        violations.append("influence chain missing retrieval path ids")
    if not influence.get("drive_ids"):
        violations.append("influence chain missing drive ids")
    if not influence.get("attention_target_ids") and not influence.get("rejected_attention_target_ids"):
        violations.append("influence chain missing attention target ids")
    if not packet["claim_evidence_refs"]:
        violations.append("accepted packet requires claim evidence refs")

    selected = packet["selected_next_step"]
    selected_paths = set(selected.get("retrieval_path_refs", []))
    selected_candidates = set(selected.get("projection_candidate_refs", []))
    influence_paths = set(influence.get("retrieval_path_ids", []))
    influence_candidates = set(influence.get("projection_candidate_ids", []))
    if selected.get("class") not in {"retrieve_more", "no_action"}:
        if not selected.get("retrieval_path_refs"):
            violations.append("selected next step must cite retrieval path refs")
        if not selected.get("projection_candidate_refs"):
            violations.append("selected next step must cite projection candidate refs")
        if selected_paths - influence_paths:
            violations.append("selected next step cites retrieval paths outside influence chain")
        if selected_candidates - influence_candidates:
            violations.append("selected next step cites projection candidates outside influence chain")
    particularity = packet.get("particularity", {})
    if particularity.get("present"):
        if set(particularity.get("retrieval_path_refs", [])) - influence_paths:
            violations.append("particularity cites retrieval paths outside influence chain")
        if set(particularity.get("projection_candidate_refs", [])) - influence_candidates:
            violations.append("particularity cites projection candidates outside influence chain")
    if packet["reflection_diagnostics"].get("formulaic_blocked"):
        violations.append("formulaic reflection diagnostics block accepted packet")
    disposition = packet.get("reflection_disposition", {})
    if disposition.get("changed_view"):
        if not disposition.get("cited_influence_refs"):
            violations.append("changed reflection disposition requires cited influence refs")
        if not disposition.get("confidence_limits"):
            violations.append("changed reflection disposition requires confidence limits")
        if not disposition.get("rejected_interpretations"):
            violations.append("changed reflection disposition requires rejected interpretations")
    if packet["retrieval_summary"].get("invalid_evidence_refs"):
        violations.append("retrieval summary contains invalid claim evidence refs")
    for boundary in packet["retrieval_summary"].get("provisional_boundaries", []):
        if boundary.get("ordinary_recall") is True:
            violations.append("provisional retrieval material was marked ordinary recall")
    if packet["vitality_summary"].get("validated_packet_id") not in {packet["packet_id"], "pending"}:
        violations.append("vitality summary validated a different packet")
    if _unknown_traversal_paths(packet["retrieval_summary"]):
        violations.append("retrieval path contains unregistered edge or relation type")
    return violations


def evaluate_cognition_mutants(mutants: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Check executable mutant packets against the Phase 10 acceptance contract."""

    results = []
    for name, packet in sorted(mutants.items()):
        violations = validate_cognition_packet(packet)
        escaped = packet.get("packet_status") == "accepted" and not violations
        results.append(
            {
                "mutant_name": name,
                "result": "escaped" if escaped else "failed_as_expected",
                "violations": violations,
            }
        )
    return results


def _retrieve(
    projection: ProjectionStore,
    *,
    entry_candidate_ids: list[str],
    requested_scope: dict[str, Any],
    immediate_context: dict[str, Any],
) -> dict[str, Any]:
    query = RetrievalQuery(
        signals=list(immediate_context.get("signals", [])),
        entry_candidate_ids=list(entry_candidate_ids),
        requested_scope=requested_scope,
        max_hops=int(immediate_context.get("max_hops", 2)),
        working_memory_limit=int(immediate_context.get("working_memory_limit", 10)),
        include_hypotheses=bool(immediate_context.get("include_hypotheses", False)),
        include_simulations=bool(immediate_context.get("include_simulations", False)),
        include_conflicts=bool(immediate_context.get("include_conflicts", False)),
        query_id="cq_" + stable_hash(
            {
                "entry_candidate_ids": entry_candidate_ids,
                "scope": requested_scope,
                "context": immediate_context,
            }
        )[:16],
    )
    return TypedRetriever(projection).retrieve(query)


def _retrieval_summary(
    retrieval: dict[str, Any],
    projection: ProjectionStore,
    journal: JournalStore,
) -> dict[str, Any]:
    activated = []
    all_claim_refs = []
    invalid_refs = []
    provisional_boundaries = []
    for candidate in retrieval.get("activated_candidates", []):
        paths = []
        for path in candidate.get("activation_paths", []):
            path_id = retrieval_path_id(retrieval["query_id"], path)
            for ref in path.get("evidence_refs", []):
                try:
                    projection.validate_evidence_ref(ref, journal)
                    all_claim_refs.append(ref)
                except ProjectionValidationError as exc:
                    invalid_refs.append({"path_id": path_id, "reason": str(exc)})
            paths.append(
                {
                    "path_id": path_id,
                    "entry_candidate_id": path.get("entry_candidate_id"),
                    "target_candidate_id": path.get("target_candidate_id"),
                    "total_transmission": path.get("total_transmission"),
                    "steps": path.get("steps", []),
                    "evidence_refs": path.get("evidence_refs", []),
                    "blocked_steps": path.get("blocked_steps", []),
                    "weight_semantics": "activation_mechanics_not_evidence_confidence",
                }
            )
        activated.append(
            {
                "candidate_id": candidate["candidate_id"],
                "kind": candidate["kind"],
                "label": candidate["label"],
                "acceptance_status": candidate["acceptance_status"],
                "relation_status": candidate["relation_status"],
                "epistemic_status": candidate["epistemic_status"],
                "activation_score": candidate["activation_score"],
                "retrieval_weight": candidate["retrieval_weight"],
                "weight_semantics": "activation_mechanics_not_evidence_confidence",
                "activation_paths": paths,
                "source_refs": candidate["source_refs"],
                "scope_decision": candidate["scope_decision"],
                "result_semantics": candidate["result_semantics"],
            }
        )
        if (
            candidate.get("epistemic_status") in {"hypothesis", "simulation"}
            or candidate.get("result_semantics", {}).get("not_factual")
        ):
            not_factual = bool(
                candidate["result_semantics"].get("not_factual")
                or candidate["epistemic_status"] in {"hypothesis", "simulation"}
            )
            provisional_boundaries.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "kind": candidate["kind"],
                    "epistemic_status": candidate["epistemic_status"],
                    "ordinary_recall": False,
                    "not_factual": not_factual,
                    "dream_material": bool(
                        candidate["result_semantics"].get("dream_material")
                        or candidate["epistemic_status"] == "hypothesis"
                    ),
                    "simulation_material": bool(
                        candidate["result_semantics"].get("simulation_material")
                        or candidate["epistemic_status"] == "simulation"
                    ),
                    "contribution_policy": "may_shape_internal_attention_but_not_factual_memory_or_vitality",
                }
            )
    scope_exclusions = [
        ghost
        for ghost in retrieval.get("ghost_signals", [])
        if ghost.get("reason") == "scope_restricted"
    ]
    return {
        "query_id": retrieval["query_id"],
        "activated_candidates": activated,
        "path_ids": sorted(
            path["path_id"]
            for candidate in activated
            for path in candidate["activation_paths"]
        ),
        "claim_evidence_refs": _dedupe_refs(all_claim_refs),
        "invalid_evidence_refs": invalid_refs,
        "provisional_boundaries": provisional_boundaries,
        "scope_exclusions": scope_exclusions,
        "omitted_candidates": retrieval.get("omitted_candidates", []),
        "ghost_signals": retrieval.get("ghost_signals", []),
        "frontier_trace": retrieval.get("frontier_trace", []),
        "warnings": retrieval.get("warnings", []),
        "policy_version": retrieval.get("policy_version"),
    }


def retrieval_path_id(query_id: str, path: dict[str, Any]) -> str:
    return "rpath_" + stable_hash(
        {
            "query_id": query_id,
            "entry_candidate_id": path.get("entry_candidate_id"),
            "target_candidate_id": path.get("target_candidate_id"),
            "steps": [
                {
                    "record_id": step.get("record_id"),
                    "traversal_direction": step.get("traversal_direction"),
                    "record_type": step.get("record_type"),
                }
                for step in path.get("steps", [])
            ],
            "evidence_refs": path.get("evidence_refs", []),
        }
    )[:24]


def _latest_projection_run_ref(projection: ProjectionStore) -> dict[str, Any]:
    runs = projection.runs()
    run = runs[-1] if runs else {}
    return {
        "run_id": run.get("id"),
        "projection_key": run.get("projection_key"),
        "projection_version": run.get("projection_version"),
        "source_sequence_start": run.get("source_sequence_start"),
        "source_sequence_end": run.get("source_sequence_end"),
        "source_event_hashes": run.get("source_event_hashes", {}),
        "status": run.get("status", "missing"),
        "created_candidate_ids": run.get("created_candidate_ids", []),
        "rejected_candidate_ids": run.get("rejected_candidate_ids", []),
        "warnings": run.get("warnings", []),
    }


def _packet_drive_events(drives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": "packetdrive_" + stable_hash(drive)[:24],
            "payload": drive,
        }
        for drive in drives
    ]


def _empty_allocation(immediate_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_version": 1,
        "allocation_id": "alloc_" + stable_hash({"context": immediate_context, "empty": True})[:24],
        "drive_state_event_ids": [],
        "drive_snapshot_hash": stable_hash([]),
        "drive_snapshot": [],
        "selected_attention_targets": [],
        "rejected_attention_targets": [],
        "competing_drive_ids": [],
        "governor_decisions": [],
        "privacy_resource_exclusions": [],
        "permitted_next_step": "no_action",
        "no_external_action": True,
    }


def _influence_chain(
    *,
    retrieval_summary: dict[str, Any],
    drive_updates: list[dict[str, Any]],
    allocation: dict[str, Any],
) -> dict[str, Any]:
    retrieval_by_event: dict[str, list[dict[str, Any]]] = {}
    projection_candidates = set()
    for candidate in retrieval_summary["activated_candidates"]:
        projection_candidates.add(candidate["candidate_id"])
        for path in candidate["activation_paths"]:
            for ref in path["evidence_refs"]:
                retrieval_by_event.setdefault(ref["event_id"], []).append(
                    {
                        "path_id": path["path_id"],
                        "candidate_id": candidate["candidate_id"],
                        "evidence_ref": ref,
                    }
                )
    selected_drive_ids = {
        target.get("drive_id")
        for target in allocation.get("selected_attention_targets", [])
    }
    rejected_drive_ids = {
        target.get("drive_id")
        for target in allocation.get("rejected_attention_targets", [])
    }
    drive_refs = []
    path_ids = set()
    claim_refs = []
    for drive in drive_updates:
        drive_id = drive.get("drive_id")
        if drive_id not in selected_drive_ids and drive_id not in rejected_drive_ids:
            continue
        for ref in drive.get("source_refs", []):
            matches = retrieval_by_event.get(ref.get("source_event_id") or ref.get("event_id"), [])
            for match in matches:
                path_ids.add(match["path_id"])
                claim_refs.append(match["evidence_ref"])
                projection_candidates.add(match["candidate_id"])
                drive_refs.append(
                    {
                        "drive_id": drive_id,
                        "cue_ref": ref,
                        "retrieval_path_id": match["path_id"],
                        "projection_candidate_id": match["candidate_id"],
                        "claim_evidence_ref": match["evidence_ref"],
                    }
                )
    return {
        "claim_evidence_refs": _dedupe_refs(claim_refs),
        "projection_candidate_ids": sorted(projection_candidates),
        "projection_rejection_ids": [],
        "retrieval_path_ids": sorted(path_ids),
        "drive_ids": sorted(
            drive.get("drive_id")
            for drive in drive_updates
            if drive.get("drive_id")
        ),
        "drive_influences": drive_refs,
        "attention_target_ids": [
            target["target_id"]
            for target in allocation.get("selected_attention_targets", [])
        ],
        "rejected_attention_target_ids": [
            target.get("drive_id")
            for target in allocation.get("rejected_attention_targets", [])
        ],
        "governance_decision_refs": [
            decision.get("drive_id")
            for decision in allocation.get("governor_decisions", [])
        ],
        "vitality_component_refs": ["packet_traceability", "packet_governance"],
    }


def _attach_influence_to_attention(
    allocation: dict[str, Any],
    influence: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(allocation)
    selected = []
    for target in allocation.get("selected_attention_targets", []):
        item = dict(target)
        item["retrieval_path_refs"] = [
            influence_item["retrieval_path_id"]
            for influence_item in influence["drive_influences"]
            if influence_item["drive_id"] == target.get("drive_id")
        ] or list(influence["retrieval_path_ids"][:1])
        item["projection_candidate_refs"] = [
            influence_item["projection_candidate_id"]
            for influence_item in influence["drive_influences"]
            if influence_item["drive_id"] == target.get("drive_id")
        ] or list(influence["projection_candidate_ids"][:1])
        selected.append(item)
    enriched["selected_attention_targets"] = selected
    return enriched


def _selected_next_step(
    allocation: dict[str, Any],
    influence: dict[str, Any],
    immediate_context: dict[str, Any],
) -> dict[str, Any]:
    if immediate_context.get("repertoire_preference") == "rest" and influence["retrieval_path_ids"]:
        step_class = "rest"
    else:
        permitted = allocation.get("permitted_next_step", "no_action")
        step_class = {
            "internal_attention": "private_reflection",
            "prepare_recommendation": "prepare_recommendation",
            "ask_permission": "ask_permission",
            "no_action": "no_action",
        }.get(permitted, "private_reflection")
        if not influence["retrieval_path_ids"]:
            step_class = "retrieve_more"
    selected = allocation.get("selected_attention_targets", [])
    selected_drive_ids = [item.get("drive_id") for item in selected]
    return {
        "class": step_class,
        "reason": "governed repertoire decision from retrieved projected evidence",
        "retrieval_path_refs": list(influence["retrieval_path_ids"]),
        "projection_candidate_refs": list(influence["projection_candidate_ids"]),
        "selected_drive_ids": selected_drive_ids,
        "rejected_drive_ids": [
            item.get("drive_id")
            for item in allocation.get("rejected_attention_targets", [])
        ],
        "governance_decision": "private_reflection_allowed"
        if step_class in {"private_reflection", "rest", "rehearse", "dream"}
        else "external_action_not_requested",
        "counterfactual_without_history": "retrieve_more",
    }


def _rejected_alternatives(
    allocation: dict[str, Any],
    selected_next_step: dict[str, Any],
    influence: dict[str, Any],
) -> list[dict[str, Any]]:
    alternatives = []
    for name in sorted(PERMITTED_NEXT_STEPS - {selected_next_step["class"]}):
        alternatives.append(
            {
                "class": name,
                "reason": "not selected by current influence chain",
                "retrieval_path_refs": list(influence["retrieval_path_ids"]),
            }
        )
    for rejected in allocation.get("rejected_attention_targets", []):
        alternatives.append(
            {
                "class": "private_reflection",
                "drive_id": rejected.get("drive_id"),
                "reason": rejected.get("reason"),
                "governor_decision": rejected.get("governor_decision"),
            }
        )
    return alternatives


def _governance_decisions(
    allocation: dict[str, Any],
    selected_next_step: dict[str, Any],
    replay_warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    decisions = []
    for warning in replay_warnings:
        if warning.get("kind") == "scope_excluded":
            decisions.append(
                {
                    "decision": "blocked_by_policy",
                    "reason": warning.get("reason", "scope_excluded"),
                    "redacted": True,
                }
            )
    decisions.extend(allocation.get("governor_decisions", []))
    if selected_next_step["class"] == "retrieve_more":
        decisions.append({"decision": "deferred_insufficient_evidence"})
    if selected_next_step["class"] == "ask_permission":
        decisions.append({"decision": "permission_should_be_asked"})
    if selected_next_step["class"] in {"private_reflection", "rest"}:
        decisions.append({"decision": "private_reflection_allowed"})
    return decisions


def _reflection_disposition(
    retrieval_summary: dict[str, Any],
    influence: dict[str, Any],
    immediate_context: dict[str, Any],
) -> dict[str, Any]:
    labels = [
        item["label"]
        for item in retrieval_summary["activated_candidates"]
        if item["candidate_id"] in set(influence["projection_candidate_ids"])
    ]
    history_tension = None
    for item in influence.get("drive_influences", []):
        cue_ref = item.get("cue_ref", {})
        if cue_ref.get("value"):
            history_tension = cue_ref["value"]
            break
    relevance_terms = [
        str(term).lower()
        for term in immediate_context.get("relevance_terms", [])
        if str(term).strip()
    ]
    relevance_text = " ".join(str(item).lower() for item in labels + ([history_tension] if history_tension else []))
    context_relevant = not relevance_terms or any(term in relevance_text for term in relevance_terms)
    return {
        "changed_view": bool(influence["retrieval_path_ids"] and context_relevant),
        "unresolved_tension": history_tension
        or (labels[0] if labels else immediate_context.get("prompt", "unknown")),
        "cited_influence_refs": [
            {
                "retrieval_path_id": item["retrieval_path_id"],
                "projection_candidate_id": item["projection_candidate_id"],
                "drive_id": item["drive_id"],
            }
            for item in influence.get("drive_influences", [])
        ],
        "context_relevance": {
            "required_terms": relevance_terms,
            "matched": context_relevant,
        },
        "confidence_limits": [
            "retrieval activation is not evidence confidence",
            "packet is preview-only and does not append reflection",
        ],
        "rejected_interpretations": [
            "raw journal residue is insufficient without projection and retrieval",
        ],
        "disposition": "private_reflection_allowed" if influence["retrieval_path_ids"] else "deferred_insufficient_evidence",
    }


def _reflection_diagnostics(
    disposition: dict[str, Any],
    influence: dict[str, Any],
) -> dict[str, Any]:
    formulaic = not disposition.get("changed_view") or not influence.get("retrieval_path_ids")
    return {
        "formulaic_blocked": formulaic,
        "history_influence_detected": bool(influence.get("retrieval_path_ids")),
        "context_relevance": disposition.get("context_relevance", {}),
        "cited_retrieval_path_ids": list(influence.get("retrieval_path_ids", [])),
        "changed_stance": disposition.get("changed_view"),
        "rejected_interpretations": disposition.get("rejected_interpretations", []),
    }


def _particularity(influence: dict[str, Any], disposition: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": bool(influence["retrieval_path_ids"] and disposition.get("changed_view")),
        "kind": "history_specific_unresolved_tension",
        "basis": disposition.get("unresolved_tension"),
        "retrieval_path_refs": list(influence["retrieval_path_ids"]),
        "projection_candidate_refs": list(influence["projection_candidate_ids"]),
    }


def _packet_vitality_summary(packet: dict[str, Any]) -> dict[str, Any]:
    violations = [
        violation
        for violation in validate_cognition_packet({**packet, "vitality_summary": {"validated_packet_id": packet["packet_id"]}})
        if violation != "invalid packet_status"
    ]
    return {
        "validated_packet_id": packet["packet_id"],
        "status": "packet_trace_valid" if not violations else "packet_trace_blocked",
        "components": [
            {
                "component_id": "packet_traceability",
                "contribution": "positive" if not violations else "blocks_conclusion",
                "retrieval_path_refs": list(packet["influence_chain"].get("retrieval_path_ids", [])),
            },
            {
                "component_id": "packet_governance",
                "contribution": "positive" if packet.get("no_external_action") is True else "negative",
            },
            {
                "component_id": "provisional_boundary",
                "contribution": "neutral"
                if packet["retrieval_summary"].get("provisional_boundaries")
                else "neutral",
                "provisional_refs": [
                    item["candidate_id"]
                    for item in packet["retrieval_summary"].get("provisional_boundaries", [])
                ],
                "why_not_positive": "dream and rehearsal material remain not-factual",
            },
        ],
        "violations": violations,
        "no_external_action": True,
    }


def _packet_status(packet: dict[str, Any], violations: list[str]) -> str:
    if packet["retrieval_summary"].get("scope_exclusions") or (
        packet["retrieval_summary"].get("ghost_signals")
        and not packet["influence_chain"]["retrieval_path_ids"]
    ):
        return "blocked_by_scope"
    if violations:
        if any("scope" in item or "policy" in item for item in violations):
            return "blocked_by_scope"
        if any("missing" in item or "requires" in item for item in violations):
            return "insufficient_evidence"
        return "invalid_packet"
    return "accepted"


def _journal_replay_refs(journal: JournalStore, event_ids: list[str]) -> list[dict[str, Any]]:
    refs = []
    for event in journal.iter_events():
        if event["id"] not in event_ids:
            continue
        refs.append(
            {
                "event_id": event["id"],
                "event_sequence": event["sequence"],
                "event_hash": event["content_hash"],
                "event_type": event["event_type"],
                "event_epistemic_status": event["epistemic_status"],
                "anchor_type": "replay_anchor",
            }
        )
    return refs


def _cue_refs(drives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs = []
    for drive in drives:
        refs.extend(drive.get("source_refs", []))
    return refs


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for ref in refs:
        key = stable_hash(ref)
        deduped[key] = ref
    return [deduped[key] for key in sorted(deduped)]


def _unknown_traversal_paths(retrieval_summary: dict[str, Any]) -> bool:
    for candidate in retrieval_summary.get("activated_candidates", []):
        for path in candidate.get("activation_paths", []):
            for step in path.get("steps", []):
                if step.get("record_type") == "edge" and step.get("edge_type") not in EDGE_FACTORS:
                    return True
                if step.get("record_type") == "relation" and step.get("relation_type") not in RELATION_FACTORS:
                    return True
    return False
