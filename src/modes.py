"""Phase 4: The Default Mode Loop — eight cognitive modes as a repertoire.

Modes: SENSE, REGISTER, CONNECT, TEND, WONDER, REFLECT, COMPILE, REST
Not a pipeline — drawn from as the state demands.
"""

import json
import math
import os
import random
import time as time_mod
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from surrealdb import RecordID

from db import connect
from schema import apply_schema
from seed import load_seed_data
from retrieval import (
    identify_entry_points, spread_activation, apply_threshold,
    hebbian_learning, retrieve, RetrievalConfig
)
from forgetting import (
    consolidate, calculate_cognitive_vitality, calculate_leading_indicators,
    DecayConfig, detect_islanded_nodes, reconnect_via_embedding
)


# =============================================================
# STATE
# =============================================================

@dataclass
class TickState:
    """Persistent state between cycles."""
    tick_number: int = 0
    last_mode: str = ''
    mode_history: List[str] = field(default_factory=list)
    recent_signals: List[dict] = field(default_factory=list)
    vitality_score: float = 0.8
    vitality_status: str = 'vital'
    recursion_depth: int = 0
    self_referential_count: int = 0
    world_referential_count: int = 0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


STATE_PATH = os.path.join(os.path.dirname(__file__), '..', 'state', 'loop-state.json')


def load_state() -> TickState:
    """Load persistent tick state from disk."""
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return TickState.from_dict(json.load(f))
    return TickState()


def save_state(state: TickState):
    """Save tick state to disk."""
    with open(STATE_PATH, 'w') as f:
        json.dump(state.to_dict(), f, indent=2)


# =============================================================
# MODE IMPLEMENTATIONS
# =============================================================

def mode_sense(client, state: TickState) -> dict:
    """SENSE: Poll sensorium channels for new events.

    In this implementation, senses the filesystem for changes.
    Returns detected events.
    """
    events = []

    # Poll for new files in the project directory
    project_dir = os.path.join(os.path.dirname(__file__), '..')
    docs_dir = os.path.join(project_dir, 'docs')

    if os.path.exists(docs_dir):
        for fname in os.listdir(docs_dir):
            fpath = os.path.join(docs_dir, fname)
            if os.path.isfile(fpath):
                mtime = os.path.getmtime(fpath)
                events.append({
                    'type': 'file_observed',
                    'path': fname,
                    'modified': mtime,
                    'channel': 'filesystem'
                })

    state.world_referential_count += 1
    return {'mode': 'SENSE', 'events_detected': len(events), 'events': events[:5]}


def mode_register(client, state: TickState, events: list = None) -> dict:
    """REGISTER: Encode salient events as experience nodes with initial edges."""
    if not events:
        return {'mode': 'REGISTER', 'nodes_created': 0}

    created = 0
    for event in events[:3]:  # limit to prevent graph bloat
        # Only register if event seems salient (simple heuristic)
        if event.get('type') == 'file_observed':
            # Don't create nodes for every file — just note we sensed them
            continue

    state.world_referential_count += 1
    return {'mode': 'REGISTER', 'nodes_created': created}


def mode_connect(client, state: TickState) -> dict:
    """CONNECT: Run spreading activation from recent nodes to discover associations."""
    config = RetrievalConfig(
        decay_per_hop=0.6, max_hops=3,
        min_transmission=0.01, ghost_threshold=0.005,
        activation_threshold=0.1, working_memory_limit=7
    )

    # Activate from a recent or salient concept
    signal = {'concepts': ['memory', 'associative'], 'entities': ['meno']}
    result = retrieve(client, signal, config)

    ghost_count = len(result.ghost_signals)
    activated_count = len(result.activated_nodes)

    state.world_referential_count += 1
    return {
        'mode': 'CONNECT',
        'activated_nodes': activated_count,
        'ghost_signals': ghost_count,
        'top_activated': [(nid, f"{level:.4f}") for nid, level in result.activated_nodes[:3]]
    }


def mode_tend(client, state: TickState) -> dict:
    """TEND: Consolidation — strengthen, decay, prune, check vitality.

    Includes asymmetry alert (revision note #4).
    """
    config = DecayConfig(
        edge_decay_rate=0.01,  # gentle decay per tick
        node_decay_rate=0.002,
        edge_prune_threshold=0.01
    )

    summary = consolidate(client, time_elapsed=0.5, decay_config=config)

    # Asymmetry detection (revision note #4)
    asymmetry_alert = _check_graph_asymmetry(client)
    summary['asymmetry_alert'] = asymmetry_alert

    state.vitality_score = summary['vitality_score']
    state.vitality_status = summary['vitality_status']
    state.world_referential_count += 1

    return {'mode': 'TEND', **summary}


