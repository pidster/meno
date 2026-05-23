"""Phase 1 rethink journal tests.

These tests intentionally import only the standalone stdlib journal module.
They do not touch the legacy SurrealDB-backed runtime.
"""

import os
import sqlite3
import sys
import tempfile
import hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from journal import (  # noqa: E402
    DEFAULT_PRIVACY_SCOPE,
    DEFAULT_RESOURCE_SCOPE,
    GraphProposal,
    JournalStore,
    JournalValidationError,
    canonical_json,
    content_hash,
    unknown_residue,
)
from dreaming import run_dream_cycle  # noqa: E402
from rehearsal import run_rehearsal_cycle  # noqa: E402


def make_store():
    tmp = tempfile.TemporaryDirectory()
    store = JournalStore(os.path.join(tmp.name, "journal.sqlite3"))
    return tmp, store


def residue(
    *,
    salience=0.7,
    attention="journal",
    uncertainty=0.2,
    tension="unknown",
    drives=None,
    outcome="unknown",
    importance="test fixture",
    affect="unknown",
):
    data = unknown_residue("test")
    data["salience"] = {
        "value": salience,
        "source": "test",
        "epistemic_status": "authored",
    }
    data["open_tensions"] = {
        "value": tension,
        "source": "test",
        "epistemic_status": "authored",
    }
    data["attention_target"] = {
        "value": attention,
        "source": "test",
        "epistemic_status": "authored",
    }
    data["uncertainty"] = {
        "value": uncertainty,
        "source": "test",
        "epistemic_status": "authored",
    }
    data["drive_refs"] = {
        "value": drives if drives is not None else ["convergence"],
        "source": "test",
        "epistemic_status": "authored",
    }
    data["expected_outcome"] = {
        "value": outcome,
        "source": "test",
        "epistemic_status": "authored",
    }
    data["importance_reason"] = {
        "value": importance,
        "source": "test",
        "epistemic_status": "authored",
    }
    data["affect_valence"] = {
        "value": affect,
        "source": "test",
        "epistemic_status": "authored",
    }
    return data


def context(task="phase-1-journal"):
    return {"active_task": task, "source_channel": "test"}


def append_conversation(store, message, **kwargs):
    epistemic_status = kwargs.pop("epistemic_status", "authored")
    return store.append_event(
        event_type="conversation",
        epistemic_status=epistemic_status,
        actor="pid",
        source="test",
        capture_method="manual",
        payload={
            "speaker": "pid",
            "message": message,
            "channel": "test",
            "turn_id": kwargs.pop("turn_id", "turn-1"),
        },
        context=context(),
        residue=kwargs.pop("residue_value", residue()),
        **kwargs,
    )


def append_dream(store):
    return run_dream_cycle(
        store,
        immediate_context={"label": "journal test"},
        actor="meno",
        source="test",
    )["dream_event"]


def append_failed_outcome(store):
    source = append_conversation(
        store,
        "source for rehearsal",
        epistemic_status="observed",
        residue_value=residue(tension="source for dry run"),
    )
    return store.append_event(
        event_type="outcome",
        epistemic_status="observed",
        actor="tool",
        source="test",
        capture_method="manual",
        payload={
            "expected_outcome_link": source["id"],
            "observed_result": "prior attempt failed",
            "match": False,
        },
        context=context(),
        residue=residue(tension="prior attempt failed"),
        links=[
            {
                "type": "derived_from",
                "target_event_id": source["id"],
                "rationale": "failed attempt seeds rehearsal",
            }
        ],
    )


