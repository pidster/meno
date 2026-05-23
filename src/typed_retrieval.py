"""Phase 3 typed retrieval over projected memory.

Retrieval is read-only in this phase. It consumes the Phase 2 projection
surface and returns structural activation traces; it does not mutate memory or
write retrieval traces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import uuid
from typing import Any

from memory_projection import ProjectionStore, stable_hash


POLICY_VERSION = 1

EDGE_FACTORS = {
    "observed_cooccurrence": 0.70,
    "explicit_claim": 0.45,
    "reflective_interpretation": 0.40,
    "contradiction": 0.20,
    "correction": 0.25,
    "dream_association": 0.30,
    "rehearsal_candidate": 0.30,
    "outcome_confirmation": 0.60,
    "outcome_falsification": 0.25,
    "outcome_partial_match": 0.40,
    "outcome_inconclusive": 0.20,
    "temporal_sequence": 0.35,
    "participation": 0.45,
}

RELATION_FACTORS = {
    "conflicts_with": 0.20,
    "supersedes": 0.20,
    "invalidates": 0.15,
    "corrects": 0.25,
    "corroborates": 0.55,
    "outcome_confirms": 0.60,
    "outcome_falsifies": 0.25,
    "outcome_partially_matches": 0.40,
    "outcome_inconclusive_for": 0.20,
}

CONFIDENCE_FACTORS = {
    "none": 0.0,
    "weak": 0.75,
    "moderate": 0.90,
    "strong": 1.0,
    "decisive": 1.10,
}

STATUS_FACTORS = {
    "accepted": 1.0,
    "provisional": 0.60,
    "candidate": 0.50,
    "rejected": 0.0,
}

CANDIDATE_LIFECYCLE_FACTORS = {
    "active": 1.0,
    "dormant": 0.25,
    "rediscovered": 0.85,
    "pruning_proposed": 0.20,
    "tombstoned": 0.0,
}

EDGE_LIFECYCLE_FACTORS = {
    "active": 1.0,
    "weakened": 0.45,
    "archived": 0.0,
    "rediscovered_bridge": 0.80,
    "pruning_proposed": 0.20,
    "released": 0.0,
    "tombstoned": 0.0,
}

EPISTEMIC_FACTORS = {
    "observed": 1.0,
    "authored": 0.80,
    "inferred": 0.70,
    "hypothesis": 0.45,
    "simulation": 0.45,
    "correction": 0.70,
    "retraction": 0.60,
    "contradiction": 0.50,
    "mixed": 0.70,
}


@dataclass(frozen=True)
class RetrievalQuery:
    signals: list[str] = field(default_factory=list)
    entry_candidate_ids: list[str] = field(default_factory=list)
    requested_scope: dict[str, Any] = field(default_factory=dict)
    max_hops: int = 2
    working_memory_limit: int = 10
    include_hypotheses: bool = False
    include_simulations: bool = False
    include_conflicts: bool = False
    query_id: str = field(default_factory=lambda: "rq_" + uuid.uuid4().hex[:16])
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


class TypedRetriever:
    def __init__(self, projection: ProjectionStore):
        self.projection = projection

    def retrieve(self, query: RetrievalQuery) -> dict[str, Any]:
        candidates = {item["candidate_id"]: item for item in self.projection.candidates()}
        records = self._traversal_records()
        degree = self._degree(records)
        entry_ids = self._entry_ids(query, candidates)
        warnings: list[dict[str, Any]] = []
        if not entry_ids:
            warnings.append({"kind": "no_entry_candidates", "signals": list(query.signals)})

        activation: dict[str, dict[str, Any]] = {}
        frontier: dict[str, list[dict[str, Any]]] = {}
        ghost_signals: list[dict[str, Any]] = []
        frontier_trace: list[dict[str, Any]] = []

        for entry_id in sorted(entry_ids):
            candidate = candidates.get(entry_id)
            if candidate is None:
                warnings.append({"kind": "missing_entry_candidate", "candidate_id": entry_id})
                continue
            decision = self._eligibility(candidate, query)
            if not decision["allowed"]:
                ghost_signals.append(
                    self._ghost(
                        reason=decision["reason"],
                        candidate=candidate,
                        path_shape=[],
                        scope_decision=decision,
                    )
                )
                continue
            path = {
                "entry_candidate_id": entry_id,
                "target_candidate_id": entry_id,
                "steps": [],
                "total_transmission": 1.0,
                "blocked_steps": [],
                "evidence_refs": candidate["source_refs"],
            }
            activation[entry_id] = {
                "score": 1.0,
                "paths": [path],
                "candidate": candidate,
                "weight": self._entry_weight(candidate, degree.get(entry_id, 0)),
            }
            frontier[entry_id] = [path]

        for hop in range(1, max(query.max_hops, 0) + 1):
            next_frontier: dict[str, list[dict[str, Any]]] = {}
            for from_id in sorted(frontier):
                for record in self._outgoing(records, from_id):
                    to_id = record["to_candidate_id"]
                    to_candidate = candidates.get(to_id)
                    if to_candidate is None:
                        continue
                    source_paths = frontier[from_id]
                    for source_path in source_paths:
                        incoming = float(source_path["total_transmission"])
                        weight = self._step_weight(
                            record=record,
                            candidate=to_candidate,
                            hop=hop,
                            degree=degree.get(to_id, 0),
                        )
                        outgoing = incoming * weight["final"]
                        scope_decision = self._step_decision(record, to_candidate, query)
                        step = {
                            "from_candidate_id": from_id,
                            "to_candidate_id": to_id,
                            "record_type": record["record_type"],
                            "record_id": record["record_id"],
                            "edge_type": record.get("edge_type"),
                            "relation_type": record.get("relation_type"),
                            "stored_direction": record["stored_direction"],
                            "traversal_direction": record["traversal_direction"],
                            "hop_index": hop,
                            "incoming_activation": round(incoming, 6),
                            "transmission_factor": round(weight["final"], 6),
                            "outgoing_activation": round(outgoing, 6),
                            "candidate_kind": to_candidate["kind"],
                            "acceptance_status": to_candidate["acceptance_status"],
                            "relation_status": to_candidate["relation_status"],
                            "epistemic_status": to_candidate["epistemic_status"],
                            "confidence_record": {
                                "candidate": to_candidate["confidence"],
                                "record": record["confidence"],
                            },
                            "candidate_confidence_record": to_candidate["confidence"],
                            "record_confidence_record": record["confidence"],
                            "record_epistemic_status": record["epistemic_status"],
                            "record_lifecycle": record["lifecycle"],
                            "candidate_lifecycle": to_candidate["lifecycle"],
                            "retrieval_weight": weight,
                            "scope_decision": scope_decision,
                            "source_refs": record["source_refs"],
                            "why_allowed": self._why_allowed(record, to_candidate, scope_decision),
                        }
                        new_path = {
                            "entry_candidate_id": source_path["entry_candidate_id"],
                            "target_candidate_id": to_id,
                            "steps": source_path["steps"] + [step],
                            "total_transmission": round(outgoing, 6),
                            "blocked_steps": list(source_path["blocked_steps"]),
                            "evidence_refs": source_path["evidence_refs"] + record["source_refs"] + to_candidate["source_refs"],
                        }
                        if not scope_decision["allowed"]:
                            blocked_path = dict(new_path)
                            blocked_path["blocked_steps"] = new_path["blocked_steps"] + [step]
                            frontier_trace.append(self._blocked_trace(hop, scope_decision, record))
                            ghost_signals.append(
                                self._ghost(
                                    reason=scope_decision["reason"],
                                    candidate=to_candidate,
                                    path_shape=self._ghost_path_shape(blocked_path["steps"], scope_decision),
                                    scope_decision=scope_decision,
                                    record=record,
                                )
                            )
                            continue
                        frontier_trace.append(
                            {
                                "hop_index": hop,
                                "from_candidate_id": from_id,
                                "to_candidate_id": to_id,
                                "record_type": record["record_type"],
                                "record_id": record["record_id"],
                                "outgoing_activation": round(outgoing, 6),
                                "scope_decision": scope_decision,
                            }
                        )
                        current = activation.setdefault(
                            to_id,
                            {
                                "score": 0.0,
                                "paths": [],
                                "candidate": to_candidate,
                                "weight": weight,
                            },
                        )
                        current["score"] = round(float(current["score"]) + outgoing, 6)
                        current["paths"].append(new_path)
                        if not scope_decision.get("terminal", False):
                            next_frontier.setdefault(to_id, []).append(new_path)
            frontier = next_frontier

        activated = self._activated_results(activation, query, degree)
        omitted: list[dict[str, Any]] = []
        if len(activated) > query.working_memory_limit:
            kept = activated[: query.working_memory_limit]
            for rank, item in enumerate(activated[query.working_memory_limit :], start=query.working_memory_limit + 1):
                omitted.append(
                    {
                        "candidate_id": item["candidate_id"],
                        "rank": rank,
                        "reason": "working_memory_limit",
                        "safe_kind": item["kind"],
                    }
                )
            activated = kept

        return {
            "query_id": query.query_id,
            "activated_candidates": activated,
            "ghost_signals": self._dedupe_ghosts(ghost_signals),
            "omitted_candidates": omitted,
            "frontier_trace": frontier_trace,
            "policy_version": POLICY_VERSION,
            "warnings": warnings,
        }

    def _entry_ids(
        self,
        query: RetrievalQuery,
        candidates: dict[str, dict[str, Any]],
    ) -> list[str]:
        if query.entry_candidate_ids:
            return sorted(dict.fromkeys(query.entry_candidate_ids))
        return []

    def _traversal_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for edge in self.projection.edges():
            records.extend(self._record_directions(edge, "edge"))
        for relation in self.projection.relations():
            records.extend(self._record_directions(relation, "relation"))
        return records

    def _record_directions(self, record: dict[str, Any], record_type: str) -> list[dict[str, Any]]:
        relation_type = record.get("relation_type")
        edge_type = record.get("edge_type")
        stored = record["direction"]
        source = record["source_candidate_id"]
        target = record["target_candidate_id"]
        if record_type == "edge":
            allowed = self._edge_allowed_directions(edge_type, stored)
        else:
            allowed = self._relation_allowed_directions(relation_type, stored)
        output = []
        if "forward" in allowed:
            output.append(self._directional_record(record, record_type, source, target, "forward"))
        if "reverse" in allowed:
            output.append(self._directional_record(record, record_type, target, source, "reverse"))
        return output

    def _directional_record(
        self,
        record: dict[str, Any],
        record_type: str,
        source: str,
        target: str,
        traversal_direction: str,
    ) -> dict[str, Any]:
        return {
            "record_type": record_type,
            "record_id": record["id"],
            "source_candidate_id": record["source_candidate_id"],
            "target_candidate_id": record["target_candidate_id"],
            "from_candidate_id": source,
            "to_candidate_id": target,
            "edge_type": record.get("edge_type"),
            "relation_type": record.get("relation_type"),
            "stored_direction": record["direction"],
            "traversal_direction": traversal_direction,
            "confidence": record["confidence"],
            "epistemic_status": record.get("epistemic_status")
            or record["confidence"].get("evidence_class", "observed"),
            "source_refs": record["source_refs"],
            "privacy_scope": record["privacy_scope"],
            "resource_scope": record["resource_scope"],
            "lifecycle": record.get(
                "lifecycle",
                {
                    "lifecycle_state": "active",
                    "accessibility": 1.0,
                    "traversal_factor": 1.0,
                },
            ),
        }

    def _edge_allowed_directions(self, edge_type: str, stored_direction: str) -> set[str]:
        if edge_type in {"outcome_confirmation", "outcome_falsification", "outcome_partial_match", "outcome_inconclusive"}:
            return {"forward"}
        if edge_type in {"temporal_sequence", "dream_association", "rehearsal_candidate", "correction", "explicit_claim", "reflective_interpretation"}:
            return {"forward"} if stored_direction != "reverse" else {"reverse"}
        if stored_direction == "symmetric":
            return {"forward", "reverse"}
        if stored_direction == "reverse":
            return {"reverse"}
        return {"forward"}

    def _relation_allowed_directions(self, relation_type: str, stored_direction: str) -> set[str]:
        if relation_type in {"outcome_confirms", "outcome_falsifies", "outcome_partially_matches", "outcome_inconclusive_for"}:
            return {"forward"}
        if relation_type == "conflicts_with":
            return {"forward", "reverse"}
        if relation_type in {"supersedes", "invalidates", "corrects", "corroborates"}:
            return {"forward"} if stored_direction != "reverse" else {"reverse"}
        if stored_direction == "symmetric":
            return {"forward", "reverse"}
        return {"forward"}

    def _outgoing(self, records: list[dict[str, Any]], candidate_id: str) -> list[dict[str, Any]]:
        return sorted(
            [record for record in records if record["from_candidate_id"] == candidate_id],
            key=lambda record: (record["record_type"], record["edge_type"] or record["relation_type"], record["record_id"], record["to_candidate_id"]),
        )

    def _degree(self, records: list[dict[str, Any]]) -> dict[str, int]:
        degree: dict[str, set[str]] = {}
        for record in records:
            degree.setdefault(record["from_candidate_id"], set()).add(record["to_candidate_id"])
            degree.setdefault(record["to_candidate_id"], set()).add(record["from_candidate_id"])
        return {candidate_id: len(neighbors) for candidate_id, neighbors in degree.items()}

    def _eligibility(self, candidate: dict[str, Any], query: RetrievalQuery) -> dict[str, Any]:
        scope = self._scope_decision(candidate.get("privacy_scope", {}), candidate.get("resource_scope", {}), query)
        if not scope["allowed"]:
            return scope
        acceptance = candidate["acceptance_status"]
        relation = candidate["relation_status"]
        epistemic = candidate["epistemic_status"]
        lifecycle = candidate.get("lifecycle", {})
        if lifecycle.get("lifecycle_state") == "tombstoned":
            return self._blocked("tombstoned", scope_checked=["candidate_lifecycle"])
        if acceptance == "rejected":
            return self._blocked("rejected", scope_checked=["candidate"])
        if relation in {"invalidated", "superseded"}:
            return self._blocked(relation, scope_checked=["candidate"])
        if epistemic == "hypothesis" and not query.include_hypotheses:
            return self._blocked("hypothesis_suppressed", scope_checked=["candidate"])
        if epistemic == "simulation" and not query.include_simulations:
            return self._blocked("simulation_suppressed", scope_checked=["candidate"])
        if relation == "conflicted" and not query.include_conflicts:
            return self._blocked("conflicted", scope_checked=["candidate"])
        return {
            "allowed": True,
            "decision": "allowed",
            "reason": "eligible",
            "redacted_fields": [],
            "scope_checked": ["candidate"],
            "terminal": relation == "conflicted",
        }

    def _step_decision(
        self,
        record: dict[str, Any],
        candidate: dict[str, Any],
        query: RetrievalQuery,
    ) -> dict[str, Any]:
        edge_type = record.get("edge_type")
        relation_type = record.get("relation_type")
        lifecycle = record.get("lifecycle", {})
        if lifecycle.get("lifecycle_state") in {"archived", "released", "tombstoned"}:
            return self._blocked("archived", scope_checked=["edge_lifecycle"])
        if edge_type == "dream_association" and not query.include_hypotheses:
            return self._blocked("hypothesis_suppressed", scope_checked=["edge"])
        if edge_type == "rehearsal_candidate" and not query.include_simulations:
            return self._blocked("simulation_suppressed", scope_checked=["edge"])
        if edge_type == "contradiction" and not query.include_conflicts:
            return self._blocked("conflicted", scope_checked=["edge"])
        if relation_type in {"conflicts_with", "invalidates", "supersedes"} and not query.include_conflicts:
            return self._blocked("conflicted", scope_checked=["relation"])

        candidate_decision = self._eligibility(candidate, query)
        if not candidate_decision["allowed"]:
            return candidate_decision
        scope = self._scope_decision(record["privacy_scope"], record["resource_scope"], query)
        if not scope["allowed"]:
            scope["scope_checked"] = ["edge" if record["record_type"] == "edge" else "relation"]
            return scope
        decision = dict(candidate_decision)
        decision["scope_checked"] = sorted(set(candidate_decision["scope_checked"] + scope["scope_checked"]))
        if edge_type == "contradiction" or relation_type in {"conflicts_with", "invalidates", "supersedes"}:
            decision["reason"] = "conflict_included"
            decision["terminal"] = True
        return decision

    def _scope_decision(
        self,
        privacy: dict[str, Any],
        resource: dict[str, Any],
        query: RetrievalQuery,
    ) -> dict[str, Any]:
        requested = query.requested_scope or {}
        if requested.get("export") and not privacy.get("export_allowed", False):
            return self._blocked(
                "scope_restricted",
                redacted_fields=["label", "source_refs", "path_internals"],
            )
        if requested.get("network") and not resource.get("network_access", False):
            return self._blocked(
                "scope_restricted",
                redacted_fields=["label", "source_refs", "path_internals"],
            )
        if requested.get("external_contact") and not resource.get("external_contact", False):
            return self._blocked(
                "scope_restricted",
                redacted_fields=["label", "source_refs", "path_internals"],
            )
        if requested.get("autonomous_spend") and not resource.get("autonomous_spend", False):
            return self._blocked(
                "scope_restricted",
                redacted_fields=["label", "source_refs", "path_internals"],
            )
        if requested.get("compute_escalation") and not resource.get("compute_escalation", False):
            return self._blocked(
                "scope_restricted",
                redacted_fields=["label", "source_refs", "path_internals"],
            )
        return {
            "allowed": True,
            "decision": "allowed",
            "reason": "scope_allows",
            "redacted_fields": [],
            "scope_checked": ["candidate", "edge", "relation", "source_refs"],
            "terminal": False,
        }

    def _blocked(
        self,
        reason: str,
        redacted_fields: list[str] | None = None,
        scope_checked: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "allowed": False,
            "decision": "ghosted",
            "reason": reason,
            "redacted_fields": redacted_fields or ["label", "source_refs", "path_internals"],
            "scope_checked": scope_checked or ["candidate"],
            "terminal": True,
        }

    def _blocked_trace(
        self,
        hop: int,
        decision: dict[str, Any],
        record: dict[str, Any],
    ) -> dict[str, Any]:
        trace = {
            "hop_index": hop,
            "blocked": True,
            "reason": decision["reason"],
            "scope_decision": decision,
        }
        if "path_internals" not in decision.get("redacted_fields", []):
            trace["safe_edge_type"] = record.get("edge_type")
            trace["safe_relation_type"] = record.get("relation_type")
        return trace

    def _ghost_path_shape(
        self,
        steps: list[dict[str, Any]],
        decision: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if "path_internals" in decision.get("redacted_fields", []):
            return []
        return steps

    def _step_weight(
        self,
        *,
        record: dict[str, Any],
        candidate: dict[str, Any],
        hop: int,
        degree: int,
    ) -> dict[str, Any]:
        edge_factor = EDGE_FACTORS.get(record.get("edge_type"), 1.0) if record["record_type"] == "edge" else 1.0
        relation_factor = RELATION_FACTORS.get(record.get("relation_type"), 1.0) if record["record_type"] == "relation" else 1.0
        record_confidence = dict(record["confidence"])
        record_confidence["_lifecycle"] = record.get("lifecycle", {})
        return self._weight(
            candidate=candidate,
            record_confidence=record_confidence,
            edge_type_factor=edge_factor,
            relation_type_factor=relation_factor,
            hop=hop,
            degree=degree,
            scope_factor=1.0,
        )

    def _entry_weight(self, candidate: dict[str, Any], degree: int) -> dict[str, Any]:
        return self._weight(
            candidate=candidate,
            record_confidence=None,
            edge_type_factor=1.0,
            relation_type_factor=1.0,
            hop=0,
            degree=degree,
            scope_factor=1.0,
        )

    def _weight(
        self,
        *,
        candidate: dict[str, Any],
        record_confidence: dict[str, Any] | None,
        edge_type_factor: float,
        relation_type_factor: float,
        hop: int,
        degree: int,
        scope_factor: float,
    ) -> dict[str, Any]:
        status_factor = STATUS_FACTORS.get(candidate["acceptance_status"], 0.4)
        epistemic_factor = EPISTEMIC_FACTORS.get(candidate["epistemic_status"], 0.5)
        candidate_lifecycle = candidate.get("lifecycle", {})
        candidate_lifecycle_factor = CANDIDATE_LIFECYCLE_FACTORS.get(
            candidate_lifecycle.get("lifecycle_state", "active"),
            0.5,
        ) * float(candidate_lifecycle.get("accessibility", 1.0))
        record_lifecycle_factor = 1.0
        if record_confidence is not None:
            record_lifecycle = record_confidence.get("_lifecycle", {})
            record_lifecycle_factor = EDGE_LIFECYCLE_FACTORS.get(
                record_lifecycle.get("lifecycle_state", "active"),
                0.5,
            ) * float(record_lifecycle.get("traversal_factor", 1.0))
        candidate_confidence_factor = CONFIDENCE_FACTORS.get(candidate["confidence"].get("level", "weak"), 0.75)
        record_confidence_factor = (
            CONFIDENCE_FACTORS.get(record_confidence.get("level", "weak"), 0.75)
            if record_confidence is not None
            else 1.0
        )
        if candidate["epistemic_status"] in {"hypothesis", "simulation"}:
            evidence_factor = 1.0
        else:
            evidence_factor = min(1.5, 1.0 + (max(0, len(candidate["source_refs"]) - 1) * 0.10))
        path_factor = 1.0 if hop == 0 else 1.0 / (hop + 0.5)
        centrality_factor = 1.0 / (1.0 + max(0, degree - 2) * 0.25)
        final = (
            1.0
            * edge_type_factor
            * relation_type_factor
            * status_factor
            * epistemic_factor
            * candidate_lifecycle_factor
            * record_lifecycle_factor
            * candidate_confidence_factor
            * record_confidence_factor
            * evidence_factor
            * path_factor
            * centrality_factor
            * scope_factor
        )
        return {
            "base": 1.0,
            "edge_type_factor": edge_type_factor,
            "relation_type_factor": relation_type_factor,
            "status_factor": status_factor,
            "epistemic_factor": epistemic_factor,
            "candidate_lifecycle_factor": round(candidate_lifecycle_factor, 6),
            "record_lifecycle_factor": round(record_lifecycle_factor, 6),
            "candidate_confidence_factor": candidate_confidence_factor,
            "record_confidence_factor": record_confidence_factor,
            "confidence_factor": round(candidate_confidence_factor * record_confidence_factor, 6),
            "evidence_accumulation_factor": round(evidence_factor, 6),
            "path_length_factor": round(path_factor, 6),
            "centrality_damping_factor": round(centrality_factor, 6),
            "scope_factor": scope_factor,
            "final": round(final, 6),
            "rationale": "retrieval weight separates activation from evidence confidence",
        }

    def _activated_results(
        self,
        activation: dict[str, dict[str, Any]],
        query: RetrievalQuery,
        degree: dict[str, int],
    ) -> list[dict[str, Any]]:
        results = []
        for cid, data in activation.items():
            candidate = data["candidate"]
            paths = sorted(
                data["paths"],
                key=lambda path: (-path["total_transmission"], len(path["steps"]), path["target_candidate_id"]),
            )
            result_semantics = self._result_semantics(paths, candidate)
            result = {
                "candidate_id": cid,
                "kind": candidate["kind"],
                "label": candidate["label"],
                "acceptance_status": candidate["acceptance_status"],
                "relation_status": candidate["relation_status"],
                "epistemic_status": candidate["epistemic_status"],
                "lifecycle": candidate["lifecycle"],
                "activation_score": round(float(data["score"]), 6),
                "retrieval_weight": data["weight"],
                "activation_paths": paths,
                "source_refs": candidate["source_refs"],
                "scope_decision": self._eligibility(candidate, query),
                "result_semantics": result_semantics,
                "explanation": {
                    "kind": "structural",
                    "path_count": len(paths),
                    "evidence_ref_count": len(candidate["source_refs"]),
                    "centrality_degree": degree.get(cid, 0),
                },
            }
            results.append(result)
        return sorted(
            results,
            key=lambda item: (
                -item["activation_score"],
                -len(item["source_refs"]),
                item["retrieval_weight"]["centrality_damping_factor"],
                max(
                    (ref["event_sequence"] for ref in item["source_refs"]),
                    default=0,
                )
                * -1,
                item["candidate_id"],
            ),
        )

    def _result_semantics(self, paths: list[dict[str, Any]], candidate: dict[str, Any]) -> dict[str, Any]:
        conflict_steps = []
        hypothesis_steps = []
        simulation_steps = []
        for path in paths:
            for step in path["steps"]:
                if step["scope_decision"].get("reason") == "conflict_included":
                    conflict_steps.append(step)
                if step.get("edge_type") == "dream_association":
                    hypothesis_steps.append(step)
                if step.get("edge_type") == "rehearsal_candidate":
                    simulation_steps.append(step)
        direct_simulation = candidate.get("epistemic_status") == "simulation"
        return {
            "ordinary_recall": not conflict_steps and not hypothesis_steps and not simulation_steps and not direct_simulation,
            "conflict_material": bool(conflict_steps),
            "hypothesis_material": bool(hypothesis_steps),
            "dream_material": bool(hypothesis_steps),
            "not_factual": bool(hypothesis_steps or simulation_steps or direct_simulation),
            "simulation_material": bool(simulation_steps or direct_simulation),
            "terminal": any(step["scope_decision"].get("terminal", False) for step in conflict_steps),
        }

    def _ghost(
        self,
        *,
        reason: str,
        candidate: dict[str, Any],
        path_shape: list[dict[str, Any]],
        scope_decision: dict[str, Any],
        record: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        safe_shape = [
            {
                "record_type": step["record_type"],
                "edge_type": step.get("edge_type"),
                "relation_type": step.get("relation_type"),
                "traversal_direction": step["traversal_direction"],
                "hop_index": step["hop_index"],
            }
            for step in path_shape
        ]
        ghost_id = "ghost_" + stable_hash(
            {
                "reason": reason,
                "candidate_id": candidate["candidate_id"],
                "shape": safe_shape,
                "record_id": record["record_id"] if record else None,
            }
        )[:24]
        return {
            "ghost_id": ghost_id,
            "reason": reason,
            "safe_kind": candidate["kind"],
            "safe_status": candidate["acceptance_status"],
            "safe_relation_type": record.get("relation_type") if record else None,
            "safe_edge_type": record.get("edge_type") if record else None,
            "redacted": True,
            "suppressed_path_shape": safe_shape,
            "scope_decision": scope_decision,
        }

    def _dedupe_ghosts(self, ghosts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        for ghost in ghosts:
            deduped[ghost["ghost_id"]] = ghost
        return [deduped[key] for key in sorted(deduped)]

    def _why_allowed(
        self,
        record: dict[str, Any],
        candidate: dict[str, Any],
        scope_decision: dict[str, Any],
    ) -> str:
        if not scope_decision["allowed"]:
            return f"blocked:{scope_decision['reason']}"
        record_kind = record.get("edge_type") or record.get("relation_type")
        return (
            f"{record_kind} permits {record['traversal_direction']} traversal "
            f"to {candidate['kind']}:{candidate['acceptance_status']}:"
            f"{candidate['epistemic_status']}"
        )


def retrieve(projection: ProjectionStore, query: RetrievalQuery) -> dict[str, Any]:
    return TypedRetriever(projection).retrieve(query)
