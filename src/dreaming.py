"""Phase 6 deterministic dreaming workflow.

Dreaming is deliberately journal-first and stdlib-only. It selects unresolved
residue from prior evidence and records structured hypothesis fragments without
mutating projection state or factual confidence.
"""

from __future__ import annotations

from typing import Any

from journal import JournalStore
from memory_projection import ProjectionStore, stable_hash


DREAM_POLICY_VERSION = 1

FIELD_CATEGORIES = {
    "salience": "salience",
    "attention_target": "attention_target",
    "uncertainty": "uncertainty",
    "open_tensions": "open_tension",
    "drive_refs": "drive",
    "importance_reason": "importance_reason",
    "affect_valence": "affect",
    "expected_outcome": "expected_outcome",
}

UNRESOLVED_CATEGORIES = {
    "uncertainty",
    "open_tension",
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

REFLECTION_PAYLOAD_FIELDS = {
    "open_questions": "reflection_question",
    "rejected_interpretations": "rejected_interpretation",
    "future_attention": "future_attention",
    "deferred_graph_updates": "deferred_graph_update",
}


class DreamingError(Exception):
    """Base dreaming exception."""


def run_dream_cycle(
    journal: JournalStore,
    *,
    projection: ProjectionStore | None = None,
    retrieval_result: dict[str, Any] | None = None,
    requested_scope: dict[str, Any] | None = None,
    immediate_context: dict[str, Any] | None = None,
    actor: str = "meno",
    source: str = "dreaming_workflow",
    max_fragments: int = 3,
) -> dict[str, Any]:
    """Select residue, generate fragments, and append a dream event if useful."""

    residues = select_dream_residues(
        journal,
        projection=projection,
        retrieval_result=retrieval_result,
        requested_scope=requested_scope,
    )
    fragments = generate_dream_fragments(
        residues,
        immediate_context=immediate_context,
        max_fragments=max_fragments,
    )
    if not fragments:
        return {
            "dream_event": None,
            "residues_used": residues,
            "generated_candidates": [],
            "no_action_reason": "no eligible unresolved residue pair",
        }
    event = append_dream_event(
        journal,
        residues_used=residues,
        generated_candidates=fragments,
        actor=actor,
        source=source,
        requested_scope=requested_scope,
        immediate_context=immediate_context,
    )
    return {
        "dream_event": event,
        "residues_used": residues,
        "generated_candidates": fragments,
        "no_action_reason": None,
    }


def select_dream_residues(
    journal: JournalStore,
    *,
    projection: ProjectionStore | None = None,
    retrieval_result: dict[str, Any] | None = None,
    requested_scope: dict[str, Any] | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    warnings = journal.verify_integrity()
    if warnings:
        raise DreamingError(f"journal integrity warnings block dreaming: {warnings}")
    replay = journal.replay_context(limit=80, requested_scope=requested_scope)
    if replay.integrity_warnings:
        blocking = [
            warning
            for warning in replay.integrity_warnings
            if warning.get("kind") != "scope_excluded"
        ]
        if blocking:
            raise DreamingError(f"journal replay warnings block dreaming: {blocking}")

    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket_name, category in (
        ("open_tensions", "open_tension"),
        ("uncertainty_markers", "uncertainty"),
        ("attention_targets", "attention_target"),
        ("importance_reasons", "importance_reason"),
        ("drive_refs", "drive"),
        ("expected_outcomes", "expected_outcome"),
        ("affect_valence", "affect"),
        ("salient_residues", "salience"),
    ):
        for item in getattr(replay, bucket_name):
            event = journal.get_event(item["event_id"])
            if event is None or event["event_type"] in {"dream", "rehearsal"}:
                continue
            ref = _residue_ref(
                event=event,
                field=item["field"],
                value=item["residue"].get("value"),
                category=category,
                reason=_selection_reason(category),
                base_weight=_selection_weight(category),
            )
            if ref["residue_ref_id"] not in seen:
                refs.append(ref)
                seen.add(ref["residue_ref_id"])

    for event in journal.iter_events():
        if event["id"] not in replay.ordered_recent_event_ids:
            continue
        if event["event_type"] == "reflection":
            for field, category in REFLECTION_PAYLOAD_FIELDS.items():
                values = event["payload"].get(field, [])
                if isinstance(values, str):
                    values = [values]
                for index, value in enumerate(values or []):
                    ref = _residue_ref(
                        event=event,
                        field=f"payload.{field}.{index}",
                        value=value,
                        category=category,
                        reason=f"reflection left {field} unresolved",
                        base_weight=0.92,
                    )
                    if ref["residue_ref_id"] not in seen:
                        refs.append(ref)
                        seen.add(ref["residue_ref_id"])
        if event["event_type"] == "correction":
            ref = _residue_ref(
                event=event,
                field="payload.corrected_claim",
                value=event["payload"].get("corrected_claim"),
                category="correction",
                reason="correction marks unsettled model repair material",
                base_weight=0.90,
            )
            if ref["residue_ref_id"] not in seen:
                refs.append(ref)
                seen.add(ref["residue_ref_id"])

    if retrieval_result:
        refs.extend(_retrieval_residue_refs(journal, retrieval_result, seen))
    if projection:
        refs.extend(_projection_lifecycle_refs(journal, projection, seen))

    refs = [
        ref
        for ref in refs
        if ref["material_category"] != "salience"
        or _event_has_unresolved_material(journal, ref["source_event_id"])
    ]
    return sorted(
        refs,
        key=lambda ref: (
            -float(ref["selection_weight"]),
            ref["source_event_id"],
            ref.get("residue_field") or ref.get("retrieval_path_id", ""),
        ),
    )[:limit]


def generate_dream_fragments(
    residues: list[dict[str, Any]],
    *,
    immediate_context: dict[str, Any] | None = None,
    max_fragments: int = 3,
) -> list[dict[str, Any]]:
    if len(residues) < 2:
        return []
    if not any(ref["material_category"] in UNRESOLVED_CATEGORIES for ref in residues):
        return []

    context_label = str((immediate_context or {}).get("label") or "current context")
    fragments: list[dict[str, Any]] = []
    for left, right in _paired_residues(residues):
        if len(fragments) >= max_fragments:
            break
        label = f"{_short_value(left)} <-> {_short_value(right)}"
        kind = "bridge" if {left["material_category"], right["material_category"]} & {"dormant_memory", "archived_edge"} else "association"
        useful_if = _useful_if(left, right, context_label)
        fragment = {
            "fragment_id": "dreamfrag_"
            + stable_hash(
                {
                    "label": label,
                    "kind": kind,
                    "refs": [left["residue_ref_id"], right["residue_ref_id"]],
                    "policy_version": DREAM_POLICY_VERSION,
                }
            )[:24],
            "label": label,
            "fragment_kind": kind,
            "source_residue_refs": [left["residue_ref_id"], right["residue_ref_id"]],
            "association_rationale": (
                f"{left['selection_reason']} can be rehearsed against "
                f"{right['selection_reason']}"
            ),
            "uncertainty_note": "Generated by loosened association; not evidence.",
            "useful_if": useful_if,
            "review_status": "review_pending",
            "not_factual": True,
        }
        fragments.append(fragment)
    return fragments


def append_dream_event(
    journal: JournalStore,
    *,
    residues_used: list[dict[str, Any]],
    generated_candidates: list[dict[str, Any]],
    actor: str = "meno",
    source: str = "dreaming_workflow",
    requested_scope: dict[str, Any] | None = None,
    immediate_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return journal.append_event(
        event_type="dream",
        epistemic_status="hypothesis",
        actor=actor,
        source=source,
        capture_method="dream_workflow",
        payload={
            "policy_version": DREAM_POLICY_VERSION,
            "residues_used": residues_used,
            "generated_candidates": generated_candidates,
            "uncertainty_notes": "Dream fragments are associative hypotheses, not facts.",
            "requested_scope": requested_scope or {},
        },
        context={
            "active_task": (immediate_context or {}).get("active_task", "dreaming"),
            "source_channel": (immediate_context or {}).get("source_channel", "default_mode"),
            "immediate_context": immediate_context or {},
        },
        residue={
            "salience": {
                "value": max((float(ref["selection_weight"]) for ref in residues_used), default=0.0),
                "source": "dreaming_workflow",
                "epistemic_status": "hypothesis",
            },
            "attention_target": {
                "value": "dream review",
                "source": "dreaming_workflow",
                "epistemic_status": "hypothesis",
            },
            "uncertainty": {
                "value": "associative hypothesis",
                "source": "dreaming_workflow",
                "epistemic_status": "hypothesis",
            },
            "open_tensions": {
                "value": "; ".join(fragment["label"] for fragment in generated_candidates),
                "source": "dreaming_workflow",
                "epistemic_status": "hypothesis",
            },
            "drive_refs": {
                "value": ["dreaming", "integration"],
                "source": "dreaming_workflow",
                "epistemic_status": "hypothesis",
            },
            "importance_reason": {
                "value": "candidate association needs waking review",
                "source": "dreaming_workflow",
                "epistemic_status": "hypothesis",
            },
            "affect_valence": {
                "value": "unsettled",
                "source": "dreaming_workflow",
                "epistemic_status": "hypothesis",
            },
            "expected_outcome": {
                "value": "review or discard dream fragment",
                "source": "dreaming_workflow",
                "epistemic_status": "hypothesis",
            },
        },
        privacy_scope=_merge_scopes(residues_used, "privacy_scope"),
        resource_scope=_merge_scopes(residues_used, "resource_scope"),
    )


def append_dream_review_event(
    journal: JournalStore,
    *,
    dream_event_id: str,
    fragment_id: str,
    review_decision: str,
    rationale: str,
    actor: str = "meno",
    source: str = "dream_review_workflow",
    observed_evidence_event_ids: list[str] | None = None,
    proposed_graph_updates: list[dict[str, Any]] | None = None,
    deferred_graph_updates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return journal.append_event(
        event_type="dream_review",
        epistemic_status="authored",
        actor=actor,
        source=source,
        capture_method="dream_review_workflow",
        payload={
            "dream_event_id": dream_event_id,
            "fragment_id": fragment_id,
            "review_decision": review_decision,
            "rationale": rationale,
            "observed_evidence_event_ids": observed_evidence_event_ids or [],
            "proposed_graph_updates": proposed_graph_updates or [],
            "deferred_graph_updates": deferred_graph_updates or [],
            "not_factual": True,
        },
        context={"active_task": "dream_review", "source_channel": "default_mode"},
        residue={
            field: {"value": "not_applicable", "source": "dream_review", "epistemic_status": "unknown"}
            for field in FIELD_CATEGORIES
        },
    )


def _residue_ref(
    *,
    event: dict[str, Any],
    field: str,
    value: Any,
    category: str,
    reason: str,
    base_weight: float,
) -> dict[str, Any]:
    ref_id = "dreamres_" + stable_hash(
        {
            "event_id": event["id"],
            "event_hash": event["content_hash"],
            "field": field,
            "value": value,
            "category": category,
        }
    )[:24]
    return {
        "residue_ref_id": ref_id,
        "source_event_id": event["id"],
        "source_event_hash": event["content_hash"],
        "source_event_type": event["event_type"],
        "source_epistemic_status": event["epistemic_status"],
        "residue_field": field,
        "scope_decision": {"decision": "included", "reason": "requested scope permits source"},
        "selection_reason": reason,
        "selection_weight": round(base_weight, 3),
        "material_category": category,
        "value": value,
        "privacy_scope": event["privacy_scope"],
        "resource_scope": event["resource_scope"],
    }


def _retrieval_residue_refs(
    journal: JournalStore,
    retrieval_result: dict[str, Any],
    seen: set[str],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for field, category in (
        ("omitted_candidates", "omitted_candidate"),
        ("ghost_signals", "ghost_signal"),
    ):
        for index, item in enumerate(retrieval_result.get(field, [])):
            source = _event_from_retrieval_item(journal, item)
            if source is None:
                continue
            ref = _residue_ref(
                event=source,
                field=f"retrieval.{field}.{index}",
                value=item.get("candidate_id") or item.get("ghost_id") or item.get("reason"),
                category=category,
                reason=f"retrieval produced {field} residue",
                base_weight=0.86,
            )
            ref["retrieval_path_id"] = item.get("ghost_id") or item.get("candidate_id")
            if ref["residue_ref_id"] not in seen:
                refs.append(ref)
                seen.add(ref["residue_ref_id"])
    return refs


def _projection_lifecycle_refs(
    journal: JournalStore,
    projection: ProjectionStore,
    seen: set[str],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for lifecycle in projection.candidate_lifecycle():
        if lifecycle["lifecycle_state"] not in {"dormant", "rediscovered"}:
            continue
        source = _first_event_from_candidate(journal, projection, lifecycle["candidate_id"])
        if source is None:
            continue
        ref = _residue_ref(
            event=source,
            field=f"candidate_lifecycle.{lifecycle['candidate_id']}",
            value=lifecycle["candidate_id"],
            category="dormant_memory",
            reason="dormant memory can re-enter association without becoming fact",
            base_weight=0.88,
        )
        if ref["residue_ref_id"] not in seen:
            refs.append(ref)
            seen.add(ref["residue_ref_id"])
    for lifecycle in projection.edge_lifecycle():
        if lifecycle["lifecycle_state"] != "archived":
            continue
        source = _first_event_from_edge(journal, projection, lifecycle["edge_id"])
        if source is None:
            continue
        ref = _residue_ref(
            event=source,
            field=f"edge_lifecycle.{lifecycle['edge_id']}",
            value=lifecycle["edge_id"],
            category="archived_edge",
            reason="archived association can shape a bridge hypothesis",
            base_weight=0.87,
        )
        if ref["residue_ref_id"] not in seen:
            refs.append(ref)
            seen.add(ref["residue_ref_id"])
    return refs


def _first_event_from_candidate(
    journal: JournalStore,
    projection: ProjectionStore,
    candidate_id: str,
) -> dict[str, Any] | None:
    candidate = projection._get_candidate_by_id(candidate_id)  # noqa: SLF001 - local workflow reads projection state
    if not candidate:
        return None
    for ref in candidate["source_refs"]:
        event = journal.get_event(ref.get("event_id", ""))
        if event is not None:
            return event
    return None


def _first_event_from_edge(
    journal: JournalStore,
    projection: ProjectionStore,
    edge_id: str,
) -> dict[str, Any] | None:
    edge = next((item for item in projection.edges() if item["id"] == edge_id), None)
    if edge is None:
        return None
    for ref in edge["source_refs"]:
        event = journal.get_event(ref.get("event_id", ""))
        if event is not None:
            return event
    return None


def _event_from_retrieval_item(
    journal: JournalStore,
    item: dict[str, Any],
) -> dict[str, Any] | None:
    for ref in item.get("source_refs", []):
        event = journal.get_event(ref.get("event_id", ""))
        if event is not None:
            return event
    return None


def _event_has_unresolved_material(journal: JournalStore, event_id: str) -> bool:
    event = journal.get_event(event_id)
    if event is None:
        return False
    if event["event_type"] in {"reflection", "correction"}:
        return True
    for field in ("open_tensions", "uncertainty"):
        residue = event["residue"].get(field, {})
        if residue.get("value") not in {None, "unknown", "not_applicable", ""}:
            return True
    return False


def _paired_residues(residues: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs = []
    for left_index, left in enumerate(residues):
        for right in residues[left_index + 1 :]:
            if left["residue_ref_id"] == right["residue_ref_id"]:
                continue
            if left["source_event_id"] == right["source_event_id"] and left["material_category"] == right["material_category"]:
                continue
            if left["material_category"] not in UNRESOLVED_CATEGORIES and right["material_category"] not in UNRESOLVED_CATEGORIES:
                continue
            pairs.append((left, right))
    return pairs


def _short_value(ref: dict[str, Any]) -> str:
    value = ref.get("value")
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(item) for item in value)
    label = " ".join(str(value).split())
    return label[:64] or ref["material_category"]


def _selection_reason(category: str) -> str:
    if category in UNRESOLVED_CATEGORIES:
        return f"{category} remains unresolved"
    return f"{category} is eligible only as context for unresolved residue"


def _selection_weight(category: str) -> float:
    if category in {"open_tension", "uncertainty", "reflection_question"}:
        return 0.95
    if category in UNRESOLVED_CATEGORIES:
        return 0.88
    return 0.62


def _useful_if(left: dict[str, Any], right: dict[str, Any], context_label: str) -> str:
    categories = {left["material_category"], right["material_category"]}
    if categories & {"dormant_memory", "archived_edge"}:
        return f"Useful if {context_label} needs a rediscovery bridge without factual promotion."
    if categories & {"correction", "conflict", "rejected_interpretation"}:
        return f"Useful if {context_label} needs a dry check against unsettled correction/conflict material."
    if categories & {"open_tension", "uncertainty", "reflection_question", "deferred_graph_update"}:
        return f"Useful if {context_label} is still blocked by an unresolved question or tension."
    return f"Useful only if later waking review finds a concrete unresolved role in {context_label}."


def _merge_scopes(residues: list[dict[str, Any]], field: str) -> dict[str, Any]:
    if field == "privacy_scope":
        exposure_rank = {"public": 0, "team": 1, "local-only": 2, "internal-only": 3}
        scopes = [ref.get(field, {}) for ref in residues]
        exposure = max((scope.get("exposure", "local-only") for scope in scopes), key=lambda value: exposure_rank.get(value, 2), default="local-only")
        return {
            "retention": "local",
            "exposure": exposure,
            "export_allowed": all(scope.get("export_allowed", False) for scope in scopes),
        }
    scopes = [ref.get(field, {}) for ref in residues]
    return {
        "external_contact": all(scope.get("external_contact", False) for scope in scopes),
        "network_access": all(scope.get("network_access", False) for scope in scopes),
        "autonomous_spend": all(scope.get("autonomous_spend", False) for scope in scopes),
        "compute_escalation": all(scope.get("compute_escalation", False) for scope in scopes),
    }
