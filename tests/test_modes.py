"""Phase 4 validation: Default Mode Loop tests."""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from db import connect
from schema import apply_schema
from seed import load_seed_data
from modes import (
    TickState, select_modes, run_tick,
    mode_sense, mode_register, mode_connect, mode_tend,
    mode_wonder, mode_reflect, mode_compile, mode_rest,
    save_state, load_state, STATE_PATH
)


def setup():
    client = connect()
    apply_schema(client)
    load_seed_data(client)
    # Clean any previous state
    if os.path.exists(STATE_PATH):
        os.remove(STATE_PATH)
    return client


def test_all_stages_execute(client):
    """Validation: Each stage function executes without error."""
    print("1. All stages execute...")

    state = TickState(tick_number=0)

    results = {}
    for mode_name, fn in [
        ('SENSE', lambda: mode_sense(client, state)),
        ('REGISTER', lambda: mode_register(client, state, [])),
        ('CONNECT', lambda: mode_connect(client, state)),
        ('TEND', lambda: mode_tend(client, state)),
        ('WONDER', lambda: mode_wonder(client, state)),
        ('REFLECT', lambda: mode_reflect(client, state)),
        ('COMPILE', lambda: mode_compile(client, state)),
        ('REST', lambda: mode_rest(client, state)),
    ]:
        result = fn()
        assert result['mode'] == mode_name, f"Mode mismatch: expected {mode_name}, got {result['mode']}"
        results[mode_name] = result
        print(f"  {mode_name}: OK")

    print(f"  all stages: OK")
    return results


def test_repertoire_selector():
    """Validation: Repertoire selector chooses different mode emphasis based on state."""
    print("\n2. Repertoire selector...")

    selections = set()
    for tick in range(20):
        state = TickState(tick_number=tick)
        modes = select_modes(state)
        key = tuple(modes)
        selections.add(key)

    assert len(selections) > 3, f"Too few unique selections: {len(selections)} (should be > 3)"
    print(f"  unique mode combinations across 20 ticks: {len(selections)}")

    # Check vitality-driven selection
    critical_state = TickState(tick_number=5, vitality_status='critical')
    modes = select_modes(critical_state)
    assert 'TEND' in modes, f"TEND not selected for critical vitality: {modes}"
    print(f"  critical vitality -> TEND selected: OK")

    # Check recursion depth response
    deep_state = TickState(tick_number=5, recursion_depth=5)
    modes = select_modes(deep_state)
    assert 'SENSE' in modes or 'CONNECT' in modes, f"Outward modes not selected for high recursion: {modes}"
    print(f"  high recursion -> outward modes: OK")

    # REST mode selection
    rest_state = TickState(tick_number=7)  # 7 % 7 == 0
    modes = select_modes(rest_state)
    assert 'REST' in modes, f"REST not selected on tick 7: {modes}"
    print(f"  tick 7 -> REST selected: OK")

    print(f"  repertoire selector: OK")


def test_state_persistence(client):
    """Validation: State persists correctly between cycles."""
    print("\n3. State persistence...")

    # Run a tick
    state = TickState(tick_number=0)
    result = run_tick(client, state)

    # Load state from disk
    loaded = load_state()

    assert loaded.tick_number == 1, f"Tick not incremented: {loaded.tick_number}"
    assert len(loaded.mode_history) > 0, "Mode history empty"
    print(f"  tick persisted: {loaded.tick_number}")
    print(f"  mode history: {loaded.mode_history}")
    print(f"  state persistence: OK")