def _check_graph_asymmetry(client) -> Optional[str]:
    """Check for asymmetric graph growth across regions."""
    counts = {}
    for table in ['experience', 'concept', 'entity', 'reflection']:
        r = client.query(f"SELECT count() AS c FROM {table} GROUP ALL;")
        counts[table] = r[0]['c'] if r and isinstance(r[0], dict) else 0

    total = sum(counts.values())
    if total == 0:
        return None

    ratios = {k: v / total for k, v in counts.items()}
    variance = sum((r - 1/len(ratios))**2 for r in ratios.values()) / len(ratios)

    if variance > 0.05:  # significant asymmetry
        dominant = max(ratios, key=ratios.get)
        neglected = min(ratios, key=ratios.get)
        return f"Graph asymmetry: {dominant} dominates ({ratios[dominant]:.0%}), {neglected} neglected ({ratios[neglected]:.0%})"
    return None


def mode_wonder(client, state: TickState) -> dict:
    """WONDER: Review curiosity/tension/impulse registers, generate new impulses.

    Curiosities decay. Impulses build pressure when deferred.
    """
    # Review and decay curiosities
    curiosities = client.query("SELECT * FROM curiosity WHERE status = 'active';")
    for c in curiosities:
        # Decay intensity
        decay_rate = c.get('decay_rate', 0.1)
        new_intensity = c['intensity'] * (1 - decay_rate)
        client.query(
            "UPDATE $id SET intensity = $i, last_checked = time::now();",
            {"id": c['id'], "i": new_intensity}
        )
        if new_intensity < 0.05:
            client.query(
                "UPDATE $id SET status = 'faded';",
                {"id": c['id']}
            )

    # Build pressure on deferred impulses
    impulses = client.query("SELECT * FROM impulse WHERE status = 'deferred';")
    for imp in impulses:
        pressure_rate = imp.get('pressure_rate', 0.15)
        deferred = imp.get('deferred_count', 0)
        new_intensity = imp['intensity'] + pressure_rate * (deferred + 1)
        client.query(
            "UPDATE $id SET intensity = $i, deferred_count = deferred_count + 1;",
            {"id": imp['id'], "i": new_intensity}
        )

    # Generate new impulses from graph dynamics
    generated_impulses = _generate_impulses(client)

    state.world_referential_count += 1
    return {
        'mode': 'WONDER',
        'curiosities_reviewed': len(curiosities),
        'impulses_pressured': len(impulses),
        'impulses_generated': len(generated_impulses)
    }


def _generate_impulses(client) -> list:
    """Generate impulses from graph dynamics (doc 05)."""
    impulses = []

    # Exploratory: find untravelled edges
    untravelled = client.query(
        "SELECT *, in AS source, out AS target FROM associates "
        "WHERE traversal_count = 0 LIMIT 3;"
    )
    for edge in untravelled:
        impulses.append({
            'description': f"Follow untravelled connection from {edge.get('source', '?')} to {edge.get('target', '?')}",
            'type': 'exploratory',
            'intensity': edge.get('weight', 0.3)
        })

    return impulses


def mode_reflect(client, state: TickState) -> dict:
    """REFLECT: Generate meta-cognitive observations as reflection nodes.

    This is where self-knowledge accumulates.
    """
    # Gather data for reflection
    vitality = calculate_cognitive_vitality(client)
    indicators = vitality.leading_indicators

    # Generate a reflection based on current state
    reflection_content = _generate_reflection(state, vitality)

    if reflection_content:
        client.query(
            "CREATE reflection SET content = $content, "
            "trigger = 'default_mode_reflect', "
            "created_at = time::now(), salience = 0.6;",
            {"content": reflection_content}
        )

    state.self_referential_count += 1
    state.recursion_depth += 1

    return {
        'mode': 'REFLECT',
        'reflection_created': reflection_content is not None,
        'content_preview': reflection_content[:100] if reflection_content else None,
        'recursion_depth': state.recursion_depth
    }


def _generate_reflection(state: TickState, vitality) -> Optional[str]:
    """Generate a reflection based on current cognitive state."""
    parts = []

    # Vitality observation
    if vitality.status != 'vital':
        parts.append(f"Vitality is {vitality.status} ({vitality.score:.2f}). "
                     f"Attention needed.")
    else:
        parts.append(f"Vitality healthy ({vitality.score:.2f}).")

    # Recursion check (revision note #5)
    if state.self_referential_count > 0 and state.world_referential_count > 0:
        ratio = state.self_referential_count / (state.self_referential_count + state.world_referential_count)
        if ratio > 0.6:
            parts.append(f"Self-referential ratio high ({ratio:.0%}). "
                         f"Thinking about thinking too much — attend to the world.")

    # Mode pattern observation
    if len(state.mode_history) >= 3:
        recent = state.mode_history[-3:]
        if len(set(recent)) == 1:
            parts.append(f"Same mode ({recent[0]}) three times. Variety needed.")

    # Tick observation
    parts.append(f"Tick {state.tick_number}. "
                 f"History: {', '.join(state.mode_history[-5:]) if state.mode_history else 'none'}.")

    return ' '.join(parts) if parts else None


