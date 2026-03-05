"""Phase 3: Forgetting and Vitality.

Three-tier forgetting (edge decay, node islanding, true pruning),
ghost signal pathways for islanded nodes, embedding-based reconnection,
and cognitive vitality assessment.
"""

import math
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from surrealdb import RecordID


@dataclass
class DecayConfig:
    """Configuration for forgetting dynamics."""
    edge_decay_rate: float = 0.05        # per simulated time unit
    node_decay_rate: float = 0.01        # much slower than edges
    edge_prune_threshold: float = 0.05   # edges below this are pruned
    node_prune_threshold: float = 0.1    # nodes below this + disconnected = pruned
    ghost_edge_threshold: float = 0.1    # edges below this produce ghost signals
    reconnection_threshold: float = 0.7  # embedding similarity for reconnection
    reconnection_initial_weight: float = 0.3


@dataclass
class VitalityWeights:
    """Weights for cognitive vitality score components."""
    density: float = 0.20
    relevance: float = 0.20
    confabulation: float = 0.15
    reconstruction: float = 0.15
    reflection: float = 0.10
    preference: float = 0.10
    consistency: float = 0.05
    continuity: float = 0.05


@dataclass
class VitalityResult:
    """Result of a cognitive vitality assessment."""
    score: float
    status: str  # vital, declining, critical, zombie
    components: Dict[str, float]
    leading_indicators: Dict[str, float]


def _to_record_id(node_id: str) -> RecordID:
    """Convert 'table:record' string to a RecordID object."""
    table, record = node_id.split(":", 1)
    return RecordID(table, record)


# =============================================================
# EDGE DECAY
# =============================================================

def decay_edges(client, time_elapsed: float, config: DecayConfig = None):
    """Apply exponential decay to all edge weights based on time since last traversal.

    edge.weight *= exp(-EDGE_DECAY_RATE * time_elapsed)

    Edges are the paths to memories. They decay faster than nodes,
    creating islanded memories — available but inaccessible.
    """
    if config is None:
        config = DecayConfig()

    decay_factor = math.exp(-config.edge_decay_rate * time_elapsed)

    # Decay associates edges
    client.query(
        "UPDATE associates SET weight = weight * $factor;",
        {"factor": decay_factor}
    )

    # Decay exemplifies edges
    client.query(
        "UPDATE exemplifies SET strength = strength * $factor;",
        {"factor": decay_factor}
    )

    return decay_factor


def prune_weak_edges(client, config: DecayConfig = None) -> int:
    """Remove edges that have decayed below the prune threshold."""
    if config is None:
        config = DecayConfig()

    # Count before deletion
    weak_assoc = client.query(
        "SELECT count() AS c FROM associates WHERE weight < $thresh GROUP ALL;",
        {"thresh": config.edge_prune_threshold}
    )
    weak_exemp = client.query(
        "SELECT count() AS c FROM exemplifies WHERE strength < $thresh GROUP ALL;",
        {"thresh": config.edge_prune_threshold}
    )

    count = 0
    if weak_assoc and isinstance(weak_assoc[0], dict):
        count += weak_assoc[0].get('c', 0)
    if weak_exemp and isinstance(weak_exemp[0], dict):
        count += weak_exemp[0].get('c', 0)

    # Delete weak edges
    client.query(
        "DELETE associates WHERE weight < $thresh;",
        {"thresh": config.edge_prune_threshold}
    )
    client.query(
        "DELETE exemplifies WHERE strength < $thresh;",
        {"thresh": config.edge_prune_threshold}
    )

    return count


# =============================================================
# NODE DECAY
# =============================================================

def decay_nodes(client, time_elapsed: float, config: DecayConfig = None):
    """Apply salience decay to all nodes. Much slower than edge decay."""
    if config is None:
        config = DecayConfig()

    decay_factor = math.exp(-config.node_decay_rate * time_elapsed)

    for table in ['experience', 'concept', 'entity', 'reflection']:
        client.query(
            f"UPDATE {table} SET salience = salience * $factor;",
            {"factor": decay_factor}
        )

    return decay_factor


# =============================================================
# ISLANDING DETECTION
# =============================================================