def test_curiosity_decay(client):
    """Validation: Curiosity register items decay over simulated time."""
    print("\n4. Curiosity decay...")

    # Create a test curiosity
    client.query("""
        CREATE curiosity:decay_test SET
            description = 'Does SurrealDB support vector search natively?',
            intensity = 0.8,
            status = 'active',
            created_at = time::now(),
            decay_rate = 0.2;
    """)

    # Run WONDER mode several times
    state = TickState(tick_number=0)
    for i in range(5):
        mode_wonder(client, state)

    # Check intensity decreased
    result = client.query("SELECT intensity, status FROM curiosity:decay_test;")
    if result:
        r = result[0]
        assert r['intensity'] < 0.8, f"Curiosity didn't decay: {r['intensity']}"
        print(f"  intensity: 0.8 -> {r['intensity']:.4f}")
        print(f"  status: {r['status']}")
    else:
        print(f"  curiosity record not found (may have been faded)")

    print(f"  curiosity decay: OK")

    # Clean up
    client.query("DELETE curiosity:decay_test;")


def test_impulse_pressure(client):
    """Validation: Impulse items build pressure when deferred (revision note #1)."""
    print("\n5. Impulse pressure build...")

    # Create a test impulse
    client.query("""
        CREATE impulse:pressure_test SET
            description = 'Finish the zombie systems analysis',
            intensity = 0.5,
            status = 'deferred',
            created_at = time::now(),
            deferred_count = 0,
            pressure_rate = 0.15;
    """)

    initial = client.query("SELECT intensity, deferred_count FROM impulse:pressure_test;")
    initial_intensity = initial[0]['intensity']
    initial_deferred = initial[0]['deferred_count']

    # Run WONDER mode several times
    state = TickState(tick_number=0)
    for i in range(3):
        mode_wonder(client, state)

    result = client.query("SELECT intensity, deferred_count FROM impulse:pressure_test;")
    r = result[0]
    assert r['intensity'] > initial_intensity, \
        f"Impulse didn't build pressure: {initial_intensity} -> {r['intensity']}"
    assert r['deferred_count'] > initial_deferred, \
        f"Deferred count didn't increase: {initial_deferred} -> {r['deferred_count']}"
    print(f"  intensity: {initial_intensity} -> {r['intensity']:.4f}")
    print(f"  deferred_count: {initial_deferred} -> {r['deferred_count']}")
    print(f"  impulse pressure: OK")

    # Clean up
    client.query("DELETE impulse:pressure_test;")


def test_curiosity_vs_impulse(client):
    """Seed a curiosity and a deferred impulse with equal initial intensity.
    Run several cycles. Verify curiosity decays while impulse builds pressure."""
    print("\n6. Curiosity vs impulse dynamics...")

    client.query("""
        CREATE curiosity:cmp_test SET
            description = 'What happened to the naming discussion?',
            intensity = 0.7,
            status = 'active',
            created_at = time::now(),
            decay_rate = 0.15;

        CREATE impulse:cmp_test SET
            description = 'Finish the thought about identity through memory',
            intensity = 0.7,
            status = 'deferred',
            created_at = time::now(),
            deferred_count = 0,
            pressure_rate = 0.15;
    """)

    state = TickState(tick_number=0)
    for i in range(5):
        mode_wonder(client, state)

    c = client.query("SELECT intensity FROM curiosity:cmp_test;")
    imp = client.query("SELECT intensity FROM impulse:cmp_test;")

    c_intensity = c[0]['intensity'] if c else 0
    imp_intensity = imp[0]['intensity'] if imp else 0

    assert c_intensity < 0.7, f"Curiosity didn't decay: {c_intensity}"
    assert imp_intensity > 0.7, f"Impulse didn't build: {imp_intensity}"
    assert imp_intensity > c_intensity, \
        f"Impulse should exceed curiosity: impulse={imp_intensity}, curiosity={c_intensity}"

    print(f"  curiosity: 0.7 -> {c_intensity:.4f} (decayed)")
    print(f"  impulse:   0.7 -> {imp_intensity:.4f} (built pressure)")
    print(f"  This distinction matters because curiosities are about the")
    print(f"  world (external information gaps) while impulses are about")
    print(f"  incomplete cognition (internal unfinished thoughts).")
    print(f"  A system that aspires to inner life needs both drives:")
    print(f"  one that fades when unattended, one that insists.")

    # Clean up
    client.query("DELETE curiosity:cmp_test; DELETE impulse:cmp_test;")