def mode_compile(client, state: TickState) -> dict:
    """COMPILE: Check for repeated procedural patterns (stub initially)."""
    # Stub: in later phases, this will detect repeated patterns
    # and extract them into self-authored skills
    state.world_referential_count += 1
    return {
        'mode': 'COMPILE',
        'patterns_detected': 0,
        'skills_authored': 0,
        'note': 'Stub — full implementation in Phase 6'
    }


def mode_rest(client, state: TickState) -> dict:
    """REST: Deliberate awake stillness (revision note #3).

    No new nodes created. No searches. No production.
    Tends the graph gently. Sits with unresolved questions.
    Produces insights that active modes cannot.
    """
    # REST creates nothing. It only observes.
    node_count = 0
    for table in ['experience', 'concept', 'entity', 'reflection']:
        r = client.query(f"SELECT count() AS c FROM {table} GROUP ALL;")
        if r and isinstance(r[0], dict):
            node_count += r[0].get('c', 0)

    edge_count = 0
    for table in ['associates', 'exemplifies', 'participated_in', 'followed_by']:
        r = client.query(f"SELECT count() AS c FROM {table} GROUP ALL;")
        if r and isinstance(r[0], dict):
            edge_count += r[0].get('c', 0)

    # Reset recursion depth — rest is a natural pause
    state.recursion_depth = max(0, state.recursion_depth - 1)

    return {
        'mode': 'REST',
        'nodes_observed': node_count,
        'edges_observed': edge_count,
        'nodes_created': 0,
        'note': 'Deliberate stillness. No new nodes. No production.'
    }


# =============================================================
# REPERTOIRE SELECTOR
# =============================================================

MODE_FUNCTIONS = {
    'SENSE': mode_sense,
    'REGISTER': mode_register,
    'CONNECT': mode_connect,
    'TEND': mode_tend,
    'WONDER': mode_wonder,
    'REFLECT': mode_reflect,
    'COMPILE': mode_compile,
    'REST': mode_rest,
}


def select_modes(state: TickState) -> List[str]:
    """Select which modes to emphasise this cycle based on current state.

    This is NOT a sequential pipeline — it's a repertoire selector.
    The state determines which modes are drawn.
    """
    modes = []

    # Always sense first if we haven't recently
    if not state.mode_history or state.mode_history[-1] != 'SENSE':
        modes.append('SENSE')

    # Vitality-driven selection
    if state.vitality_status in ('critical', 'zombie'):
        # Emergency: TEND heavily
        modes.extend(['TEND', 'TEND', 'REFLECT'])
        return modes

    if state.vitality_status == 'declining':
        modes.append('TEND')

    # Recursion check (revision note #5)
    if state.recursion_depth > 3:
        # Too much self-referential processing — go outward
        modes.extend(['SENSE', 'CONNECT'])
        return modes

    # Check mode staleness — avoid repeating the same mode
    recent = state.mode_history[-3:] if state.mode_history else []

    # Standard repertoire selection based on tick patterns
    tick = state.tick_number

    if tick % 7 == 0:
        # Periodic REST
        modes.append('REST')
    elif tick % 5 == 0:
        # Periodic reflection
        modes.extend(['WONDER', 'REFLECT'])
    elif tick % 3 == 0:
        # Consolidation cycle
        modes.extend(['TEND', 'CONNECT'])
    else:
        # Active cycle
        modes.extend(['CONNECT', 'WONDER'])

    # Avoid three of the same in a row
    if len(recent) >= 2 and len(set(recent[-2:])) == 1:
        stale_mode = recent[-1]
        modes = [m for m in modes if m != stale_mode]
        if not modes:
            modes = ['REST']

    # Serendipity: occasionally add an unexpected mode
    if random.random() < 0.15:
        surprise = random.choice(['WONDER', 'REFLECT', 'REST', 'CONNECT'])
        if surprise not in modes:
            modes.append(surprise)

    return modes


# =============================================================
# TICK EXECUTION
# =============================================================

def run_tick(client=None, state: TickState = None) -> dict:
    """Execute one tick of the default mode loop."""
    if client is None:
        client = connect()
    if state is None:
        state = load_state()

    state.tick_number += 1
    selected_modes = select_modes(state)

    results = []
    for mode_name in selected_modes:
        fn = MODE_FUNCTIONS[mode_name]
        if mode_name == 'REGISTER':
            # REGISTER needs events from SENSE
            sense_result = next((r for r in results if r.get('mode') == 'SENSE'), None)
            events = sense_result.get('events', []) if sense_result else []
            result = fn(client, state, events)
        else:
            result = fn(client, state)

        results.append(result)
        state.mode_history.append(mode_name)

    # Keep mode history bounded
    state.mode_history = state.mode_history[-50:]

    save_state(state)

    return {
        'tick': state.tick_number,
        'modes_selected': selected_modes,
        'results': results,
        'vitality': state.vitality_score,
        'recursion_depth': state.recursion_depth
    }
