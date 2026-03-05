"""Phase 1 validation: Memory Graph Schema tests."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from db import connect
from schema import apply_schema
from seed import load_seed_data


def as_list(result):
    """Normalise query result to a list of records."""
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return [result]
    if result is None:
        return []
    return [result]


def first(result):
    """Get the first record from a query result."""
    records = as_list(result)
    return records[0] if records else None


def run_validations():
    client = connect()

    print("Applying schema...")
    apply_schema(client)
    print("  OK")

    print("Loading seed data...")
    load_seed_data(client)
    print("  OK")

    # --- Validation 1: All four node types can be created and queried ---
    print("\n1. Node types...")
    for table in ['experience', 'concept', 'entity']:
        records = as_list(client.query(f"SELECT * FROM {table};"))
        assert len(records) > 0, f"No records found in {table}"
        print(f"  {table}: OK ({len(records)} records)")

    # Reflection — create a test one
    client.query("""
        CREATE reflection:test SET
            content = 'Test reflection',
            trigger = 'validation',
            created_at = time::now(),
            salience = 0.5;
    """)
    r = first(client.query("SELECT * FROM reflection:test;"))
    assert r['content'] == 'Test reflection'
    client.query("DELETE reflection:test;")
    print(f"  reflection: OK (created and verified)")

    # --- Validation 2: All four edge types work ---
    print("\n2. Edge types...")
    for edge_table in ['associates', 'participated_in', 'exemplifies', 'followed_by']:
        records = as_list(client.query(f"SELECT * FROM {edge_table};"))
        assert len(records) > 0, f"No {edge_table} edges found"
        print(f"  {edge_table}: OK ({len(records)} edges)")

    # --- Validation 3: Seed data is queryable ---
    print("\n3. Seed data queries...")

    pid = first(client.query("SELECT * FROM entity:pid;"))
    assert pid['name'] == 'Pid'
    print(f"  entity:pid: OK")

    # Graph traversal: Pid's experiences
    r = first(client.query("""
        SELECT ->participated_in->experience.summary AS experiences
        FROM entity:pid;
    """))
    exps = r.get('experiences', [])
    assert len(exps) > 0, f"No experiences for Pid"
    print(f"  Pid's experiences: OK ({len(exps)} found)")

    # Graph traversal: meno's concepts
    r = first(client.query("""
        SELECT ->associates->concept.name AS concepts
        FROM entity:meno;
    """))
    concepts = r.get('concepts', [])
    assert len(concepts) > 0
    print(f"  meno's concepts: OK ({concepts})")

    # --- Validation 4: Vector embedding fields exist ---
    print("\n4. Vector embedding fields...")
    for table in ['experience', 'concept', 'reflection']:
        info = client.query(f"INFO FOR TABLE {table};")
        info_str = str(info)
        assert 'embedding' in info_str, f"No embedding field on {table}"
        print(f"  {table}.embedding: OK")

    # --- Validation 5: Distinct register tables ---
    print("\n5. Register tables...")

    client.query("""
        CREATE curiosity:test SET
            description = 'What is the current state of SurrealDB vector search?',
            intensity = 0.7, status = 'active',
            created_at = time::now(), decay_rate = 0.1;
    """)
    c = first(client.query("SELECT * FROM curiosity:test;"))
    assert c['intensity'] == 0.7
    assert 'decay_rate' in c
    print(f"  curiosity: OK (intensity={c['intensity']}, decay_rate={c['decay_rate']})")

    client.query("""
        CREATE impulse:test SET
            description = 'Finish the thought about zombie systems',
            intensity = 0.5, status = 'deferred',
            created_at = time::now(), deferred_count = 2, pressure_rate = 0.15;
    """)
    i = first(client.query("SELECT * FROM impulse:test;"))
    assert i['deferred_count'] == 2
    assert 'pressure_rate' in i
    print(f"  impulse: OK (deferred_count={i['deferred_count']}, pressure_rate={i['pressure_rate']})")

    client.query("""
        CREATE tension:test SET
            description = 'Balanced growth vs deep expertise',
            intensity = 0.6, status = 'unresolved',
            created_at = time::now();
    """)
    t = first(client.query("SELECT * FROM tension:test;"))
    assert t['status'] == 'unresolved'
    print(f"  tension: OK (status={t['status']})")

    client.query("DELETE curiosity:test; DELETE impulse:test; DELETE tension:test;")

    # --- Validation 6: Edge weights are numeric and updatable ---
    print("\n6. Edge weight updates...")
    edges = as_list(client.query("""
        SELECT weight FROM associates
        WHERE in = concept:associative_memory
        AND out = concept:spreading_activation;
    """))
    original_weight = edges[0]['weight']

    client.query("""
        UPDATE associates SET weight = weight + 0.05
        WHERE in = concept:associative_memory
        AND out = concept:spreading_activation;
    """)
    edges = as_list(client.query("""
        SELECT weight FROM associates
        WHERE in = concept:associative_memory
        AND out = concept:spreading_activation;
    """))
    new_weight = edges[0]['weight']
    assert abs(new_weight - original_weight - 0.05) < 0.001
    print(f"  weight update: OK ({original_weight} -> {new_weight})")

    # Restore
    client.query(f"""
        UPDATE associates SET weight = {original_weight}
        WHERE in = concept:associative_memory
        AND out = concept:spreading_activation;
    """)

    print("\n=== ALL PHASE 1 VALIDATIONS PASSED ===")
    return True


if __name__ == '__main__':
    try:
        run_validations()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nFAIL: {e}")
        sys.exit(1)