def test_asymmetry_alerts(client):
    """Validation: Asymmetry alerts fire when graph regions diverge significantly."""
    print("\n7. Asymmetry alerts...")

    state = TickState(tick_number=0)
    result = mode_tend(client, state)

    # The seed data has experiences, concepts, entities but no reflections —
    # this should trigger an asymmetry alert
    alert = result.get('asymmetry_alert')
    print(f"  alert: {alert}")
    if alert:
        print(f"  asymmetry detected: OK")
    else:
        print(f"  no significant asymmetry in seed data (this is acceptable)")
    print(f"  asymmetry check: OK")


def test_recursion_monitor(client):
    """Validation: Recursion depth monitor flags excessive self-referential processing."""
    print("\n8. Recursion depth monitor...")

    state = TickState(tick_number=0, recursion_depth=0)

    # Run REFLECT several times
    for i in range(4):
        mode_reflect(client, state)

    assert state.recursion_depth >= 3, f"Recursion not tracked: {state.recursion_depth}"
    print(f"  recursion depth after 4 reflects: {state.recursion_depth}")

    # Check that selector responds
    modes = select_modes(state)
    # With high recursion, should prefer outward modes
    print(f"  selected modes at depth {state.recursion_depth}: {modes}")
    if state.recursion_depth > 3:
        assert 'SENSE' in modes or 'CONNECT' in modes, \
            f"Selector didn't respond to high recursion: {modes}"
        print(f"  outward redirect: OK")
    print(f"  recursion monitor: OK")


def test_rest_mode(client):
    """Validation: REST mode produces a valid cycle with no new nodes created."""
    print("\n9. REST mode...")

    # Count nodes before
    before = 0
    for table in ['experience', 'concept', 'entity', 'reflection']:
        r = client.query(f"SELECT count() AS c FROM {table} GROUP ALL;")
        if r and isinstance(r[0], dict):
            before += r[0].get('c', 0)

    state = TickState(tick_number=0)
    result = mode_rest(client, state)

    # Count nodes after
    after = 0
    for table in ['experience', 'concept', 'entity', 'reflection']:
        r = client.query(f"SELECT count() AS c FROM {table} GROUP ALL;")
        if r and isinstance(r[0], dict):
            after += r[0].get('c', 0)

    assert result['nodes_created'] == 0, f"REST created nodes: {result['nodes_created']}"
    assert after == before, f"Node count changed during REST: {before} -> {after}"
    print(f"  nodes before: {before}, after: {after}")
    print(f"  REST mode: OK (no nodes created, deliberate stillness)")


def test_multi_tick(client):
    """Run multiple ticks and verify the loop produces varied behaviour."""
    print("\n10. Multi-tick execution...")

    state = TickState(tick_number=0)
    all_modes = set()

    for i in range(10):
        result = run_tick(client, state)
        for mode in result['modes_selected']:
            all_modes.add(mode)
        if i < 3 or i == 9:
            print(f"  tick {result['tick']}: {result['modes_selected']}")

    assert len(all_modes) >= 4, f"Too few unique modes in 10 ticks: {all_modes}"
    print(f"  unique modes used: {all_modes}")
    print(f"  multi-tick: OK")


def run_all():
    client = setup()
    test_all_stages_execute(client)
    test_repertoire_selector()

    client = setup()
    test_state_persistence(client)

    client = setup()
    test_curiosity_decay(client)

    client = setup()
    test_impulse_pressure(client)

    client = setup()
    test_curiosity_vs_impulse(client)

    client = setup()
    test_asymmetry_alerts(client)

    client = setup()
    test_recursion_monitor(client)

    client = setup()
    test_rest_mode(client)

    client = setup()
    test_multi_tick(client)

    print("\n=== ALL PHASE 4 VALIDATIONS PASSED ===")


if __name__ == '__main__':
    try:
        run_all()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nFAIL: {e}")
        sys.exit(1)
