"""Phase 3 typed retrieval tests.

These tests assert semantic retrieval behavior over projected memory. They use
projection storage directly so retrieval tests can isolate traversal policy from
Phase 2 projection heuristics.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory_projection import ProjectionStore, candidate_id, canonical_json, stable_hash  # noqa: E402
from typed_retrieval import RetrievalQuery, retrieve  # noqa: E402


def make_store():
    tmp = tempfile.TemporaryDirectory()
    projection = ProjectionStore(os.path.join(tmp.name, "projection.sqlite3"))
    return tmp, projection


def confidence(level="strong", evidence_class="observed", refs=1):
    return {
        "level": level,
        "evidence_class": evidence_class,
        "inference_distance": "direct",
        "corroboration_count": refs,
        "contradiction_count": 0,
        "rationale": "retrieval fixture",
    }


def source_refs(label, count=1, event_type="observation", epistemic="observed"):
    refs = []
    for index in range(count):
        refs.append(
            {
                "event_id": f"event-{label}-{index}",
                "event_sequence": index + 1,
                "event_hash": stable_hash({"label": label, "index": index}),
                "event_type": event_type,
                "event_epistemic_status": epistemic,
                "payload_path": "payload.evidence",
                "residue_field": "not_applicable",
                "link_type": "not_applicable",
                "replay_trace_item": "not_applicable",
                "source_selector": "payload.evidence",
                "source_value_hash": stable_hash(label),
                "rationale": "retrieval fixture source",
            }
        )
    return refs


def privacy(export_allowed=True, exposure="local-only"):
    return {
        "retention": "local",
        "exposure": exposure,
        "export_allowed": export_allowed,
    }


def resource(network=False):
    return {
        "external_contact": False,
        "network_access": network,
        "autonomous_spend": False,
        "compute_escalation": False,
    }


def add_run(projection, run_id="run-fixture"):
    projection._conn.execute(  # noqa: SLF001 - fixture setup
        """
        INSERT OR IGNORE INTO projection_runs (
            id, projection_key, projection_version, source_sequence_start,
            source_sequence_end, source_event_hashes_json, created_candidate_ids_json,
            rejected_candidate_ids_json, warnings_json, status, failure_reason,
            started_at, completed_at
        ) VALUES (?, ?, 1, 1, 1, '{}', '[]', '[]', '[]', 'succeeded', NULL, 'now', 'now')
        """,
        (run_id, f"pkey-{run_id}"),
    )
    projection._conn.commit()  # noqa: SLF001
    return run_id


def add_candidate(
    projection,
    kind,
    label,
    *,
    acceptance="accepted",
    relation="active",
    epistemic="observed",
    refs=1,
    confidence_level="strong",
    export_allowed=True,
):
    cid = candidate_id(kind, label)
    ref_rows = source_refs(label, refs, epistemic=epistemic)
    projection._conn.execute(  # noqa: SLF001 - fixture setup
        """
        INSERT INTO memory_candidates (
            candidate_id, kind, label, epistemic_status, acceptance_status,
            relation_status, confidence_json, source_refs_json, privacy_scope_json,
            resource_scope_json, semantic_fingerprint, created_from_sequence_range_json,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'now')
        """,
        (
            cid,
            kind,
            label,
            epistemic,
            acceptance,
            relation,
            canonical_json(confidence(confidence_level, epistemic, refs)),
            canonical_json(ref_rows),
            canonical_json(privacy(export_allowed=export_allowed)),
            canonical_json(resource()),
            stable_hash({"kind": kind, "label": label}),
            canonical_json([1, refs]),
        ),
    )
    projection._conn.commit()  # noqa: SLF001
    return cid


def add_edge(
    projection,
    source_id,
    target_id,
    edge_type,
    *,
    direction="directed",
    run_id="run-fixture",
    epistemic="observed",
    confidence_level="strong",
    export_allowed=True,
):
    edge_id = "edge_" + stable_hash(
        {"source": source_id, "target": target_id, "edge_type": edge_type, "direction": direction}
    )[:16]
    refs = source_refs(edge_id, event_type="observation", epistemic=epistemic)
    projection._conn.execute(  # noqa: SLF001 - fixture setup
        """
        INSERT INTO memory_edges (
            id, source_candidate_id, target_candidate_id, edge_type, direction,
            epistemic_status, confidence_json, source_refs_json, privacy_scope_json,
            resource_scope_json, semantic_fingerprint, projection_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            edge_id,
            source_id,
            target_id,
            edge_type,
            direction,
            epistemic,
            canonical_json(confidence(confidence_level, epistemic)),
            canonical_json(refs),
            canonical_json(privacy(export_allowed=export_allowed)),
            canonical_json(resource()),
            stable_hash({"source": source_id, "target": target_id, "edge_type": edge_type}),
            run_id,
        ),
    )
    projection._conn.commit()  # noqa: SLF001
    return edge_id


