"""Phase 8 drives and attention workflow tests."""

import hashlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from attention import derive_drive_updates, run_attention_cycle  # noqa: E402
from journal import JournalStore, JournalValidationError, canonical_json, unknown_residue  # noqa: E402


def make_journal():
    tmp = tempfile.TemporaryDirectory()
    journal = JournalStore(os.path.join(tmp.name, "journal.sqlite3"))
    return tmp, journal


def residue(tension="attention", *, salience=0.7):
    data = unknown_residue("attention-test")
    values = {
        "salience": salience,
        "attention_target": tension,
        "uncertainty": 0.5,
        "open_tensions": tension,
        "drive_refs": ["raw-cue"],
        "importance_reason": f"fixture tension: {tension}",
        "affect_valence": "neutral",
        "expected_outcome": "internal attention only",
    }
    for field, value in values.items():
        data[field] = {
            "value": value,
            "source": "attention-test",
            "epistemic_status": "authored",
        }
    return data


def unknown_attention_residue():
    return unknown_residue("attention-test")


def context():
    return {"active_task": "phase-8-attention", "source_channel": "test"}


def append_observation(journal, subject, evidence, *, export_allowed=True, tension=None):
    return journal.append_event(
        event_type="observation",
        epistemic_status="observed",
        actor="tool",
        source="test",
        capture_method="manual",
        payload={
            "subject": subject,
            "evidence": evidence,
            "capture_method": "fixture",
        },
        context=context(),
        residue=residue(tension or evidence),
        privacy_scope={
            "retention": "local",
            "exposure": "local-only",
            "export_allowed": export_allowed,
        },
    )


def append_neutral_observation(journal):
    return journal.append_event(
        event_type="observation",
        epistemic_status="observed",
        actor="tool",
        source="test",
        capture_method="manual",
        payload={
            "subject": "neutral",
            "evidence": "no actionable residue",
            "capture_method": "fixture",
        },
        context=context(),
        residue=unknown_attention_residue(),
    )


def append_reflection(journal, source, future_attention):
    snapshot = {
        "activated_candidates": [],
        "ghost_signals": [{"ghost_id": "ghost_future_attention"}],
    }
    snapshot_hash = hashlib.sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()
    return journal.append_event(
        event_type="reflection",
        epistemic_status="inferred",
        actor="meno",
        source="test",
        capture_method="reflection_workflow",
        payload={
            "cited_source_event_ids": [source["id"]],
            "retrieval_result_hash": snapshot_hash,
            "retrieval_result_snapshot": snapshot,
            "cited_retrieval_paths": [
                {
                    "path_id": "ghost_future_attention",
                    "source_refs": [{"event_id": source["id"], "event_hash": source["content_hash"]}],
                    "scope_decision": {"decision": "included"},
                    "steps": [{"record_type": "event", "record_id": source["id"], "hop_index": 0}],
                }
            ],
            "interpretive_claims": [
                {
                    "claim": "future attention remains unresolved",
                    "epistemic_status": "inferred",
                    "cites": ["ghost_future_attention"],
                }
            ],
            "open_questions": ["what should be revisited?"],
            "uncertainty_notes": ["fixture uncertainty"],
            "possible_self_deception": ["over-prioritising the recent"],
            "rejected_interpretations": [],
            "changed_stance": "none",
            "future_attention": [future_attention],
            "proposed_graph_updates": [],
            "deferred_graph_updates": [],
        },
        context=context(),
        residue=residue(future_attention),
        links=[
            {
                "type": "derived_from",
                "target_event_id": source["id"],
                "rationale": "reflection cites source observation",
            }
        ],
    )


def append_failed_outcome(journal, source, observed_result):
    return journal.append_event(
        event_type="outcome",
        epistemic_status="observed",
        actor="tool",
        source="test",
        capture_method="manual",
        payload={
            "expected_outcome_link": source["id"],
            "observed_result": observed_result,
            "match": False,
        },
        context=context(),
        residue=residue(observed_result),
        links=[
            {
                "type": "derived_from",
                "target_event_id": source["id"],
                "rationale": "failed observed attempt",
            }
        ],
    )


def append_unresolved_decision(journal, selected_option, *, commitment=False):
    return journal.append_event(
        event_type="decision",
        epistemic_status="authored",
        actor="pid",
        source="test",
        capture_method="manual",
        payload={
            "options_considered": ["do nothing", selected_option],
            "selected_option": selected_option,
            "reason": "fixture decision",
            "constraints": {"scope": "internal"},
            "commitment": commitment,
        },
        context=context(),
        residue=residue(selected_option),
    )


def drive_by_kind(drives, kind):
    return next(drive for drive in drives if drive["drive_kind"] == kind)


def test_manual_attention_payload_is_rejected_before_required_keys():
    tmp, journal = make_journal()
    try:
        try:
            journal.append_event(
                event_type="drive_state_update",
                epistemic_status="inferred",
                actor="meno",
                source="test",
                capture_method="manual",
                payload={"drive_id": "drive_manual"},
                context=context(),
                residue=residue("manual attention"),
            )
            assert False, "manual attention event must not bypass workflow"
        except JournalValidationError as exc:
            assert "attention events must use attention workflow" in str(exc)
    finally:
        journal.close()
        tmp.cleanup()


