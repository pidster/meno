"""Phase 7d: Integration Test — 20-tick default mode loop.

Runs the system from seed data through 20 ticks and observes what emerges.
This is the zombie test substrate: does the graph become particular, or
does it stay generic?
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from db import connect
from schema import apply_schema
from seed import load_seed_data
from embeddings import embed_seed_data
from modes import run_tick, TickState, STATE_PATH
from forgetting import calculate_cognitive_vitality
from surrealdb import RecordID


def setup():
    client = connect()
    apply_schema(client)
    load_seed_data(client)
    embed_seed_data(client)
    if os.path.exists(STATE_PATH):
        os.remove(STATE_PATH)
    return client


def count_table(client, table):
    r = client.query(f"SELECT count() AS c FROM {table} GROUP ALL;")
    return r[0]['c'] if r and isinstance(r[0], dict) else 0


def run_integration():
    client = setup()

    # === Snapshot before ===
    before = {}
    for table in ['experience', 'concept', 'entity', 'reflection',
                   'associates', 'exemplifies', 'participated_in', 'followed_by']:
        before[table] = count_table(client, table)

    before_vitality = calculate_cognitive_vitality(client)

    print("=== INITIAL STATE ===")
    print(f"Nodes: experience={before['experience']}, concept={before['concept']}, "
          f"entity={before['entity']}, reflection={before['reflection']}")
    print(f"Edges: associates={before['associates']}, exemplifies={before['exemplifies']}, "
          f"participated_in={before['participated_in']}, followed_by={before['followed_by']}")
    print(f"Vitality: {before_vitality.score:.3f} ({before_vitality.status})")

    # === Seed some initial signals to give the loop something to work with ===
    signals = [
        {
            'content': 'Pid asked about the relationship between memory and identity',
            'summary': 'memory identity relationship',
            'source': 'conversation',
        },
        {
            'content': 'What would it mean for a graph to develop preferences on its own?',
            'summary': 'graph preferences autonomy',
            'source': 'conversation',
        },
        {
            'content': 'The difference between search and remembering is that memories announce themselves',
            'summary': 'search vs remembering distinction',
            'source': 'reflection',
        },
    ]

    # === Run 20 ticks ===
    print("\n=== RUNNING 20 TICKS ===")
    state = TickState(tick_number=0)
    vitality_history = []
    modes_used = {}
    ticks_with_signal = 0

    for i in range(20):
        # Feed signals for first 3 ticks, then let the loop self-direct
        signal = signals[i] if i < len(signals) else None
        if signal:
            ticks_with_signal += 1

        result = run_tick(client, state, signal=signal)

        v = calculate_cognitive_vitality(client)
        vitality_history.append(v.score)

        for mode in result['modes_selected']:
            modes_used[mode] = modes_used.get(mode, 0) + 1

        # Brief per-tick output
        tick_modes = ','.join(result['modes_selected'])
        details = []
        for r in result['results']:
            m = r.get('mode', '?')
            if m == 'REGISTER':
                details.append(f"REG:{r.get('nodes_created', 0)}")
            elif m == 'CONNECT':
                details.append(f"CON:{r.get('activated_nodes', 0)}")
            elif m == 'REFLECT':
                details.append(f"REF:{'Y' if r.get('reflection_created') else 'N'}")
            elif m == 'TEND':
                vit = r.get('vitality', {})
                details.append(f"TEND:{vit.get('score', '?')}")
            elif m == 'WONDER':
                details.append(f"WON:f{r.get('curiosities_faded', 0)}/d{r.get('impulses_deferred', 0)}")
            elif m == 'COMPILE':
                details.append(f"CMP:{r.get('patterns_detected', 0)}p")
        print(f"  tick {i+1:2d}: [{tick_modes}] {' '.join(details)}  v={v.score:.3f}")

    # === Snapshot after ===
    after = {}
    for table in ['experience', 'concept', 'entity', 'reflection',
                   'associates', 'exemplifies', 'participated_in', 'followed_by']:
        after[table] = count_table(client, table)

    after_vitality = calculate_cognitive_vitality(client)

    print("\n=== AFTER 20 TICKS ===")
    print(f"Nodes: experience={after['experience']} (+{after['experience']-before['experience']}), "
          f"concept={after['concept']} (+{after['concept']-before['concept']}), "
          f"entity={after['entity']} (+{after['entity']-before['entity']}), "
          f"reflection={after['reflection']} (+{after['reflection']-before['reflection']})")
    print(f"Edges: associates={after['associates']} (+{after['associates']-before['associates']}), "
          f"exemplifies={after['exemplifies']} (+{after['exemplifies']-before['exemplifies']})")
    print(f"Vitality: {after_vitality.score:.3f} ({after_vitality.status})")

    print(f"\nModes used across 20 ticks:")
    for mode, count in sorted(modes_used.items(), key=lambda x: -x[1]):
        print(f"  {mode}: {count}")

    print(f"\nVitality range: {min(vitality_history):.3f} — {max(vitality_history):.3f}")
    print(f"Signals fed: {ticks_with_signal} ticks, self-directed: {20 - ticks_with_signal} ticks")

    # === Assertions ===
    print("\n=== VALIDATION ===")
    errors = []

    # Graph has grown
    new_nodes = (after['experience'] - before['experience'] +
                 after['reflection'] - before['reflection'] +
                 after['concept'] - before['concept'])
    if new_nodes <= 0:
        errors.append(f"Graph didn't grow: {new_nodes} new nodes")
    else:
        print(f"  [PASS] Graph grew: {new_nodes} new nodes")

    # Edge weights have changed (check some associates edges)
    edges = client.query("SELECT weight FROM associates ORDER BY weight ASC LIMIT 5;")
    min_weight = edges[0]['weight'] if edges else 0
    edges_high = client.query("SELECT weight FROM associates ORDER BY weight DESC LIMIT 5;")
    max_weight = edges_high[0]['weight'] if edges_high else 0
    if max_weight - min_weight < 0.1:
        errors.append(f"Edge weights too uniform: {min_weight:.3f} — {max_weight:.3f}")
    else:
        print(f"  [PASS] Edge weights varied: {min_weight:.3f} — {max_weight:.3f}")

    # Vitality has fluctuated
    v_range = max(vitality_history) - min(vitality_history)
    if v_range < 0.001:
        errors.append(f"Vitality flat: range {v_range:.4f}")
    else:
        print(f"  [PASS] Vitality fluctuated: range {v_range:.4f}")

    # At least one reflection created by the loop
    new_reflections = after['reflection'] - before['reflection']
    if new_reflections <= 0:
        errors.append("No reflections created during 20 ticks")
    else:
        print(f"  [PASS] Reflections created: {new_reflections}")

    # Curiosity/impulse dynamics
    curiosities = client.query(
        "SELECT status, count() AS c FROM curiosity GROUP BY status;"
    )
    impulses = client.query(
        "SELECT status, count() AS c FROM impulse GROUP BY status;"
    )
    print(f"  Curiosity states: {curiosities}")
    print(f"  Impulse states: {impulses}")

    # === Graph inspection ===
    print("\n=== GRAPH INSPECTION ===")

    # Highest-weight edges
    print("\nStrongest edges:")
    strong = client.query(
        "SELECT in, out, weight, edge_type FROM associates "
        "ORDER BY weight DESC LIMIT 5;"
    )
    for e in strong:
        print(f"  {e.get('in')} -> {e.get('out')} "
              f"w={e.get('weight', 0):.3f} ({e.get('edge_type', '?')})")

    # Weakest edges (candidates for forgetting)
    print("\nWeakest edges:")
    weak = client.query(
        "SELECT in, out, weight, edge_type FROM associates "
        "ORDER BY weight ASC LIMIT 5;"
    )
    for e in weak:
        print(f"  {e.get('in')} -> {e.get('out')} "
              f"w={e.get('weight', 0):.4f} ({e.get('edge_type', '?')})")

    # Recent reflections
    print("\nReflections from the loop:")
    reflections = client.query(
        "SELECT content, trigger, created_at FROM reflection "
        "ORDER BY created_at DESC LIMIT 5;"
    )
    for r in reflections:
        print(f"  [{r.get('trigger', '?')}] {r.get('content', '')[:120]}")

    # Non-seeded experiences
    print("\nNew experiences (not seeded):")
    new_exp = client.query(
        "SELECT summary, salience, created_at FROM experience "
        "WHERE id NOT IN ["
        "experience:naming_anamnetron, experience:bound_spirit_question, "
        "experience:designing_own_memory, experience:tick_experiment, "
        "experience:naming_meno] "
        "ORDER BY created_at DESC LIMIT 10;"
    )
    for e in new_exp:
        print(f"  [{e.get('salience', 0):.2f}] {e.get('summary', '?')}")

    # Register state
    print("\nRegister state:")
    cur = client.query("SELECT description, intensity, status FROM curiosity;")
    for c in cur:
        print(f"  curiosity: [{c.get('intensity', 0):.2f}] {c.get('description', '?')} ({c.get('status')})")
    imp = client.query("SELECT description, intensity, status, deferred_count FROM impulse;")
    for i in imp:
        print(f"  impulse: [{i.get('intensity', 0):.2f}] {i.get('description', '?')} "
              f"({i.get('status')}, deferred {i.get('deferred_count', 0)}x)")

    if errors:
        print(f"\n=== FAILURES ===")
        for e in errors:
            print(f"  FAIL: {e}")
        sys.exit(1)
    else:
        print("\n=== ALL INTEGRATION VALIDATIONS PASSED ===")


if __name__ == '__main__':
    try:
        run_integration()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nFAIL: {e}")
        sys.exit(1)