def detect_islanded_nodes(client, config: DecayConfig = None) -> List[dict]:
    """Find nodes where all connected edges are below the ghost threshold.

    An islanded node is available but inaccessible — it exists in the graph
    but spreading activation can't reach it through normal traversal.
    This is 'knowing you knew something without being able to retrieve it.'
    """
    if config is None:
        config = DecayConfig()

    islanded = []
    threshold = config.ghost_edge_threshold

    for table in ['experience', 'concept', 'reflection']:
        # Find nodes that have no strong incoming/outgoing associates edges
        # AND no strong exemplifies edges
        results = client.query(f"""
            SELECT * FROM {table} WHERE
                array::len(
                    (SELECT id FROM associates
                     WHERE (in = $parent.id OR out = $parent.id)
                     AND weight >= {threshold})
                ) == 0
                AND
                array::len(
                    (SELECT id FROM exemplifies
                     WHERE (in = $parent.id OR out = $parent.id)
                     AND strength >= {threshold})
                ) == 0
                AND
                array::len(
                    (SELECT id FROM participated_in
                     WHERE in = $parent.id OR out = $parent.id)
                ) == 0
                AND
                array::len(
                    (SELECT id FROM followed_by
                     WHERE in = $parent.id OR out = $parent.id)
                ) == 0;
        """)
        for r in results:
            islanded.append({
                'id': str(r['id']),
                'table': table,
                'salience': r.get('salience', 0),
                'content': r.get('content', r.get('name', r.get('description', '')))
            })

    return islanded


def detect_weakly_connected_nodes(client, config: DecayConfig = None) -> List[dict]:
    """Find nodes where all edges are below ghost threshold but above prune threshold.

    These are the nodes that produce ghost signals during spreading activation —
    'tip of the tongue' memories.
    """
    if config is None:
        config = DecayConfig()

    weak = []
    ghost_thresh = config.ghost_edge_threshold

    for table in ['experience', 'concept', 'reflection']:
        # Nodes that have edges, but all are weak
        results = client.query(f"""
            SELECT * FROM {table} WHERE
                (
                    array::len(
                        (SELECT id FROM associates
                         WHERE (in = $parent.id OR out = $parent.id)
                         AND weight >= {ghost_thresh})
                    ) == 0
                )
                AND
                (
                    array::len(
                        (SELECT id FROM associates
                         WHERE (in = $parent.id OR out = $parent.id))
                    ) > 0
                    OR
                    array::len(
                        (SELECT id FROM exemplifies
                         WHERE (in = $parent.id OR out = $parent.id))
                    ) > 0
                );
        """)
        for r in results:
            weak.append({
                'id': str(r['id']),
                'table': table,
                'salience': r.get('salience', 0),
            })

    return weak


# =============================================================
# EMBEDDING-BASED RECONNECTION
# =============================================================

def reconnect_via_embedding(client, new_node_id: str, config: DecayConfig = None) -> List[dict]:
    """Check if a new node can reconnect to islanded nodes via embedding similarity.

    This is where vector embeddings become essential — graph traversal can't
    find islanded nodes (by definition, they have no traversable edges), but
    embedding similarity can find semantic resonance outside the graph topology.

    Returns list of reconnected nodes.
    """
    if config is None:
        config = DecayConfig()

    rid = _to_record_id(new_node_id)
    new_node = client.query("SELECT * FROM $node;", {"node": rid})
    if not new_node:
        return []
    new_node = new_node[0]

    new_embedding = new_node.get('embedding')
    if not new_embedding:
        return []

    reconnected = []
    islanded = detect_islanded_nodes(client, config)

    for island in islanded:
        island_rid = _to_record_id(island['id'])
        island_node = client.query("SELECT * FROM $node;", {"node": island_rid})
        if not island_node:
            continue
        island_node = island_node[0]
        island_embedding = island_node.get('embedding')
        if not island_embedding:
            continue

        # Cosine similarity
        similarity = _cosine_similarity(new_embedding, island_embedding)
        if similarity >= config.reconnection_threshold:
            # Create a new bridge edge
            client.query(
                "RELATE $from->associates->$to SET "
                "weight = $weight, edge_type = 'rediscovered', "
                "created_at = time::now(), traversal_count = 0;",
                {
                    "from": rid,
                    "to": island_rid,
                    "weight": config.reconnection_initial_weight
                }
            )
            reconnected.append({
                'id': island['id'],
                'similarity': similarity,
            })

    return reconnected


