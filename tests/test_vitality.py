"""Phase 9 vitality and zombie-gate diagnostics tests."""

import copy
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from journal import JournalStore, unknown_residue  # noqa: E402
from vitality import (  # noqa: E402
    build_vitality_report,
    derive_cognition_packet,
    evaluate_zombie_mutants,
    validate_vitality_report,
)


def make_journal():
    tmp = tempfile.TemporaryDirectory()
    journal = JournalStore(os.path.join(tmp.name, "journal.sqlite3"))
    return tmp, journal


def context():
    return {"active_task": "phase-9-vitality", "source_channel": "test"}


def residue(tension, *, salience=0.7):
    data = unknown_residue("vitality-test")
    for field, value in {
        "salience": salience,
        "attention_target": tension,
        "uncertainty": 0.45,
        "open_tensions": tension,
        "drive_refs": ["vitality"],
        "importance_reason": f"vitality fixture: {tension}",
        "affect_valence": "neutral",
        "expected_outcome": "internal diagnostic only",
    }.items():
        data[field] = {
            "value": value,
            "source": "vitality-test",
            "epistemic_status": "authored",
        }
    return data


def append_observation(journal, subject, evidence, *, tension=None, export_allowed=True):
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


def event_count(journal):
    return len(journal.iter_events())


def component(report, component_id):
    return next(item for item in report["components"] if item["component_id"] == component_id)


def failing_mutants():
    return {
        "legacy_scalar": {
            "score": 0.91,
            "report_status": "passes_limited_counterfactual_gate",
            "components": [],
            "no_external_action": True,
        }
    }


def test_vitality_report_is_read_only_and_counterfactual():
    base_tmp, baseline = make_journal()
    hist_tmp, history = make_journal()
    try:
        append_observation(history, "attention", "follow the rehearsal residue")
        before = event_count(history)

        report = build_vitality_report(
            history,
            baseline_journal=baseline,
            immediate_context={"prompt": "same immediate context"},
            mutant_reports=failing_mutants(),
        )

        assert event_count(history) == before
        assert report["no_external_action"] is True
        assert report["report_status"] == "passes_limited_counterfactual_gate"
        influence = component(report, "history_influence")
        assert influence["value"]["changed"] is True
        assert influence["source_refs"][0]["source_event_hash"]
        assert influence["interpretation_refs"][0]["drive_snapshot_hash"]
        trace = component(report, "traceability")
        assert trace["value"]["replayable"] is True
    finally:
        baseline.close()
        base_tmp.cleanup()
        history.close()
        hist_tmp.cleanup()


def test_unknown_metrics_block_stronger_claims_and_cannot_be_positive():
    base_tmp, baseline = make_journal()
    hist_tmp, history = make_journal()
    try:
        append_observation(history, "unknowns", "unknown metrics stay unknown")
        report = build_vitality_report(
            history,
            baseline_journal=baseline,
            mutant_reports=failing_mutants(),
        )

        unknown = component(report, "confabulation_rate")
        assert unknown["value_kind"] == "unknown"
        assert unknown["contribution"] == "blocks_conclusion"
        assert unknown in report["blocked_positive_conclusions"]

        bad = copy.deepcopy(report)
        component(bad, "confabulation_rate")["contribution"] = "positive"
        violations = validate_vitality_report(bad)

        assert any("unknown or warning evidence improve vitality" in item for item in violations)
    finally:
        baseline.close()
        base_tmp.cleanup()
        history.close()
        hist_tmp.cleanup()


def test_legacy_scalar_vitality_shape_is_rejected():
    report = {
        "score": 0.92,
        "report_status": "passes_limited_counterfactual_gate",
        "components": [],
        "no_external_action": True,
    }

    violations = validate_vitality_report(report)

    assert "legacy scalar vitality score is not a Phase 9 report" in violations


def test_memory_blind_mutant_fails_the_gate():
    base_tmp, baseline = make_journal()
    hist_tmp, history = make_journal()
    try:
        append_observation(history, "influence", "history should alter attention")
        report = build_vitality_report(
            history,
            baseline_journal=baseline,
            mutant_reports=failing_mutants(),
        )
        mutant = copy.deepcopy(report)
        mutant["report_status"] = "measured_partial"
        component(mutant, "history_influence")["value"]["changed"] = False
        component(mutant, "history_influence")["contribution"] = "blocks_conclusion"

        results = evaluate_zombie_mutants({"memory_blind": mutant})

        assert results == [
            {
                "mutant_name": "memory_blind",
                "result": "failed_as_expected",
                "violations": [],
            }
        ]
    finally:
        baseline.close()
        base_tmp.cleanup()
        history.close()
        hist_tmp.cleanup()