def add_relation(
    projection,
    source_id,
    target_id,
    relation_type,
    *,
    direction="directed",
    run_id="run-fixture",
    epistemic="observed",
    confidence_level="moderate",
    export_allowed=True,
):
    relation_id = "relation_" + stable_hash(
        {"source": source_id, "target": target_id, "relation_type": relation_type, "direction": direction}
    )[:16]
    refs = source_refs(relation_id, event_type="relation", epistemic=epistemic)
    decision_id = f"decision-{relation_id}"
    projection._conn.execute(  # noqa: SLF001 - fixture setup
        """
        INSERT INTO projection_decisions (
            projection_record_id, candidate_id, decision,
            acceptance_status_before, acceptance_status_after,
            relation_status_before, relation_status_after,
            projection_run_id, projection_rule_id, projection_version,
            projection_fingerprint, source_refs_json, confidence_record_json,
            reason, timestamp
        ) VALUES (?, ?, ?, 'accepted', 'accepted', 'active', 'active', ?, ?, 1, ?, ?, ?, ?, 'now')
        """,
        (
            decision_id,
            source_id,
            relation_type,
            run_id,
            f"relation_{relation_type}",
            stable_hash({"relation": relation_id}),
            canonical_json(refs),
            canonical_json(confidence(confidence_level, epistemic)),
            "retrieval fixture relation",
        ),
    )
    projection._conn.execute(  # noqa: SLF001 - fixture setup
        """
        INSERT INTO projection_relations (
            id, relation_type, source_candidate_id, target_candidate_id, direction,
            source_refs_json, privacy_scope_json, resource_scope_json,
            confidence_json, projection_run_id, projection_rule_id,
            projection_version, projection_decision_id, reason, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 'now')
        """,
        (
            relation_id,
            relation_type,
            source_id,
            target_id,
            direction,
            canonical_json(refs),
            canonical_json(privacy(export_allowed=export_allowed)),
            canonical_json(resource()),
            canonical_json(confidence(confidence_level, epistemic)),
            run_id,
            f"relation_{relation_type}",
            decision_id,
            "retrieval fixture relation",
        ),
    )
    projection._conn.commit()  # noqa: SLF001
    return relation_id


def candidate_ids(result):
    return [item["candidate_id"] for item in result["activated_candidates"]]


def test_observed_cooccurrence_is_symmetric_but_outcome_confirmation_is_forward_only():
    tmp, projection = make_store()
    try:
        run_id = add_run(projection)
        a = add_candidate(projection, "entity", "A")
        b = add_candidate(projection, "concept", "B")
        rehearsal = add_candidate(
            projection,
            "rehearsal",
            "try fixture-first",
            acceptance="provisional",
            epistemic="simulation",
        )
        outcome = add_candidate(projection, "concept", "fixture-first worked")
        add_edge(projection, a, b, "observed_cooccurrence", direction="symmetric", run_id=run_id)
        add_edge(projection, rehearsal, outcome, "outcome_confirmation", direction="directed", run_id=run_id)

        from_b = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[b], max_hops=1, include_simulations=True),
        )
        from_outcome = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[outcome], max_hops=1, include_simulations=True),
        )
        from_rehearsal = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[rehearsal], max_hops=1, include_simulations=True),
        )

        assert a in candidate_ids(from_b)
        assert rehearsal not in candidate_ids(from_outcome)
        assert outcome in candidate_ids(from_rehearsal)
        outcome_path = next(item for item in from_rehearsal["activated_candidates"] if item["candidate_id"] == outcome)
        assert outcome_path["activation_paths"][0]["steps"][0]["edge_type"] == "outcome_confirmation"
        assert outcome_path["activation_paths"][0]["steps"][0]["traversal_direction"] == "forward"
    finally:
        projection.close()
        tmp.cleanup()


