"""Phase 8 drives and attention workflow.

This module turns journaled residue into evidence-cited drive pressure and a
bounded internal attention allocation. It does not execute external actions.
"""

from __future__ import annotations

from typing import Any

from journal import JournalStore
from memory_projection import stable_hash


ATTENTION_POLICY_VERSION = 1

DRIVE_KINDS = {
    "curiosity",
    "deferred_impulse",
    "concern",
    "chosen_commitment",
    "inferred_commitment_candidate",
    "preference_pressure",
    "boredom",
    "coherence_pressure",
    "rehearsal_pressure",
}

DRIVE_DYNAMICS = {
    "curiosity": {
        "rule": "decays_when_unattended",
        "decay": -0.12,
        "build": 0.0,
        "saturation": 1.0,
        "cooldown": "release when stale or answered",
        "inhibition": "privacy/resource governors may internalize or block",
    },
    "deferred_impulse": {
        "rule": "builds_while_deferred",
        "decay": 0.0,
        "build": 0.15,
        "saturation": 1.0,
        "cooldown": "release through decision, action, or abandonment",
        "inhibition": "external effects require authorization",
    },
    "concern": {
        "rule": "inhibits_outward_action_until_addressed",
        "decay": -0.03,
        "build": 0.10,
        "saturation": 1.0,
        "cooldown": "release when risk is resolved or accepted",
        "inhibition": "blocks external initiative",
    },
    "chosen_commitment": {
        "rule": "tracks_explicit_choice_until_fulfilled_or_revoked",
        "decay": -0.02,
        "build": 0.05,
        "saturation": 1.0,
        "cooldown": "release on fulfillment, revocation, or supersession",
        "inhibition": "scope and consent constraints remain binding",
    },
    "inferred_commitment_candidate": {
        "rule": "requests_review_without_obligation",
        "decay": -0.08,
        "build": 0.02,
        "saturation": 0.7,
        "cooldown": "release if not chosen",
        "inhibition": "cannot act as obligation",
    },
    "preference_pressure": {
        "rule": "remains_provisional_until_preference_thresholds_hold",
        "decay": -0.05,
        "build": 0.04,
        "saturation": 0.8,
        "cooldown": "release when contradicted or unsupported",
        "inhibition": "cannot become accepted preference here",
    },
    "boredom": {
        "rule": "selects_neglected_eligible_material",
        "decay": -0.04,
        "build": 0.06,
        "saturation": 0.6,
        "cooldown": "release when material is attended",
        "inhibition": "cannot override governors",
    },
    "coherence_pressure": {
        "rule": "builds_from_conflict_or_unresolved_tension",
        "decay": -0.02,
        "build": 0.12,
        "saturation": 1.0,
        "cooldown": "release when contradiction is resolved",
        "inhibition": "must cite conflict/tension",
    },
    "rehearsal_pressure": {
        "rule": "tracks_unvalidated_or_falsified_simulation",
        "decay": -0.04,
        "build": 0.08,
        "saturation": 0.9,
        "cooldown": "release when observed outcome validates or falsifies the rehearsal",
        "inhibition": "simulation status remains visible",
    },
}


class AttentionError(Exception):
    """Base attention workflow exception."""


def run_attention_cycle(
    journal: JournalStore,
    *,
    requested_scope: dict[str, Any] | None = None,
    immediate_context: dict[str, Any] | None = None,
    actor: str = "meno",
    source: str = "attention_workflow",
) -> dict[str, Any]:
    drives = derive_drive_updates(
        journal,
        requested_scope=requested_scope,
        immediate_context=immediate_context,
    )
    if not drives:
        return {
            "drive_events": [],
            "allocation_event": None,
            "no_action_reason": "no eligible drive after governance",
        }
    drive_events = [
        append_drive_state_update(journal, payload=drive, actor=actor, source=source)
        for drive in drives
    ]
    allocation = build_attention_allocation(
        drive_events,
        immediate_context=immediate_context,
    )
    if not allocation["selected_attention_targets"]:
        return {
            "drive_events": drive_events,
            "allocation_event": None,
            "no_action_reason": "no eligible drive after governance",
        }
    allocation_event = append_attention_allocation(
        journal,
        payload=allocation,
        actor=actor,
        source=source,
    )
    return {
        "drive_events": drive_events,
        "allocation_event": allocation_event,
        "no_action_reason": None,
    }


