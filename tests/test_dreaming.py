"""Phase 6 dreaming workflow tests."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dreaming import append_dream_review_event, run_dream_cycle  # noqa: E402
from journal import JournalStore, JournalValidationError, unknown_residue  # noqa: E402
from memory_projection import ProjectionStore  # noqa: E402
from typed_retrieval import RetrievalQuery, retrieve  # noqa: E402


def make_stores():
    tmp = tempfile.TemporaryDirectory()
    journal = JournalStore(os.path.join(tmp.name, "journal.sqlite3"))
    projection = ProjectionStore(os.path.join(tmp.name, "projection.sqlite3"))
    return tmp, journal, projection


def residue(tension, *, export_allowed=False, attention="dreaming", salience=0.7):
    data = unknown_residue("dream-test")
    values = {
        "salience": salience,
        "attention_target": attention,
        "uncertainty": 0.6,
        "open_tensions": tension,
        "drive_refs": ["integration"],
        "importance_reason": f"unresolved: {tension}",
        "affect_valence": "unsettled",
        "expected_outcome": "waking review",
    }
    for field, value in values.items():
        data[field] = {
            "value": value,
            "source": "dream-test",
            "epistemic_status": "authored",
        }
    return data


def context():
    return {"active_task": "phase-6-dreaming", "source_channel": "test"}


def append_observation(journal, subject, evidence, *, residue_value=None, export_allowed=False):
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
        residue=residue_value or residue(f"{subject}/{evidence} unresolved", export_allowed=export_allowed),
        privacy_scope={
            "retention": "local",
            "exposure": "local-only",
            "export_allowed": export_allowed,
        },
    )


def candidate_ids(result):
    return {item["candidate_id"] for item in result["activated_candidates"]}


def test_same_context_different_history_shapes_different_dream_fragments():
    tmp1, journal1, _projection1 = make_stores()
    tmp2, journal2, _projection2 = make_stores()
    try:
        append_observation(journal1, "same prompt", "bridge identity through forgetting")
        append_observation(journal2, "same prompt", "bridge rehearsal through dry runs")

        dream1 = run_dream_cycle(journal1, immediate_context={"label": "same immediate context"})
        dream2 = run_dream_cycle(journal2, immediate_context={"label": "same immediate context"})

        fragment1 = dream1["generated_candidates"][0]
        fragment2 = dream2["generated_candidates"][0]
        assert fragment1["label"] != fragment2["label"]
        assert fragment1["useful_if"] != ""
        assert fragment2["source_residue_refs"] != fragment1["source_residue_refs"]
    finally:
        journal1.close()
        _projection1.close()
        tmp1.cleanup()
        journal2.close()
        _projection2.close()
        tmp2.cleanup()


def test_no_eligible_residue_produces_no_substantive_dream():
    tmp, journal, projection = make_stores()
    try:
        journal.append_event(
            event_type="conversation",
            epistemic_status="authored",
            actor="pid",
            source="test",
            capture_method="manual",
            payload={
                "speaker": "pid",
                "message": "plain note",
                "channel": "test",
                "turn_id": "turn-1",
            },
            context=context(),
            residue=unknown_residue("test"),
        )

        dream = run_dream_cycle(journal, projection=projection)

        assert dream["dream_event"] is None
        assert dream["generated_candidates"] == []
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_dream_event_rejects_arbitrary_string_candidates():
    tmp, journal, projection = make_stores()
    try:
        append_observation(journal, "source", "unsettled bridge")
        try:
            journal.append_event(
                event_type="dream",
                epistemic_status="hypothesis",
                actor="meno",
                source="test",
                capture_method="manual",
                payload={
                    "residues_used": ["unsettled bridge"],
                    "generated_candidates": ["generic insight"],
                    "uncertainty_notes": "none",
                },
                context=context(),
                residue=residue("manual string dream"),
            )
            assert False, "string dreams must not bypass the workflow"
        except JournalValidationError as exc:
            assert "dream events must use dream workflow" in str(exc)
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_private_residue_is_excluded_from_export_scope():
    tmp, journal, projection = make_stores()
    try:
        append_observation(journal, "private", "unresolved private bridge", export_allowed=False)
        append_observation(journal, "public", "unresolved public bridge", export_allowed=True)

        dream = run_dream_cycle(
            journal,
            projection=projection,
            requested_scope={"export": True},
            immediate_context={"label": "export review"},
        )

        assert all(ref["privacy_scope"]["export_allowed"] for ref in dream["residues_used"])
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_structured_dream_projects_and_retrieves_only_as_not_factual_hypothesis():
    tmp, journal, projection = make_stores()
    try:
        append_observation(journal, "identity", "forgetting leaves rediscovery islands")
        dream = run_dream_cycle(journal, projection=projection)
        projection.project_journal(journal)

        dream_candidates = [candidate for candidate in projection.candidates() if candidate["kind"] == "dream"]
        assert dream_candidates
        dream_candidate = dream_candidates[0]
        assert dream_candidate["epistemic_status"] == "hypothesis"
        assert dream_candidate["acceptance_status"] == "provisional"
        assert dream["generated_candidates"][0]["not_factual"] is True

        default = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[dream_candidate["candidate_id"]]),
        )
        assert dream_candidate["candidate_id"] not in candidate_ids(default)

        included = retrieve(
            projection,
            RetrievalQuery(
                entry_candidate_ids=[dream_candidate["candidate_id"]],
                include_hypotheses=True,
            ),
        )
        assert dream_candidate["candidate_id"] in candidate_ids(included)
        result = next(
            item for item in included["activated_candidates"] if item["candidate_id"] == dream_candidate["candidate_id"]
        )
        assert result["result_semantics"]["ordinary_recall"] is True
        assert result["retrieval_weight"]["evidence_accumulation_factor"] == 1.0

        residue_candidate_id = next(
            edge["target_candidate_id"]
            for edge in projection.edges()
            if edge["edge_type"] == "dream_association"
            and edge["source_candidate_id"] == dream_candidate["candidate_id"]
        )
        traversed = retrieve(
            projection,
            RetrievalQuery(
                entry_candidate_ids=[dream_candidate["candidate_id"]],
                include_hypotheses=True,
            ),
        )
        residue_result = next(
            item for item in traversed["activated_candidates"] if item["candidate_id"] == residue_candidate_id
        )
        assert residue_result["result_semantics"]["dream_material"] is True
        assert residue_result["result_semantics"]["not_factual"] is True
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_waking_review_cannot_corroborate_without_later_observed_evidence():
    tmp, journal, projection = make_stores()
    try:
        append_observation(journal, "source", "unresolved rehearsal bridge")
        dream = run_dream_cycle(journal, projection=projection)["dream_event"]
        fragment_id = dream["payload"]["generated_candidates"][0]["fragment_id"]

        try:
            append_dream_review_event(
                journal,
                dream_event_id=dream["id"],
                fragment_id=fragment_id,
                review_decision="corroborate_observation",
                rationale="too soon",
            )
            assert False, "corroboration requires later observation"
        except JournalValidationError as exc:
            assert "requires later observed evidence" in str(exc)

        observed = append_observation(journal, "later", "same bridge appears in observed work")
        review = append_dream_review_event(
            journal,
            dream_event_id=dream["id"],
            fragment_id=fragment_id,
            review_decision="corroborate_observation",
            rationale="later observation matches useful fragment",
            observed_evidence_event_ids=[observed["id"]],
        )

        assert review["event_type"] == "dream_review"
        assert journal.get_event(dream["id"])["epistemic_status"] == "hypothesis"
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()
