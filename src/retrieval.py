"""Phase 2: Retrieval Engine — Spreading Activation.

Implements the triggering and retrieval mechanism from docs/03-triggering-and-retrieval.md.
Signal arrives -> entry points identified -> activation spreads through weighted edges ->
threshold applied -> top-N returned as working memory.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math

from surrealdb import RecordID


def _to_record_id(node_id: str) -> RecordID:
    """Convert 'table:record' string to a RecordID object."""
    table, record = node_id.split(":", 1)
    return RecordID(table, record)


@dataclass
class RetrievalConfig:
    """Configuration for spreading activation retrieval."""
    decay_per_hop: float = 0.6
    max_hops: int = 3
    min_transmission: float = 0.01
    ghost_threshold: float = 0.005
    activation_threshold: float = 0.1
    working_memory_limit: int = 7
    learning_rate: float = 0.05
    max_edge_weight: float = 1.0


@dataclass
class GhostSignal:
    """A sub-threshold activation — the 'tip of the tongue' phenomenon."""
    target_id: str
    strength: float
    via_edge_id: str
    source_id: str


@dataclass
class RetrievalResult:
    """Result of a spreading activation retrieval."""
    activated_nodes: List[Tuple[str, float]]  # (node_id, activation_level)
    ghost_signals: List[GhostSignal]
    activation_map: Dict[str, float]
    hops_used: int


def identify_entry_points(client, signal: dict) -> Dict[str, float]:
    """Match a signal against the graph to find entry nodes.

    Signal can contain:
        - entities: list of entity names to match
        - concepts: list of concept names/keywords to match
        - keywords: list of keywords to match against experience content/tags
    """
    entry_points = {}

    # Match entities by name
    for entity_name in signal.get('entities', []):
        results = client.query(
            "SELECT * FROM entity WHERE name = $name;",
            {"name": entity_name}
        )
        for r in results:
            node_id = str(r['id'])
            entry_points[node_id] = max(entry_points.get(node_id, 0), r.get('salience', 0.5))

    # Match concepts by name (substring match)
    for concept_term in signal.get('concepts', []):
        results = client.query(
            "SELECT * FROM concept WHERE string::lowercase(name) CONTAINS string::lowercase($term);",
            {"term": concept_term}
        )
        for r in results:
            node_id = str(r['id'])
            entry_points[node_id] = max(entry_points.get(node_id, 0), r.get('salience', 0.5))

    # Match keywords against experience tags and content
    for keyword in signal.get('keywords', []):
        results = client.query(
            "SELECT * FROM experience WHERE $kw IN tags OR content CONTAINS $kw;",
            {"kw": keyword}
        )
        for r in results:
            node_id = str(r['id'])
            entry_points[node_id] = max(entry_points.get(node_id, 0), r.get('salience', 0.5))

    return entry_points


def _get_edges_from(client, node_id: str) -> list:
    """Get all outgoing edges from a node, across all edge types."""
    rid = _to_record_id(node_id)
    edges = []

    edge_specs = [
        ('associates',      'out', 'out AS target', lambda r: r.get('weight', 0.5)),
        ('associates',      'in',  'in AS target',  lambda r: r.get('weight', 0.5)),
        ('participated_in', 'out', 'out AS target', lambda r: 0.7),
        ('participated_in', 'in',  'in AS target',  lambda r: 0.7),
        ('exemplifies',     'out', 'out AS target', lambda r: r.get('strength', 0.5)),
        ('exemplifies',     'in',  'in AS target',  lambda r: r.get('strength', 0.5)),
        ('followed_by',     'out', 'out AS target', lambda r: 0.5),
        ('followed_by',     'in',  'in AS target',  lambda r: 0.5),
    ]

    for table, match_field, target_expr, weight_fn in edge_specs:
        where_field = 'in' if match_field == 'out' else 'out'
        results = client.query(
            f"SELECT *, {target_expr} FROM {table} WHERE {where_field} = $node;",
            {"node": rid}
        )
        for r in results:
            edges.append({
                'id': str(r['id']),
                'target': str(r['target']),
                'weight': weight_fn(r),
                'table': table
            })

    return edges


def spread_activation(client, entry_points: Dict[str, float],
                      config: RetrievalConfig = None) -> RetrievalResult:
    """Spread activation from entry points through the graph.

    This is the core retrieval mechanism. Activation propagates along edges,
    accumulating across multiple paths. Nodes weakly connected to many active
    nodes can activate more strongly than nodes with one strong connection.
    """
    if config is None:
        config = RetrievalConfig()

    activation = dict(entry_points)
    ghost_signals = []
    hops_used = 0

    for hop in range(config.max_hops):
        next_activation: Dict[str, float] = {}
        any_transmitted = False

        for node_id, level in activation.items():
            if level < config.min_transmission:
                continue

            edges = _get_edges_from(client, node_id)
            for edge in edges:
                target = edge['target']
                transmitted = level * edge['weight'] * config.decay_per_hop

                if transmitted > config.min_transmission:
                    next_activation[target] = next_activation.get(target, 0) + transmitted
                    any_transmitted = True

                    # Record traversal
                    if edge['table'] in ('associates', 'exemplifies'):
                        client.query(
                            f"UPDATE $edge_id SET last_traversed = time::now(), "
                            f"traversal_count += 1;",
                            {"edge_id": _to_record_id(edge['id'])}
                        )

                elif transmitted > config.ghost_threshold:
                    ghost_signals.append(GhostSignal(
                        target_id=target,
                        strength=transmitted,
                        via_edge_id=edge['id'],
                        source_id=node_id
                    ))

        if not any_transmitted:
            break

        # Merge: accumulate new activations into existing map
        for node_id, added in next_activation.items():
            activation[node_id] = activation.get(node_id, 0) + added

        hops_used = hop + 1

    return RetrievalResult(
        activated_nodes=[],  # filled by apply_threshold
        ghost_signals=ghost_signals,
        activation_map=activation,
        hops_used=hops_used
    )


def apply_threshold(result: RetrievalResult, config: RetrievalConfig = None) -> RetrievalResult:
    """Filter activation map to top-N nodes above threshold."""
    if config is None:
        config = RetrievalConfig()

    above_threshold = [
        (node_id, level) for node_id, level in result.activation_map.items()
        if level > config.activation_threshold
    ]
    above_threshold.sort(key=lambda x: x[1], reverse=True)
    result.activated_nodes = above_threshold[:config.working_memory_limit]
    return result


def hebbian_learning(client, result: RetrievalResult, config: RetrievalConfig = None):
    """Strengthen edges between co-activated nodes.

    'Nodes that fire together wire together.' When two nodes are both
    activated above threshold, the edge between them is strengthened.
    """
    if config is None:
        config = RetrievalConfig()

    activated_ids = [node_id for node_id, _ in result.activated_nodes]

    for i, node_a in enumerate(activated_ids):
        for node_b in activated_ids[i+1:]:
            act_a = result.activation_map.get(node_a, 0)
            act_b = result.activation_map.get(node_b, 0)
            delta = config.learning_rate * act_a * act_b

            if delta < 0.001:
                continue

            # Check if edge exists between them (in associates table)
            rid_a = _to_record_id(node_a)
            rid_b = _to_record_id(node_b)
            edges = client.query(
                "SELECT * FROM associates WHERE (in = $a AND out = $b) "
                "OR (in = $b AND out = $a);",
                {"a": rid_a, "b": rid_b}
            )

            if edges:
                # Strengthen existing edge
                edge = edges[0]
                new_weight = min(edge['weight'] + delta, config.max_edge_weight)
                client.query(
                    "UPDATE $edge_id SET weight = $w;",
                    {"edge_id": edge['id'], "w": new_weight}
                )
            # Note: new edge creation (for frequently co-activated nodes
            # without direct edges) is deferred to Phase 3's consolidation


def retrieve(client, signal: dict, config: RetrievalConfig = None) -> RetrievalResult:
    """Full retrieval pipeline: entry points -> spread -> threshold -> learn."""
    if config is None:
        config = RetrievalConfig()

    entry_points = identify_entry_points(client, signal)
    if not entry_points:
        return RetrievalResult(
            activated_nodes=[], ghost_signals=[],
            activation_map={}, hops_used=0
        )

    result = spread_activation(client, entry_points, config)
    result = apply_threshold(result, config)
    hebbian_learning(client, result, config)

    # Update last_activated on retrieved nodes
    for node_id, _ in result.activated_nodes:
        client.query(
            "UPDATE $node SET last_activated = time::now(), activation_count += 1;",
            {"node": _to_record_id(node_id)}
        )

    return result
