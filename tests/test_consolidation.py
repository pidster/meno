"""Phase 5 consolidation and forgetting tests."""

import copy
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from consolidation import append_retrieval_use_trace, consolidate, propose_pruning  # noqa: E402
from journal import JournalStore, content_hash, unknown_residue  # noqa: E402
from memory_projection import ProjectionStore, ProjectionValidationError, candidate_id, canonical_json, stable_hash  # noqa: E402
from typed_retrieval import RetrievalQuery, retrieve  # noqa: E402


REQUIRED_PHASE5_TABLES = {
    "candidate_lifecycle",
    "edge_lifecycle",
    "lifecycle_history",
}


def make_stores():
    tmp = tempfile.TemporaryDirectory()
    journal = JournalStore(os.path.join(tmp.name, "journal.sqlite3"))
    projection = ProjectionStore(os.path.join(tmp.name, "projection.sqlite3"))
    return tmp, journal, projection


def residue():
    data = unknown_residue("consolidation-test")
    data["attention_target"] = {
        "value": "consolidation",
        "source": "consolidation-test",
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
        context={"active_task": "phase-5-consolidation", "source_channel": "test"},
        residue=residue(),
    )


def add_run(projection):
    projection._conn.execute(  # noqa: SLF001 - fixture setup
        """
        INSERT INTO projection_runs (
            id, projection_key, projection_version, source_sequence_start,
            source_sequence_end, source_event_hashes_json, created_candidate_ids_json,
            rejected_candidate_ids_json, warnings_json, status, failure_reason,
            started_at, completed_at
        ) VALUES (
            'run-fixture', 'pkey-fixture', 1, 1, 1, '{}', '[]', '[]', '[]',
            'succeeded', NULL, 'now', 'now'
        )
        """
    )
    projection._conn.commit()  # noqa: SLF001
    return "run-fixture"


def confidence(level="strong", evidence_class="observed"):
    return {
        "level": level,
        "evidence_class": evidence_class,
        "inference_distance": "direct",
        "corroboration_count": 1,
        "contradiction_count": 0,
        "rationale": "consolidation fixture confidence",
    }


def source_ref(event, label, *, epistemic="observed", event_type="observation"):
    return {
        "event_id": event["id"],
        "event_sequence": event["sequence"],
        "event_hash": event["content_hash"],
        "event_type": event_type,
        "event_epistemic_status": epistemic,
        "payload_path": "payload.evidence",
        "residue_field": "not_applicable",
        "link_type": "not_applicable",
        "replay_trace_item": "not_applicable",
        "source_selector": "payload.evidence",
        "source_value_hash": stable_hash(label),
        "rationale": "consolidation fixture source",
    }


def privacy():
    return {"retention": "local", "exposure": "local-only", "export_allowed": True}


def resource():
    return {
        "external_contact": False,
        "network_access": False,
        "autonomous_spend": False,
        "compute_escalation": False,
    }


def add_candidate(projection, event, kind, label, *, confidence_level="strong", epistemic="observed"):
    cid = candidate_id(kind, label)
    ref = source_ref(event, label, epistemic=epistemic)
    projection._conn.execute(  # noqa: SLF001 - fixture setup
        """
        INSERT INTO memory_candidates (
            candidate_id, kind, label, epistemic_status, acceptance_status,
            relation_status, confidence_json, source_refs_json, privacy_scope_json,
            resource_scope_json, semantic_fingerprint, created_from_sequence_range_json,
            updated_at
        ) VALUES (?, ?, ?, ?, 'accepted', 'active', ?, ?, ?, ?, ?, '[1,1]', 'now')
        """,
        (
            cid,
            kind,
            label,
            epistemic,
            canonical_json(confidence(confidence_level, epistemic)),
            canonical_json([ref]),
            canonical_json(privacy()),
            canonical_json(resource()),
            stable_hash({"kind": kind, "label": label}),
        ),
    )
    projection._conn.commit()  # noqa: SLF001
    return cid


def add_edge(
    projection,
    event,
    source_id,
    target_id,
    edge_type,
    *,
    confidence_level="strong",
    epistemic="observed",
):
    edge_id = "edge_" + stable_hash({"source": source_id, "target": target_id, "edge_type": edge_type})[:16]
    ref = source_ref(event, edge_id, epistemic=epistemic)
    projection._conn.execute(  # noqa: SLF001 - fixture setup
        """
        INSERT INTO memory_edges (
            id, source_candidate_id, target_candidate_id, edge_type, direction,
            epistemic_status, confidence_json, source_refs_json, privacy_scope_json,
            resource_scope_json, semantic_fingerprint, projection_run_id
        ) VALUES (?, ?, ?, ?, 'symmetric', ?, ?, ?, ?, ?, ?, 'run-fixture')
        """,
        (
            edge_id,
            source_id,
            target_id,
            edge_type,
            epistemic,
            canonical_json(confidence(confidence_level, epistemic)),
            canonical_json([ref]),
            canonical_json(privacy()),
            canonical_json(resource()),
            stable_hash({"source": source_id, "target": target_id, "edge_type": edge_type}),
        ),
    )
    projection._conn.commit()  # noqa: SLF001
    return edge_id


