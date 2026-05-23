"""Phase 4 reflection workflow tests."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from journal import DEFAULT_RESOURCE_SCOPE, JournalStore, unknown_residue  # noqa: E402
from memory_projection import ProjectionStore  # noqa: E402
from reflection import (  # noqa: E402
    ReflectionValidationError,
    append_reflection_proposal_events,
    append_reflection_event,
    cite_retrieval_path,
    formulaic_reflection_report,
    history_influence_report,
    retrieval_result_hash,
)
from typed_retrieval import RetrievalQuery, retrieve  # noqa: E402


def make_stores():
    tmp = tempfile.TemporaryDirectory()
    journal = JournalStore(os.path.join(tmp.name, "journal.sqlite3"))
    projection = ProjectionStore(os.path.join(tmp.name, "projection.sqlite3"))
    return tmp, journal, projection


def context(task="phase-4-reflection"):
    return {"active_task": task, "source_channel": "test"}


def residue(tension="reflection must change something"):
    data = unknown_residue("reflection-test")
    for field, value in {
        "salience": 0.8,
        "attention_target": "reflection gate",
        "uncertainty": 0.4,
        "open_tensions": tension,
        "drive_refs": ["convergence"],
        "importance_reason": "phase 4 fixture",
        "affect_valence": "neutral",
        "expected_outcome": "auditable authored meaning",
    }.items():
        data[field] = {
            "value": value,
            "source": "reflection-test",
            "epistemic_status": "authored",
        }
    return data


def append_observation(journal, subject, evidence):
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
        residue=residue("observed reflection evidence"),
    )


def reflection_payload(source_event, retrieval_result, target_candidate):
    result_hash = retrieval_result_hash(retrieval_result)
    target = next(
        item for item in retrieval_result["activated_candidates"] if item["candidate_id"] == target_candidate
    )
    path = cite_retrieval_path(retrieval_result, target["candidate_id"])
    return {
        "cited_source_event_ids": [source_event["id"]],
        "retrieval_result_hash": result_hash,
        "cited_retrieval_paths": [path],
        "interpretive_claims": [
            {
                "type": "tension",
                "claim": "The observed evidence shifts attention from generic memory continuity to path-level auditability.",
                "cites": [path["path_id"]],
                "epistemic_status": "authored",
            }
        ],
        "open_questions": ["Which later projection rule should consume this reflection?"],
        "uncertainty_notes": ["One observation is not enough to promote this beyond authored interpretation."],
        "possible_self_deception": ["The reflection may overvalue auditability because this test is about provenance."],
        "rejected_interpretations": ["This is not evidence that all reflections are meaningful."],
        "changed_stance": "Prefer reflection artifacts that alter future attention over citation-bearing summaries.",
        "future_attention": [
            {
                "target": "reflection provenance",
                "reason": "history-specific retrieval path exposed the auditability tension",
                "resource_scope": DEFAULT_RESOURCE_SCOPE,
            }
        ],
        "proposed_graph_updates": [],
        "deferred_graph_updates": [
            {
                "reason": "No factual graph update until later observed evidence exists.",
                "source_event_ids": [source_event["id"]],
            }
        ],
    }


def test_reflection_event_is_journaled_before_projection_and_stays_provisional():
    tmp, journal, projection = make_stores()
    try:
        observed = append_observation(journal, "reflection", "path-level citations prevent generic summary")
        projection.project_journal(journal)
        subject = next(item for item in projection.candidates() if item["label"] == "reflection")
        result = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[subject["candidate_id"]], max_hops=1),
        )
        target = next(
            item for item in result["activated_candidates"] if item["candidate_id"] != subject["candidate_id"]
        )
        payload = reflection_payload(observed, result, target["candidate_id"])

        event = append_reflection_event(
            journal,
            payload=payload,
            actor="meno",
            source="test",
            context=context(),
            residue=residue(),
            retrieval_result=result,
        )
        assert event["event_type"] == "reflection"

        projection.project_journal(journal)
        reflections = [item for item in projection.candidates() if item["kind"] == "reflection"]
        assert len(reflections) == 1
        assert reflections[0]["acceptance_status"] == "provisional"
        assert reflections[0]["epistemic_status"] == "authored"
        reflective_edges = [
            edge for edge in projection.edges() if edge["edge_type"] == "reflective_interpretation"
        ]
        assert reflective_edges
        assert reflective_edges[0]["source_candidate_id"] == reflections[0]["candidate_id"]
        assert reflective_edges[0]["target_candidate_id"] == target["candidate_id"]
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_formulaic_reflection_is_rejected_even_with_citations():
    tmp, journal, projection = make_stores()
    try:
        observed = append_observation(journal, "continuity", "generic phrases can hide summary")
        projection.project_journal(journal)
        entry = next(item for item in projection.candidates() if item["label"] == "continuity")
        result = retrieve(projection, RetrievalQuery(entry_candidate_ids=[entry["candidate_id"]], max_hops=1))
        target = next(item for item in result["activated_candidates"] if item["candidate_id"] != entry["candidate_id"])
        payload = reflection_payload(observed, result, target["candidate_id"])
        payload["interpretive_claims"][0]["claim"] = "This shows the importance of continuity."

        report = formulaic_reflection_report(payload)
        assert report["formulaic"] is True
        assert any("generic phrase" in reason for reason in report["reasons"])
        try:
            append_reflection_event(
                journal,
                payload=payload,
                actor="meno",
                source="test",
                context=context(),
                residue=residue(),
                retrieval_result=result,
            )
            assert False, "formulaic reflection should be rejected"
        except ReflectionValidationError as exc:
            assert "formulaic reflection rejected" in str(exc)
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_fake_path_citation_and_redaction_leakage_are_rejected():
    tmp, journal, projection = make_stores()
    try:
        observed = append_observation(journal, "scope", "restricted source should not leak")
        projection.project_journal(journal)
        entry = next(item for item in projection.candidates() if item["label"] == "scope")
        result = retrieve(projection, RetrievalQuery(entry_candidate_ids=[entry["candidate_id"]], max_hops=1))
        target = next(item for item in result["activated_candidates"] if item["candidate_id"] != entry["candidate_id"])
        payload = reflection_payload(observed, result, target["candidate_id"])

        payload["retrieval_result_hash"] = "wrong-hash"
        try:
            append_reflection_event(
                journal,
                payload=payload,
                actor="meno",
                source="test",
                context=context(),
                residue=residue(),
                retrieval_result=result,
            )
            assert False, "retrieval hash mismatch should fail"
        except ReflectionValidationError as exc:
            assert "retrieval result hash does not match" in str(exc)

        payload = reflection_payload(observed, result, target["candidate_id"])
        payload["cited_retrieval_paths"][0]["candidate_id"] = "fake-candidate"
        try:
            append_reflection_event(
                journal,
                payload=payload,
                actor="meno",
                source="test",
                context=context(),
                residue=residue(),
                retrieval_result=result,
            )
            assert False, "candidate mismatch should fail"
        except ReflectionValidationError as exc:
            assert "retrieval path candidate mismatch" in str(exc)

        payload = reflection_payload(observed, result, target["candidate_id"])
        payload["interpretive_claims"][0]["cites"] = ["made-up-path"]
        try:
            append_reflection_event(
                journal,
                payload=payload,
                actor="meno",
                source="test",
                context=context(),
                residue=residue(),
                retrieval_result=result,
            )
            assert False, "fake path citation should fail"
        except ReflectionValidationError as exc:
            assert "claim cites unknown retrieval path" in str(exc)

        payload = reflection_payload(observed, result, target["candidate_id"])
        payload["cited_retrieval_paths"][0]["redacted"] = True
        payload["cited_retrieval_paths"][0]["redacted_terms"] = ["restricted source"]
        payload["changed_stance"] = "The restricted source is decisive"
        try:
            append_reflection_event(
                journal,
                payload=payload,
                actor="meno",
                source="test",
                context=context(),
                residue=residue(),
                retrieval_result=result,
            )
            assert False, "redaction leak should fail"
        except ReflectionValidationError as exc:
            assert "redacted retrieval material leaked" in str(exc)
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_reflection_proposals_are_separate_journal_events():
    tmp, journal, projection = make_stores()
    try:
        observed = append_observation(journal, "proposal", "proposal must be journaled")
        projection.project_journal(journal)
        entry = next(item for item in projection.candidates() if item["label"] == "proposal")
        result = retrieve(projection, RetrievalQuery(entry_candidate_ids=[entry["candidate_id"]], max_hops=1))
        target = next(item for item in result["activated_candidates"] if item["candidate_id"] != entry["candidate_id"])
        payload = reflection_payload(observed, result, target["candidate_id"])
        draft = {
            "proposed_operation": "create",
            "proposed_target_kind": "reflection",
            "source_event_ids": [observed["id"]],
            "intended_status": "provisional",
            "rationale": "reflection may seed provisional attention only",
        }
        reflection_event = append_reflection_event(
            journal,
            payload=payload,
            actor="meno",
            source="test",
            context=context(),
            residue=residue(),
            retrieval_result=result,
        )
        proposals = append_reflection_proposal_events(
            journal,
            reflection_event=reflection_event,
            proposal_drafts=[draft],
            actor="meno",
            source="test",
            context=context(),
            residue=residue(),
        )

        assert len(proposals) == 1
        assert proposals[0]["event_type"] == "graph_update_proposal"
        assert any(
            link["type"] == "derived_from" and link["target_event_id"] == reflection_event["id"]
            for link in proposals[0]["links"]
        )
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_history_influence_requires_history_specific_paths_and_dispositions():
    history_payload = {
        "cited_retrieval_paths": [{"candidate_id": "history-candidate"}],
        "future_attention": [{"target": "history-specific follow-up"}],
        "proposed_graph_updates": [],
        "deferred_graph_updates": [{"reason": "need later outcome"}],
        "rejected_interpretations": ["generic continuity summary"],
        "cited_source_event_ids": ["event-1"],
        "retrieval_result_hash": "hash",
        "interpretive_claims": [
            {
                "type": "tension",
                "claim": "history creates a specific tension",
                "cites": ["path"],
                "epistemic_status": "authored",
            }
        ],
        "open_questions": ["what next"],
        "uncertainty_notes": ["uncertain"],
        "possible_self_deception": ["overfit"],
        "changed_stance": "changed",
    }
    baseline_payload = dict(history_payload)
    baseline_payload["cited_retrieval_paths"] = [{"candidate_id": "baseline-candidate"}]
    baseline_payload["future_attention"] = [{"target": "generic follow-up"}]
    baseline_payload["deferred_graph_updates"] = [{"reason": "generic uncertainty"}]
    baseline_payload["rejected_interpretations"] = ["none"]

    report = history_influence_report(history_payload, baseline_payload)

    assert report["passes"] is True
    assert report["history_specific_candidates"] == ["history-candidate"]