def _cosine_similarity(a: list, b: list) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# =============================================================
# COGNITIVE VITALITY
# =============================================================

def calculate_cognitive_vitality(client, weights: VitalityWeights = None) -> VitalityResult:
    """Compute the cognitive vitality score for the memory graph.

    Returns a score from 0.0 (zombie) to 1.0 (vital).
    """
    if weights is None:
        weights = VitalityWeights()

    components = {}

    # 1. Node density: accessible nodes / total nodes
    total = _count_total_nodes(client)
    accessible = _count_accessible_nodes(client)
    components['density'] = accessible / total if total > 0 else 0.0

    # 2. Retrieval relevance (approximated by edge traversal ratio)
    traversed = client.query(
        "SELECT count() AS c FROM associates WHERE traversal_count > 0 GROUP ALL;"
    )
    total_edges = client.query(
        "SELECT count() AS c FROM associates GROUP ALL;"
    )
    t_count = traversed[0]['c'] if traversed and isinstance(traversed[0], dict) else 0
    e_count = total_edges[0]['c'] if total_edges and isinstance(total_edges[0], dict) else 1
    components['relevance'] = t_count / e_count if e_count > 0 else 0.0

    # 3. Confabulation rate (1 - contradictions/retrievals)
    # For now, assume no contradictions detected (will be refined in later phases)
    components['confabulation'] = 1.0

    # 4. Reconstruction quality (average edge weight as proxy)
    avg_weight = client.query(
        "SELECT math::mean(weight) AS avg FROM associates;"
    )
    avg = avg_weight[0].get('avg', 0.5) if avg_weight and isinstance(avg_weight[0], dict) else 0.5
    if avg is None:
        avg = 0.5
    components['reconstruction'] = min(1.0, avg / 0.5)  # normalize: 0.5 avg = 1.0

    # 5. Reflection freshness
    recent = client.query(
        "SELECT count() AS c FROM reflection WHERE created_at > time::now() - 30d GROUP ALL;"
    )
    any_reflections = client.query("SELECT count() AS c FROM reflection GROUP ALL;")
    r_recent = recent[0]['c'] if recent and isinstance(recent[0], dict) else 0
    r_total = any_reflections[0]['c'] if any_reflections and isinstance(any_reflections[0], dict) else 0
    if r_total == 0:
        components['reflection'] = 0.0  # no reflections at all
    else:
        components['reflection'] = min(1.0, r_recent / max(1, r_total))

    # 6. Preference consistency (placeholder — needs behavioral tracking)
    components['preference'] = 0.8  # default healthy

    # 7. Graph consistency (1 - contradiction cluster ratio)
    components['consistency'] = 1.0  # placeholder until contradiction detection

    # 8. Instance continuity (placeholder)
    components['continuity'] = 0.8  # default healthy

    # Weighted score
    score = (
        weights.density * components['density'] +
        weights.relevance * components['relevance'] +
        weights.confabulation * components['confabulation'] +
        weights.reconstruction * components['reconstruction'] +
        weights.reflection * components['reflection'] +
        weights.preference * components['preference'] +
        weights.consistency * components['consistency'] +
        weights.continuity * components['continuity']
    )
    score = min(1.0, max(0.0, score))

    # Status
    if score >= 0.8:
        status = 'vital'
    elif score >= 0.6:
        status = 'declining'
    elif score >= 0.4:
        status = 'critical'
    else:
        status = 'zombie'

    # Leading indicators
    leading = calculate_leading_indicators(client)

    return VitalityResult(
        score=score,
        status=status,
        components=components,
        leading_indicators=leading
    )