def reflection_payload(source_ids):
    retrieval_path = {
        "entry_candidate_id": "entry-1",
        "target_candidate_id": "candidate-1",
        "steps": [
            {
                "record_type": "edge",
                "record_id": "edge-1",
                "hop_index": 1,
            }
        ],
        "evidence_refs": [
            {
                "event_id": source_ids[0] if source_ids else "missing",
                "payload_path": "payload.message",
                "source_value_hash": "hash",
            }
        ],
    }
    path_id = "path_" + hashlib.sha256(
        canonical_json(
            {
                "candidate_id": "candidate-1",
                "entry_candidate_id": retrieval_path["entry_candidate_id"],
                "target_candidate_id": retrieval_path["target_candidate_id"],
                "steps": retrieval_path["steps"],
            }
        ).encode("utf-8")
    ).hexdigest()[:24]
    snapshot = {
        "activated_candidates": [
            {
                "candidate_id": "candidate-1",
                "activation_paths": [retrieval_path],
            }
        ],
        "ghost_signals": [],
        "omitted_candidates": [],
    }
    stable_snapshot = {
        key: value
        for key, value in snapshot.items()
        if key not in {"query_id", "timestamp"}
    }
    return {
        "cited_source_event_ids": source_ids,
        "retrieval_result_hash": hashlib.sha256(canonical_json(stable_snapshot).encode("utf-8")).hexdigest(),
        "retrieval_result_snapshot": snapshot,
        "cited_retrieval_paths": [
            {
                "candidate_id": "candidate-1",
                "path_id": path_id,
                "activation_paths": [retrieval_path],
                "source_refs": [
                    {
                        "event_id": source_ids[0] if source_ids else "missing",
                        "payload_path": "payload.message",
                        "source_value_hash": "hash",
                    }
                ],
                "scope_decision": {"allowed": True},
                "redacted": False,
            }
        ],
        "interpretive_claims": [
            {
                "type": "interpretive_claim",
                "claim": "specific sourced interpretation",
                "cites": [path_id],
                "epistemic_status": "authored",
            }
        ],
        "open_questions": ["what should change next"],
        "uncertainty_notes": ["fixture uncertainty"],
        "possible_self_deception": ["fixture may overfit"],
        "rejected_interpretations": ["generic continuity summary"],
        "changed_stance": "specific stance changed",
        "future_attention": [{"target": "specific follow-up", "resource_scope": DEFAULT_RESOURCE_SCOPE}],
        "proposed_graph_updates": [],
        "deferred_graph_updates": [{"reason": "insufficient evidence"}],
    }


def test_append_event_uses_full_envelope_and_canonical_hash():
    tmp, store = make_store()
    try:
        event = append_conversation(store, "Remember the review pattern")

        assert event["sequence"] == 1
        assert event["schema_version"] == 1
        assert event["content_hash"] == content_hash(event)
        assert event["privacy_scope"] == DEFAULT_PRIVACY_SCOPE
        assert event["resource_scope"] == DEFAULT_RESOURCE_SCOPE
        assert set(event["residue"]).issuperset(
            {"salience", "attention_target", "open_tensions", "importance_reason"}
        )
    finally:
        store.close()
        tmp.cleanup()


def test_replay_preserves_full_residue_with_traces():
    tmp, store = make_store()
    try:
        event = append_conversation(
            store,
            "Residue should reconstruct why this mattered",
            residue_value=residue(
                salience=0.9,
                attention="phase gate",
                uncertainty=0.4,
                tension="proposal provenance still open",
                drives=["convergence", "auditability"],
                outcome="implementation tightened",
                importance="prevents log-only memory",
                affect="concerned",
            ),
        )

        replay = store.replay_context()

        assert any(item["event_id"] == event["id"] for item in replay.attention_targets)
        assert any(item["event_id"] == event["id"] for item in replay.uncertainty_markers)
        assert any(item["event_id"] == event["id"] for item in replay.drive_refs)
        assert any(item["event_id"] == event["id"] for item in replay.importance_reasons)
        assert any(item["event_id"] == event["id"] for item in replay.affect_valence)
        assert any(item["event_id"] == event["id"] for item in replay.expected_outcomes)
        assert any(
            trace["event_id"] == event["id"]
            and trace["item"] == "importance_reason"
            and trace["residue_epistemic_status"] == "authored"
            for trace in replay.traces
        )
    finally:
        store.close()
        tmp.cleanup()


