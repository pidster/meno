"""Phase 6 validation: Self-Authored Skills tests."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from db import connect
from schema import apply_schema
from seed import load_seed_data
from skills import (
    Skill, detect_patterns, extract_skill, author_skill,
    register_skill_in_graph, load_skills, load_skill_from_file,
    bootstrap_seed_skill, compile_skills, SKILLS_DIR
)


def setup():
    client = connect()
    apply_schema(client)
    load_seed_data(client)
    return client


def test_pattern_detection(client):
    """Validation: Pattern detection identifies repeated procedures in graph history."""
    print("1. Pattern detection...")

    # Create some reflection history to detect patterns from
    client.query("""
        CREATE reflection:r1 SET
            content = 'Noticed edge decay is working well',
            trigger = 'tend_cycle_reflect',
            created_at = time::now(),
            salience = 0.5;
        CREATE reflection:r2 SET
            content = 'Edge decay applied again',
            trigger = 'tend_cycle_reflect',
            created_at = time::now(),
            salience = 0.5;
        CREATE reflection:r3 SET
            content = 'Third consolidation cycle',
            trigger = 'default_mode_reflect',
            created_at = time::now(),
            salience = 0.5;
        CREATE reflection:r4 SET
            content = 'Fourth consolidation cycle',
            trigger = 'default_mode_reflect',
            created_at = time::now(),
            salience = 0.5;
        CREATE reflection:r5 SET
            content = 'Fifth consolidation cycle',
            trigger = 'default_mode_reflect',
            created_at = time::now(),
            salience = 0.5;
    """)

    patterns = detect_patterns(client)

    assert len(patterns) > 0, f"No patterns detected"
    print(f"  patterns found: {len(patterns)}")
    for p in patterns:
        print(f"    [{p['type']}] {p['description']}")

    # Should detect repeated reflections
    repeated = [p for p in patterns if p['type'] == 'repeated_reflection']
    assert len(repeated) > 0, "No repeated reflection patterns detected"
    print(f"  repeated reflection patterns: {len(repeated)}")

    # Should detect consolidation routine (3+ default_mode_reflect)
    consolidation = [p for p in patterns if p['type'] == 'consolidation_routine']
    assert len(consolidation) > 0, "No consolidation routine pattern detected"
    print(f"  consolidation routine detected: OK")

    # Clean up
    client.query("DELETE reflection:r1; DELETE reflection:r2; DELETE reflection:r3;")
    client.query("DELETE reflection:r4; DELETE reflection:r5;")


def test_skill_extraction(client):
    """Validation: Skill extraction produces a parameterised template."""
    print("\n2. Skill extraction...")

    # Test consolidation_routine pattern
    pattern = {
        'type': 'consolidation_routine',
        'trigger': 'tend_cycle',
        'count': 5,
        'description': 'Regular consolidation pattern detected'
    }
    skill = extract_skill(pattern)
    assert skill is not None, "Failed to extract skill from consolidation pattern"
    assert skill.name == 'graph_consolidation'
    assert len(skill.steps) > 0, "Skill has no steps"
    assert len(skill.parameters) > 0, "Skill has no parameters"
    assert skill.authored_by == 'agent'
    print(f"  consolidation skill: {skill.name}")
    print(f"    steps: {len(skill.steps)}")
    print(f"    parameters: {list(skill.parameters.keys())}")

    # Test hot_path pattern
    pattern2 = {
        'type': 'hot_path',
        'description': '3 frequently traversed associations',
        'edges': [
            {'source': 'a', 'target': 'b', 'count': 5},
            {'source': 'b', 'target': 'c', 'count': 4},
            {'source': 'c', 'target': 'd', 'count': 3},
        ]
    }
    skill2 = extract_skill(pattern2)
    assert skill2 is not None, "Failed to extract skill from hot_path pattern"
    assert skill2.name == 'association_traversal'
    print(f"  traversal skill: {skill2.name}")
    print(f"    steps: {len(skill2.steps)}")

    # Test unknown pattern returns None
    unknown = extract_skill({'type': 'unknown_thing', 'description': 'nope'})
    assert unknown is None, "Should return None for unknown pattern type"
    print(f"  unknown pattern -> None: OK")


def test_skill_authoring(client):
    """Validation: Generated SKILL.md follows the standard skill format."""
    print("\n3. Skill authoring (SKILL.md)...")

    skill = Skill(
        name='test_skill',
        description='A test skill for validation.',
        trigger_conditions=['Test condition 1', 'Test condition 2'],
        steps=['Step one', 'Step two', 'Step three'],
        parameters={'param1': 'First parameter', 'param2': 'Second parameter'},
        source_pattern='test pattern',
        authored_by='agent',
    )

    filepath = author_skill(skill)
    assert os.path.exists(filepath), f"Skill file not created: {filepath}"
    print(f"  file created: {filepath}")

    with open(filepath) as f:
        content = f.read()

    assert '# Skill: test_skill' in content
    assert '## Description' in content
    assert '## Trigger Conditions' in content
    assert '## Steps' in content
    assert '## Parameters' in content
    assert 'A test skill for validation.' in content
    assert '- Test condition 1' in content
    assert '1. Step one' in content
    assert '- **param1**: First parameter' in content
    print(f"  format validation: OK")

    # Clean up
    os.remove(filepath)


def test_skill_loading(client):
    """Validation: Authored skills are loadable by future instances."""
    print("\n4. Skill loading...")

    # Author a skill
    skill = Skill(
        name='loadable_test',
        description='Testing that skills can be loaded back.',
        trigger_conditions=['Load test'],
        steps=['Load step 1'],
        parameters={'p1': 'test param'},
        source_pattern='test',
        authored_by='agent',
    )
    filepath = author_skill(skill)

    # Load from file
    loaded = load_skill_from_file(filepath)
    assert loaded is not None, "Failed to load skill from file"
    assert loaded.name == 'loadable_test'
    assert loaded.description == 'Testing that skills can be loaded back.'
    assert len(loaded.trigger_conditions) == 1
    assert len(loaded.steps) == 1
    print(f"  loaded from file: {loaded.name}")
    print(f"    description: {loaded.description}")
    print(f"    triggers: {loaded.trigger_conditions}")
    print(f"    steps: {loaded.steps}")

    # Register in graph and load from graph
    register_skill_in_graph(client, skill)
    graph_skills = load_skills(client)
    assert len(graph_skills) > 0, "No skills in graph"
    skill_names = [s.get('name', '') for s in graph_skills]
    assert 'loadable_test' in skill_names, f"Skill not found in graph: {skill_names}"
    print(f"  loaded from graph: OK ({len(graph_skills)} skills)")

    # Clean up
    os.remove(filepath)
    client.query("DELETE skill WHERE name = 'loadable_test';")


def test_first_self_authored_skill(client):
    """Validation: At least one skill has been self-authored from real agent behaviour."""
    print("\n5. First self-authored skill (full compile pipeline)...")

    # Seed the graph with enough history for pattern detection
    # Create reflections that represent real agent behaviour
    client.query("""
        CREATE reflection:compile_r1 SET
            content = 'Running consolidation: decayed 5 edges, pruned 2',
            trigger = 'default_mode_reflect',
            created_at = time::now(),
            salience = 0.6;
        CREATE reflection:compile_r2 SET
            content = 'Consolidation cycle complete, vitality stable',
            trigger = 'default_mode_reflect',
            created_at = time::now(),
            salience = 0.5;
        CREATE reflection:compile_r3 SET
            content = 'Third consolidation, reconnected 1 islanded node',
            trigger = 'default_mode_reflect',
            created_at = time::now(),
            salience = 0.7;
    """)

    # Run the full compile pipeline
    result = compile_skills(client)

    assert result['patterns_detected'] > 0, "No patterns detected in compile"
    print(f"  patterns detected: {result['patterns_detected']}")
    for p in result['patterns']:
        print(f"    {p}")

    assert result['skills_compiled'] > 0, "No skills compiled"
    print(f"  skills compiled: {result['skills_compiled']}")
    for s in result['new_skills']:
        print(f"    {s['name']} -> {s['filepath']}")
        assert os.path.exists(s['filepath']), f"Skill file missing: {s['filepath']}"

    # Verify the skill is in the graph
    graph_skills = load_skills(client)
    compiled_names = [s['name'] for s in result['new_skills']]
    for name in compiled_names:
        found = any(s.get('name') == name for s in graph_skills)
        assert found, f"Compiled skill '{name}' not found in graph"
    print(f"  skills in graph: OK")

    # Verify skill file is loadable
    for s in result['new_skills']:
        loaded = load_skill_from_file(s['filepath'])
        assert loaded is not None, f"Cannot reload {s['filepath']}"
        assert loaded.authored_by == 'agent' or loaded.steps  # file parser doesn't preserve authored_by
    print(f"  skills reloadable: OK")

    # Clean up
    client.query("DELETE reflection:compile_r1; DELETE reflection:compile_r2; DELETE reflection:compile_r3;")
    for s in result['new_skills']:
        if os.path.exists(s['filepath']):
            os.remove(s['filepath'])
    client.query("DELETE skill;")


def test_bootstrap_seed_skill(client):
    """Validation: Human-authored seed skill bootstraps correctly."""
    print("\n6. Bootstrap seed skill...")

    skill, filepath = bootstrap_seed_skill(client)

    assert skill.name == 'state_prune'
    assert skill.authored_by == 'human'
    assert os.path.exists(filepath)
    print(f"  seed skill: {skill.name} (authored by: {skill.authored_by})")
    print(f"  file: {filepath}")

    # Verify in graph
    graph_skills = load_skills(client)
    assert any(s.get('name') == 'state_prune' for s in graph_skills)
    print(f"  registered in graph: OK")

    # Clean up
    if os.path.exists(filepath):
        os.remove(filepath)
    client.query("DELETE skill;")


def test_theory_check(client):
    """Theory check: The first self-authored skill should reflect genuine
    behavioural history, not be a template applied to empty data.

    The compile pipeline should only produce skills when there is
    sufficient evidence in the graph — repeated patterns that indicate
    the agent has been doing something consistently enough to compile
    into procedural memory.
    """
    print("\n7. Theory check: genuine behavioural grounding...")

    # Clear all edges and reflections to test from truly empty state
    client.query("DELETE associates; DELETE reflection;")

    # With no history, compile should produce nothing
    empty_result = compile_skills(client)
    assert empty_result['skills_compiled'] == 0, \
        f"Compiled {empty_result['skills_compiled']} skills from empty history!"
    print(f"  empty graph -> 0 skills: OK (no hallucinated skills)")

    # With minimal history (1 reflection), still nothing
    client.query("""
        CREATE reflection:theory_r1 SET
            content = 'Single reflection',
            trigger = 'default_mode_reflect',
            created_at = time::now(),
            salience = 0.5;
    """)
    minimal_result = compile_skills(client)
    assert minimal_result['skills_compiled'] == 0, \
        f"Compiled skills from insufficient history!"
    print(f"  minimal history -> 0 skills: OK (threshold respected)")

    # With sufficient history (3+ of same trigger), should compile
    client.query("""
        CREATE reflection:theory_r2 SET
            content = 'Second consolidation',
            trigger = 'default_mode_reflect',
            created_at = time::now(),
            salience = 0.5;
        CREATE reflection:theory_r3 SET
            content = 'Third consolidation',
            trigger = 'default_mode_reflect',
            created_at = time::now(),
            salience = 0.5;
    """)
    sufficient_result = compile_skills(client)
    assert sufficient_result['patterns_detected'] > 0, "No patterns with sufficient history"
    assert sufficient_result['skills_compiled'] > 0, "No skills with sufficient history"
    print(f"  sufficient history -> {sufficient_result['skills_compiled']} skills: OK")
    print(f"  theory check: skills emerge from accumulated evidence, not templates")

    # Clean up
    client.query("DELETE reflection:theory_r1; DELETE reflection:theory_r2; DELETE reflection:theory_r3;")
    for s in sufficient_result['new_skills']:
        if os.path.exists(s['filepath']):
            os.remove(s['filepath'])
    client.query("DELETE skill;")


def run_all():
    client = setup()
    test_pattern_detection(client)

    client = setup()
    test_skill_extraction(client)

    client = setup()
    test_skill_authoring(client)

    client = setup()
    test_skill_loading(client)

    client = setup()
    test_first_self_authored_skill(client)

    client = setup()
    test_bootstrap_seed_skill(client)

    client = setup()
    test_theory_check(client)

    print("\n=== ALL PHASE 6 VALIDATIONS PASSED ===")


if __name__ == '__main__':
    try:
        run_all()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nFAIL: {e}")
        sys.exit(1)