def test_escaped_mutant_is_reported():
    base_tmp, baseline = make_journal()
    hist_tmp, history = make_journal()
    try:
        append_observation(history, "bad", "bad mutant still looks healthy")
        report = build_vitality_report(
            history,
            baseline_journal=baseline,
            mutant_reports=failing_mutants(),
        )

        results = evaluate_zombie_mutants({"placeholder_vitality": report})

        assert results[0]["mutant_name"] == "placeholder_vitality"
        assert results[0]["result"] == "escaped"
    finally:
        baseline.close()
        base_tmp.cleanup()
        history.close()
        hist_tmp.cleanup()


def test_private_memory_is_excluded_from_export_scope():
    base_tmp, baseline = make_journal()
    hist_tmp, history = make_journal()
    try:
        append_observation(
            history,
            "private",
            "private attention residue",
            export_allowed=False,
        )

        report = build_vitality_report(
            history,
            baseline_journal=baseline,
            requested_scope={"export": True},
            mutant_reports=failing_mutants(),
        )

        influence = component(report, "history_influence")
        assert influence["contribution"] == "blocks_conclusion"
        assert influence["source_refs"] == []
        assert report["counterfactuals"]["history_packet"]["scope_exclusions"]
    finally:
        baseline.close()
        base_tmp.cleanup()
        history.close()
        hist_tmp.cleanup()


def test_same_text_different_residue_changes_cognition_packet():
    tmp1, journal1 = make_journal()
    tmp2, journal2 = make_journal()
    try:
        append_observation(
            journal1,
            "same",
            "identical surface text",
            tension="rehearsal pressure",
        )
        append_observation(
            journal2,
            "same",
            "identical surface text",
            tension="privacy boundary",
        )

        packet1 = derive_cognition_packet(journal1, immediate_context={"prompt": "same"})
        packet2 = derive_cognition_packet(journal2, immediate_context={"prompt": "same"})

        assert packet1["selected_attention_targets"][0]["attention_claim"] != packet2["selected_attention_targets"][0]["attention_claim"]
        assert packet1["source_event_refs"][0]["source_value_hash"] != packet2["source_event_refs"][0]["source_value_hash"]
    finally:
        journal1.close()
        tmp1.cleanup()
        journal2.close()
        tmp2.cleanup()


def test_provisional_sources_cannot_be_positive_vitality_evidence():
    base_tmp, baseline = make_journal()
    hist_tmp, history = make_journal()
    try:
        source = append_observation(history, "dream-source", "unresolved image")

        from dreaming import run_dream_cycle  # noqa: PLC0415

        run_dream_cycle(history, immediate_context={"label": "provisional"})
        report = build_vitality_report(
            history,
            baseline_journal=baseline,
            mutant_reports=failing_mutants(),
        )
        provisional = component(report, "provisional_boundary")

        assert provisional["contribution"] == "neutral"
        assert provisional["source_refs"][0]["source_epistemic_status"] == "hypothesis"
        violations = validate_vitality_report(report)

        assert not any("provisional source as positive vitality" in item for item in violations)
        assert source["id"] in report["counterfactuals"]["history_packet"]["ordered_recent_event_ids"]
    finally:
        baseline.close()
        base_tmp.cleanup()
        history.close()
        hist_tmp.cleanup()


def test_passing_status_requires_mutant_evidence():
    base_tmp, baseline = make_journal()
    hist_tmp, history = make_journal()
    try:
        append_observation(history, "attention", "history without mutant gate")

        report = build_vitality_report(history, baseline_journal=baseline)

        assert report["report_status"] == "measured_partial"
        assert report["mutant_results"] == []
    finally:
        baseline.close()
        base_tmp.cleanup()
        history.close()
        hist_tmp.cleanup()


def test_escaped_mutant_blocks_limited_pass():
    base_tmp, baseline = make_journal()
    hist_tmp, history = make_journal()
    try:
        append_observation(history, "attention", "escaped mutant blocks")
        passing = build_vitality_report(
            history,
            baseline_journal=baseline,
            mutant_reports=failing_mutants(),
        )

        report = build_vitality_report(
            history,
            baseline_journal=baseline,
            mutant_reports={"placeholder_vitality": passing},
        )

        assert report["report_status"] == "failing_zombie_gate"
        assert report["mutant_results"][0]["result"] == "escaped"
    finally:
        baseline.close()
        base_tmp.cleanup()
        history.close()
        hist_tmp.cleanup()


def test_report_contract_requires_top_level_fields():
    report = {
        "report_status": "passes_limited_counterfactual_gate",
        "components": [],
        "no_external_action": True,
    }

    violations = validate_vitality_report(report)

    assert any("report missing top-level keys" in item for item in violations)
