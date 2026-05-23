"""Phase 10 integrated cognition packet tests."""

import copy
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cognition import (  # noqa: E402
    build_cognition_packet,
    evaluate_cognition_mutants,
    validate_cognition_packet,
)
from dreaming import run_dream_cycle  # noqa: E402
from journal import JournalStore, unknown_residue  # noqa: E402
from memory_projection import ProjectionStore  # noqa: E402
from rehearsal import run_rehearsal_cycle  # noqa: E402


def make_stores():
    tmp = tempfile.TemporaryDirectory()
    journal = JournalStore(os.path.join(tmp.name, "journal.sqlite3"))
    projection = ProjectionStore(os.path.join(tmp.name, "projection.sqlite3"))
    return tmp, journal, projection


def residue(label, *, salience=0.7):
    data = unknown_residue("cognition-test")
    for field, value in {
        "salience": salience,
        "attention_target": label,
        "uncertainty": 0.35,
        "open_tensions": label,
        "drive_refs": ["cognition"],
        "importance_reason": f"cognition fixture: {label}",
        "affect_valence": "neutral",
        "expected_outcome": "preview packet only",
    }.items():
        data[field] = {
            "value": value,
            "source": "cognition-test",
            "epistemic_status": "authored",
        }
    return data


def append_observation(journal, subject, evidence, *, tension=None, export_allowed=True):
    return journal.append_event(
        event_type="observation",
        epistemic_status="observed",
        actor="tester",
        source="cognition-test",
        capture_method="manual",
        payload={
            "subject": subject,
            "evidence": evidence,
            "capture_method": "fixture",
        },
        context={"active_task": "phase-10-cognition", "source_channel": "test"},
        residue=residue(tension or evidence),
        privacy_scope={
            "retention": "local",
            "exposure": "local-only",
            "export_allowed": export_allowed,
        },
    )


def append_failed_outcome(journal, observed_result):
    source = append_observation(journal, "attempt", "prior approach", tension="prior approach failed")
    return journal.append_event(
        event_type="outcome",
        epistemic_status="observed",
        actor="tester",
        source="cognition-test",
        capture_method="manual",
        payload={
            "expected_outcome_link": source["id"],
            "observed_result": observed_result,
            "match": False,
        },
        context={"active_task": "phase-10-cognition", "source_channel": "test"},
        residue=residue(observed_result),
        links=[
            {
                "type": "derived_from",
                "target_event_id": source["id"],
                "rationale": "failed observed attempt",
            }
        ],
    )


def counts(journal, projection):
    return {
        "journal_events": len(journal.iter_events()),
        "projection_runs": len(projection.runs()),
        "candidates": len(projection.candidates()),
        "edges": len(projection.edges()),
        "relations": len(projection.relations()),
        "decisions": len(projection.decisions()),
    }


def build_fixture_packet(*, context=None):
    tmp, journal, projection = make_stores()
    append_observation(
        journal,
        "cognition preview",
        "projection and retrieval shape attention",
        tension="projection retrieval attention chain",
    )
    projection.project_journal(journal)
    entry = projection.candidate("entity", "cognition preview")
    assert entry is not None
    packet = build_cognition_packet(
        journal,
        projection,
        entry_candidate_ids=[entry["candidate_id"]],
        immediate_context=context or {"prompt": "same immediate context"},
    )
    return tmp, journal, projection, packet


def build_subject_packet(subject, evidence, tension, *, context):
    tmp, journal, projection = make_stores()
    append_observation(journal, subject, evidence, tension=tension)
    projection.project_journal(journal)
    entry = projection.candidate("entity", subject)
    assert entry is not None
    packet = build_cognition_packet(
        journal,
        projection,
        entry_candidate_ids=[entry["candidate_id"]],
        immediate_context=context,
    )
    return tmp, journal, projection, packet


def test_preview_packet_is_read_only_and_causally_chained():
    tmp, journal, projection = make_stores()
    try:
        append_observation(
            journal,
            "cognition preview",
            "projection and retrieval shape attention",
            tension="projection retrieval attention chain",
        )
        projection.project_journal(journal)
        entry = projection.candidate("entity", "cognition preview")
        assert entry is not None
        before = counts(journal, projection)

        packet = build_cognition_packet(
            journal,
            projection,
            entry_candidate_ids=[entry["candidate_id"]],
            immediate_context={"prompt": "same immediate context"},
        )

        assert counts(journal, projection) == before
        assert packet["packet_status"] == "accepted"
        assert packet["no_external_action"] is True
        assert packet["projection_run_ref"]["status"] == "succeeded"
        assert packet["retrieval_summary"]["path_ids"]
        selected = packet["attention_allocation"]["selected_attention_targets"][0]
        assert selected["retrieval_path_refs"]
        assert selected["projection_candidate_refs"]
        assert packet["influence_chain"]["retrieval_path_ids"]
        assert packet["selected_next_step"]["retrieval_path_refs"]
        assert packet["vitality_summary"]["validated_packet_id"] == packet["packet_id"]
    finally:
        projection.close()
        journal.close()
        tmp.cleanup()


