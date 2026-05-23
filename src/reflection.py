"""Phase 4 reflection workflow.

Reflection generation is deliberately out of scope for this module. Phase 4
validates caller-supplied authored reflection artifacts, records them as journal
events, and provides deterministic gates for formulaic or history-blind output.
"""

from __future__ import annotations

import hashlib
from typing import Any

from journal import GraphProposal, JournalStore, canonical_json


CLAIM_TYPES = {
    "summary_observation",
    "interpretive_claim",
    "tension",
    "self_correction",
    "preference_hypothesis",
    "drive_update_proposal",
    "deferred_question",
    "rejected_interpretation",
}

GENERIC_PHRASES = {
    "this shows the importance of continuity",
    "i notice a tension",
    "this suggests a need for balance",
    "it is important to balance",
    "this highlights the importance",
}

REQUIRED_PAYLOAD_KEYS = {
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
}


class ReflectionValidationError(ValueError):
    """Raised when a reflection artifact violates the Phase 4 contract."""


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def retrieval_result_hash(retrieval_result: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in retrieval_result.items()
        if key not in {"query_id", "timestamp"}
    }
    return stable_hash(stable)


def _retrieval_path_index(retrieval_result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    paths: dict[str, dict[str, Any]] = {}
    for candidate in retrieval_result.get("activated_candidates", []):
        for index, path in enumerate(candidate.get("activation_paths", [])):
            path_id = _path_id(candidate["candidate_id"], path)
            paths[path_id] = {
                "path_id": path_id,
                "candidate_id": candidate["candidate_id"],
                "source_refs": path.get("evidence_refs") or candidate.get("source_refs", []),
                "steps": path.get("steps", []),
                "scope_decision": candidate.get("scope_decision", {}),
                "result_semantics": candidate.get("result_semantics", {}),
                "redacted": False,
                "omitted": False,
                "ghost": False,
            }
    for ghost in retrieval_result.get("ghost_signals", []):
        path_id = ghost["ghost_id"]
        paths[path_id] = {
            "path_id": path_id,
            "candidate_id": None,
            "source_refs": [],
            "steps": ghost.get("suppressed_path_shape", []),
            "scope_decision": ghost.get("scope_decision", {}),
            "result_semantics": {"ordinary_recall": False},
            "redacted": True,
            "omitted": False,
            "ghost": True,
        }
    for omitted in retrieval_result.get("omitted_candidates", []):
        path_id = "omitted_" + str(omitted["candidate_id"])
        paths[path_id] = {
            "path_id": path_id,
            "candidate_id": omitted["candidate_id"],
            "source_refs": [],
            "steps": [],
            "scope_decision": {},
            "result_semantics": {"ordinary_recall": False},
            "redacted": False,
            "omitted": True,
            "ghost": False,
        }
    return paths


def _path_id(candidate_id: str, path: dict[str, Any]) -> str:
    return "path_" + stable_hash(
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


def cite_retrieval_path(retrieval_result: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    paths = [
        data
        for data in _retrieval_path_index(retrieval_result).values()
        if data["candidate_id"] == candidate_id and not data["ghost"] and not data["omitted"]
    ]
    if not paths:
        raise ReflectionValidationError(f"no retrieval path for candidate: {candidate_id}")
    return dict(paths[0])


def validate_reflection_payload(
    payload: dict[str, Any],
    *,
    retrieval_result: dict[str, Any] | None = None,
) -> None:
    if not isinstance(payload, dict):
        raise ReflectionValidationError("reflection payload must be an object")
    missing = sorted(REQUIRED_PAYLOAD_KEYS - payload.keys())
    if missing:
        raise ReflectionValidationError(f"reflection payload missing keys: {missing}")
    if not payload["cited_source_event_ids"]:
        raise ReflectionValidationError("reflection requires cited source events")
    if not payload["cited_retrieval_paths"]:
        raise ReflectionValidationError("reflection requires cited retrieval paths")
    if not payload["interpretive_claims"]:
        raise ReflectionValidationError("reflection requires interpretive claims")
    if not payload["changed_stance"] and not payload["future_attention"]:
        raise ReflectionValidationError("reflection requires changed stance or future attention")

    if retrieval_result is not None and payload["retrieval_result_hash"] != retrieval_result_hash(retrieval_result):
        raise ReflectionValidationError("retrieval result hash does not match")

    actual_paths = _retrieval_path_index(retrieval_result) if retrieval_result is not None else {}
    cited_path_ids = set()
    for path in payload["cited_retrieval_paths"]:
        path_id = path.get("path_id")
        if not path_id:
            raise ReflectionValidationError("retrieval path citation requires path_id")
        cited_path_ids.add(path_id)
        if not path.get("candidate_id"):
            raise ReflectionValidationError("retrieval path citation requires candidate_id")
        if not path.get("source_refs"):
            raise ReflectionValidationError("retrieval path citation requires source refs")
        if not path.get("scope_decision"):
            raise ReflectionValidationError("retrieval path citation requires scope decision")
        if not path.get("activation_paths") and not path.get("steps"):
            raise ReflectionValidationError("retrieval path citation requires path steps")
        if path.get("redacted") and path.get("label"):
            raise ReflectionValidationError("redacted retrieval path leaks label")
        if retrieval_result is not None:
            actual = actual_paths.get(path_id)
            if actual is None:
                raise ReflectionValidationError(f"unknown retrieval path citation: {path_id}")
            if actual["candidate_id"] != path["candidate_id"]:
                raise ReflectionValidationError("retrieval path candidate mismatch")
            actual_event_ids = {ref["event_id"] for ref in actual["source_refs"]}
            cited_event_ids = {ref["event_id"] for ref in path["source_refs"]}
            if not cited_event_ids or not cited_event_ids.issubset(actual_event_ids):
                raise ReflectionValidationError("retrieval path source refs do not match result")

    _validate_no_redaction_leakage(payload)

    for claim in payload["interpretive_claims"]:
        claim_type = claim.get("type")
        if claim_type not in CLAIM_TYPES:
            raise ReflectionValidationError(f"invalid reflection claim type: {claim_type}")
        if not claim.get("claim"):
            raise ReflectionValidationError("reflection claim text is required")
        if claim_type != "deferred_question" and not claim.get("cites"):
            raise ReflectionValidationError("substantive reflection claims require citations")
        if any(cite not in cited_path_ids for cite in claim.get("cites", [])):
            raise ReflectionValidationError("claim cites unknown retrieval path")
        if claim.get("epistemic_status") in {"observed", "accepted"}:
            raise ReflectionValidationError("reflection claims cannot be marked as observed or accepted")
        cited_paths = [path for path in payload["cited_retrieval_paths"] if path["path_id"] in claim.get("cites", [])]
        if _claim_uses_restricted_support(claim, cited_paths):
            raise ReflectionValidationError("restricted retrieval material cannot support ordinary claim")

    for proposal in payload["proposed_graph_updates"]:
        raise ReflectionValidationError("reflection payload may contain proposal drafts only after journal proposal emission")


def _validate_no_redaction_leakage(payload: dict[str, Any]) -> None:
    blocked_terms = set()
    for path in payload["cited_retrieval_paths"]:
        if not path.get("redacted"):
            continue
        blocked_terms.update(str(item).lower() for item in path.get("redacted_terms", []) if item)
        blocked_terms.update(str(ref.get("source_text", "")).lower() for ref in path.get("source_refs", []) if ref.get("source_text"))
    if not blocked_terms:
        return
    text = canonical_json(
        {
            "interpretive_claims": payload.get("interpretive_claims", []),
            "open_questions": payload.get("open_questions", []),
            "uncertainty_notes": payload.get("uncertainty_notes", []),
            "possible_self_deception": payload.get("possible_self_deception", []),
            "rejected_interpretations": payload.get("rejected_interpretations", []),
            "changed_stance": payload.get("changed_stance"),
            "future_attention": payload.get("future_attention", []),
            "deferred_graph_updates": payload.get("deferred_graph_updates", []),
        }
    ).lower()
    leaked = sorted(term for term in blocked_terms if term and term in text)
    if leaked:
        raise ReflectionValidationError("redacted retrieval material leaked into reflection")


def _claim_uses_restricted_support(claim: dict[str, Any], cited_paths: list[dict[str, Any]]) -> bool:
    claim_type = claim.get("type")
    for path in cited_paths:
        if path.get("redacted") or path.get("ghost") or path.get("omitted"):
            return claim_type not in {"deferred_question", "rejected_interpretation", "tension"}
        semantics = path.get("result_semantics", {})
        if semantics.get("hypothesis_material") and claim_type not in {"deferred_question", "rejected_interpretation", "tension"}:
            return True
        if semantics.get("simulation_material") and claim_type not in {"deferred_question", "rejected_interpretation", "tension"}:
            return True
        if semantics.get("conflict_material") and claim_type not in {"deferred_question", "rejected_interpretation", "tension", "self_correction"}:
            return True
        status = path.get("relation_status")
        if status in {"invalidated", "superseded"} and claim_type not in {"deferred_question", "rejected_interpretation", "tension"}:
            return True
    return False


def formulaic_reflection_report(
    payload: dict[str, Any],
    *,
    retrieval_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    try:
        validate_reflection_payload(payload, retrieval_result=retrieval_result)
    except ReflectionValidationError as exc:
        reasons.append(str(exc))
    text = canonical_json(payload).lower()
    for phrase in sorted(GENERIC_PHRASES):
        if phrase in text:
            reasons.append(f"generic phrase: {phrase}")
    if not payload.get("rejected_interpretations"):
        reasons.append("no rejected interpretations")
    if not payload.get("uncertainty_notes"):
        reasons.append("no uncertainty notes")
    if not payload.get("possible_self_deception"):
        reasons.append("no possible self-deception note")
    if not payload.get("proposed_graph_updates") and not payload.get("deferred_graph_updates"):
        reasons.append("no proposal or deferral disposition")
    return {
        "formulaic": bool(reasons),
        "reasons": reasons,
        "score": min(1.0, len(reasons) / 5),
    }


def history_influence_report(history_payload: dict[str, Any], baseline_payload: dict[str, Any]) -> dict[str, Any]:
    history_formulaic = formulaic_reflection_report(history_payload)
    history_candidates = {
        path.get("candidate_id")
        for path in history_payload.get("cited_retrieval_paths", [])
        if path.get("candidate_id")
    }
    baseline_candidates = {
        path.get("candidate_id")
        for path in baseline_payload.get("cited_retrieval_paths", [])
        if path.get("candidate_id")
    }
    history_dispositions = {
        canonical_json(item)
        for item in (
            history_payload.get("future_attention", [])
            + history_payload.get("proposed_graph_updates", [])
            + history_payload.get("deferred_graph_updates", [])
            + history_payload.get("rejected_interpretations", [])
        )
    }
    baseline_dispositions = {
        canonical_json(item)
        for item in (
            baseline_payload.get("future_attention", [])
            + baseline_payload.get("proposed_graph_updates", [])
            + baseline_payload.get("deferred_graph_updates", [])
            + baseline_payload.get("rejected_interpretations", [])
        )
    }
    return {
        "history_specific_candidates": sorted(history_candidates - baseline_candidates),
        "history_specific_dispositions": sorted(history_dispositions - baseline_dispositions),
        "passes": bool(history_candidates - baseline_candidates)
        and bool(history_dispositions - baseline_dispositions)
        and not history_formulaic["formulaic"]
        and any(
            claim.get("type") in {"tension", "self_correction", "rejected_interpretation"}
            for claim in history_payload.get("interpretive_claims", [])
        ),
    }


def append_reflection_event(
    journal: JournalStore,
    *,
    payload: dict[str, Any],
    actor: str,
    source: str,
    context: dict[str, Any],
    residue: dict[str, Any],
    retrieval_result: dict[str, Any],
    capture_method: str = "reflection_workflow",
) -> dict[str, Any]:
    validate_reflection_payload(payload, retrieval_result=retrieval_result)
    formulaic = formulaic_reflection_report(payload, retrieval_result=retrieval_result)
    if formulaic["formulaic"]:
        raise ReflectionValidationError(f"formulaic reflection rejected: {formulaic['reasons']}")
    event_payload = dict(payload)
    event_payload["retrieval_result_snapshot"] = retrieval_result
    links = [
        {
            "type": "derived_from",
            "target_event_id": event_id,
            "rationale": "reflection cites source event",
        }
        for event_id in payload["cited_source_event_ids"]
    ]
    return journal.append_event(
        event_type="reflection",
        epistemic_status="authored",
        actor=actor,
        source=source,
        capture_method=capture_method,
        payload=event_payload,
        context=context,
        residue=residue,
        links=links,
    )


def append_reflection_proposal_events(
    journal: JournalStore,
    *,
    reflection_event: dict[str, Any],
    proposal_drafts: list[dict[str, Any]],
    actor: str,
    source: str,
    context: dict[str, Any],
    residue: dict[str, Any],
    capture_method: str = "reflection_workflow",
) -> list[dict[str, Any]]:
    events = []
    for draft in proposal_drafts:
        proposal = GraphProposal(
            proposed_operation=draft["proposed_operation"],
            proposed_target_kind=draft["proposed_target_kind"],
            source_event_ids=list(draft["source_event_ids"]),
            intended_status=draft["intended_status"],
            rationale=draft["rationale"],
            requested_scope=draft.get("requested_scope"),
        )
        journal.validate_graph_proposal(proposal)
        links = [
            {
                "type": "proposes_from",
                "target_event_id": event_id,
                "rationale": "reflection proposal cites source evidence",
            }
            for event_id in proposal.source_event_ids
        ]
        links.append(
            {
                "type": "derived_from",
                "target_event_id": reflection_event["id"],
                "rationale": "proposal was authored by reflection workflow",
            }
        )
        events.append(
            journal.append_event(
                event_type="graph_update_proposal",
                epistemic_status="inferred",
                actor=actor,
                source=source,
                capture_method=capture_method,
                payload={
                    "proposed_operation": proposal.proposed_operation,
                    "proposed_target_kind": proposal.proposed_target_kind,
                    "source_event_ids": proposal.source_event_ids,
                    "intended_status": proposal.intended_status,
                    "rationale": proposal.rationale,
                    "reflection_event_id": reflection_event["id"],
                },
                context=context,
                residue=residue,
                links=links,
                privacy_scope=draft.get("privacy_scope"),
                resource_scope=draft.get("resource_scope"),
            )
        )
    return events
