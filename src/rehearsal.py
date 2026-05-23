"""Phase 7 deterministic rehearsal workflow.

Rehearsal is a dry-run over evidence-cited action targets. It records
simulation, predictions, and provisional procedure drafts without executing
external action or creating accepted skills.
"""

from __future__ import annotations

from typing import Any

from journal import JournalStore
from memory_projection import stable_hash


REHEARSAL_POLICY_VERSION = 1

TARGET_CATEGORIES = {
    "failed_outcome",
    "repeated_workflow",
    "correction",
    "fragile_commitment",
    "reflection_deferred_action",
}

PREDICTION_RESULTS = {
    "confirmed",
    "falsified",
    "partially_matched",
    "inconclusive",
}


class RehearsalError(Exception):
    """Base rehearsal exception."""


def run_rehearsal_cycle(
    journal: JournalStore,
    *,
    requested_scope: dict[str, Any] | None = None,
    immediate_context: dict[str, Any] | None = None,
    actor: str = "meno",
    source: str = "rehearsal_workflow",
) -> dict[str, Any]:
    target_refs = select_rehearsal_targets(
        journal,
        requested_scope=requested_scope,
    )
    if not target_refs:
        return {
            "rehearsal_event": None,
            "target_refs": [],
            "no_action_reason": "no eligible rehearsal target",
        }
    payload = build_rehearsal_payload(
        target_refs=target_refs[:2],
        immediate_context=immediate_context,
    )
    event = append_rehearsal_event(
        journal,
        payload=payload,
        actor=actor,
        source=source,
        immediate_context=immediate_context,
    )
    return {
        "rehearsal_event": event,
        "target_refs": target_refs[:2],
        "no_action_reason": None,
    }