def test_dream_and_rehearsal_require_explicit_inclusion_and_do_not_become_facts():
    tmp, projection = make_store()
    try:
        run_id = add_run(projection)
        entry = add_candidate(projection, "concept", "A")
        dream = add_candidate(
            projection,
            "dream",
            "A relates to B",
            acceptance="provisional",
            epistemic="hypothesis",
        )
        rehearsal = add_candidate(
            projection,
            "rehearsal",
            "try B",
            acceptance="provisional",
            epistemic="simulation",
        )
        add_edge(projection, entry, dream, "dream_association", run_id=run_id, epistemic="hypothesis")
        add_edge(projection, entry, rehearsal, "rehearsal_candidate", run_id=run_id, epistemic="simulation")

        default = retrieve(projection, RetrievalQuery(entry_candidate_ids=[entry], max_hops=1))

        assert dream not in candidate_ids(default)
        assert rehearsal not in candidate_ids(default)
        assert {ghost["reason"] for ghost in default["ghost_signals"]} >= {
            "hypothesis_suppressed",
            "simulation_suppressed",
        }
        assert all("A relates to B" not in str(ghost) for ghost in default["ghost_signals"])

        included = retrieve(
            projection,
            RetrievalQuery(
                entry_candidate_ids=[entry],
                max_hops=1,
                include_hypotheses=True,
                include_simulations=True,
            ),
        )
        assert dream in candidate_ids(included)
        assert rehearsal in candidate_ids(included)
        dream_result = next(item for item in included["activated_candidates"] if item["candidate_id"] == dream)
        assert dream_result["epistemic_status"] == "hypothesis"
    finally:
        projection.close()
        tmp.cleanup()


def test_dream_and_rehearsal_edges_do_not_launder_accepted_targets():
    tmp, projection = make_store()
    try:
        run_id = add_run(projection)
        entry = add_candidate(projection, "concept", "entry")
        same_label_dream = add_candidate(projection, "concept", "same label")
        same_label_rehearsal = add_candidate(projection, "entity", "same label")
        add_edge(projection, entry, same_label_dream, "dream_association", run_id=run_id, epistemic="hypothesis")
        add_edge(projection, entry, same_label_rehearsal, "rehearsal_candidate", run_id=run_id, epistemic="simulation")

        default = retrieve(projection, RetrievalQuery(entry_candidate_ids=[entry], max_hops=1))

        assert same_label_dream not in candidate_ids(default)
        assert same_label_rehearsal not in candidate_ids(default)
        assert {ghost["reason"] for ghost in default["ghost_signals"]} >= {
            "hypothesis_suppressed",
            "simulation_suppressed",
        }

        included = retrieve(
            projection,
            RetrievalQuery(
                entry_candidate_ids=[entry],
                max_hops=1,
                include_hypotheses=True,
                include_simulations=True,
            ),
        )
        assert same_label_dream in candidate_ids(included)
        assert same_label_rehearsal in candidate_ids(included)
        dream_step = next(
            item for item in included["activated_candidates"] if item["candidate_id"] == same_label_dream
        )["activation_paths"][0]["steps"][0]
        rehearsal_step = next(
            item for item in included["activated_candidates"] if item["candidate_id"] == same_label_rehearsal
        )["activation_paths"][0]["steps"][0]
        assert dream_step["record_epistemic_status"] == "hypothesis"
        assert dream_step["candidate_confidence_record"]["level"] == "strong"
        assert dream_step["record_confidence_record"]["evidence_class"] == "hypothesis"
        assert rehearsal_step["record_epistemic_status"] == "simulation"
        assert rehearsal_step["candidate_confidence_record"]["level"] == "strong"
        assert rehearsal_step["record_confidence_record"]["evidence_class"] == "simulation"
    finally:
        projection.close()
        tmp.cleanup()


def test_signals_do_not_perform_keyword_retrieval_without_explicit_entries():
    tmp, projection = make_store()
    try:
        add_run(projection)
        add_candidate(projection, "concept", "keyword bait")

        result = retrieve(projection, RetrievalQuery(signals=["keyword"], max_hops=1))

        assert result["activated_candidates"] == []
        assert result["warnings"] == [{"kind": "no_entry_candidates", "signals": ["keyword"]}]
    finally:
        projection.close()
        tmp.cleanup()