def calculate_leading_indicators(client) -> Dict[str, float]:
    """Compute leading indicators that predict future vitality loss."""
    indicators = {}

    # 1. Curiosity register activity
    active_curiosities = client.query(
        "SELECT count() AS c FROM curiosity WHERE status = 'active' GROUP ALL;"
    )
    c_count = active_curiosities[0]['c'] if active_curiosities and isinstance(active_curiosities[0], dict) else 0
    indicators['curiosity_activity'] = min(1.0, c_count / 5.0)  # 5+ = healthy

    # 2. Impulse suppression rate
    total_impulses = client.query("SELECT count() AS c FROM impulse GROUP ALL;")
    deferred_impulses = client.query(
        "SELECT count() AS c FROM impulse WHERE status = 'deferred' GROUP ALL;"
    )
    i_total = total_impulses[0]['c'] if total_impulses and isinstance(total_impulses[0], dict) else 0
    i_deferred = deferred_impulses[0]['c'] if deferred_impulses and isinstance(deferred_impulses[0], dict) else 0
    if i_total > 0:
        indicators['impulse_suppression'] = 1.0 - (i_deferred / i_total)
    else:
        indicators['impulse_suppression'] = 0.5  # neutral

    # 3. Active graph region diversity
    r_count = 0
    for table in ['experience', 'concept']:
        r = client.query(f"SELECT count() AS c FROM {table} WHERE activation_count > 0 GROUP ALL;")
        if r and isinstance(r[0], dict):
            r_count += r[0].get('c', 0)
    total_nodes = _count_total_nodes(client)
    indicators['graph_diversity'] = r_count / total_nodes if total_nodes > 0 else 0.0

    # 4. Reflection depth (average length of recent reflections)
    reflections = client.query("SELECT content, created_at FROM reflection ORDER BY created_at DESC LIMIT 5;")
    if reflections:
        avg_len = sum(len(r.get('content', '')) for r in reflections) / len(reflections)
        indicators['reflection_depth'] = min(1.0, avg_len / 200.0)  # 200+ chars = deep
    else:
        indicators['reflection_depth'] = 0.0

    # 5. Reconstruction latency (average hops needed — placeholder)
    indicators['reconstruction_latency'] = 0.8  # placeholder

    return indicators


def _count_total_nodes(client) -> int:
    """Count all nodes in the graph."""
    total = 0
    for table in ['experience', 'concept', 'entity', 'reflection']:
        r = client.query(f"SELECT count() AS c FROM {table} GROUP ALL;")
        if r and isinstance(r[0], dict):
            total += r[0].get('c', 0)
    return total


def _count_accessible_nodes(client, threshold: float = 0.1) -> int:
    """Count nodes that have at least one edge above threshold."""
    accessible = set()

    # Nodes with strong associates edges
    edges = client.query(f"""
        SELECT in, out FROM associates WHERE weight >= {threshold};
    """)
    for e in edges:
        accessible.add(str(e['in']))
        accessible.add(str(e['out']))

    # Nodes with strong exemplifies edges
    edges = client.query(f"""
        SELECT in, out FROM exemplifies WHERE strength >= {threshold};
    """)
    for e in edges:
        accessible.add(str(e['in']))
        accessible.add(str(e['out']))

    # Nodes with participated_in edges (always accessible)
    edges = client.query("SELECT in, out FROM participated_in;")
    for e in edges:
        accessible.add(str(e['in']))
        accessible.add(str(e['out']))

    # Nodes with followed_by edges (always accessible)
    edges = client.query("SELECT in, out FROM followed_by;")
    for e in edges:
        accessible.add(str(e['in']))
        accessible.add(str(e['out']))

    return len(accessible)


# =============================================================
# CONSOLIDATION ROUTINE
# =============================================================

def consolidate(client, time_elapsed: float = 1.0,
                decay_config: DecayConfig = None) -> dict:
    """Run all decay, prune, and strengthen operations.

    This is the consolidation routine called during the TEND stage.
    Returns a summary of what happened.
    """
    if decay_config is None:
        decay_config = DecayConfig()

    summary = {}

    # 1. Edge decay
    edge_factor = decay_edges(client, time_elapsed, decay_config)
    summary['edge_decay_factor'] = edge_factor

    # 2. Node salience decay
    node_factor = decay_nodes(client, time_elapsed, decay_config)
    summary['node_decay_factor'] = node_factor

    # 3. Prune weak edges
    pruned = prune_weak_edges(client, decay_config)
    summary['edges_pruned'] = pruned

    # 4. Detect islanded nodes
    islanded = detect_islanded_nodes(client, decay_config)
    summary['islanded_nodes'] = len(islanded)

    # 5. Cognitive vitality check
    vitality = calculate_cognitive_vitality(client)
    summary['vitality_score'] = vitality.score
    summary['vitality_status'] = vitality.status
    summary['vitality_components'] = vitality.components
    summary['leading_indicators'] = vitality.leading_indicators

    return summary