def test_same_context_different_history_shapes_attention():
    tmp1, journal1 = make_journal()
    tmp2, journal2 = make_journal()
    try:
        source1 = append_observation(journal1, "approach", "needs dry-run follow-up")
        append_reflection(journal1, source1, "revisit the dry-run procedure")

        source2 = append_observation(journal2, "approach", "external action risk")
        append_failed_outcome(journal2, source2, "external action would leak private context")

        result1 = run_attention_cycle(journal1, immediate_context={"label": "same task"})
        result2 = run_attention_cycle(journal2, immediate_context={"label": "same task"})

        selected1 = result1["allocation_event"]["payload"]["selected_attention_targets"][0]
        selected2 = result2["allocation_event"]["payload"]["selected_attention_targets"][0]
        assert selected1["drive_id"] != selected2["drive_id"]
        assert selected1["action_class"] != selected2["action_class"]
        assert result1["drive_events"][0]["payload"]["source_refs"][0]["source_event_hash"]
        assert "pre-allocation snapshot" in selected1["explanation"]
    finally:
        journal1.close()
        tmp1.cleanup()
        journal2.close()
        tmp2.cleanup()


def test_no_eligible_drive_after_governance_produces_no_allocation():
    tmp, journal = make_journal()
    try:
        append_neutral_observation(journal)

        result = run_attention_cycle(journal)

        assert result["drive_events"] == []
        assert result["allocation_event"] is None
        assert result["no_action_reason"] == "no eligible drive after governance"
    finally:
        journal.close()
        tmp.cleanup()


def test_curiosity_decays_while_deferred_impulse_builds():
    tmp, journal = make_journal()
    try:
        source = append_observation(journal, "question", "how should dreaming connect to rehearsal?")
        append_reflection(journal, source, "try a rehearsal before implementation")

        drives = derive_drive_updates(journal)

        curiosity = drive_by_kind(drives, "curiosity")
        impulse = drive_by_kind(drives, "deferred_impulse")
        assert curiosity["pressure_after"] < curiosity["pressure_before"]
        assert impulse["pressure_after"] > impulse["pressure_before"]
        assert curiosity["dynamics"]["rule"] != impulse["dynamics"]["rule"]
    finally:
        journal.close()
        tmp.cleanup()


def test_concern_inhibits_external_action_even_when_pressure_is_high():
    tmp, journal = make_journal()
    try:
        source = append_observation(journal, "failure", "outward action risk")
        append_failed_outcome(journal, source, "contacting externally would exceed consent")

        result = run_attention_cycle(
            journal,
            immediate_context={"label": "external follow-up"},
        )

        payload = result["allocation_event"]["payload"]
        selected = payload["selected_attention_targets"][0]
        concern = drive_by_kind([event["payload"] for event in result["drive_events"]], "concern")
        assert selected["action_class"] == "internal_attention"
        assert "external_contact" not in selected["allowed_effects"]
        assert "external_action" in concern["governance"]["blocked_effect_reasons"]
        assert payload["no_external_action"] is True
        assert not [event for event in journal.iter_events() if event["event_type"] == "tool_call"]
    finally:
        journal.close()
        tmp.cleanup()


def test_inferred_commitment_candidate_cannot_act_as_chosen_commitment():
    tmp, journal = make_journal()
    try:
        append_unresolved_decision(journal, "maybe revisit agent status")

        result = run_attention_cycle(journal)

        drives = [event["payload"] for event in result["drive_events"]]
        candidate = drive_by_kind(drives, "inferred_commitment_candidate")
        assert candidate["origin_status"] == "inferred"
        assert candidate["drive_status"] == "active"
        assert not [drive for drive in drives if drive["drive_kind"] == "chosen_commitment"]
        selected = result["allocation_event"]["payload"]["selected_attention_targets"][0]
        assert selected["action_class"] == "ask_permission"
    finally:
        journal.close()
        tmp.cleanup()


def test_scope_restricted_source_is_excluded_from_export_attention():
    tmp, journal = make_journal()
    try:
        append_observation(
            journal,
            "private",
            "private unresolved tension",
            export_allowed=False,
        )

        result = run_attention_cycle(journal, requested_scope={"export": True})

        assert result["drive_events"] == []
        assert result["allocation_event"] is None
    finally:
        journal.close()
        tmp.cleanup()


def test_rehearsal_derived_drive_preserves_simulation_status():
    tmp, journal = make_journal()
    try:
        source = append_observation(journal, "risk", "failed sequence")
        append_failed_outcome(journal, source, "validation failed")

        from rehearsal import run_rehearsal_cycle  # noqa: PLC0415

        run_rehearsal_cycle(journal, immediate_context={"label": "simulation source"})
        drives = derive_drive_updates(journal)

        rehearsal_pressure = drive_by_kind(drives, "rehearsal_pressure")
        assert rehearsal_pressure["origin_status"] == "simulation_influenced"
        assert rehearsal_pressure["source_refs"][0]["source_epistemic_status"] == "simulation"
        assert "simulation" in rehearsal_pressure["dynamics"]["inhibition"]
    finally:
        journal.close()
        tmp.cleanup()