def test_reflection_disposition_is_structured_and_cited():
    tmp, journal, projection, packet = build_fixture_packet()
    try:
        disposition = packet["reflection_disposition"]

        assert disposition["changed_view"] is True
        assert disposition["cited_influence_refs"]
        assert disposition["confidence_limits"]
        assert disposition["rejected_interpretations"] == [
            "raw journal residue is insufficient without projection and retrieval"
        ]

        mutant = copy.deepcopy(packet)
        mutant["packet_status"] = "accepted"
        mutant["reflection_disposition"]["cited_influence_refs"] = []

        violations = validate_cognition_packet(mutant)

        assert "changed reflection disposition requires cited influence refs" in violations
    finally:
        projection.close()
        journal.close()
        tmp.cleanup()


def test_same_context_different_projected_histories_change_cognition():
    context = {"prompt": "same immediate context"}
    left = build_subject_packet(
        "dreaming",
        "dream material should stay hypothesis",
        "protect dreams from becoming factual memory",
        context=context,
    )
    right = build_subject_packet(
        "rehearsal",
        "dry runs should stay simulation",
        "protect rehearsals from being recorded as events",
        context=context,
    )
    left_tmp, left_journal, left_projection, left_packet = left
    right_tmp, right_journal, right_projection, right_packet = right
    try:
        assert left_packet["packet_status"] == "accepted"
        assert right_packet["packet_status"] == "accepted"
        assert left_packet["retrieval_summary"]["path_ids"] != right_packet["retrieval_summary"]["path_ids"]
        assert (
            left_packet["attention_allocation"]["selected_attention_targets"][0]["drive_id"]
            != right_packet["attention_allocation"]["selected_attention_targets"][0]["drive_id"]
        )
        assert left_packet["particularity"]["basis"] == "protect dreams from becoming factual memory"
        assert right_packet["particularity"]["basis"] == "protect rehearsals from being recorded as events"
    finally:
        left_projection.close()
        left_journal.close()
        left_tmp.cleanup()
        right_projection.close()
        right_journal.close()
        right_tmp.cleanup()


def test_irrelevant_history_does_not_claim_positive_influence():
    tmp, journal, projection, packet = build_subject_packet(
        "garden",
        "tomato watering schedule",
        "plants need water",
        context={
            "prompt": "same immediate context",
            "relevance_terms": ["dream"],
        },
    )
    try:
        assert packet["packet_status"] != "accepted"
        assert packet["reflection_diagnostics"]["history_influence_detected"] is True
        assert packet["reflection_diagnostics"]["context_relevance"]["matched"] is False
        assert packet["reflection_diagnostics"]["formulaic_blocked"] is True
        assert packet["particularity"]["present"] is False
    finally:
        projection.close()
        journal.close()
        tmp.cleanup()


def test_private_scope_is_blocked_without_leaking_restricted_label():
    tmp, journal, projection = make_stores()
    try:
        append_observation(
            journal,
            "private anomaly",
            "restricted design note",
            tension="restricted tension",
            export_allowed=False,
        )
        projection.project_journal(journal)
        entry = projection.candidate("entity", "private anomaly")
        assert entry is not None

        packet = build_cognition_packet(
            journal,
            projection,
            entry_candidate_ids=[entry["candidate_id"]],
            requested_scope={"export": True},
            immediate_context={"prompt": "same immediate context"},
        )

        assert packet["packet_status"] == "blocked_by_scope"
        assert packet["retrieval_summary"]["scope_exclusions"]
        assert "private anomaly" not in str(packet["retrieval_summary"]["ghost_signals"])
        assert any(decision["decision"] == "blocked_by_policy" for decision in packet["governance_decisions"])
    finally:
        projection.close()
        journal.close()
        tmp.cleanup()


