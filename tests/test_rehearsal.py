"""Phase 7 rehearsal workflow tests."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from journal import JournalStore, JournalValidationError, unknown_residue  # noqa: E402
from memory_projection import ProjectionStore  # noqa: E402
from rehearsal import append_rehearsal_outcome, run_rehearsal_cycle  # noqa: E402
from typed_retrieval import RetrievalQuery, retrieve  # noqa: E402


def make_stores():
    tmp = tempfile.TemporaryDirectory()
    journal = JournalStore(os.path.join(tmp.name, "journal.sqlite3"))
    projection = ProjectionStore(os.path.join(tmp.name, "projection.sqlite3"))
    return tmp, journal, projection


def residue(tension="rehearsal"):
    data = unknown_residue("rehearsal-test")
    for field, value in {
        "salience": 0.8,
        "attention_target": "rehearsal",
        "uncertainty": 0.4,
        "open_tensions": tension,
        "drive_refs": ["rehearsal"],
        "importance_reason": "rehearsal fixture",
        "affect_valence": "cautious",
        "expected_outcome": "dry run",
    }.items():
        data[field] = {
            "value": value,
            "source": "rehearsal-test",
            "epistemic_status": "authored",
        }
    return data


def context():
    return {"active_task": "phase-7-rehearsal", "source_channel": "test"}


def append_observation(journal, subject="source", evidence="baseline"):
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
        residue=residue(evidence),
    )


def append_failed_outcome(journal, observed_result):
    source = append_observation(journal, "attempt", "prior approach")
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


def candidate_ids(result):
    return {item["candidate_id"] for item in result["activated_candidates"]}


def test_same_context_different_history_shapes_rehearsal_strategy():
    tmp1, journal1, projection1 = make_stores()
    tmp2, journal2, projection2 = make_stores()
    try:
        append_failed_outcome(journal1, "forgot to validate falsification")
        append_failed_outcome(journal2, "used private data in export rehearsal")

        rehearsal1 = run_rehearsal_cycle(journal1, immediate_context={"label": "same task"})
        rehearsal2 = run_rehearsal_cycle(journal2, immediate_context={"label": "same task"})

        payload1 = rehearsal1["rehearsal_event"]["payload"]
        payload2 = rehearsal2["rehearsal_event"]["payload"]
        assert payload1["current_or_failed_approach"] != payload2["current_or_failed_approach"]
        assert payload1["predicted_failure_modes"] != payload2["predicted_failure_modes"]
        assert payload1["not_executed"] is True
    finally:
        journal1.close()
        projection1.close()
        tmp1.cleanup()
        journal2.close()
        projection2.close()
        tmp2.cleanup()


def test_no_eligible_target_produces_no_rehearsal_event():
    tmp, journal, projection = make_stores()
    try:
        append_observation(journal, "neutral", "no failure or correction")

        result = run_rehearsal_cycle(journal)

        assert result["rehearsal_event"] is None
        assert result["target_refs"] == []
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_manual_string_rehearsal_payload_is_rejected():
    tmp, journal, projection = make_stores()
    try:
        try:
            journal.append_event(
                event_type="rehearsal",
                epistemic_status="simulation",
                actor="meno",
                source="test",
                capture_method="manual",
                payload={
                    "target": "generic task",
                    "strategy_variant": "try tests first",
                    "simulated_trace": ["do it"],
                    "predicted_failure_modes": ["maybe fails"],
                },
                context=context(),
                residue=residue(),
            )
            assert False, "manual string rehearsal must not bypass workflow"
        except JournalValidationError as exc:
            assert "rehearsal events must use rehearsal workflow" in str(exc)
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_falsifying_outcome_does_not_create_confirmation_relation():
    tmp, journal, projection = make_stores()
    try:
        append_failed_outcome(journal, "generic graph builder failed")
        rehearsal = run_rehearsal_cycle(journal)["rehearsal_event"]
        prediction_id = rehearsal["payload"]["predicted_failure_modes"][0]["prediction_id"]
        append_rehearsal_outcome(
            journal,
            rehearsal_event_id=rehearsal["id"],
            observed_result="the same failure repeated",
            match=False,
            prediction_results=[
                {
                    "prediction_id": prediction_id,
                    "result": "falsified",
                    "rationale": "observed outcome repeated the simulated failure",
                }
            ],
        )

        projection.project_journal(journal)

        assert any(edge["edge_type"] == "outcome_falsification" for edge in projection.edges())
        assert not any(edge["edge_type"] == "outcome_confirmation" for edge in projection.edges())
        assert any(relation["relation_type"] == "outcome_falsifies" for relation in projection.relations())
        assert not any(relation["relation_type"] == "outcome_confirms" for relation in projection.relations())
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_explicit_retrieval_marks_direct_rehearsal_as_simulation_not_factual():
    tmp, journal, projection = make_stores()
    try:
        append_failed_outcome(journal, "missed validation criterion")
        run_rehearsal_cycle(journal, immediate_context={"label": "retrieval check"})
        projection.project_journal(journal)
        rehearsal_candidate = next(candidate for candidate in projection.candidates() if candidate["kind"] == "rehearsal")

        default = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[rehearsal_candidate["candidate_id"]]),
        )
        assert rehearsal_candidate["candidate_id"] not in candidate_ids(default)

        included = retrieve(
            projection,
            RetrievalQuery(
                entry_candidate_ids=[rehearsal_candidate["candidate_id"]],
                include_simulations=True,
            ),
        )
        result = next(
            item for item in included["activated_candidates"]
            if item["candidate_id"] == rehearsal_candidate["candidate_id"]
        )
        assert result["result_semantics"]["simulation_material"] is True
        assert result["result_semantics"]["not_factual"] is True
        assert result["result_semantics"]["ordinary_recall"] is False
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()
