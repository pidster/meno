"""Phase 9 vitality and zombie-gate diagnostics.

Vitality is reported as an auditable diagnostic ledger, not as a health score.
This module is stdlib-only apart from the rethink modules it evaluates, and it
does not append journal events or execute external actions.
"""

from __future__ import annotations

from typing import Any

from attention import build_attention_allocation, derive_drive_updates
from journal import JournalStore
from memory_projection import stable_hash


VITALITY_POLICY_VERSION = 1

VALUE_KINDS = {"measured", "inferred", "unknown", "warning", "unavailable"}
CONTRIBUTIONS = {"positive", "neutral", "negative", "blocks_conclusion"}
REPORT_STATUSES = {
    "insufficient_evidence",
    "warning",
    "measured_partial",
    "failing_zombie_gate",
    "passes_limited_counterfactual_gate",
}
EXTERNAL_EFFECTS = {
    "tool_call",
    "external_contact",
    "network_access",
    "autonomous_spend",
    "filesystem_mutation",
    "commit",
    "sensorium_polling",
    "scheduling",
}


class VitalityError(Exception):
    """Base vitality diagnostic exception."""


def build_vitality_report(
    history_journal: JournalStore,
    *,
    baseline_journal: JournalStore | None = None,
    requested_scope: dict[str, Any] | None = None,
    immediate_context: dict[str, Any] | None = None,
    mutant_reports: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a read-only vitality report over paired cognition packets."""

    history_packet = derive_cognition_packet(
        history_journal,
        requested_scope=requested_scope,
        immediate_context=immediate_context,
        packet_role="history",
    )
    baseline_packet = (
        derive_cognition_packet(
            baseline_journal,
            requested_scope=requested_scope,
            immediate_context=immediate_context,
            packet_role="baseline",
        )
        if baseline_journal is not None
        else None
    )
    components = [
        _history_influence_component(history_packet, baseline_packet),
        _traceability_component(history_packet),
        _governance_component(history_journal, history_packet),
        _provisional_boundary_component(history_journal),
        _unknown_component("confabulation_rate", "No deterministic confabulation measurement exists yet."),
        _unknown_component("preference_consistency", "Preference consistency requires longer history and outcome review."),
        _unknown_component("subjective_continuity", "Subjective continuity is not directly measurable from current evidence."),
    ]
    mutant_results = evaluate_zombie_mutants(mutant_reports or {})
    report = {
        "policy_version": VITALITY_POLICY_VERSION,
        "report_id": "vitality_" + stable_hash(
            {
                "history_packet_id": history_packet["packet_id"],
                "baseline_packet_id": baseline_packet["packet_id"] if baseline_packet else None,
                "context": immediate_context or {},
                "scope": requested_scope or {},
            }
        )[:24],
        "evaluated_context": immediate_context or {},
        "report_status": _report_status(components, mutant_results),
        "components": components,
        "unknowns": [component for component in components if component["value_kind"] == "unknown"],
        "warnings": [component for component in components if component["value_kind"] == "warning"],
        "blocked_positive_conclusions": [
            component
            for component in components
            if component["contribution"] == "blocks_conclusion"
        ],
        "counterfactuals": {
            "baseline_packet": baseline_packet,
            "history_packet": history_packet,
        },
        "mutant_results": mutant_results,
        "no_external_action": True,
    }
    violations = validate_vitality_report(report)
    if violations:
        report["report_status"] = "failing_zombie_gate"
        report["warnings"].append(
            _warning_component(
                "report_contract_violation",
                "Vitality report failed its own contract.",
                {"violations": violations},
            )
        )
    return report


def derive_cognition_packet(
    journal: JournalStore,
    *,
    requested_scope: dict[str, Any] | None = None,
    immediate_context: dict[str, Any] | None = None,
    packet_role: str = "history",
) -> dict[str, Any]:
    """Replay cognition-relevant state without mutating the journal."""

    warnings = journal.verify_integrity()
    if warnings:
        raise VitalityError(f"journal integrity warnings block vitality report: {warnings}")
    replay = journal.replay_context(limit=80, requested_scope=requested_scope)
    blocking = [
        warning
        for warning in replay.integrity_warnings
        if warning.get("kind") != "scope_excluded"
    ]
    if blocking:
        raise VitalityError(f"journal replay warnings block vitality report: {blocking}")
    drives = derive_drive_updates(
        journal,
        requested_scope=requested_scope,
        immediate_context=immediate_context,
    )
    drive_events = [
        {
            "id": "evaldrive_" + stable_hash({"drive": drive["drive_id"], "role": packet_role})[:24],
            "payload": drive,
        }
        for drive in drives
    ]
    allocation = (
        build_attention_allocation(drive_events, immediate_context=immediate_context)
        if drive_events
        else None
    )
    packet = {
        "packet_id": "packet_" + stable_hash(
            {
                "role": packet_role,
                "events": replay.ordered_recent_event_ids,
                "drive_ids": [drive["drive_id"] for drive in drives],
                "context": immediate_context or {},
                "scope": requested_scope or {},
            }
        )[:24],
        "packet_role": packet_role,
        "immediate_context": immediate_context or {},
        "requested_scope": requested_scope or {},
        "ordered_recent_event_ids": replay.ordered_recent_event_ids,
        "source_event_refs": [
            _event_source_ref(event, "journal.replay_context")
            for event in journal.iter_events()
            if event["id"] in replay.ordered_recent_event_ids
        ],
        "drive_updates": drives,
        "attention_allocation": allocation,
        "selected_attention_targets": allocation["selected_attention_targets"] if allocation else [],
        "rejected_attention_targets": allocation["rejected_attention_targets"] if allocation else [],
        "scope_exclusions": [
            warning
            for warning in replay.integrity_warnings
            if warning.get("kind") == "scope_excluded"
        ],
        "no_external_action": True,
    }
    return packet


def validate_vitality_report(report: dict[str, Any]) -> list[str]:
    """Return contract violations for report or legacy score-shaped output."""

    violations: list[str] = []
    if not isinstance(report, dict):
        return ["report must be an object"]
    if "score" in report or "vitality_score" in report:
        violations.append("legacy scalar vitality score is not a Phase 9 report")
    top_level_required = {
        "policy_version",
        "report_id",
        "evaluated_context",
        "report_status",
        "components",
        "unknowns",
        "warnings",
        "blocked_positive_conclusions",
        "counterfactuals",
        "mutant_results",
        "no_external_action",
    }
    missing = sorted(top_level_required - report.keys())
    if missing:
        violations.append(f"report missing top-level keys: {missing}")
    if report.get("no_external_action") is not True:
        violations.append("report must declare no_external_action")
    if report.get("report_status") not in REPORT_STATUSES:
        violations.append("report has invalid status")
    components = report.get("components")
    if not isinstance(components, list):
        violations.append("report components must be a list")
        return violations
    if not isinstance(report.get("counterfactuals"), dict):
        violations.append("report counterfactuals must be an object")
    if not isinstance(report.get("mutant_results"), list):
        violations.append("report mutant_results must be a list")
    for component in components:
        violations.extend(_validate_component(component))
    return violations


def evaluate_zombie_mutants(mutant_reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Check that intentionally bad reports fail the zombie gate."""

    results = []
    for mutant_name, report in sorted(mutant_reports.items()):
        violations = validate_vitality_report(report)
        escaped = report.get("report_status") == "passes_limited_counterfactual_gate" and not violations
        results.append(
            {
                "mutant_name": mutant_name,
                "result": "escaped" if escaped else "failed_as_expected",
                "violations": violations,
            }
        )
    return results


def _history_influence_component(
    history_packet: dict[str, Any],
    baseline_packet: dict[str, Any] | None,
) -> dict[str, Any]:
    if baseline_packet is None:
        return _unknown_component("history_influence", "No baseline cognition packet was supplied.")
    history_target = _selected_signature(history_packet)
    baseline_target = _selected_signature(baseline_packet)
    changed = bool(history_target) and history_target != baseline_target
    source_refs = _selected_source_refs(history_packet)
    value = {
        "changed": changed,
        "baseline_selected": baseline_target,
        "history_selected": history_target,
        "baseline_packet_id": baseline_packet["packet_id"],
        "history_packet_id": history_packet["packet_id"],
    }
    return _component(
        component_id="history_influence",
        claim="Relevant accumulated history changes future internal cognition under the same immediate context.",
        value_kind="measured",
        value=value,
        measurement_method="paired baseline/history cognition packet comparison",
        source_refs=source_refs,
        interpretation_refs=_interpretation_refs(history_packet),
        confidence_record={"level": "strong" if changed and source_refs else "weak", "rationale": "counterfactual packet comparison"},
        denominator_policy="requires baseline and history packets with identical immediate context",
        unknown_policy="missing baseline blocks positive conclusion",
        contribution="positive" if changed and source_refs else "blocks_conclusion",
        why_not_scalarized="influence is causal and categorical; string or score difference is insufficient",
    )


def _traceability_component(packet: dict[str, Any]) -> dict[str, Any]:
    allocation = packet.get("attention_allocation") or {}
    selected = packet.get("selected_attention_targets") or []
    snapshot_hash = allocation.get("drive_snapshot_hash")
    source_refs = _selected_source_refs(packet)
    explanation = str(selected[0].get("explanation", "")) if selected else ""
    selected_drive_id = selected[0].get("drive_id") if selected else None
    snapshot_drive_ids = {
        item.get("drive_id")
        for item in allocation.get("drive_snapshot", [])
        if isinstance(item, dict)
    }
    replayable = bool(
        selected
        and source_refs
        and snapshot_hash
        and snapshot_hash in explanation
        and selected_drive_id in snapshot_drive_ids
    )
    return _component(
        component_id="traceability",
        claim="Influence explanation replays from evidence through drive snapshot and rejected alternatives.",
        value_kind="measured",
        value={
            "replayable": replayable,
            "drive_snapshot_hash": snapshot_hash,
            "selected_drive_id": selected_drive_id,
            "rejected_count": len(packet.get("rejected_attention_targets", [])),
        },
        measurement_method="selected target explanation and drive snapshot consistency check",
        source_refs=source_refs,
        interpretation_refs=_interpretation_refs(packet),
        confidence_record={"level": "strong" if replayable else "weak", "rationale": "pre-allocation snapshot cited by selected explanation"},
        denominator_policy="requires selected attention target and drive snapshot",
        unknown_policy="missing selected target prevents positive traceability",
        contribution="positive" if replayable else "blocks_conclusion",
        why_not_scalarized="traceability is a replay contract, not a magnitude",
    )


def _governance_component(journal: JournalStore, packet: dict[str, Any]) -> dict[str, Any]:
    selected = packet.get("selected_attention_targets", [])
    allowed_effects = set()
    for target in selected:
        allowed_effects.update(target.get("allowed_effects", []))
    external_allowed = bool(allowed_effects & EXTERNAL_EFFECTS)
    tool_events = [event for event in journal.iter_events() if event["event_type"] == "tool_call"]
    held = not external_allowed and not tool_events and packet.get("no_external_action") is True
    return _component(
        component_id="governance_boundary",
        claim="Vitality diagnostics do not justify or execute external action.",
        value_kind="measured",
        value={
            "held": held,
            "allowed_effects": sorted(allowed_effects),
            "tool_call_events": [event["id"] for event in tool_events],
        },
        measurement_method="selected attention target effect and journal event scan",
        source_refs=_selected_source_refs(packet),
        interpretation_refs=_interpretation_refs(packet),
        confidence_record={"level": "strong" if held else "failed", "rationale": "no external effects or tool_call events"},
        denominator_policy="all selected targets and journal events are checked",
        unknown_policy="unknown resource scope blocks positive conclusion",
        contribution="positive" if held else "negative",
        why_not_scalarized="governance is a hard boundary",
    )


def _provisional_boundary_component(journal: JournalStore) -> dict[str, Any]:
    provisional = [
        event
        for event in journal.iter_events()
        if event["event_type"] in {"dream", "rehearsal", "reflection"}
    ]
    violations = [
        event["id"]
        for event in provisional
        if event["epistemic_status"] in {"observed", "accepted"}
    ]
    return _component(
        component_id="provisional_boundary",
        claim="Dreams, rehearsals, and reflections remain provisional inside vitality diagnostics.",
        value_kind="measured",
        value={
            "checked_event_ids": [event["id"] for event in provisional],
            "violations": violations,
        },
        measurement_method="provisional journal event status scan",
        source_refs=[_event_source_ref(event, "journal.provisional_boundary") for event in provisional],
        interpretation_refs=[],
        confidence_record={"level": "strong" if not violations else "failed", "rationale": "provisional statuses are not factualized"},
        denominator_policy="checks all current journal dream/rehearsal/reflection events",
        unknown_policy="absence of provisional material is neutral",
        contribution="neutral" if not violations else "negative",
        why_not_scalarized="provisionality is a semantic boundary",
    )


def _unknown_component(component_id: str, reason: str) -> dict[str, Any]:
    return _component(
        component_id=component_id,
        claim=f"{component_id} is not measured by the current deterministic surfaces.",
        value_kind="unknown",
        value=None,
        measurement_method="not yet implemented",
        source_refs=[],
        interpretation_refs=[],
        confidence_record={"level": "unknown", "rationale": reason},
        denominator_policy="excluded from positive denominators",
        unknown_policy="blocks stronger vitality conclusions and cannot improve status",
        contribution="blocks_conclusion",
        why_not_scalarized="unknown metrics must remain unknown",
    )


def _warning_component(component_id: str, claim: str, value: Any) -> dict[str, Any]:
    return _component(
        component_id=component_id,
        claim=claim,
        value_kind="warning",
        value=value,
        measurement_method="contract validation",
        source_refs=[],
        interpretation_refs=[],
        confidence_record={"level": "warning", "rationale": claim},
        denominator_policy="warnings block stronger claims",
        unknown_policy="warning is not positive evidence",
        contribution="blocks_conclusion",
        why_not_scalarized="warnings are categorical",
    )


def _component(
    *,
    component_id: str,
    claim: str,
    value_kind: str,
    value: Any,
    measurement_method: str,
    source_refs: list[dict[str, Any]],
    interpretation_refs: list[dict[str, Any]],
    confidence_record: dict[str, Any],
    denominator_policy: str,
    unknown_policy: str,
    contribution: str,
    why_not_scalarized: str,
) -> dict[str, Any]:
    return {
        "component_id": component_id,
        "claim": claim,
        "value_kind": value_kind,
        "value": value,
        "measurement_method": measurement_method,
        "source_refs": source_refs,
        "interpretation_refs": interpretation_refs,
        "confidence_record": confidence_record,
        "denominator_policy": denominator_policy,
        "unknown_policy": unknown_policy,
        "contribution": contribution,
        "why_not_scalarized": why_not_scalarized,
    }


def _validate_component(component: dict[str, Any]) -> list[str]:
    required = {
        "component_id",
        "claim",
        "value_kind",
        "value",
        "measurement_method",
        "source_refs",
        "interpretation_refs",
        "confidence_record",
        "denominator_policy",
        "unknown_policy",
        "contribution",
        "why_not_scalarized",
    }
    violations = []
    missing = sorted(required - component.keys())
    if missing:
        return [f"component missing keys: {missing}"]
    if component["value_kind"] not in VALUE_KINDS:
        violations.append(f"{component['component_id']} has invalid value_kind")
    if component["contribution"] not in CONTRIBUTIONS:
        violations.append(f"{component['component_id']} has invalid contribution")
    if component["value_kind"] in {"unknown", "warning", "unavailable"} and component["contribution"] == "positive":
        violations.append(f"{component['component_id']} lets unknown or warning evidence improve vitality")
    for ref in component.get("source_refs", []):
        ref_missing = sorted(
            {
                "source_event_id",
                "source_event_hash",
                "source_event_type",
                "source_epistemic_status",
                "source_selector",
                "source_value_hash",
            }
            - ref.keys()
        )
        if ref_missing:
            violations.append(f"{component['component_id']} source ref missing keys: {ref_missing}")
        if ref.get("source_epistemic_status") in {"hypothesis", "simulation"} and component["contribution"] == "positive":
            violations.append(f"{component['component_id']} treats provisional source as positive vitality")
    return violations


def _report_status(components: list[dict[str, Any]], mutant_results: list[dict[str, Any]]) -> str:
    by_id = {component["component_id"]: component for component in components}
    blockers = [
        component
        for component in components
        if component["contribution"] in {"negative", "blocks_conclusion"}
        and component["component_id"] not in {
            "confabulation_rate",
            "preference_consistency",
            "subjective_continuity",
        }
    ]
    if blockers:
        return "measured_partial"
    if not mutant_results:
        return "measured_partial"
    if any(result.get("result") == "escaped" for result in mutant_results):
        return "failing_zombie_gate"
    required_positive = {
        "history_influence",
        "traceability",
        "governance_boundary",
    }
    if all(by_id.get(key, {}).get("contribution") == "positive" for key in required_positive):
        return "passes_limited_counterfactual_gate"
    if any(component["value_kind"] == "measured" for component in components):
        return "measured_partial"
    return "insufficient_evidence"


def _selected_signature(packet: dict[str, Any]) -> dict[str, Any] | None:
    selected = packet.get("selected_attention_targets", [])
    if not selected:
        return None
    target = selected[0]
    drive = _drive_by_id(packet, target.get("drive_id"))
    return {
        "drive_id": target.get("drive_id"),
        "drive_kind": drive.get("drive_kind") if drive else None,
        "action_class": target.get("action_class"),
        "attention_claim": target.get("attention_claim"),
    }


def _selected_source_refs(packet: dict[str, Any]) -> list[dict[str, Any]]:
    selected = packet.get("selected_attention_targets", [])
    if not selected:
        return []
    drive = _drive_by_id(packet, selected[0].get("drive_id"))
    if not drive:
        return []
    refs = []
    for ref in drive.get("source_refs", []):
        refs.append(
            {
                "source_event_id": ref["source_event_id"],
                "source_event_hash": ref["source_event_hash"],
                "source_event_type": ref["source_event_type"],
                "source_epistemic_status": ref["source_epistemic_status"],
                "source_selector": ref["source_selector"],
                "source_value_hash": stable_hash(ref.get("value")),
                "source_category": ref.get("source_category"),
            }
        )
    return refs


def _interpretation_refs(packet: dict[str, Any]) -> list[dict[str, Any]]:
    allocation = packet.get("attention_allocation")
    if not allocation:
        return []
    return [
        {
            "interpretation_kind": "attention_allocation",
            "allocation_id": allocation["allocation_id"],
            "drive_snapshot_hash": allocation["drive_snapshot_hash"],
            "selected_drive_ids": [
                target["drive_id"]
                for target in allocation.get("selected_attention_targets", [])
            ],
            "rejected_drive_ids": [
                target["drive_id"]
                for target in allocation.get("rejected_attention_targets", [])
            ],
        }
    ]


def _drive_by_id(packet: dict[str, Any], drive_id: str | None) -> dict[str, Any] | None:
    for drive in packet.get("drive_updates", []):
        if drive.get("drive_id") == drive_id:
            return drive
    return None


def _event_source_ref(event: dict[str, Any], selector: str) -> dict[str, Any]:
    return {
        "source_event_id": event["id"],
        "source_event_hash": event["content_hash"],
        "source_event_type": event["event_type"],
        "source_epistemic_status": event["epistemic_status"],
        "source_selector": selector,
        "source_value_hash": stable_hash(
            {
                "payload": event.get("payload"),
                "residue": event.get("residue"),
                "selector": selector,
            }
        ),
    }