def derive_drive_updates(
    journal: JournalStore,
    *,
    requested_scope: dict[str, Any] | None = None,
    immediate_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if journal.verify_integrity():
        raise AttentionError("journal integrity warnings block attention")
    replay = journal.replay_context(limit=80, requested_scope=requested_scope)
    blocking = [
        warning
        for warning in replay.integrity_warnings
        if warning.get("kind") != "scope_excluded"
    ]
    if blocking:
        raise AttentionError(f"journal replay warnings block attention: {blocking}")
    drives: list[dict[str, Any]] = []
    for event in journal.iter_events():
        if event["id"] not in replay.ordered_recent_event_ids:
            continue
        for kind, selector, value, reason, base_pressure, origin_status in _event_drive_sources(event):
            source_ref = _source_ref(
                event=event,
                selector=selector,
                value=value,
                source_category=kind,
                reason=reason,
            )
            drive = _drive_payload(
                kind=kind,
                source_refs=[source_ref],
                base_pressure=base_pressure,
                origin_status=origin_status,
                attention_claim=_attention_claim(kind, value),
                requested_scope=requested_scope or {},
                immediate_context=immediate_context or {},
            )
            drives.append(drive)
    return sorted(
        drives,
        key=lambda item: (
            -float(item["pressure_after"]),
            item["drive_kind"],
            item["drive_id"],
        ),
    )


def build_attention_allocation(
    drive_events: list[dict[str, Any]],
    *,
    immediate_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = [_drive_snapshot_item(event) for event in drive_events]
    snapshot_hash = stable_hash(snapshot)
    selected = []
    rejected = []
    for event in sorted(drive_events, key=lambda item: (-item["payload"]["pressure_after"], item["id"])):
        payload = event["payload"]
        governance = payload["governance"]
        if not governance["allowed_effects"]:
            rejected.append(
                {
                    "drive_id": payload["drive_id"],
                    "reason": "no allowed effect after governance",
                    "governor_decision": governance["decision"],
                }
            )
            continue
        action_class = _action_class(payload)
        if not selected:
            selected.append(
                {
                    "target_id": "attn_" + stable_hash(payload["drive_id"])[:16],
                    "drive_id": payload["drive_id"],
                    "action_class": action_class,
                    "allowed_effects": governance["allowed_effects"],
                    "attention_claim": payload["attention_claim"],
                    "explanation": (
                        f"{payload['drive_kind']} pressure {payload['pressure_after']} "
                        f"from pre-allocation snapshot {snapshot_hash} and "
                        f"{payload['source_refs'][0]['contribution_reason']}"
                    ),
                }
            )
        else:
            rejected.append(
                {
                    "drive_id": payload["drive_id"],
                    "reason": "lower pressure than selected drive",
                    "governor_decision": governance["decision"],
                }
            )
    permitted = selected[0]["action_class"] if selected else "no_action"
    if permitted not in {"internal_attention", "prepare_recommendation", "ask_permission"}:
        permitted = "internal_attention"
    return {
        "policy_version": ATTENTION_POLICY_VERSION,
        "allocation_id": "alloc_" + stable_hash(
            {"snapshot": snapshot_hash, "context": immediate_context or {}}
        )[:24],
        "drive_state_event_ids": [event["id"] for event in drive_events],
        "drive_snapshot_hash": snapshot_hash,
        "drive_snapshot": snapshot,
        "selected_attention_targets": selected,
        "rejected_attention_targets": rejected,
        "competing_drive_ids": [event["payload"]["drive_id"] for event in drive_events],
        "governor_decisions": [
            {
                "drive_id": event["payload"]["drive_id"],
                "decision": event["payload"]["governance"]["decision"],
                "blocked_effects": event["payload"]["governance"]["blocked_effects"],
                "blocked_effect_reasons": event["payload"]["governance"]["blocked_effect_reasons"],
            }
            for event in drive_events
        ],
        "privacy_resource_exclusions": [
            {
                "drive_id": event["payload"]["drive_id"],
                "blocked_effects": event["payload"]["governance"]["blocked_effects"],
            }
            for event in drive_events
            if event["payload"]["governance"]["blocked_effects"]
        ],
        "permitted_next_step": permitted if selected else "no_action",
        "no_external_action": True,
    }


def append_drive_state_update(
    journal: JournalStore,
    *,
    payload: dict[str, Any],
    actor: str = "meno",
    source: str = "attention_workflow",
) -> dict[str, Any]:
    return journal.append_event(
        event_type="drive_state_update",
        epistemic_status="inferred",
        actor=actor,
        source=source,
        capture_method="attention_workflow",
        payload=payload,
        context={"active_task": "attention", "source_channel": "default_mode"},
        residue=_attention_residue(payload),
        privacy_scope=payload["governance"]["privacy_scope"],
        resource_scope=payload["governance"]["resource_scope"],
    )


def append_attention_allocation(
    journal: JournalStore,
    *,
    payload: dict[str, Any],
    actor: str = "meno",
    source: str = "attention_workflow",
) -> dict[str, Any]:
    return journal.append_event(
        event_type="attention_allocation",
        epistemic_status="inferred",
        actor=actor,
        source=source,
        capture_method="attention_workflow",
        payload=payload,
        context={"active_task": "attention", "source_channel": "default_mode"},
        residue={
            "salience": {"value": 0.7, "source": "attention_workflow", "epistemic_status": "inferred"},
            "attention_target": {"value": payload["permitted_next_step"], "source": "attention_workflow", "epistemic_status": "inferred"},
            "uncertainty": {"value": "attention allocation is internal only", "source": "attention_workflow", "epistemic_status": "inferred"},
            "open_tensions": {"value": "governed attention selection", "source": "attention_workflow", "epistemic_status": "inferred"},
            "drive_refs": {"value": payload["competing_drive_ids"], "source": "attention_workflow", "epistemic_status": "inferred"},
            "importance_reason": {"value": "attention allocation cites drive state", "source": "attention_workflow", "epistemic_status": "inferred"},
            "affect_valence": {"value": "neutral", "source": "attention_workflow", "epistemic_status": "inferred"},
            "expected_outcome": {"value": "private attention or permission request", "source": "attention_workflow", "epistemic_status": "inferred"},
        },
    )


def _event_drive_sources(event: dict[str, Any]) -> list[tuple[str, str, Any, str, float, str]]:
    sources: list[tuple[str, str, Any, str, float, str]] = []
    residue = event["residue"]
    if event["event_type"] == "reflection" and event["payload"].get("future_attention"):
        sources.append(
            (
                "deferred_impulse",
                "payload.future_attention.0",
                event["payload"]["future_attention"][0],
                "reflection proposed future attention",
                0.72,
                "inferred",
            )
        )
    if event["event_type"] == "correction":
        sources.append(
            (
                "coherence_pressure",
                "payload.corrected_claim",
                event["payload"].get("corrected_claim"),
                "correction creates coherence pressure",
                0.86,
                "observed" if event["epistemic_status"] == "observed" else "inferred",
            )
        )
    if event["event_type"] == "outcome" and event["payload"].get("match") is False:
        sources.append(
            (
                "concern",
                "payload.observed_result",
                event["payload"].get("observed_result"),
                "failed outcome creates concern",
                0.90,
                "observed",
            )
        )
    if event["event_type"] == "rehearsal":
        sources.append(
            (
                "rehearsal_pressure",
                "payload.predicted_failure_modes.0.prediction_id",
                event["payload"]["predicted_failure_modes"][0]["prediction_id"],
                "unvalidated rehearsal prediction creates simulation-linked pressure",
                0.66,
                "simulation_influenced",
            )
        )
    if event["event_type"] == "decision" and event["payload"].get("commitment") is True:
        sources.append(
            (
                "chosen_commitment",
                "payload.selected_option",
                event["payload"].get("selected_option"),
                "decision explicitly chose a commitment",
                0.88,
                "chosen",
            )
        )
    elif event["event_type"] == "decision" and not event["payload"].get("resolved", False):
        sources.append(
            (
                "inferred_commitment_candidate",
                "payload.selected_option",
                event["payload"].get("selected_option"),
                "unresolved decision suggests commitment candidate",
                0.52,
                "inferred",
            )
        )
    if event["event_type"] in {"observation", "conversation"}:
        tension = residue.get("open_tensions", {})
        if tension.get("value") not in {None, "", "unknown", "not_applicable"}:
            sources.append(
                (
                    "curiosity",
                    "residue.open_tensions.value",
                    tension.get("value"),
                    "open tension creates curiosity",
                    0.58,
                    "authored" if event["epistemic_status"] == "authored" else "observed",
                )
            )
    return sources


def _source_ref(
    *,
    event: dict[str, Any],
    selector: str,
    value: Any,
    source_category: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "source_ref_id": "drivesrc_" + stable_hash(
            {
                "event_id": event["id"],
                "event_hash": event["content_hash"],
                "selector": selector,
                "category": source_category,
                "value": value,
            }
        )[:24],
        "source_event_id": event["id"],
        "source_event_hash": event["content_hash"],
        "source_event_type": event["event_type"],
        "source_epistemic_status": event["epistemic_status"],
        "source_selector": selector,
        "source_category": source_category,
        "scope_decision": {"decision": "included", "reason": "requested scope permits source"},
        "contribution_reason": reason,
        "value": value,
        "privacy_scope": event["privacy_scope"],
        "resource_scope": event["resource_scope"],
    }


def _drive_payload(
    *,
    kind: str,
    source_refs: list[dict[str, Any]],
    base_pressure: float,
    origin_status: str,
    attention_claim: str,
    requested_scope: dict[str, Any],
    immediate_context: dict[str, Any],
) -> dict[str, Any]:
    dynamics = DRIVE_DYNAMICS[kind]
    before = base_pressure
    after = _pressure_after(kind, before)
    governance = _governance(kind, source_refs, requested_scope)
    drive_id = "drive_" + stable_hash(
        {
            "kind": kind,
            "source_refs": [ref["source_ref_id"] for ref in source_refs],
            "context": immediate_context,
            "policy_version": ATTENTION_POLICY_VERSION,
        }
    )[:24]
    return {
        "policy_version": ATTENTION_POLICY_VERSION,
        "drive_id": drive_id,
        "drive_kind": kind,
        "drive_status": "active" if governance["allowed_effects"] else "inhibited",
        "origin_status": origin_status,
        "source_refs": source_refs,
        "pressure_before": round(before, 3),
        "pressure_after": round(after, 3),
        "pressure_components": [
            {"component": "source_pressure", "value": round(before, 3)},
            {"component": dynamics["rule"], "value": round(after - before, 3)},
        ],
        "dynamics": dynamics,
        "governance": governance,
        "attention_claim": attention_claim,
        "outcome_update_policy": {
            "satisfied": "reduce pressure and mark satisfied",
            "frustrated": "redirect or increase concern only with cited outcome",
            "weakened": "decay pressure",
            "strengthened": "increase pressure with cited outcome",
            "released": "mark released",
            "inconclusive": "leave pressure bounded",
        },
        "review_status": "review_pending",
        "no_external_action": True,
    }


def _pressure_after(kind: str, pressure: float) -> float:
    if kind == "curiosity":
        return max(0.0, pressure - 0.12)
    if kind == "deferred_impulse":
        return min(1.0, pressure + 0.15)
    if kind == "concern":
        return min(1.0, pressure + 0.10)
    if kind == "coherence_pressure":
        return min(1.0, pressure + 0.12)
    return min(DRIVE_DYNAMICS[kind]["saturation"], max(0.0, pressure + DRIVE_DYNAMICS[kind]["build"]))


def _governance(
    kind: str,
    source_refs: list[dict[str, Any]],
    requested_scope: dict[str, Any],
) -> dict[str, Any]:
    privacy = _merge_privacy(source_refs)
    resource = _merge_resource(source_refs)
    blocked: list[str] = []
    allowed = ["influence_recall", "private_review"]
    if kind in {"chosen_commitment", "deferred_impulse"}:
        allowed.append("prepare_recommendation")
    if kind in {"concern", "coherence_pressure"}:
        blocked.append("external_action")
    if requested_scope.get("external_contact") and not resource.get("external_contact", False):
        blocked.append("external_contact")
    if requested_scope.get("network") and not resource.get("network_access", False):
        blocked.append("network_access")
    if requested_scope.get("export") and not privacy.get("export_allowed", False):
        blocked.append("export")
    if blocked:
        allowed = [effect for effect in allowed if effect not in {"prepare_recommendation"}]
    blocked_reasons = {
        effect: "no recorded consent or scope grant for this effect"
        for effect in blocked
    }
    return {
        "decision": "allowed_internal_only" if allowed else "blocked",
        "privacy_scope": privacy,
        "resource_scope": resource,
        "consent_basis": "no external authorization recorded",
        "allowed_effects": allowed,
        "disallowed_effects": [
            "tool_call",
            "external_contact",
            "network_access",
            "autonomous_spend",
            "filesystem_mutation",
            "commit",
            "sensorium_polling",
        ],
        "blocked_effects": blocked,
        "blocked_effect_reasons": blocked_reasons,
    }


def _attention_claim(kind: str, value: Any) -> str:
    text = " ".join(str(value).split())[:80]
    if kind == "curiosity":
        return f"privately revisit question: {text}"
    if kind == "deferred_impulse":
        return f"prepare review of deferred attention: {text}"
    if kind == "concern":
        return f"address risk before outward action: {text}"
    if kind == "coherence_pressure":
        return f"resolve correction/tension: {text}"
    if kind == "rehearsal_pressure":
        return f"review unvalidated rehearsal prediction: {text}"
    if kind == "chosen_commitment":
        return f"track chosen commitment: {text}"
    if kind == "inferred_commitment_candidate":
        return f"ask whether this is a real commitment: {text}"
    return f"internal attention: {text}"


def _drive_snapshot_item(event: dict[str, Any]) -> dict[str, Any]:
    payload = event["payload"]
    return {
        "drive_event_id": event["id"],
        "drive_id": payload["drive_id"],
        "drive_kind": payload["drive_kind"],
        "drive_status": payload["drive_status"],
        "pressure_after": payload["pressure_after"],
        "source_ref_ids": [ref["source_ref_id"] for ref in payload["source_refs"]],
        "governance_decision": payload["governance"]["decision"],
    }


def _action_class(payload: dict[str, Any]) -> str:
    effects = payload["governance"]["allowed_effects"]
    if "prepare_recommendation" in effects:
        return "prepare_recommendation"
    if payload["drive_kind"] == "inferred_commitment_candidate":
        return "ask_permission"
    return "internal_attention"


def _attention_residue(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "salience": {"value": payload["pressure_after"], "source": "attention_workflow", "epistemic_status": "inferred"},
        "attention_target": {"value": payload["attention_claim"], "source": "attention_workflow", "epistemic_status": "inferred"},
        "uncertainty": {"value": "drive is pressure, not fact", "source": "attention_workflow", "epistemic_status": "inferred"},
        "open_tensions": {"value": payload["attention_claim"], "source": "attention_workflow", "epistemic_status": "inferred"},
        "drive_refs": {"value": [payload["drive_id"]], "source": "attention_workflow", "epistemic_status": "inferred"},
        "importance_reason": {"value": payload["source_refs"][0]["contribution_reason"], "source": "attention_workflow", "epistemic_status": "inferred"},
        "affect_valence": {"value": "neutral", "source": "attention_workflow", "epistemic_status": "inferred"},
        "expected_outcome": {"value": "governed internal attention", "source": "attention_workflow", "epistemic_status": "inferred"},
    }


def _merge_privacy(source_refs: list[dict[str, Any]]) -> dict[str, Any]:
    exposure_rank = {"public": 0, "team": 1, "local-only": 2, "internal-only": 3}
    scopes = [ref.get("privacy_scope", {}) for ref in source_refs]
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


def _merge_resource(source_refs: list[dict[str, Any]]) -> dict[str, Any]:
    scopes = [ref.get("resource_scope", {}) for ref in source_refs]
    return {
        "external_contact": all(scope.get("external_contact", False) for scope in scopes),
        "network_access": all(scope.get("network_access", False) for scope in scopes),
        "autonomous_spend": all(scope.get("autonomous_spend", False) for scope in scopes),
        "compute_escalation": all(scope.get("compute_escalation", False) for scope in scopes),
    }