def edge_lifecycle(projection, edge_id):
    return projection.edge_lifecycle(edge_id)


def candidate_lifecycle(projection, candidate):
    return projection.candidate_lifecycle(candidate)


def test_phase5_schema_adds_lifecycle_without_permitting_deletes():
    tmp, journal, projection = make_stores()
    try:
        assert REQUIRED_PHASE5_TABLES.issubset(projection.required_tables())
        observed = append_observation(journal, "schema", "lifecycle rows are interpretations")
        add_run(projection)
        cid = add_candidate(projection, observed, "concept", "lifecycle rows")
        target = add_candidate(projection, observed, "concept", "delete target")
        edge = add_edge(projection, observed, cid, target, "observed_cooccurrence")
        try:
            projection._conn.execute("DELETE FROM memory_candidates WHERE candidate_id = ?", (cid,))  # noqa: SLF001
            assert False, "candidate should not be physically deletable"
        except sqlite3.DatabaseError:
            pass
        try:
            projection._conn.execute("DELETE FROM memory_edges WHERE id = ?", (edge,))  # noqa: SLF001
            assert False, "edge should not be physically deletable"
        except sqlite3.DatabaseError:
            pass
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()

def test_recent_use_resists_decay_and_confidence_is_not_mutated():
    tmp, journal, projection = make_stores()
    try:
        observed = append_observation(journal, "retrieval", "use-sensitive decay")
        add_run(projection)
        entry = add_candidate(projection, observed, "concept", "entry")
        used = add_candidate(projection, observed, "concept", "used target")
        stale = add_candidate(projection, observed, "concept", "stale target")
        used_edge = add_edge(projection, observed, entry, used, "observed_cooccurrence")
        stale_edge = add_edge(projection, observed, entry, stale, "observed_cooccurrence")
        before_confidence = {
            edge["id"]: edge["confidence"]
            for edge in projection.edges()
        }

        result = retrieve(projection, RetrievalQuery(entry_candidate_ids=[entry], max_hops=1))
        append_retrieval_use_trace(
            journal,
            retrieval_result=result,
            used_candidate_ids=[entry, used],
            used_record_ids=[used_edge],
        )

        consolidate(journal, projection)

        assert edge_lifecycle(projection, used_edge)["lifecycle_state"] == "active"
        assert edge_lifecycle(projection, used_edge)["accessibility"] == 1.0
        assert edge_lifecycle(projection, stale_edge)["lifecycle_state"] == "weakened"
        assert edge_lifecycle(projection, stale_edge)["accessibility"] < 1.0
        for edge in projection.edges():
            assert edge["confidence"] == before_confidence[edge["id"]]
        assert any(event["event_type"] == "edge_decay_assessment" for event in journal.iter_events())
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_retrieval_use_trace_cannot_reinforce_paths_absent_from_snapshot():
    tmp, journal, projection = make_stores()
    try:
        observed = append_observation(journal, "retrieval", "forge-resistant use")
        add_run(projection)
        entry = add_candidate(projection, observed, "concept", "entry")
        hidden = add_candidate(projection, observed, "concept", "hidden")
        hidden_edge = add_edge(projection, observed, entry, hidden, "observed_cooccurrence")

        result = retrieve(projection, RetrievalQuery(entry_candidate_ids=[entry], max_hops=0))
        try:
            append_retrieval_use_trace(
                journal,
                retrieval_result=result,
                used_candidate_ids=[entry, hidden],
                used_record_ids=[hidden_edge],
            )
            assert False, "retrieval use trace should reject absent candidate and edge ids"
        except Exception as exc:
            assert "retrieval use" in str(exc)
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_lifecycle_mutation_rejects_forged_maintenance_envelope():
    tmp, journal, projection = make_stores()
    try:
        observed = append_observation(journal, "forgery", "lifecycle event must be persisted")
        add_run(projection)
        entry = add_candidate(projection, observed, "concept", "entry")
        target = add_candidate(projection, observed, "concept", "target")
        add_edge(projection, observed, entry, target, "observed_cooccurrence")
        consolidate(journal, projection)
        consolidate(journal, projection)
        real_event = next(
            event
            for event in journal.iter_events()
            if event["event_type"] == "candidate_dormancy_mark"
        )
        forged = copy.deepcopy(real_event)
        forged["id"] = "evt_not_in_journal"
        forged["content_hash"] = content_hash(forged)

        try:
            projection.record_candidate_lifecycle(
                journal=journal,
                candidate_id=target,
                lifecycle_state="dormant",
                accessibility=0.25,
                maintenance_event=forged,
                decay_basis={"forged": True},
            )
            assert False, "forged maintenance event should not mutate lifecycle"
        except ProjectionValidationError as exc:
            assert "not persisted" in str(exc)
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_dormant_memory_remains_recoverable_as_low_accessibility_evidence():
    tmp, journal, projection = make_stores()
    try:
        observed = append_observation(journal, "dormancy", "forgotten bridge")
        add_run(projection)
        entry = add_candidate(projection, observed, "concept", "entry")
        dormant = add_candidate(projection, observed, "concept", "forgotten bridge")
        add_edge(projection, observed, entry, dormant, "observed_cooccurrence")

        consolidate(journal, projection)
        assert candidate_lifecycle(projection, dormant)["lifecycle_state"] == "active"
        consolidate(journal, projection)

        lifecycle = candidate_lifecycle(projection, dormant)
        assert lifecycle["lifecycle_state"] == "dormant"
        assert lifecycle["accessibility"] == 0.25

        result = retrieve(projection, RetrievalQuery(entry_candidate_ids=[entry], max_hops=1))
        recovered = next(item for item in result["activated_candidates"] if item["candidate_id"] == dormant)
        assert recovered["lifecycle"]["lifecycle_state"] == "dormant"
        assert recovered["activation_score"] < 0.2
        assert recovered["source_refs"]
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_rediscovery_requires_new_observed_bridge_and_records_audit_event():
    tmp, journal, projection = make_stores()
    try:
        old = append_observation(journal, "old", "forgotten bridge")
        add_run(projection)
        entry = add_candidate(projection, old, "concept", "entry")
        dormant = add_candidate(projection, old, "concept", "forgotten bridge")
        add_edge(projection, old, entry, dormant, "observed_cooccurrence")
        consolidate(journal, projection)
        assert candidate_lifecycle(projection, dormant)["lifecycle_state"] == "active"
        consolidate(journal, projection)
        assert candidate_lifecycle(projection, dormant)["lifecycle_state"] == "dormant"
        assert not [event for event in journal.iter_events() if event["event_type"] == "rediscovery"]

        new = append_observation(journal, "new", "new evidence mentions forgotten bridge")
        new_candidate = add_candidate(projection, new, "concept", "new bridge evidence")
        bridge_edge = add_edge(projection, new, new_candidate, dormant, "observed_cooccurrence")

        result = consolidate(journal, projection)

        assert result.rediscoveries
        assert candidate_lifecycle(projection, dormant)["lifecycle_state"] == "rediscovered"
        assert edge_lifecycle(projection, bridge_edge)["lifecycle_state"] == "rediscovered_bridge"
        rediscovery_events = [event for event in journal.iter_events() if event["event_type"] == "rediscovery"]
        assert rediscovery_events
        assert rediscovery_events[-1]["payload"]["new_evidence_event_id"] == new["id"]
        assert rediscovery_events[-1]["payload"]["reflection_required"] is True
        reflection = journal.get_event(rediscovery_events[-1]["payload"]["reflection_event_id"])
        assert reflection is not None
        assert reflection["event_type"] == "reflection"
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


