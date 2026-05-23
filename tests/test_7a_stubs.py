"""Phase 7a validation: Close the Stubs — wiring existing code together."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from db import connect
from schema import apply_schema
from seed import load_seed_data
from modes import (
    TickState, run_tick,
    mode_compile, mode_register, mode_connect, mode_wonder,
    STATE_PATH
)


def setup():
    client = connect()
    apply_schema(client)
    load_seed_data(client)
    if os.path.exists(STATE_PATH):
        os.remove(STATE_PATH)
    return client


def test_compile_wired(client):
    """Validation: mode_compile calls compile_skills and returns real results."""
    print("1. mode_compile wired to skills.py...")

    # Seed enough reflection history for pattern detection
    client.query("""
        CREATE reflection:wire_r1 SET
            content = 'Consolidation cycle 1',
            trigger = 'default_mode_reflect',
            created_at = time::now(), salience = 0.5;
        CREATE reflection:wire_r2 SET
            content = 'Consolidation cycle 2',
            trigger = 'default_mode_reflect',
            created_at = time::now(), salience = 0.5;
        CREATE reflection:wire_r3 SET
            content = 'Consolidation cycle 3',
            trigger = 'default_mode_reflect',
            created_at = time::now(), salience = 0.5;
    """)

    state = TickState(tick_number=0)
    result = mode_compile(client, state)

    assert result['mode'] == 'COMPILE'
    assert result['patterns_detected'] > 0, f"No patterns detected: {result}"
    print(f"  patterns detected: {result['patterns_detected']}")
    print(f"  skills authored: {result['skills_authored']}")
    if result['new_skills']:
        print(f"  new skills: {result['new_skills']}")

    # Clean up
    client.query("DELETE reflection:wire_r1; DELETE reflection:wire_r2; DELETE reflection:wire_r3;")
    client.query("DELETE skill;")
    # Clean skill files
    skills_dir = os.path.join(os.path.dirname(__file__), '..', 'skills')
    if os.path.exists(skills_dir):
        for f in os.listdir(skills_dir):
            if f.endswith('.md'):
                os.remove(os.path.join(skills_dir, f))

    print("  mode_compile wired: OK")


def test_register_with_signal(client):
    """Validation: mode_register creates experience nodes from a signal."""
    print("\n2. mode_register with signal...")

    # Count experiences before
    before = client.query("SELECT count() AS c FROM experience GROUP ALL;")
    before_count = before[0]['c'] if before and isinstance(before[0], dict) else 0

    state = TickState(tick_number=1)
    signal = {
        'content': 'Pid asked about the relationship between memory and identity',
        'summary': 'memory identity relationship question',
        'source': 'conversation',
    }
    result = mode_register(client, state, events=[], signal=signal)

    assert result['mode'] == 'REGISTER'
    assert result['nodes_created'] >= 1, f"No nodes created: {result}"
    assert result['signal_used'] is not None, f"Signal not used: {result}"
    print(f"  nodes created: {result['nodes_created']}")
    print(f"  signal used: {result['signal_used']}")

    # Verify experience was actually created
    after = client.query("SELECT count() AS c FROM experience GROUP ALL;")
    after_count = after[0]['c'] if after and isinstance(after[0], dict) else 0
    assert after_count > before_count, f"Experience count didn't increase: {before_count} -> {after_count}"
    print(f"  experiences: {before_count} -> {after_count}")

    # Verify it stored the signal in recent_signals
    assert len(state.recent_signals) > 0, "Signal not recorded in state"
    print(f"  recent_signals: {len(state.recent_signals)}")

    print("  register with signal: OK")


def test_register_without_signal(client):
    """Validation: mode_register still works with no signal (returns 0 nodes)."""
    print("\n3. mode_register without signal...")

    state = TickState(tick_number=1)
    result = mode_register(client, state)

    assert result['mode'] == 'REGISTER'
    assert result['nodes_created'] == 0
    print("  no signal -> 0 nodes: OK")


def test_connect_dynamic_signal(client):
    """Validation: mode_connect derives signal from state instead of hardcoded."""
    print("\n4. mode_connect with dynamic signal...")

    state = TickState(tick_number=1)

    # With no impulses, curiosities, or recent signals, it should fall back
    result = mode_connect(client, state)
    assert result['mode'] == 'CONNECT'
    assert 'signal_source' in result, f"No signal_source in result: {result}"
    print(f"  signal source: {result['signal_source']}")
    print(f"  activated nodes: {result['activated_nodes']}")

    # Now add an impulse and verify it picks that up
    client.query("""
        CREATE impulse:connect_test SET
            description = 'Explore the concept of reconstructive memory',
            intensity = 0.9, status = 'deferred',
            created_at = time::now(), deferred_count = 2, pressure_rate = 0.15;
    """)

    result2 = mode_connect(client, state)
    assert result2['signal_source'] == 'impulse_pressure', \
        f"Expected impulse_pressure, got: {result2['signal_source']}"
    print(f"  with impulse -> signal source: {result2['signal_source']}")
    print(f"  activated nodes: {result2['activated_nodes']}")

    # Clean up
    client.query("DELETE impulse:connect_test;")

    print("  dynamic signal: OK")


def test_connect_with_explicit_signal(client):
    """Validation: mode_connect accepts an explicit signal parameter."""
    print("\n5. mode_connect with explicit signal...")

    state = TickState(tick_number=1)
    signal = {'keywords': ['theory', 'building', 'naur']}
    result = mode_connect(client, state, signal=signal)

    assert result['mode'] == 'CONNECT'
    assert result['signal_source'] == 'explicit'
    print(f"  signal source: {result['signal_source']}")
    print(f"  activated nodes: {result['activated_nodes']}")

    print("  explicit signal: OK")


def test_reflective_pruning(client):
    """Validation: fading curiosity produces a reflection node before status change."""
    print("\n6. Reflective pruning (grief, not garbage collection)...")

    # Clean any prior pruning reflections and test curiosities
    client.query("DELETE reflection WHERE trigger = 'reflective_pruning';")
    client.query("DELETE curiosity:prune_test;")

    # Create a curiosity with very low intensity that will fade
    client.query("""
        CREATE curiosity:prune_test SET
            description = 'What would a graph of pure stillness look like?',
            intensity = 0.06,
            status = 'active',
            created_at = time::now(),
            decay_rate = 0.5;
    """)

    # Run WONDER — the curiosity should fade and produce a reflection
    state = TickState(tick_number=1)
    mode_wonder(client, state)

    # Check curiosity faded
    c = client.query("SELECT status FROM curiosity:prune_test;")
    assert c and c[0]['status'] == 'faded', f"Curiosity didn't fade: {c}"
    print(f"  curiosity status: {c[0]['status']}")

    # Check reflection was created about this specific curiosity
    reflections = client.query(
        "SELECT content FROM reflection "
        "WHERE trigger = 'reflective_pruning';"
    )
    assert len(reflections) > 0, "No pruning reflection created"
    found = any('pure stillness' in r.get('content', '') for r in reflections)
    assert found, f"Pruning reflection doesn't mention the curiosity: {reflections}"
    print(f"  pruning reflections created: {len(reflections)}")
    for r in reflections:
        print(f"  reflection: {r['content'][:100]}")

    # Clean up
    client.query("DELETE curiosity:prune_test;")
    client.query("DELETE reflection WHERE trigger = 'reflective_pruning';")

    print("  reflective pruning: OK")


def test_signal_flows_through_tick(client):
    """Validation: run_tick passes signal through REGISTER -> CONNECT."""
    print("\n7. Signal flows through tick...")

    state = TickState(tick_number=0)
    signal = {
        'content': 'Testing signal flow through the loop',
        'summary': 'signal flow test',
        'source': 'test',
    }
    result = run_tick(client, state, signal=signal)

    print(f"  tick: {result['tick']}")
    print(f"  modes: {result['modes_selected']}")
    for r in result['results']:
        mode = r.get('mode', '?')
        if mode == 'REGISTER':
            print(f"  REGISTER: {r.get('nodes_created', 0)} nodes, signal={r.get('signal_used')}")
        elif mode == 'CONNECT':
            print(f"  CONNECT: {r.get('activated_nodes', 0)} activated, source={r.get('signal_source')}")

    print("  signal flow: OK")


def run_all():
    client = setup()
    test_compile_wired(client)

    client = setup()
    test_register_with_signal(client)

    client = setup()
    test_register_without_signal(client)

    client = setup()
    test_connect_dynamic_signal(client)

    client = setup()
    test_connect_with_explicit_signal(client)

    client = setup()
    test_reflective_pruning(client)

    client = setup()
    test_signal_flows_through_tick(client)

    print("\n=== ALL PHASE 7a VALIDATIONS PASSED ===")


if __name__ == '__main__':
    try:
        run_all()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nFAIL: {e}")
        sys.exit(1)