def test_sqlite_triggers_reject_direct_update_and_delete():
    tmp, store = make_store()
    try:
        event = append_conversation(store, "Append only matters")

        try:
            store._conn.execute(  # noqa: SLF001 - direct tampering for contract test
                "UPDATE journal_events SET actor = 'other' WHERE id = ?", (event["id"],)
            )
            assert False, "direct update should fail"
        except sqlite3.DatabaseError as exc:
            assert "append-only" in str(exc)

        try:
            store._conn.execute(  # noqa: SLF001 - direct tampering for contract test
                "DELETE FROM journal_events WHERE id = ?", (event["id"],)
            )
            assert False, "direct delete should fail"
        except sqlite3.DatabaseError as exc:
            assert "append-only" in str(exc)
    finally:
        store.close()
        tmp.cleanup()


def test_replay_detects_corrupt_content_hash():
    tmp, store = make_store()
    try:
        event = append_conversation(store, "Hash mismatch should surface")
        store._conn.execute("DROP TRIGGER journal_events_no_update")  # noqa: SLF001
        store._conn.execute(  # noqa: SLF001
            "UPDATE journal_events SET actor = 'tampered' WHERE id = ?", (event["id"],)
        )
        store._conn.commit()  # noqa: SLF001

        replay = store.replay_context()

        assert {"event_id": event["id"], "kind": "hash_mismatch"} in replay.integrity_warnings
    finally:
        store.close()
        tmp.cleanup()


def test_event_status_payload_residue_and_idempotency_validation():
    tmp, store = make_store()
    try:
        try:
            store.append_event(
                event_type="dream",
                epistemic_status="observed",
                actor="meno",
                source="test",
                capture_method="manual",
                payload={
                    "residues_used": [],
                    "generated_candidates": [],
                    "uncertainty_notes": "none",
                },
                context=context(),
                residue=residue(),
            )
            assert False, "dream cannot be observed"
        except JournalValidationError as exc:
            assert "invalid epistemic status" in str(exc)

        try:
            store.append_event(
                event_type="conversation",
                epistemic_status="authored",
                actor="pid",
                source="test",
                capture_method="manual",
                payload={"speaker": "pid"},
                context=context(),
                residue=residue(),
            )
            assert False, "malformed payload should fail"
        except JournalValidationError as exc:
            assert "payload missing" in str(exc)

        try:
            incomplete = unknown_residue("test")
            incomplete.pop("salience")
            store.append_event(
                event_type="conversation",
                epistemic_status="authored",
                actor="pid",
                source="test",
                capture_method="manual",
                payload={
                    "speaker": "pid",
                    "message": "missing residue",
                    "channel": "test",
                    "turn_id": "turn-x",
                },
                context=context(),
                residue=incomplete,
            )
            assert False, "missing residue should fail"
        except JournalValidationError as exc:
            assert "residue missing" in str(exc)

        try:
            store.append_event(
                event_type="tool_call",
                epistemic_status="observed",
                actor="tool",
                source="test",
                capture_method="tool",
                payload={
                    "tool_name": "demo",
                    "arguments_summary": {},
                    "result_boundary": "stdout",
                    "success": True,
                },
                context=context(),
                residue=residue(),
            )
            assert False, "tool captures require idempotency"
        except JournalValidationError as exc:
            assert "idempotency_key" in str(exc)
    finally:
        store.close()
        tmp.cleanup()


def test_duplicate_non_null_idempotency_key_is_rejected():
    tmp, store = make_store()
    try:
        for turn in ("a", "b"):
            try:
                store.append_event(
                    event_type="tool_call",
                    epistemic_status="observed",
                    actor="tool",
                    source="test",
                    capture_method="tool",
                    payload={
                        "tool_name": "demo",
                        "arguments_summary": {"turn": turn},
                        "result_boundary": "stdout",
                        "success": True,
                    },
                    context=context(),
                    residue=residue(),
                    idempotency_key="tool:demo:1",
                )
                if turn == "b":
                    assert False, "duplicate idempotency key should fail"
            except JournalValidationError as exc:
                assert turn == "b"
                assert "idempotency_key" in str(exc)
    finally:
        store.close()
        tmp.cleanup()