def test_scope_restricted_memory_becomes_redacted_ghost_without_label_leakage():
    tmp, projection = make_store()
    try:
        run_id = add_run(projection)
        entry = add_candidate(projection, "concept", "public cue")
        secret = add_candidate(
            projection,
            "concept",
            "secret restricted label",
            export_allowed=False,
        )
        add_edge(projection, entry, secret, "observed_cooccurrence", direction="symmetric", run_id=run_id)

        result = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[entry], max_hops=1, requested_scope={"export": True}),
        )

        assert secret not in candidate_ids(result)
        assert result["ghost_signals"]
        assert result["ghost_signals"][0]["reason"] == "scope_restricted"
        assert "secret restricted label" not in str(result)
        assert secret not in str(result)
        assert "path_internals" in result["ghost_signals"][0]["scope_decision"]["redacted_fields"]
        assert result["ghost_signals"][0]["suppressed_path_shape"] == []
    finally:
        projection.close()
        tmp.cleanup()


def test_scope_restricted_edges_do_not_leak_blocked_path_internals():
    tmp, projection = make_store()
    try:
        run_id = add_run(projection)
        entry = add_candidate(projection, "concept", "public entry")
        target = add_candidate(projection, "concept", "public target behind private edge")
        edge_id = add_edge(
            projection,
            entry,
            target,
            "observed_cooccurrence",
            direction="symmetric",
            run_id=run_id,
            export_allowed=False,
        )

        result = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[entry], max_hops=1, requested_scope={"export": True}),
        )

        assert target not in candidate_ids(result)
        assert result["frontier_trace"] == [
            {
                "hop_index": 1,
                "blocked": True,
                "reason": "scope_restricted",
                "scope_decision": {
                    "allowed": False,
                    "decision": "ghosted",
                    "reason": "scope_restricted",
                    "redacted_fields": ["label", "source_refs", "path_internals"],
                    "scope_checked": ["edge"],
                    "terminal": True,
                },
            }
        ]
        assert edge_id not in str(result)
        assert target not in str(result["frontier_trace"])
        assert result["ghost_signals"][0]["suppressed_path_shape"] == []
    finally:
        projection.close()
        tmp.cleanup()


def test_eligibility_matrix_blocks_non_working_memory_statuses():
    tmp, projection = make_store()
    try:
        run_id = add_run(projection)
        entry = add_candidate(projection, "concept", "entry")
        rejected = add_candidate(projection, "concept", "rejected", acceptance="rejected")
        invalidated = add_candidate(projection, "concept", "invalidated", relation="invalidated")
        superseded = add_candidate(projection, "concept", "superseded", relation="superseded")
        conflicted = add_candidate(projection, "concept", "conflicted", relation="conflicted")
        for target in [rejected, invalidated, superseded, conflicted]:
            add_edge(projection, entry, target, "observed_cooccurrence", direction="symmetric", run_id=run_id)

        default = retrieve(projection, RetrievalQuery(entry_candidate_ids=[entry], max_hops=1))

        assert {rejected, invalidated, superseded, conflicted}.isdisjoint(candidate_ids(default))
        assert {ghost["reason"] for ghost in default["ghost_signals"]} >= {
            "rejected",
            "invalidated",
            "superseded",
            "conflicted",
        }

        with_conflicts = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[entry], max_hops=1, include_conflicts=True),
        )
        assert conflicted in candidate_ids(with_conflicts)
        assert {rejected, invalidated, superseded}.isdisjoint(candidate_ids(with_conflicts))
    finally:
        projection.close()
        tmp.cleanup()


def test_conflicted_candidate_is_terminal_even_through_ordinary_edge():
    tmp, projection = make_store()
    try:
        run_id = add_run(projection)
        entry = add_candidate(projection, "concept", "entry")
        conflicted = add_candidate(projection, "concept", "conflicted", relation="conflicted")
        onward = add_candidate(projection, "concept", "onward from conflict")
        add_edge(projection, entry, conflicted, "observed_cooccurrence", direction="symmetric", run_id=run_id)
        add_edge(projection, conflicted, onward, "observed_cooccurrence", direction="symmetric", run_id=run_id)

        included = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[entry], max_hops=2, include_conflicts=True),
        )

        assert conflicted in candidate_ids(included)
        assert onward not in candidate_ids(included)
        conflict_result = next(item for item in included["activated_candidates"] if item["candidate_id"] == conflicted)
        assert conflict_result["scope_decision"]["terminal"] is True
    finally:
        projection.close()
        tmp.cleanup()


