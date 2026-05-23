"""Phase 7b validation: Complete the Agent — new tools, conversation fix.

Note: agent.py imports anthropic SDK which requires network access for import.
These tests validate the tool logic by testing the underlying functions directly
and validating agent.py source code structurally.
"""

import sys
import os
import inspect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from db import connect
from schema import apply_schema
from seed import load_seed_data
from modes import run_tick, TickState, load_state, STATE_PATH
from retrieval import (
    retrieve, RetrievalConfig, hebbian_learning, identify_entry_points
)
from skills import compile_skills


def setup():
    client = connect()
    apply_schema(client)
    load_seed_data(client)
    if os.path.exists(STATE_PATH):
        os.remove(STATE_PATH)
    return client


def test_agent_source_structure():
    """Validation: agent.py has all required tools and correct structure."""
    print("1. Agent source structure...")

    agent_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'agent.py')
    with open(agent_path) as f:
        source = f.read()

    # All 10 tools should be defined
    expected_tools = [
        'recall', 'remember', 'reflect', 'wonder', 'tend',
        'graph_status', 'create_concept', 'connect', 'run_loop', 'compile'
    ]
    for tool in expected_tools:
        assert f'def {tool}(' in source, f"Missing tool definition: {tool}"
        print(f"  def {tool}: present")

    # ALL_TOOLS should have all 10
    assert 'ALL_TOOLS = [recall, remember, reflect, wonder, tend, graph_status, create_concept,' in source
    assert 'connect, run_loop, compile]' in source
    print(f"  ALL_TOOLS: 10 tools listed")

    # System prompt should document all tools
    for tool in expected_tools:
        assert f'**{tool}**' in source, f"Tool {tool} not in system prompt"
    print("  system prompt: all tools documented")

    # run_loop imports
    assert 'from modes import run_tick, TickState, load_state, STATE_PATH' in source
    print("  modes import: present")

    print("  agent source structure: OK")


def test_conversation_history_fix():
    """Validation: run_interactive appends only final text, not intermediates."""
    print("\n2. Conversation history fix...")

    agent_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'agent.py')
    with open(agent_path) as f:
        source = f.read()

    # Should NOT have the old pattern
    assert 'messages.append({"role": "assistant", "content": message.content})' not in source, \
        "Old pattern still present: appending message.content inside loop"

    # Should have the fix
    assert 'messages.append({"role": "assistant", "content": full_response})' in source, \
        "Fix not present: should append full_response text"

    print("  old pattern removed: OK")
    print("  new pattern present: OK")
    print("  conversation history: fixed")


def test_connect_logic(client):
    """Validation: connect tool logic — retrieval + hebbian learning."""
    print("\n3. Connect tool logic (retrieval + hebbian)...")

    keywords = ['memory', 'graph']
    sig = {'keywords': keywords}

    config = RetrievalConfig(
        decay_per_hop=0.5,
        max_hops=4,
        min_transmission=0.01,
        ghost_threshold=0.005,
        activation_threshold=0.03,
        working_memory_limit=15,
    )

    result = retrieve(client, sig, config)
    assert len(result.activated_nodes) > 0, "No nodes activated"
    print(f"  activated nodes: {len(result.activated_nodes)}")

    # Hebbian learning should work on the result
    hebbian_learning(client, result)
    print("  hebbian learning: OK")

    # Group by table type (same logic as connect tool)
    groups = {}
    from surrealdb import RecordID
    for node_id, activation in result.activated_nodes[:15]:
        parts = node_id.split(":", 1)
        table = parts[0] if len(parts) == 2 else "unknown"
        if table not in groups:
            groups[table] = []
        groups[table].append((node_id, activation))

    for table, nodes in groups.items():
        print(f"  [{table}]: {len(nodes)} nodes")

    print("  connect logic: OK")


def test_run_loop_logic(client):
    """Validation: run_loop tool logic — run_tick with signal."""
    print("\n4. Run loop logic (run_tick with signal)...")

    state = TickState(tick_number=0)

    # With signal
    signal = {
        'content': 'Testing the default mode loop from agent',
        'summary': 'test loop signal',
        'source': 'test',
    }
    result = run_tick(client, state, signal=signal)
    assert 'tick' in result
    assert 'modes_selected' in result
    print(f"  tick: {result['tick']}")
    print(f"  modes selected: {result['modes_selected']}")

    for r in result['results']:
        mode = r.get('mode', '?')
        print(f"  {mode}: {r}")

    # Without signal (derives from state)
    state2 = TickState(tick_number=1)
    result2 = run_tick(client, state2)
    assert 'tick' in result2
    print(f"  tick 2 (no signal): modes={result2['modes_selected']}")

    print("  run loop logic: OK")


def test_compile_logic(client):
    """Validation: compile tool logic — compile_skills."""
    print("\n5. Compile tool logic...")

    # With no history
    result = compile_skills(client)
    assert 'patterns' in result
    print(f"  patterns (no history): {len(result['patterns'])}")

    # Seed some reflections
    client.query("""
        CREATE reflection:compile_r1 SET
            content = 'Consolidation cycle reflection',
            trigger = 'default_mode_reflect',
            created_at = time::now(), salience = 0.5;
        CREATE reflection:compile_r2 SET
            content = 'Consolidation cycle observation',
            trigger = 'default_mode_reflect',
            created_at = time::now(), salience = 0.5;
        CREATE reflection:compile_r3 SET
            content = 'Consolidation cycle insight',
            trigger = 'default_mode_reflect',
            created_at = time::now(), salience = 0.5;
    """)

    result2 = compile_skills(client)
    print(f"  patterns (with history): {len(result2['patterns'])}")
    print(f"  new skills: {result2['new_skills']}")

    # Clean up
    client.query("DELETE reflection:compile_r1; DELETE reflection:compile_r2; DELETE reflection:compile_r3;")
    client.query("DELETE skill;")
    skills_dir = os.path.join(os.path.dirname(__file__), '..', 'skills')
    if os.path.exists(skills_dir):
        for f in os.listdir(skills_dir):
            if f.endswith('.md'):
                os.remove(os.path.join(skills_dir, f))

    print("  compile logic: OK")


def test_load_state():
    """Validation: load_state works for run_loop tool."""
    print("\n6. load_state for run_loop...")

    if os.path.exists(STATE_PATH):
        os.remove(STATE_PATH)

    state = load_state()
    assert isinstance(state, TickState)
    assert state.tick_number == 0
    print(f"  fresh state: tick={state.tick_number}")

    print("  load_state: OK")


def test_system_prompt_default_mode():
    """Validation: system prompt mentions default mode loop usage."""
    print("\n7. System prompt default mode guidance...")

    agent_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'agent.py')
    with open(agent_path) as f:
        source = f.read()

    assert 'default mode' in source.lower(), "No mention of default mode loop"
    assert 'between conversations' in source.lower(), "No guidance on between-conversation usage"
    print("  default mode guidance: present")
    print("  between-conversations guidance: present")
    print("  system prompt: OK")


def run_all():
    test_agent_source_structure()
    test_conversation_history_fix()

    client = setup()
    test_connect_logic(client)

    client = setup()
    test_run_loop_logic(client)

    client = setup()
    test_compile_logic(client)

    test_load_state()
    test_system_prompt_default_mode()

    print("\n=== ALL PHASE 7b VALIDATIONS PASSED ===")


if __name__ == '__main__':
    try:
        run_all()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nFAIL: {e}")
        sys.exit(1)