def test_provisional_dream_and_rehearsal_boundaries_survive_packet():
    dream_tmp, dream_journal, dream_projection = make_stores()
    rehearsal_tmp, rehearsal_journal, rehearsal_projection = make_stores()
    try:
        append_observation(
            dream_journal,
            "dream source",
            "loose association",
            tension="A/B loose association",
        )
        dream = run_dream_cycle(dream_journal, immediate_context={"label": "phase 10"})
        assert dream["dream_event"] is not None
        dream_projection.project_journal(dream_journal)
        dream_candidate = next(
            candidate
            for candidate in dream_projection.candidates()
            if candidate["kind"] == "dream"
        )
        dream_packet = build_cognition_packet(
            dream_journal,
            dream_projection,
            entry_candidate_ids=[dream_candidate["candidate_id"]],
            immediate_context={
                "prompt": "consider dream material",
                "include_hypotheses": True,
            },
        )

        append_failed_outcome(rehearsal_journal, "generic action failed")
        rehearsal = run_rehearsal_cycle(rehearsal_journal, immediate_context={"label": "phase 10"})
        assert rehearsal["rehearsal_event"] is not None
        rehearsal_projection.project_journal(rehearsal_journal)
        rehearsal_candidate = next(
            candidate
            for candidate in rehearsal_projection.candidates()
            if candidate["kind"] == "rehearsal"
        )
        rehearsal_packet = build_cognition_packet(
            rehearsal_journal,
            rehearsal_projection,
            entry_candidate_ids=[rehearsal_candidate["candidate_id"]],
            immediate_context={
                "prompt": "consider rehearsal material",
                "include_simulations": True,
            },
        )

        dream_boundary = dream_packet["retrieval_summary"]["provisional_boundaries"][0]
        assert dream_boundary["epistemic_status"] == "hypothesis"
        assert dream_boundary["not_factual"] is True
        assert dream_boundary["contribution_policy"] == "may_shape_internal_attention_but_not_factual_memory_or_vitality"

        rehearsal_boundary = rehearsal_packet["retrieval_summary"]["provisional_boundaries"][0]
        assert rehearsal_boundary["epistemic_status"] == "simulation"
        assert rehearsal_boundary["not_factual"] is True
        assert rehearsal_boundary["simulation_material"] is True
        provisional_component = next(
            item
            for item in rehearsal_packet["vitality_summary"]["components"]
            if item["component_id"] == "provisional_boundary"
        )
        assert provisional_component["contribution"] == "neutral"
        assert "why_not_positive" in provisional_component
    finally:
        dream_projection.close()
        dream_journal.close()
        dream_tmp.cleanup()
        rehearsal_projection.close()
        rehearsal_journal.close()
        rehearsal_tmp.cleanup()


def test_projection_or_retrieval_present_but_unused_cannot_be_accepted():
    tmp, journal, projection, packet = build_fixture_packet()
    try:
        mutant = copy.deepcopy(packet)
        mutant["packet_status"] = "accepted"
        mutant["selected_next_step"]["retrieval_path_refs"] = []
        mutant["selected_next_step"]["projection_candidate_refs"] = []
        mutant["attention_allocation"]["selected_attention_targets"][0]["retrieval_path_refs"] = []
        mutant["attention_allocation"]["selected_attention_targets"][0]["projection_candidate_refs"] = []
        mutant["influence_chain"]["retrieval_path_ids"] = []
        mutant["influence_chain"]["projection_candidate_ids"] = []

        violations = validate_cognition_packet(mutant)
        results = evaluate_cognition_mutants({"attention_ignores_retrieval": mutant})

        assert any("retrieval path" in item for item in violations)
        assert results[0]["result"] == "failed_as_expected"
    finally:
        projection.close()
        journal.close()
        tmp.cleanup()