def select_rehearsal_targets(
    journal: JournalStore,
    *,
    requested_scope: dict[str, Any] | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    warnings = journal.verify_integrity()
    if warnings:
        raise RehearsalError(f"journal integrity warnings block rehearsal: {warnings}")
    replay = journal.replay_context(limit=80, requested_scope=requested_scope)
    blocking = [
        warning
        for warning in replay.integrity_warnings
        if warning.get("kind") != "scope_excluded"
    ]
    if blocking:
        raise RehearsalError(f"journal replay warnings block rehearsal: {blocking}")

    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in journal.iter_events():
        if event["id"] not in replay.ordered_recent_event_ids:
            continue
        candidates = _event_targets(event)
        for category, selector, value, reason, weight in candidates:
            ref = _target_ref(
                event=event,
                target_field=selector,
                value=value,
                category=category,
                reason=reason,
                weight=weight,
            )
            if ref["target_ref_id"] in seen:
                continue
            refs.append(ref)
            seen.add(ref["target_ref_id"])

    return sorted(
        refs,
        key=lambda ref: (
            -float(ref["selection_weight"]),
            ref["source_event_id"],
            ref["target_field"],
        ),
    )[:limit]


def build_rehearsal_payload(
    *,
    target_refs: list[dict[str, Any]],
    immediate_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not target_refs:
        raise RehearsalError("rehearsal requires target refs")
    primary = target_refs[0]
    context_label = str((immediate_context or {}).get("label") or primary.get("value") or "current task")
    variant_id = "variant_" + stable_hash(
        {
            "target_refs": [ref["target_ref_id"] for ref in target_refs],
            "context": context_label,
            "policy_version": REHEARSAL_POLICY_VERSION,
        }
    )[:16]
    failure_prediction_id = "pred_" + stable_hash(
        {"variant": variant_id, "kind": "failure", "target": primary["target_ref_id"]}
    )[:16]
    success_prediction_id = "pred_" + stable_hash(
        {"variant": variant_id, "kind": "success", "target": primary["target_ref_id"]}
    )[:16]
    procedure_id = "proc_" + stable_hash({"variant": variant_id, "target": primary["target_ref_id"]})[:16]
    return {
        "policy_version": REHEARSAL_POLICY_VERSION,
        "target_refs": target_refs,
        "problem_context": context_label,
        "current_or_failed_approach": _short_value(primary),
        "strategy_variants": [
            {
                "variant_id": variant_id,
                "label": f"evidence-first dry run for {context_label}",
                "rationale": f"Responds to {primary['selection_reason']}",
                "expected_advantage": "Expose failure before real execution.",
                "preconditions": ["journal evidence remains valid", "no external side effects"],
                "resource_contact_requirements": {
                    "external_contact": False,
                    "network_access": False,
                    "autonomous_spend": False,
                    "compute_escalation": False,
                },
                "risks": ["simulation may omit runtime constraints"],
            }
        ],
        "selected_variant_id": variant_id,
        "improvement_hypothesis": "A cited dry-run can identify failure conditions before action.",
        "assumptions": [
            {
                "assumption_id": "assump_" + stable_hash(primary["target_ref_id"])[:16],
                "text": "The cited source is a valid rehearsal target.",
                "source_target_refs": [primary["target_ref_id"]],
                "uncertainty_note": "Assumption remains simulation-bound.",
            }
        ],
        "simulated_trace": [
            {
                "step_id": "step_" + stable_hash({"variant": variant_id, "step": 1})[:16],
                "variant_id": variant_id,
                "simulated_action": "Review cited failure or constraint before choosing action.",
                "expected_local_state": "target risk is explicit",
                "possible_failure_point": "source evidence is too generic",
                "assumption_refs": ["assump_" + stable_hash(primary["target_ref_id"])[:16]],
                "simulated": True,
            },
            {
                "step_id": "step_" + stable_hash({"variant": variant_id, "step": 2})[:16],
                "variant_id": variant_id,
                "simulated_action": "Select the smallest action that addresses the cited risk.",
                "expected_local_state": "procedure candidate remains provisional",
                "possible_failure_point": "candidate action exceeds resource scope",
                "assumption_refs": ["assump_" + stable_hash(primary["target_ref_id"])[:16]],
                "simulated": True,
            },
        ],
        "predicted_observations": [
            {
                "prediction_id": success_prediction_id,
                "variant_id": variant_id,
                "expected_signal": "later observed outcome matches the validation criterion",
                "success_condition": "observed execution avoids the cited failure",
                "failure_condition": "observed execution repeats the cited failure",
                "matching_rule": "outcome prediction_results must cite this id",
                "uncertainty_note": "Prediction cannot validate itself.",
            }
        ],
        "predicted_failure_modes": [
            {
                "prediction_id": failure_prediction_id,
                "variant_id": variant_id,
                "expected_signal": "generic action repeats prior risk",
                "success_condition": "failure is avoided or explicitly handled",
                "failure_condition": "later observed outcome reports the same risk",
                "matching_rule": "outcome prediction_results must cite this id",
                "uncertainty_note": "Failure mode is simulated, not observed.",
            }
        ],
        "validation_criteria": [
            {
                "criterion_id": "valid_" + stable_hash({"variant": variant_id, "criterion": 1})[:16],
                "prediction_ids": [success_prediction_id],
                "required_observation": "later observed execution outcome",
            }
        ],
        "falsification_criteria": [
            {
                "criterion_id": "false_" + stable_hash({"variant": variant_id, "criterion": 1})[:16],
                "prediction_ids": [failure_prediction_id],
                "falsifying_observation": "later outcome repeats the predicted failure",
            }
        ],
        "candidate_procedure_updates": [
            {
                "procedure_id": procedure_id,
                "source_variant_id": variant_id,
                "proposed_delta": "Check cited failure evidence before execution.",
                "predicted_benefit": "Reduce repeat failure.",
                "required_validation": "confirmed observed outcome",
                "review_status": "provisional",
                "not_accepted": True,
            }
        ],
        "resource_scope_decision": {
            "decision": "simulation_only",
            "reason": "rehearsal cannot execute external action",
        },
        "privacy_scope_decision": {
            "decision": "included",
            "reason": "requested scope permits selected targets",
        },
        "review_status": "review_pending",
        "not_executed": True,
    }


def append_rehearsal_event(
    journal: JournalStore,
    *,
    payload: dict[str, Any],
    actor: str = "meno",
    source: str = "rehearsal_workflow",
    immediate_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return journal.append_event(
        event_type="rehearsal",
        epistemic_status="simulation",
        actor=actor,
        source=source,
        capture_method="rehearsal_workflow",
        payload=payload,
        context={
            "active_task": (immediate_context or {}).get("active_task", "rehearsal"),
            "source_channel": (immediate_context or {}).get("source_channel", "default_mode"),
            "immediate_context": immediate_context or {},
        },
        residue={
            "salience": {"value": 0.75, "source": "rehearsal_workflow", "epistemic_status": "simulation"},
            "attention_target": {"value": payload["problem_context"], "source": "rehearsal_workflow", "epistemic_status": "simulation"},
            "uncertainty": {"value": "simulation requires observed validation", "source": "rehearsal_workflow", "epistemic_status": "simulation"},
            "open_tensions": {"value": payload["current_or_failed_approach"], "source": "rehearsal_workflow", "epistemic_status": "simulation"},
            "drive_refs": {"value": ["rehearsal", "risk-reduction"], "source": "rehearsal_workflow", "epistemic_status": "simulation"},
            "importance_reason": {"value": payload["improvement_hypothesis"], "source": "rehearsal_workflow", "epistemic_status": "simulation"},
            "affect_valence": {"value": "cautious", "source": "rehearsal_workflow", "epistemic_status": "simulation"},
            "expected_outcome": {"value": "later observed validation or falsification", "source": "rehearsal_workflow", "epistemic_status": "simulation"},
        },
        privacy_scope=_merge_privacy(payload["target_refs"]),
        resource_scope=_merge_resource(payload["target_refs"]),
    )


def append_rehearsal_outcome(
    journal: JournalStore,
    *,
    rehearsal_event_id: str,
    observed_result: str,
    prediction_results: list[dict[str, Any]],
    actor: str = "tool",
    source: str = "rehearsal_outcome",
    match: bool | str = True,
) -> dict[str, Any]:
    return journal.append_event(
        event_type="outcome",
        epistemic_status="observed",
        actor=actor,
        source=source,
        capture_method="manual",
        payload={
            "expected_outcome_link": rehearsal_event_id,
            "observed_result": observed_result,
            "match": match,
            "prediction_results": prediction_results,
        },
        context={"active_task": "rehearsal_outcome", "source_channel": "test"},
        residue={
            "salience": {"value": 0.8, "source": "rehearsal_outcome", "epistemic_status": "observed"},
            "attention_target": {"value": "rehearsal outcome", "source": "rehearsal_outcome", "epistemic_status": "observed"},
            "uncertainty": {"value": 0.1, "source": "rehearsal_outcome", "epistemic_status": "observed"},
            "open_tensions": {"value": observed_result, "source": "rehearsal_outcome", "epistemic_status": "observed"},
            "drive_refs": {"value": ["validation"], "source": "rehearsal_outcome", "epistemic_status": "observed"},
            "importance_reason": {"value": "real outcome checks rehearsal", "source": "rehearsal_outcome", "epistemic_status": "observed"},
            "affect_valence": {"value": "neutral", "source": "rehearsal_outcome", "epistemic_status": "observed"},
            "expected_outcome": {"value": "projection updates outcome relation", "source": "rehearsal_outcome", "epistemic_status": "observed"},
        },
        links=[
            {
                "type": "derived_from",
                "target_event_id": rehearsal_event_id,
                "rationale": "observed outcome checks rehearsal prediction",
            }
        ],
    )


def _event_targets(event: dict[str, Any]) -> list[tuple[str, str, Any, str, float]]:
    if event["event_type"] == "outcome" and event["payload"].get("match") is False:
        return [
            (
                "failed_outcome",
                "payload.observed_result",
                event["payload"].get("observed_result"),
                "observed outcome did not match expectation",
                0.98,
            )
        ]
    if event["event_type"] == "correction":
        return [
            (
                "correction",
                "payload.corrected_claim",
                event["payload"].get("corrected_claim"),
                "correction implies future approach should change",
                0.94,
            )
        ]
    if event["event_type"] == "decision" and not event["payload"].get("resolved", False):
        return [
            (
                "fragile_commitment",
                "payload.selected_option",
                event["payload"].get("selected_option"),
                "decision remains fragile or unresolved",
                0.88,
            )
        ]
    if event["event_type"] == "reflection":
        updates = event["payload"].get("deferred_graph_updates", [])
        if updates:
            return [
                (
                    "reflection_deferred_action",
                    "payload.deferred_graph_updates.0",
                    updates[0],
                    "reflection deferred a future action",
                    0.90,
                )
            ]
    if event["event_type"] == "retrieval_use_trace":
        return [
            (
                "repeated_workflow",
                "payload.retrieval_result_hash",
                event["payload"].get("retrieval_result_hash"),
                "retrieval use trace can shape repeated workflow rehearsal",
                0.82,
            )
        ]
    return []


def _target_ref(
    *,
    event: dict[str, Any],
    target_field: str,
    value: Any,
    category: str,
    reason: str,
    weight: float,
) -> dict[str, Any]:
    if category not in TARGET_CATEGORIES:
        raise RehearsalError(f"invalid target category: {category}")
    return {
        "target_ref_id": "rehtarget_" + stable_hash(
            {
                "event_id": event["id"],
                "event_hash": event["content_hash"],
                "field": target_field,
                "category": category,
                "value": value,
            }
        )[:24],
        "source_event_id": event["id"],
        "source_event_hash": event["content_hash"],
        "source_event_type": event["event_type"],
        "source_epistemic_status": event["epistemic_status"],
        "target_field": target_field,
        "scope_decision": {"decision": "included", "reason": "requested scope permits source"},
        "target_category": category,
        "selection_reason": reason,
        "selection_weight": round(weight, 3),
        "value": value,
        "privacy_scope": event["privacy_scope"],
        "resource_scope": event["resource_scope"],
    }


def _short_value(ref: dict[str, Any]) -> str:
    value = ref.get("value")
    if isinstance(value, dict):
        value = value.get("reason") or value.get("summary") or value
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(item) for item in value)
    return " ".join(str(value).split())[:80] or ref["target_category"]


def _merge_privacy(target_refs: list[dict[str, Any]]) -> dict[str, Any]:
    exposure_rank = {"public": 0, "team": 1, "local-only": 2, "internal-only": 3}
    scopes = [ref.get("privacy_scope", {}) for ref in target_refs]
    exposure = max(
        (scope.get("exposure", "local-only") for scope in scopes),
        key=lambda value: exposure_rank.get(value, 2),
        default="local-only",
    )
    return {
        "retention": "local",
        "exposure": exposure,
        "export_allowed": all(scope.get("export_allowed", False) for scope in scopes),
    }


def _merge_resource(target_refs: list[dict[str, Any]]) -> dict[str, Any]:
    scopes = [ref.get("resource_scope", {}) for ref in target_refs]
    return {
        "external_contact": all(scope.get("external_contact", False) for scope in scopes),
        "network_access": all(scope.get("network_access", False) for scope in scopes),
        "autonomous_spend": all(scope.get("autonomous_spend", False) for scope in scopes),
        "compute_escalation": all(scope.get("compute_escalation", False) for scope in scopes),
    }