def test_conflict_relations_are_marked_and_terminal_when_included():
    tmp, projection = make_store()
    try:
        run_id = add_run(projection)
        entry = add_candidate(projection, "concept", "entry")
        conflict = add_candidate(projection, "concept", "conflict target")
        onward = add_candidate(projection, "concept", "ordinary onward")
        add_relation(projection, entry, conflict, "conflicts_with", direction="symmetric", run_id=run_id)
        add_edge(projection, conflict, onward, "observed_cooccurrence", direction="symmetric", run_id=run_id)

        default = retrieve(projection, RetrievalQuery(entry_candidate_ids=[entry], max_hops=2))

        assert conflict not in candidate_ids(default)
        assert default["ghost_signals"][0]["reason"] == "conflicted"

        included = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[entry], max_hops=2, include_conflicts=True),
        )
        conflict_result = next(item for item in included["activated_candidates"] if item["candidate_id"] == conflict)
        conflict_step = conflict_result["activation_paths"][0]["steps"][0]
        assert conflict_step["relation_type"] == "conflicts_with"
        assert conflict_step["scope_decision"]["reason"] == "conflict_included"
        assert conflict_result["result_semantics"] == {
            "ordinary_recall": False,
            "conflict_material": True,
            "hypothesis_material": False,
            "simulation_material": False,
            "terminal": True,
        }
        assert onward not in candidate_ids(included)
    finally:
        projection.close()
        tmp.cleanup()


def test_relation_traversal_preserves_direction_confidence_and_epistemic_status():
    tmp, projection = make_store()
    try:
        run_id = add_run(projection)
        older = add_candidate(projection, "concept", "older claim")
        newer = add_candidate(projection, "concept", "newer correction")
        corroborated = add_candidate(projection, "concept", "corroborated claim")
        add_relation(
            projection,
            newer,
            older,
            "corrects",
            direction="directed",
            run_id=run_id,
            epistemic="correction",
            confidence_level="weak",
        )
        add_relation(
            projection,
            older,
            corroborated,
            "corroborates",
            direction="directed",
            run_id=run_id,
            epistemic="observed",
            confidence_level="moderate",
        )

        from_older = retrieve(projection, RetrievalQuery(entry_candidate_ids=[older], max_hops=1))
        from_newer = retrieve(projection, RetrievalQuery(entry_candidate_ids=[newer], max_hops=1))

        assert newer not in candidate_ids(from_older)
        assert corroborated in candidate_ids(from_older)
        assert older in candidate_ids(from_newer)
        corrected_result = next(item for item in from_newer["activated_candidates"] if item["candidate_id"] == older)
        step = corrected_result["activation_paths"][0]["steps"][0]
        assert step["relation_type"] == "corrects"
        assert step["record_epistemic_status"] == "correction"
        assert step["record_confidence_record"]["level"] == "weak"
        assert step["retrieval_weight"]["record_confidence_factor"] == 0.75
        assert step["retrieval_weight"]["candidate_confidence_factor"] == 1.0
        assert step["retrieval_weight"]["confidence_factor"] == 0.75
        assert step["confidence_record"] == {
            "candidate": step["candidate_confidence_record"],
            "record": step["record_confidence_record"],
        }
    finally:
        projection.close()
        tmp.cleanup()


def test_identical_labels_correction_and_contradiction_do_not_flatten_to_recall():
    tmp, projection = make_store()
    try:
        run_id = add_run(projection)
        correction = add_candidate(
            projection,
            "reflection",
            "same assertion",
            epistemic="correction",
            confidence_level="moderate",
        )
        invalidated = add_candidate(
            projection,
            "claim",
            "same assertion",
            relation="invalidated",
            confidence_level="moderate",
        )
        contradiction_entry = add_candidate(projection, "concept", "contradiction entry")
        contested = add_candidate(projection, "entity", "same assertion")
        add_relation(
            projection,
            correction,
            invalidated,
            "invalidates",
            direction="directed",
            run_id=run_id,
            epistemic="correction",
        )
        add_relation(
            projection,
            contradiction_entry,
            contested,
            "conflicts_with",
            direction="symmetric",
            run_id=run_id,
            epistemic="contradiction",
        )

        corrected = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[correction], max_hops=1, include_conflicts=True),
        )
        contradicted_default = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[contradiction_entry], max_hops=1),
        )
        contradicted_included = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[contradiction_entry], max_hops=1, include_conflicts=True),
        )

        assert invalidated not in candidate_ids(corrected)
        assert corrected["ghost_signals"][0]["reason"] == "invalidated"
        assert contested not in candidate_ids(contradicted_default)
        assert contradicted_default["ghost_signals"][0]["reason"] == "conflicted"
        contested_result = next(
            item for item in contradicted_included["activated_candidates"] if item["candidate_id"] == contested
        )
        contested_step = contested_result["activation_paths"][0]["steps"][0]
        assert contested_step["relation_type"] == "conflicts_with"
        assert contested_step["record_epistemic_status"] == "contradiction"
        assert contested_step["scope_decision"]["terminal"] is True
        assert contested_result["result_semantics"]["conflict_material"] is True
        assert contested_result["result_semantics"]["terminal"] is True
    finally:
        projection.close()
        tmp.cleanup()


