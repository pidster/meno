"""Phase 2 memory projection tests.

These tests exercise the fixture-first projection contract. They intentionally
avoid legacy SurrealDB modules and assert semantic rows, not graph counts.
"""

import os
import sqlite3
import tempfile

sys_path = os.path.join(os.path.dirname(__file__), "..", "src")
import sys

sys.path.insert(0, sys_path)

from journal import DEFAULT_PRIVACY_SCOPE, DEFAULT_RESOURCE_SCOPE, JournalStore, unknown_residue  # noqa: E402
from dreaming import run_dream_cycle  # noqa: E402
from memory_projection import ProjectionError, ProjectionStore, ProjectionValidationError  # noqa: E402
from rehearsal import append_rehearsal_outcome, run_rehearsal_cycle  # noqa: E402


REQUIRED_TABLES = {
    "projection_runs",
    "memory_candidates",
    "memory_edges",
    "projection_decisions",
    "candidate_transitions",
    "projection_relations",
    "projection_rejections",
    "projection_evidence_refs",
}


def make_stores():
    tmp = tempfile.TemporaryDirectory()
    journal = JournalStore(os.path.join(tmp.name, "journal.sqlite3"))
    projection = ProjectionStore(os.path.join(tmp.name, "projection.sqlite3"))
    return tmp, journal, projection


def residue(tension="projection", attention="memory projection"):
    data = unknown_residue("projection-test")
    for field, value in {
        "salience": 0.7,
        "attention_target": attention,
        "uncertainty": 0.2,
        "open_tensions": tension,
        "drive_refs": ["convergence"],
        "importance_reason": "projection fixture",
        "affect_valence": "neutral",
        "expected_outcome": "typed projection",
    }.items():
        data[field] = {
            "value": value,
            "source": "projection-test",
            "epistemic_status": "authored",
        }
    return data


def context(task="phase-2-projection"):
    return {"active_task": task, "source_channel": "test"}


def append_conversation(journal, message, *, epistemic_status="authored", turn_id="turn"):
    return journal.append_event(
        event_type="conversation",
        epistemic_status=epistemic_status,
        actor="pid",
        source="test",
        capture_method="manual",
        payload={
            "speaker": "pid",
            "message": message,
            "channel": "test",
            "turn_id": turn_id,
        },
        context=context(),
        residue=residue(),
    )


def append_dream_source(journal, tension):
    return journal.append_event(
        event_type="conversation",
        epistemic_status="authored",
        actor="pid",
        source="test",
        capture_method="manual",
        payload={
            "speaker": "pid",
            "message": "dream source",
            "channel": "test",
            "turn_id": "dream-source",
        },
        context=context(),
        residue=residue(tension=tension),
    )


def append_dream(journal):
    return run_dream_cycle(
        journal,
        immediate_context={"label": "projection test"},
        actor="meno",
        source="test",
    )["dream_event"]


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
        residue=residue(tension="observed cooccurrence"),
    )


def append_failed_outcome(journal, observed_result="generic graph builder failed"):
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
        residue=residue(tension=observed_result),
        links=[
            {
                "type": "derived_from",
                "target_event_id": source["id"],
                "rationale": "failed outcome seeds rehearsal",
            }
        ],
    )


def append_decision(journal, selected):
    return journal.append_event(
        event_type="decision",
        epistemic_status="authored",
        actor="pid",
        source="test",
        capture_method="manual",
        payload={
            "options_considered": ["vim", selected],
            "selected_option": selected,
            "reason": "actual decision evidence",
            "constraints": ["fixture"],
        },
        context=context(),
        residue=residue(tension="preference from decision"),
    )


def project(journal, projection):
    projection.project_journal(journal)
    return projection.candidates(), projection.edges(), projection.relations(), projection.rejections()