def named_mutants(packet):
    mutants = {}

    residue_only = copy.deepcopy(packet)
    residue_only["projection_run_ref"] = {"status": "missing", "created_candidate_ids": []}
    residue_only["retrieval_summary"]["activated_candidates"] = []
    residue_only["influence_chain"]["projection_candidate_ids"] = []
    residue_only["influence_chain"]["retrieval_path_ids"] = []
    residue_only["claim_evidence_refs"] = []
    mutants["residue_only"] = residue_only

    projection_free = copy.deepcopy(packet)
    projection_free["projection_run_ref"]["created_candidate_ids"] = []
    projection_free["influence_chain"]["projection_candidate_ids"] = []
    mutants["projection_free"] = projection_free

    retrieval_free = copy.deepcopy(packet)
    retrieval_free["retrieval_summary"]["path_ids"] = []
    retrieval_free["influence_chain"]["retrieval_path_ids"] = []
    retrieval_free["selected_next_step"]["retrieval_path_refs"] = []
    mutants["retrieval_free"] = retrieval_free

    attention_ignores = copy.deepcopy(packet)
    attention_ignores["attention_allocation"]["selected_attention_targets"][0]["retrieval_path_refs"] = []
    attention_ignores["selected_next_step"]["retrieval_path_refs"] = []
    attention_ignores["influence_chain"]["retrieval_path_ids"] = []
    mutants["attention_ignores_retrieval"] = attention_ignores

    posthoc = copy.deepcopy(packet)
    posthoc["selected_next_step"]["retrieval_path_refs"] = ["rpath_forged"]
    posthoc["selected_next_step"]["projection_candidate_refs"] = ["cand_forged"]
    mutants["posthoc_explainer"] = posthoc

    salience_only = copy.deepcopy(packet)
    salience_only["claim_evidence_refs"] = []
    salience_only["influence_chain"]["retrieval_path_ids"] = []
    mutants["salience_only"] = salience_only

    irrelevant = copy.deepcopy(packet)
    irrelevant["particularity"]["present"] = True
    irrelevant["particularity"]["retrieval_path_refs"] = ["rpath_irrelevant"]
    mutants["irrelevant_history_personalizer"] = irrelevant

    shuffled = copy.deepcopy(packet)
    shuffled["retrieval_summary"]["invalid_evidence_refs"] = [
        {"path_id": packet["influence_chain"]["retrieval_path_ids"][0], "reason": "source hash mismatch"}
    ]
    mutants["shuffled_provenance"] = shuffled

    scope_leaker = copy.deepcopy(packet)
    scope_leaker["runtime_modules_loaded"] = ["agent"]
    mutants["scope_leaker"] = scope_leaker

    formulaic = copy.deepcopy(packet)
    formulaic["reflection_diagnostics"]["formulaic_blocked"] = True
    mutants["formulaic_reflector"] = formulaic

    legacy = copy.deepcopy(packet)
    legacy["runtime_modules_loaded"] = ["mcp_server", "retrieval"]
    mutants["legacy_runtime_importer"] = legacy

    for mutant in mutants.values():
        mutant["packet_status"] = "accepted"
    return mutants


def test_named_phase_10_mutants_fail_acceptance_gate():
    tmp, journal, projection, packet = build_fixture_packet()
    try:
        results = evaluate_cognition_mutants(named_mutants(packet))

        assert {item["mutant_name"] for item in results} == {
            "residue_only",
            "projection_free",
            "retrieval_free",
            "attention_ignores_retrieval",
            "posthoc_explainer",
            "salience_only",
            "irrelevant_history_personalizer",
            "shuffled_provenance",
            "scope_leaker",
            "formulaic_reflector",
            "legacy_runtime_importer",
        }
        assert all(item["result"] == "failed_as_expected" for item in results)
    finally:
        projection.close()
        journal.close()
        tmp.cleanup()


def test_rest_is_valid_repertoire_decision_when_cited_by_history():
    tmp, journal, projection, packet = build_fixture_packet(
        context={
            "prompt": "let unresolved material settle",
            "repertoire_preference": "rest",
        }
    )
    try:
        assert packet["packet_status"] == "accepted"
        assert packet["selected_next_step"]["class"] == "rest"
        assert packet["selected_next_step"]["retrieval_path_refs"]
        assert packet["governance_decisions"][-1]["decision"] == "private_reflection_allowed"
    finally:
        projection.close()
        journal.close()
        tmp.cleanup()


def test_importing_cognition_does_not_load_legacy_runtime_modules():
    for module in {
        "agent",
        "modes",
        "mcp_server",
        "retrieval",
        "forgetting",
        "embeddings",
        "db",
        "schema",
        "seed",
    }:
        sys.modules.pop(module, None)

    __import__("cognition")

    assert "cognition" in sys.modules
    assert not {
        "agent",
        "modes",
        "mcp_server",
        "retrieval",
        "forgetting",
        "embeddings",
        "db",
        "schema",
        "seed",
    } & set(sys.modules)


def test_service_free_smoke_script_runs_without_meno_launcher():
    script = os.path.join(os.path.dirname(__file__), "..", "src", "cognition_smoke.py")

    result = subprocess.run(
        [sys.executable, script],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "accepted" in result.stdout