def test_retrieval_accumulates_multiple_paths_and_damps_generic_hub():
    tmp, projection = make_store()
    try:
        run_id = add_run(projection)
        entry_a = add_candidate(projection, "concept", "entry A")
        entry_b = add_candidate(projection, "concept", "entry B")
        thick = add_candidate(projection, "concept", "thick memory", refs=4, confidence_level="moderate")
        hub = add_candidate(projection, "concept", "generic hub", refs=1, confidence_level="strong")
        add_edge(projection, entry_a, thick, "observed_cooccurrence", direction="symmetric", run_id=run_id)
        add_edge(projection, entry_b, thick, "observed_cooccurrence", direction="symmetric", run_id=run_id)
        add_edge(projection, entry_a, hub, "observed_cooccurrence", direction="symmetric", run_id=run_id)
        for index in range(5):
            extra = add_candidate(projection, "concept", f"generic neighbor {index}")
            add_edge(projection, hub, extra, "observed_cooccurrence", direction="symmetric", run_id=run_id)

        result = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[entry_a, entry_b], max_hops=1, working_memory_limit=10),
        )

        ordered = candidate_ids(result)
        assert ordered.index(thick) < ordered.index(hub)
        thick_result = next(item for item in result["activated_candidates"] if item["candidate_id"] == thick)
        assert len(thick_result["activation_paths"]) == 2
        assert thick_result["retrieval_weight"]["evidence_accumulation_factor"] > 1.0
    finally:
        projection.close()
        tmp.cleanup()


def test_retrieval_is_read_only_and_frontier_only_no_echo():
    tmp, projection = make_store()
    try:
        run_id = add_run(projection)
        a = add_candidate(projection, "concept", "A")
        b = add_candidate(projection, "concept", "B")
        c = add_candidate(projection, "concept", "C")
        add_edge(projection, a, b, "observed_cooccurrence", direction="symmetric", run_id=run_id)
        add_edge(projection, b, c, "observed_cooccurrence", direction="symmetric", run_id=run_id)
        before = projection_snapshot(projection)

        first = retrieve(projection, RetrievalQuery(entry_candidate_ids=[a], max_hops=2))
        second = retrieve(projection, RetrievalQuery(entry_candidate_ids=[a], max_hops=2))

        assert first["activated_candidates"] == second["activated_candidates"]
        assert before == projection_snapshot(projection)
        c_result = next(item for item in first["activated_candidates"] if item["candidate_id"] == c)
        assert all(len(path["steps"]) == 2 for path in c_result["activation_paths"])
        assert not any(
            trace["hop_index"] == 2 and trace["from_candidate_id"] == a
            for trace in first["frontier_trace"]
        )
    finally:
        projection.close()
        tmp.cleanup()


def test_working_memory_limit_returns_omitted_metadata():
    tmp, projection = make_store()
    try:
        run_id = add_run(projection)
        entry = add_candidate(projection, "concept", "entry")
        targets = [
            add_candidate(projection, "concept", f"target {index}")
            for index in range(4)
        ]
        for target in targets:
            add_edge(projection, entry, target, "observed_cooccurrence", direction="symmetric", run_id=run_id)

        result = retrieve(
            projection,
            RetrievalQuery(entry_candidate_ids=[entry], max_hops=1, working_memory_limit=2),
        )

        assert len(result["activated_candidates"]) == 2
        assert result["omitted_candidates"]
        assert all(item["reason"] == "working_memory_limit" for item in result["omitted_candidates"])
    finally:
        projection.close()
        tmp.cleanup()


def projection_snapshot(projection):
    tables = [
        "memory_candidates",
        "memory_edges",
        "projection_relations",
        "projection_decisions",
        "projection_rejections",
        "projection_evidence_refs",
        "projection_runs",
    ]
    snapshot = {}
    for table in tables:
        rows = projection._conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()  # noqa: SLF001
        snapshot[table] = [dict(row) for row in rows]
    return snapshot


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