def test_typed_links_and_corrections_are_new_events():
    tmp, store = make_store()
    try:
        original = append_conversation(store, "Original claim")
        correction = store.append_correction(
            target_event_id=original["id"],
            corrected_claim="Corrected claim",
            reason="Pid corrected the record",
            actor="pid",
            source="test",
            residue=residue(importance="correction matters"),
            target_field="payload.message",
        )

        assert correction["sequence"] == 2
        assert correction["links"][0]["type"] == "corrects"
        assert correction["links"][0]["target_event_id"] == original["id"]
        assert store.get_event(original["id"])["payload"]["message"] == "Original claim"
    finally:
        store.close()
        tmp.cleanup()


def test_dream_and_rehearsal_replay_as_provisional_not_factual():
    tmp, store = make_store()
    try:
        append_conversation(store, "source for dream", residue_value=residue(tension="loose association"))
        dream = append_dream(store)
        append_failed_outcome(store)
        rehearsal = run_rehearsal_cycle(store, immediate_context={"label": "journal implementation"})["rehearsal_event"]

        replay = store.replay_context()

        candidates = {item["event_id"]: item for item in replay.provisional_candidates}
        assert candidates[dream["id"]]["epistemic_status"] == "hypothesis"
        assert candidates[rehearsal["id"]]["epistemic_status"] == "simulation"
        assert all(item["epistemic_status"] != "observed" for item in candidates.values())
    finally:
        store.close()
        tmp.cleanup()


def test_reflection_requires_source_events():
    tmp, store = make_store()
    try:
        try:
            store.append_event(
                event_type="reflection",
                epistemic_status="authored",
                actor="meno",
                source="test",
                capture_method="reflection_workflow",
                payload=reflection_payload([]),
                context=context(),
                residue=residue(),
            )
            assert False, "reflection without evidence should fail"
        except JournalValidationError as exc:
            assert "reflection requires cited source events" in str(exc)

        try:
            store.append_event(
                event_type="reflection",
                epistemic_status="authored",
                actor="meno",
                source="test",
                capture_method="reflection_workflow",
                payload=reflection_payload(["missing-event"]),
                context=context(),
                residue=residue(),
            )
            assert False, "reflection with missing evidence should fail"
        except JournalValidationError as exc:
            assert "unknown cited source event" in str(exc)

        observed = append_conversation(store, "Observed reflection source", epistemic_status="observed")
        proposal_payload = reflection_payload([observed["id"]])
        proposal_payload["proposed_graph_updates"] = [
            {
                "proposed_operation": "create",
                "proposed_target_kind": "concept",
                "source_event_ids": [observed["id"]],
                "intended_status": "provisional",
                "rationale": "reflection proposal must be separate",
            }
        ]
        try:
            store.append_event(
                event_type="reflection",
                epistemic_status="authored",
                actor="meno",
                source="test",
                capture_method="reflection_workflow",
                payload=proposal_payload,
                context=context(),
                residue=residue(),
            )
            assert False, "reflection must not embed graph update proposal"
        except JournalValidationError as exc:
            assert "reflection cannot embed graph update proposals" in str(exc)

        fake_path_payload = reflection_payload([observed["id"]])
        fake_path_payload["cited_retrieval_paths"][0]["path_id"] = "fake-path"
        fake_path_payload["interpretive_claims"][0]["cites"] = ["fake-path"]
        try:
            store.append_event(
                event_type="reflection",
                epistemic_status="authored",
                actor="meno",
                source="test",
                capture_method="reflection_workflow",
                payload=fake_path_payload,
                context=context(),
                residue=residue(),
            )
            assert False, "direct journal reflection should reject fake retrieval path"
        except JournalValidationError as exc:
            assert "reflection cited path is not in retrieval snapshot" in str(exc)

        try:
            store.append_event(
                event_type="reflection",
                epistemic_status="authored",
                actor="meno",
                source="test",
                capture_method="manual",
                payload=reflection_payload([observed["id"]]),
                context=context(),
                residue=residue(),
            )
            assert False, "direct reflection write should require workflow"
        except JournalValidationError as exc:
            assert "reflection events must use reflection workflow" in str(exc)
    finally:
        store.close()
        tmp.cleanup()