def test_pruning_is_a_proposal_not_physical_deletion():
    tmp, journal, projection = make_stores()
    try:
        observed = append_observation(journal, "pruning", "release stale access")
        add_run(projection)
        target = add_candidate(projection, observed, "concept", "stale access")

        proposal = propose_pruning(
            journal,
            target_kind="candidate",
            target_id=target,
            source_event_ids=[observed["id"]],
            affected_path_ids=["path-fixture"],
            rejected_alternatives=["weaken only"],
            reversibility_check="source event and semantic fingerprint are retained",
            rediscovery_recipe="new observed evidence can cite the retained source",
            release_rationale="release the access path while preserving evidence",
        )

        assert proposal["event_type"] == "pruning_proposal"
        assert projection._get_candidate_by_id(target) is not None  # noqa: SLF001
        assert candidate_lifecycle(projection, target)["lifecycle_state"] == "active"
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()

def test_material_types_do_not_decay_uniformly():
    tmp, journal, projection = make_stores()
    try:
        observed = append_observation(journal, "types", "different material should decay differently")
        add_run(projection)
        entry = add_candidate(projection, observed, "concept", "entry")
        ordinary = add_candidate(projection, observed, "concept", "ordinary")
        dream = add_candidate(projection, observed, "dream", "dream residue", confidence_level="weak", epistemic="hypothesis")
        preference = add_candidate(projection, observed, "preference", "particular habit")
        ordinary_edge = add_edge(projection, observed, entry, ordinary, "observed_cooccurrence")
        dream_edge = add_edge(projection, observed, entry, dream, "dream_association", confidence_level="weak", epistemic="hypothesis")
        preference_edge = add_edge(projection, observed, entry, preference, "observed_cooccurrence")

        consolidate(journal, projection)

        states = {
            ordinary_edge: edge_lifecycle(projection, ordinary_edge),
            dream_edge: edge_lifecycle(projection, dream_edge),
            preference_edge: edge_lifecycle(projection, preference_edge),
        }
        assert states[ordinary_edge]["accessibility"] == 0.45
        assert states[dream_edge]["accessibility"] == 0.35
        assert states[preference_edge]["accessibility"] == 0.65
        assert len({item["accessibility"] for item in states.values()}) == 3
    finally:
        journal.close()
        projection.close()
        tmp.cleanup()


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