def test_projection_schema_is_pinned_to_required_tables():
    tmp, journal, projection = make_stores()
    try:
        assert REQUIRED_TABLES.issubset(projection.required_tables())
        expected_fks = {
            "memory_edges": {"memory_candidates", "projection_runs"},
            "projection_decisions": {"memory_candidates", "projection_runs"},
            "candidate_transitions": {"memory_candidates", "projection_decisions"},
            "projection_relations": {"memory_candidates", "projection_decisions", "projection_runs"},
            "projection_rejections": {"projection_runs"},
            "projection_evidence_refs": {"projection_decisions"},
        }
        for table, expected in expected_fks.items():
            actual = {
                row[2]
                for row in projection._conn.execute(  # noqa: SLF001 - schema contract test
                    f"PRAGMA foreign_key_list({table})"
                ).fetchall()
            }
            assert expected.issubset(actual), (table, actual)

        orphan_inserts = [
            """
            INSERT INTO memory_edges (
                id, source_candidate_id, target_candidate_id, edge_type, direction,
                epistemic_status, confidence_json, source_refs_json,
                privacy_scope_json, resource_scope_json, semantic_fingerprint,
                projection_run_id
            ) VALUES (
                'edge-orphan', 'missing-a', 'missing-b', 'observed_cooccurrence',
                'symmetric', 'observed', '{}', '[]', '{}', '{}', 'fp', 'missing-run'
            )
            """,
            """
            INSERT INTO projection_decisions (
                projection_record_id, candidate_id, decision, acceptance_status_after,
                relation_status_after, projection_run_id, projection_rule_id,
                projection_version, projection_fingerprint, source_refs_json,
                confidence_record_json, reason, timestamp
            ) VALUES (
                'decision-orphan', 'missing-candidate', 'created', 'accepted',
                'active', 'missing-run', 'rule', 1, 'fp', '[]', '{}', 'why', 'now'
            )
            """,
            """
            INSERT INTO candidate_transitions (
                id, candidate_id, to_acceptance_status, to_relation_status,
                source_refs_json, projection_decision_id, reason, timestamp
            ) VALUES (
                'transition-orphan', 'missing-candidate', 'accepted', 'active',
                '[]', 'missing-decision', 'why', 'now'
            )
            """,
            """
            INSERT INTO projection_relations (
                id, relation_type, source_candidate_id, target_candidate_id,
                direction, source_refs_json, privacy_scope_json, resource_scope_json,
                confidence_json, projection_run_id, projection_rule_id,
                projection_version, projection_decision_id, reason, timestamp
            ) VALUES (
                'relation-orphan', 'conflicts_with', 'missing-a', 'missing-b',
                'symmetric', '[]', '{}', '{}', '{}', 'missing-run', 'rule', 1,
                'missing-decision', 'why', 'now'
            )
            """,
            """
            INSERT INTO projection_rejections (
                id, source_refs_json, candidate_kind, normalized_claim,
                epistemic_status, privacy_scope_json, resource_scope_json,
                rejection_reason, rejecting_rule_id, projection_run_id, timestamp
            ) VALUES (
                'rejection-orphan', '[]', 'concept', 'x', 'authored', '{}', '{}',
                'why', 'rule', 'missing-run', 'now'
            )
            """,
            """
            INSERT INTO projection_evidence_refs (
                id, projection_record_id, record_type, record_id, event_id,
                event_sequence, event_hash, event_type, event_epistemic_status,
                payload_path, residue_field, link_type, replay_trace_item,
                source_selector, source_value_hash, rationale
            ) VALUES (
                'eref-orphan', 'missing-decision', 'decision', 'missing-decision',
                'event', 1, 'hash', 'conversation', 'authored', 'payload.message',
                'not_applicable', 'not_applicable', 'not_applicable',
                'payload.message', 'hash', 'why'
            )
            """,
        ]
        for statement in orphan_inserts:
            try:
                projection._conn.execute(statement)  # noqa: SLF001 - schema contract test
                assert False, "orphan insert should fail foreign key checks"
            except sqlite3.IntegrityError:
                pass
        projection.project_journal(journal)
        run = projection.runs()[0]
        assert run["status"] == "succeeded"
        assert run["source_event_hashes"] == {}
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_authored_claim_is_rejected_while_observed_claim_is_accepted():
    tmp, journal, projection = make_stores()
    try:
        append_conversation(journal, "The bridge is true", epistemic_status="authored")
        append_conversation(
            journal,
            "The bridge is true",
            epistemic_status="observed",
            turn_id="turn-observed",
        )
        append_observation(journal, "bridge sensor", "the bridge")

        candidates, _edges, _relations, rejections = project(journal, projection)

        concept = projection.candidate("concept", "the bridge")
        assert concept["acceptance_status"] == "accepted"
        assert concept["epistemic_status"] == "observed"
        assert concept["confidence"]["level"] == "strong"
        assert any(
            rejection["candidate_kind"] == "concept"
            and rejection["normalized_claim"] == "the bridge"
            and "conversation text" in rejection["rejection_reason"]
            for rejection in rejections
        )
        assert sum(
            1 for rejection in rejections if rejection["normalized_claim"] == "the bridge"
        ) == 2
        assert rejections
        for rejection in rejections:
            for ref in rejection["source_refs"]:
                projection.validate_evidence_ref(ref, journal)
        assert all(candidate["kind"] != "concept" or candidate["label"] != "The bridge" for candidate in candidates)
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_dream_association_and_observed_cooccurrence_stay_semantically_distinct():
    tmp, journal, projection = make_stores()
    try:
        append_dream_source(journal, "A/B loose association")
        append_dream(journal)
        append_observation(journal, "A", "B")

        candidates, edges, _relations, _rejections = project(journal, projection)

        dream = next(candidate for candidate in candidates if candidate["kind"] == "dream")
        observed = projection.candidate("entity", "A")
        assert dream["acceptance_status"] == "provisional"
        assert dream["epistemic_status"] == "hypothesis"
        assert observed["acceptance_status"] == "accepted"
        assert {edge["edge_type"] for edge in edges} >= {
            "dream_association",
            "observed_cooccurrence",
        }
        assert any(
            edge["edge_type"] == "dream_association"
            and edge["epistemic_status"] == "hypothesis"
            for edge in edges
        )
        assert any(
            candidate["kind"] == "concept"
            and candidate["label"] == "dream residue:A/B loose association"
            for candidate in candidates
        )
        assert not any(
            candidate["label"] in {"A relates to B", "A", "B"}
            and candidate["kind"] in {"entity", "concept"}
            and candidate["acceptance_status"] == "accepted"
            and candidate["epistemic_status"] == "hypothesis"
            for candidate in candidates
        )
        assert len(dream["source_refs"]) >= 3
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_dream_only_input_cannot_create_factual_entities_or_cooccurrence():
    tmp, journal, projection = make_stores()
    try:
        append_dream_source(journal, "A/B loose association")
        append_dream(journal)

        candidates, edges, _relations, _rejections = project(journal, projection)

        assert any(candidate["kind"] == "dream" for candidate in candidates)
        assert all(
            not (
                candidate["label"] in {"A", "B", "A relates to B"}
                and candidate["kind"] in {"entity", "concept"}
                and candidate["acceptance_status"] == "accepted"
            )
            for candidate in candidates
        )
        assert all(edge["edge_type"] != "observed_cooccurrence" for edge in edges)
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_rehearsal_prediction_and_observed_outcome_are_linked_without_promoting_simulation():
    tmp, journal, projection = make_stores()
    try:
        append_failed_outcome(journal)
        rehearsal = run_rehearsal_cycle(
            journal,
            immediate_context={"label": "projection implementation"},
        )["rehearsal_event"]
        prediction_id = rehearsal["payload"]["predicted_observations"][0]["prediction_id"]
        append_rehearsal_outcome(
            journal,
            rehearsal_event_id=rehearsal["id"],
            observed_result="fixture-first worked",
            match=True,
            prediction_results=[
                {
                    "prediction_id": prediction_id,
                    "result": "confirmed",
                    "rationale": "observed execution avoided the cited failure",
                }
            ],
        )

        _candidates, edges, relations, _rejections = project(journal, projection)

        rehearsal_candidate = projection.candidate(
            "rehearsal",
            "projection implementation via evidence-first dry run for projection implementation",
        )
        assert rehearsal_candidate["epistemic_status"] == "simulation"
        assert rehearsal_candidate["acceptance_status"] == "provisional"
        assert {
            ref["source_selector"] for ref in rehearsal_candidate["source_refs"]
        } >= {
            "payload.target_refs.0.value",
            "payload.strategy_variants.0.label",
            "payload.simulated_trace",
            "payload.predicted_failure_modes",
            "payload.not_executed",
        }
        assert any(edge["edge_type"] == "outcome_confirmation" for edge in edges)
        assert any(relation["relation_type"] == "outcome_confirms" for relation in relations)
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_rehearsal_only_input_cannot_create_accepted_outcome_or_factual_claim():
    tmp, journal, projection = make_stores()
    try:
        append_failed_outcome(journal)
        run_rehearsal_cycle(journal, immediate_context={"label": "projection implementation"})

        candidates, edges, relations, _rejections = project(journal, projection)

        rehearsal_candidate = next(candidate for candidate in candidates if candidate["kind"] == "rehearsal")
        assert rehearsal_candidate["acceptance_status"] == "provisional"
        assert all(
            candidate["acceptance_status"] == "provisional"
            for candidate in candidates
            if candidate["kind"] in {"rehearsal", "procedure"}
        )
        assert all(edge["edge_type"] != "outcome_confirmation" for edge in edges)
        assert relations == []
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_correction_supersedes_without_deleting_and_contradiction_preserves_conflict():
    tmp, journal, projection = make_stores()
    try:
        original = append_conversation(journal, "Original claim", turn_id="original")
        journal.append_event(
            event_type="correction",
            epistemic_status="correction",
            actor="pid",
            source="test",
            capture_method="manual",
            payload={
                "target": original["id"],
                "corrected_claim": "Corrected claim",
                "reason": "better evidence",
            },
            context=context(),
            residue=residue(tension="correction"),
            links=[
                {
                    "type": "corrects",
                    "target_event_id": original["id"],
                    "rationale": "better evidence",
                    "target_field": "payload.message",
                }
            ],
        )
        disputed = append_conversation(journal, "Disputed claim", turn_id="disputed")
        journal.append_event(
            event_type="correction",
            epistemic_status="contradiction",
            actor="pid",
            source="test",
            capture_method="manual",
            payload={
                "target": disputed["id"],
                "corrected_claim": "Competing claim",
                "reason": "preserve both sides",
            },
            context=context(),
            residue=residue(tension="contradiction"),
            links=[
                {
                    "type": "contradicts",
                    "target_event_id": disputed["id"],
                    "rationale": "preserve contested claims",
                }
            ],
        )

        candidates, _edges, relations, _rejections = project(journal, projection)

        labels = {candidate["label"]: candidate for candidate in candidates}
        assert labels[f"utterance:{original['id']}"]["relation_status"] == "superseded"
        assert labels["Corrected claim"]["relation_status"] == "active"
        assert labels[f"utterance:{disputed['id']}"]["relation_status"] == "conflicted"
        assert labels["Competing claim"]["relation_status"] == "conflicted"
        assert {relation["relation_type"] for relation in relations} >= {
            "corrects",
            "conflicts_with",
        }
        for relation in relations:
            assert relation["privacy_scope"]
            assert relation["resource_scope"]
            assert relation["confidence"]
            for ref in relation["source_refs"]:
                projection.validate_evidence_ref(ref, journal)
        conflicted_ids = {
            labels[f"utterance:{disputed['id']}"]["candidate_id"],
            labels["Competing claim"]["candidate_id"],
        }
        assert conflicted_ids.issubset(
            {
                transition["candidate_id"]
                for transition in projection.transitions()
                if transition["to_relation_status"] == "conflicted"
            }
        )
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_preference_threshold_distinguishes_self_report_from_decision_evidence():
    tmp, journal, projection = make_stores()
    try:
        append_conversation(journal, "I prefer vim", turn_id="self-report")
        append_decision(journal, "vim")

        candidates, _edges, _relations, _rejections = project(journal, projection)

        preference = projection.candidate("preference", "vim")
        assert preference["acceptance_status"] == "accepted"
        assert preference["confidence"]["level"] == "moderate"
        assert any(
            decision["projection_rule_id"] == "isolated_preference_self_report"
            and decision["acceptance_status_after"] == "provisional"
            for decision in projection.decisions()
        )
        assert any(
            candidate["kind"] == "preference"
            and candidate["label"] == "vim"
            for candidate in candidates
        )
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_isolated_preference_self_report_stays_provisional():
    tmp, journal, projection = make_stores()
    try:
        append_conversation(journal, "I prefer vim", turn_id="self-report")

        project(journal, projection)

        preference = projection.candidate("preference", "vim")
        assert preference["acceptance_status"] == "provisional"
        assert preference["confidence"]["level"] == "weak"
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_repeated_weak_preference_traces_accumulate_without_acceptance():
    tmp, journal, projection = make_stores()
    try:
        for index in range(3):
            append_conversation(journal, "I prefer vim", turn_id=f"self-report-{index}")

        project(journal, projection)

        preference = projection.candidate("preference", "vim")
        assert preference["acceptance_status"] == "provisional"
        assert len(preference["source_refs"]) == 3
        assert preference["confidence"]["corroboration_count"] == 3
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_preference_promotion_accumulates_prior_self_report_and_replays_cleanly():
    tmp, journal, projection = make_stores()
    try:
        append_conversation(
            journal,
            "I prefer vim",
            turn_id="local-self-report",
        )
        append_decision(journal, "vim")

        projection.project_journal(journal)
        first_decision_ids = [d["projection_record_id"] for d in projection.decisions()]
        first_preference = projection.candidate("preference", "vim")
        assert first_preference["acceptance_status"] == "accepted"
        assert len(first_preference["source_refs"]) == 2
        assert first_preference["confidence"]["corroboration_count"] == 2

        second_run = projection.project_journal(journal)
        second_run_row = next(run for run in projection.runs() if run["id"] == second_run)

        assert second_run_row["created_candidate_ids"] == []
        assert [d["projection_record_id"] for d in projection.decisions()] == first_decision_ids
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_restrictive_scope_survives_later_broader_evidence_for_same_candidate():
    tmp, journal, projection = make_stores()
    try:
        append_conversation(journal, "I prefer vim", turn_id="restricted-self-report")
        journal.append_event(
            event_type="decision",
            epistemic_status="authored",
            actor="pid",
            source="test",
            capture_method="manual",
            payload={
                "options_considered": ["vim", "emacs"],
                "selected_option": "vim",
                "reason": "decision evidence with broader scope",
                "constraints": ["fixture"],
            },
            context=context(),
            residue=residue(tension="broader decision scope"),
            privacy_scope={
                **DEFAULT_PRIVACY_SCOPE,
                "exposure": "public",
                "export_allowed": True,
            },
            resource_scope={
                **DEFAULT_RESOURCE_SCOPE,
                "network_access": True,
                "external_contact": True,
                "autonomous_spend": True,
                "compute_escalation": True,
            },
        )

        project(journal, projection)

        preference = projection.candidate("preference", "vim")
        assert preference["privacy_scope"]["export_allowed"] is False
        assert preference["privacy_scope"]["exposure"] == "local-only"
        assert preference["resource_scope"]["network_access"] is False
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_projection_is_idempotent_and_uses_resolvable_below_event_refs():
    tmp, journal, projection = make_stores()
    try:
        append_observation(journal, "A", "B")

        first_run = projection.project_journal(journal)
        first_candidates = projection.candidates()
        first_decisions = projection.decisions()
        second_run = projection.project_journal(journal)

        assert first_run != second_run
        assert {
            run["projection_key"] for run in projection.runs()
        } == {projection.runs()[0]["projection_key"]}
        assert [c["candidate_id"] for c in first_candidates] == [
            c["candidate_id"] for c in projection.candidates()
        ]
        assert [d["projection_record_id"] for d in first_decisions] == [
            d["projection_record_id"] for d in projection.decisions()
        ]
        for decision in projection.decisions():
            for ref in decision["source_refs"]:
                projection.validate_evidence_ref(ref, journal)
        for edge in projection.edges():
            for ref in edge["source_refs"]:
                projection.validate_evidence_ref(ref, journal)
        for relation in projection.relations():
            for ref in relation["source_refs"]:
                projection.validate_evidence_ref(ref, journal)
        for rejection in projection.rejections():
            for ref in rejection["source_refs"]:
                projection.validate_evidence_ref(ref, journal)
        for ref in projection.evidence_refs():
            projection.validate_evidence_ref(ref, journal)

        bad_ref = dict(projection.decisions()[0]["source_refs"][0])
        bad_ref["source_selector"] = "event"
        try:
            projection.validate_evidence_ref(bad_ref, journal)
            assert False, "event-level-only evidence ref should fail"
        except ProjectionValidationError as exc:
            assert "event-level-only" in str(exc)
        bad_hash = dict(projection.decisions()[0]["source_refs"][0])
        bad_hash["source_value_hash"] = "stale"
        try:
            projection.validate_evidence_ref(bad_hash, journal)
            assert False, "stale source value hash should fail"
        except ProjectionValidationError as exc:
            assert "source value hash" in str(exc)
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_failed_run_persists_failure_without_accepted_partials_and_can_retry():
    tmp, journal, projection = make_stores()
    try:
        append_observation(journal, "A", "B")

        try:
            projection.project_journal(journal, fail_after_first_write=True)
            assert False, "injected failure should abort projection"
        except ProjectionError as exc:
            assert "candidate write" in str(exc)

        assert projection.runs()[0]["status"] == "failed"
        assert projection.candidates() == []
        assert projection.edges() == []
        assert projection.decisions() == []
        assert projection.relations() == []
        assert projection.rejections() == []
        assert projection.evidence_refs() == []

        projection.project_journal(journal)

        assert sorted(run["status"] for run in projection.runs()) == ["failed", "succeeded"]
        assert projection.candidate("entity", "A")["acceptance_status"] == "accepted"
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