def test_privacy_and_resource_scopes_affect_replay_and_proposals():
    tmp, store = make_store()
    try:
        event = append_conversation(
            store,
            "Do not export this",
            privacy_scope={**DEFAULT_PRIVACY_SCOPE, "export_allowed": False},
            resource_scope={**DEFAULT_RESOURCE_SCOPE, "network_access": False},
        )

        replay = store.replay_context(requested_scope={"export": True})

        assert event["id"] not in replay.ordered_recent_event_ids
        assert any(w["kind"] == "scope_excluded" for w in replay.integrity_warnings)

        try:
            store.validate_graph_proposal(
                GraphProposal(
                    proposed_operation="create",
                    proposed_target_kind="concept",
                    source_event_ids=[event["id"]],
                    intended_status="factual",
                    rationale="blocked by export scope",
                    requested_scope={"export": True},
                )
            )
            assert False, "scope-disallowed proposal should fail"
        except JournalValidationError as exc:
            assert "scope disallows" in str(exc)
    finally:
        store.close()
        tmp.cleanup()


def test_graph_proposal_validator_rejects_weak_or_provisional_provenance():
    tmp, store = make_store()
    try:
        observed = append_conversation(
            store,
            "Observed enough for factual proposal",
            epistemic_status="observed",
        )
        dream = append_dream(store)

        authored = append_conversation(store, "Pid said a claim, but truth is separate")

        store.validate_graph_proposal(
            GraphProposal(
                proposed_operation="create",
                proposed_target_kind="concept",
                source_event_ids=[observed["id"]],
                intended_status="factual",
                rationale="conversation evidence",
            )
        )

        try:
            store.validate_graph_proposal(
                GraphProposal(
                    proposed_operation="create",
                    proposed_target_kind="concept",
                    source_event_ids=[authored["id"]],
                    intended_status="factual",
                    rationale="authored utterance is not world truth",
                )
            )
            assert False, "authored conversation cannot support factual proposal"
        except JournalValidationError as exc:
            assert "factual proposal requires" in str(exc)

        try:
            store.validate_graph_proposal(
                GraphProposal(
                    proposed_operation="create",
                    proposed_target_kind="concept",
                    source_event_ids=[dream["id"]],
                    intended_status="factual",
                    rationale="dream leakage",
                )
            )
            assert False, "dream cannot support factual proposal"
        except JournalValidationError as exc:
            assert "factual proposal requires" in str(exc)

        store.validate_graph_proposal(
            GraphProposal(
                proposed_operation="create",
                proposed_target_kind="concept",
                source_event_ids=[dream["id"]],
                intended_status="provisional",
                rationale="dream can seed provisional proposal",
            )
        )
    finally:
        store.close()
        tmp.cleanup()


def test_graph_update_proposal_event_uses_same_provenance_rules():
    tmp, store = make_store()
    try:
        observed = append_conversation(
            store,
            "Observed evidence for proposal",
            epistemic_status="observed",
        )
        dream = append_dream(store)

        proposal = store.append_event(
            event_type="graph_update_proposal",
            epistemic_status="inferred",
            actor="meno",
            source="test",
            capture_method="manual",
            payload={
                "proposed_operation": "create",
                "proposed_target_kind": "concept",
                "source_event_ids": [observed["id"]],
                "intended_status": "factual",
                "rationale": "observed evidence",
            },
            context=context(),
            residue=residue(),
            links=[
                {
                    "type": "proposes_from",
                    "target_event_id": observed["id"],
                    "rationale": "observed evidence",
                }
            ],
        )
        assert proposal["event_type"] == "graph_update_proposal"

        try:
            store.append_event(
                event_type="graph_update_proposal",
                epistemic_status="inferred",
                actor="meno",
                source="test",
                capture_method="manual",
                payload={
                    "proposed_operation": "create",
                    "proposed_target_kind": "concept",
                    "source_event_ids": [dream["id"]],
                    "intended_status": "factual",
                    "rationale": "dream leakage",
                },
                context=context(),
                residue=residue(),
                links=[
                    {
                        "type": "proposes_from",
                        "target_event_id": dream["id"],
                        "rationale": "dream leakage",
                    }
                ],
            )
            assert False, "direct graph proposal event should share validator rules"
        except JournalValidationError as exc:
            assert "factual proposal requires" in str(exc)
    finally:
        store.close()
        tmp.cleanup()


def test_graph_proposal_rejects_tampered_source_event():
    tmp, store = make_store()
    try:
        observed = append_conversation(
            store,
            "Observed evidence before tamper",
            epistemic_status="observed",
        )
        store._conn.execute("DROP TRIGGER journal_events_no_update")  # noqa: SLF001
        store._conn.execute(  # noqa: SLF001
            "UPDATE journal_events SET actor = 'tampered' WHERE id = ?", (observed["id"],)
        )
        store._conn.commit()  # noqa: SLF001

        try:
            store.validate_graph_proposal(
                GraphProposal(
                    proposed_operation="create",
                    proposed_target_kind="concept",
                    source_event_ids=[observed["id"]],
                    intended_status="factual",
                    rationale="tampered evidence",
                )
            )
            assert False, "tampered source event should fail provenance validation"
        except JournalValidationError as exc:
            assert "hash mismatch" in str(exc)
    finally:
        store.close()
        tmp.cleanup()


def test_rest_event_preserves_meaningful_non_action():
    tmp, store = make_store()
    try:
        rest = store.append_event(
            event_type="rest",
            epistemic_status="authored",
            actor="meno",
            source="test",
            capture_method="manual",
            payload={
                "tensions_left_unresolved": ["journal schema still open"],
                "deliberate_non_action_reason": "consolidation only",
                "consolidation_notes": "no external action",
            },
            context=context("rest"),
            residue=residue(tension="left unresolved", importance="quiet tick"),
        )

        replay = store.replay_context()

        assert rest["id"] in replay.ordered_recent_event_ids
        assert any(item["event_id"] == rest["id"] for item in replay.open_tensions)
        assert any(item["event_id"] == rest["id"] for item in replay.rest_markers)
        assert not replay.provisional_candidates
    finally:
        store.close()
        tmp.cleanup()


def test_zombie_gate_similar_text_different_residue_changes_replay_fields():
    tmp_a, store_a = make_store()
    tmp_b, store_b = make_store()
    try:
        first = append_conversation(
            store_a,
            "Review the journal plan",
            turn_id="same-text-1",
            residue_value=residue(
                salience=0.2,
                tension="unknown",
                outcome="simple review",
                importance="routine",
            ),
        )
        replay_a = store_a.replay_context()

        second = append_conversation(
            store_b,
            "Review the journal plan",
            turn_id="same-text-1",
            residue_value=residue(
                salience=0.95,
                attention="phase gate",
                uncertainty=0.8,
                tension="schema may become a log",
                outcome="contract tightened",
                importance="prevents zombie success",
                affect="concerned",
            ),
        )
        replay_b = store_b.replay_context()

        assert first["payload"]["message"] == second["payload"]["message"]
        assert len(replay_a.ordered_recent_event_ids) == len(replay_b.ordered_recent_event_ids)
        assert replay_a.salient_residues[0]["residue"]["value"] != replay_b.salient_residues[0]["residue"]["value"]
        assert any(item["event_id"] == second["id"] for item in replay_b.open_tensions)
        assert replay_a.importance_reasons[0]["residue"]["value"] != replay_b.importance_reasons[0]["residue"]["value"]
        assert any(
            trace["event_id"] == second["id"]
            and trace["item"] == "open_tensions"
            and trace["residue_epistemic_status"] == "authored"
            for trace in replay_b.traces
        )
    finally:
        store_a.close()
        store_b.close()
        tmp_a.cleanup()
        tmp_b.cleanup()


if __name__ == "__main__":
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
        print(f"{test.__name__}: OK")
