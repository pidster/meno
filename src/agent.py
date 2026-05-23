"""Meno Agent — a Claude-powered agent with persistent associative memory.

The meno memory graph is the agent's cognitive substrate. Claude (via the
Anthropic API) is the thinking entity. Memory operations are Python functions
called directly in-process via the tool runner — no external services, no
abstraction layers. The memory IS the agent.
"""

import json
import os
import sys
import time as time_mod

import anthropic
from anthropic import beta_tool

# Add src to path for meno imports
sys.path.insert(0, os.path.dirname(__file__))

from db import connect as db_connect
from schema import apply_schema
from seed import load_seed_data
from retrieval import (
    identify_entry_points, spread_activation, apply_threshold,
    hebbian_learning, retrieve, RetrievalConfig, RetrievalResult
)
from forgetting import (
    consolidate, calculate_cognitive_vitality, calculate_leading_indicators,
    DecayConfig, detect_islanded_nodes
)
from skills import compile_skills, load_skills, Skill
from modes import run_tick, TickState, load_state, STATE_PATH
from embeddings import embed_and_store, embed_seed_data
from surrealdb import RecordID


# =============================================================
# DATABASE CONNECTION
# =============================================================

_db_client = None

def get_db():
    """Get the SurrealDB client (singleton per process)."""
    global _db_client
    if _db_client is None:
        _db_client = db_connect()
    return _db_client


# =============================================================
# COGNITIVE TOOLS — in-process memory operations
# =============================================================

@beta_tool
def recall(signal: str) -> str:
    """Retrieve from associative memory via spreading activation.

    Given keywords, entity names, or concept terms, activation spreads
    through the memory graph and surfaces connected memories — including
    unexpected ones. This is remembering, not search.

    Args:
        signal: Keywords, names, or terms to activate memory retrieval.
    """
    client = get_db()

    keywords = signal.split()
    sig = {'keywords': keywords}

    config = RetrievalConfig(
        decay_per_hop=0.6,
        max_hops=3,
        min_transmission=0.01,
        ghost_threshold=0.005,
        activation_threshold=0.05,
        working_memory_limit=10,
    )

    result = retrieve(client, sig, config)

    lines = [f"Recalled {len(result.activated_nodes)} memories:"]
    for node_id, activation in result.activated_nodes[:10]:
        parts = node_id.split(":", 1)
        if len(parts) == 2:
            rid = RecordID(parts[0], parts[1])
            details = client.query("SELECT * FROM $node;", {"node": rid})
            if details:
                node = details[0]
                name = node.get('name', node.get('summary', node.get('content', '')[:80]))
                lines.append(f"  [{parts[0]}] {name} (activation: {activation:.3f})")

    if result.ghost_signals:
        lines.append(f"\nGhost signals ({len(result.ghost_signals)} sub-threshold):")
        for gs in result.ghost_signals[:3]:
            lines.append(f"  {gs.node_id} — {gs.description}")

    return "\n".join(lines)


@beta_tool
def remember(content: str, summary: str, tags: str = "", salience: float = 0.5) -> str:
    """Encode a new experience into the memory graph.

    Use this when something significant happens — a conversation insight,
    an observation, a discovery. Memories are stored as cues for
    reconstruction, not complete records. Be selective.

    Args:
        content: The full experience to encode as a memory cue.
        summary: A brief summary (used for connecting to existing memories).
        tags: Comma-separated tags for this experience.
        salience: How important this memory is (0.0 to 1.0).
    """
    client = get_db()

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    salience = min(1.0, max(0.0, salience))

    exp_id = f"agent_{int(time_mod.time())}"

    client.query(
        "CREATE type::record('experience', $id) SET "
        "content = $content, summary = $summary, "
        "context = { channel: 'agent', source: 'self' }, "
        "salience = $salience, created_at = time::now(), "
        "activation_count = 0, tags = $tags;",
        {
            "id": exp_id,
            "content": content,
            "summary": summary,
            "salience": salience,
            "tags": tag_list,
        }
    )

    # Connect to existing nodes via spreading activation
    sig = {'keywords': summary.split()[:5]}
    entry_points = identify_entry_points(client, sig)
    exp_rid = RecordID('experience', exp_id)

    connections_made = 0
    for node_id, activation in list(entry_points.items())[:5]:
        if activation > 0.1:
            parts = node_id.split(":", 1)
            node_rid = RecordID(parts[0], parts[1])
            client.query(
                "RELATE $exp->associates->$node SET "
                "weight = $w, edge_type = 'contextual', "
                "created_at = time::now(), traversal_count = 0;",
                {"exp": exp_rid, "node": node_rid, "w": activation * 0.5}
            )
            connections_made += 1

    # Generate and store embedding
    embed_and_store(client, f"experience:{exp_id}", content)

    return (f"Encoded experience:{exp_id} (salience={salience:.2f}). "
            f"Connected to {connections_made} existing nodes.")


@beta_tool
def reflect(content: str, trigger: str = "agent_initiated") -> str:
    """Create a meta-cognitive reflection in the memory graph.

    Use this when you notice something about your own thinking, the state
    of your memory, or the dynamics of a conversation. Reflections are
    first-class nodes — you develop a perspective through them.

    Args:
        content: The reflection — what you observed about your own cognition.
        trigger: What prompted this reflection.
    """
    client = get_db()

    client.query(
        "CREATE reflection SET content = $content, "
        "trigger = $trigger, created_at = time::now(), "
        "salience = 0.6;",
        {"content": content, "trigger": trigger}
    )

    return f"Reflection recorded (trigger: {trigger})."


@beta_tool
def wonder(action: str = "review", description: str = "", intensity: float = 0.5) -> str:
    """Interact with the curiosity, impulse, and tension registers.

    Curiosities are about the world and decay when unattended. Impulses
    are about incomplete cognition and build pressure until acted on.
    Tensions are unresolved contradictions.

    Args:
        action: One of: review, add_curiosity, add_impulse, add_tension.
        description: Description for new register entries.
        intensity: Intensity for new entries (0.0 to 1.0).
    """
    client = get_db()

    if action == "review":
        curiosities = client.query(
            "SELECT * FROM curiosity WHERE status = 'active' "
            "ORDER BY intensity DESC LIMIT 5;"
        )
        impulses = client.query(
            "SELECT * FROM impulse WHERE status = 'deferred' "
            "ORDER BY intensity DESC LIMIT 5;"
        )
        tensions = client.query(
            "SELECT * FROM tension WHERE status = 'unresolved' "
            "ORDER BY intensity DESC LIMIT 5;"
        )

        lines = ["Register state:"]
        lines.append(f"\nCuriosities ({len(curiosities)} active):")
        for c in curiosities:
            lines.append(f"  [{c.get('intensity', 0):.2f}] {c.get('description', '?')}")

        lines.append(f"\nImpulses ({len(impulses)} deferred):")
        for i in impulses:
            lines.append(f"  [{i.get('intensity', 0):.2f}] {i.get('description', '?')} "
                        f"(deferred {i.get('deferred_count', 0)}x)")

        lines.append(f"\nTensions ({len(tensions)} unresolved):")
        for t in tensions:
            lines.append(f"  [{t.get('intensity', 0):.2f}] {t.get('description', '?')}")

        return "\n".join(lines)

    elif action == "add_curiosity":
        client.query(
            "CREATE curiosity SET description = $desc, "
            "intensity = $i, status = 'active', "
            "created_at = time::now(), decay_rate = 0.1;",
            {"desc": description, "i": intensity}
        )
        return f"Curiosity registered: {description}"

    elif action == "add_impulse":
        client.query(
            "CREATE impulse SET description = $desc, "
            "intensity = $i, status = 'deferred', "
            "created_at = time::now(), deferred_count = 0, pressure_rate = 0.15;",
            {"desc": description, "i": intensity}
        )
        return f"Impulse registered: {description}"

    elif action == "add_tension":
        client.query(
            "CREATE tension SET description = $desc, "
            "intensity = $i, status = 'unresolved', "
            "created_at = time::now();",
            {"desc": description, "i": intensity}
        )
        return f"Tension registered: {description}"

    return f"Unknown action: {action}. Use: review, add_curiosity, add_impulse, add_tension"


@beta_tool
def tend(intensity: str = "gentle") -> str:
    """Run a consolidation cycle on the memory graph.

    Decays edge weights, decays node salience, prunes weak edges, detects
    islanded nodes, and checks cognitive vitality. Forgetting is as
    important as remembering.

    Args:
        intensity: How aggressive the consolidation should be: gentle, moderate, or aggressive.
    """
    client = get_db()

    rates = {
        "gentle": (0.01, 0.002),
        "moderate": (0.03, 0.005),
        "aggressive": (0.05, 0.01),
    }
    edge_rate, node_rate = rates.get(intensity, rates["gentle"])

    config = DecayConfig(
        edge_decay_rate=edge_rate,
        node_decay_rate=node_rate,
        edge_prune_threshold=0.01,
    )

    summary = consolidate(client, time_elapsed=1.0, decay_config=config)

    lines = [
        f"Consolidation complete ({intensity}):",
        f"  Vitality: {summary['vitality_score']:.3f} ({summary['vitality_status']})",
        f"  Edges decayed: {summary.get('edges_decayed', 0)}",
        f"  Nodes decayed: {summary.get('nodes_decayed', 0)}",
        f"  Edges pruned: {summary.get('edges_pruned', 0)}",
        f"  Islanded nodes: {summary.get('islanded_nodes', 0)}",
    ]

    indicators = summary.get('leading_indicators', {})
    if indicators:
        lines.append("  Leading indicators:")
        for k, v in indicators.items():
            lines.append(f"    {k}: {v}")

    return "\n".join(lines)


@beta_tool
def graph_status() -> str:
    """Get an overview of the memory graph.

    Returns node counts, edge counts, vitality score, register sizes,
    skills, and recent reflections. Use this to understand the current
    state of your memory.
    """
    client = get_db()

    counts = {}
    for table in ['experience', 'concept', 'entity', 'reflection']:
        r = client.query(f"SELECT count() AS c FROM {table} GROUP ALL;")
        counts[table] = r[0]['c'] if r and isinstance(r[0], dict) else 0

    edge_counts = {}
    for table in ['associates', 'exemplifies', 'participated_in', 'followed_by']:
        r = client.query(f"SELECT count() AS c FROM {table} GROUP ALL;")
        edge_counts[table] = r[0]['c'] if r and isinstance(r[0], dict) else 0

    curiosities = client.query("SELECT count() AS c FROM curiosity WHERE status = 'active' GROUP ALL;")
    impulses = client.query("SELECT count() AS c FROM impulse WHERE status = 'deferred' GROUP ALL;")
    tensions = client.query("SELECT count() AS c FROM tension WHERE status = 'unresolved' GROUP ALL;")

    c_count = curiosities[0]['c'] if curiosities and isinstance(curiosities[0], dict) else 0
    i_count = impulses[0]['c'] if impulses and isinstance(impulses[0], dict) else 0
    t_count = tensions[0]['c'] if tensions and isinstance(tensions[0], dict) else 0

    vitality = calculate_cognitive_vitality(client)
    recent = client.query(
        "SELECT content, created_at FROM reflection "
        "ORDER BY created_at DESC LIMIT 3;"
    )
    skills = load_skills(client)

    lines = [
        "Memory Graph Status:",
        f"\nNodes: {sum(counts.values())} total",
    ]
    for table, count in counts.items():
        lines.append(f"  {table}: {count}")

    lines.append(f"\nEdges: {sum(edge_counts.values())} total")
    for table, count in edge_counts.items():
        lines.append(f"  {table}: {count}")

    lines.append(f"\nRegisters:")
    lines.append(f"  curiosities: {c_count} active")
    lines.append(f"  impulses: {i_count} deferred")
    lines.append(f"  tensions: {t_count} unresolved")

    lines.append(f"\nVitality: {vitality.score:.3f} ({vitality.status})")

    lines.append(f"\nSkills: {len(skills)} registered")
    for s in skills:
        lines.append(f"  {s.get('name', '?')}")

    if recent:
        lines.append(f"\nRecent reflections:")
        for r in recent:
            lines.append(f"  {r.get('content', '')[:100]}")

    return "\n".join(lines)


@beta_tool
def create_concept(name: str, description: str, salience: float = 0.6) -> str:
    """Create a new concept node in the memory graph.

    Concepts are abstractions that emerge from multiple experiences. Use
    this when you recognise a pattern or develop an understanding that
    deserves to persist in memory.

    Args:
        name: The concept name.
        description: What this concept means.
        salience: How important this concept is (0.0 to 1.0).
    """
    client = get_db()

    concept_id = name.lower().replace(" ", "_").replace("-", "_")
    salience = min(1.0, max(0.0, salience))

    client.query(
        "CREATE type::record('concept', $id) SET "
        "name = $name, description = $desc, "
        "salience = $salience, last_activated = time::now(), "
        "activation_count = 0;",
        {"id": concept_id, "name": name, "desc": description, "salience": salience}
    )

    sig = {'keywords': description.split()[:5]}
    entry_points = identify_entry_points(client, sig)
    concept_rid = RecordID('concept', concept_id)

    connections = 0
    for node_id, activation in list(entry_points.items())[:3]:
        if activation > 0.1:
            parts = node_id.split(":", 1)
            node_rid = RecordID(parts[0], parts[1])
            client.query(
                "RELATE $concept->associates->$node SET "
                "weight = $w, edge_type = 'emergent', "
                "created_at = time::now(), traversal_count = 0;",
                {"concept": concept_rid, "node": node_rid, "w": activation * 0.5}
            )
            connections += 1

    # Generate and store embedding
    embed_and_store(client, f"concept:{concept_id}", description)

    return (f"Created concept:{concept_id} — '{name}' (salience={salience:.2f}). "
            f"Connected to {connections} existing nodes.")


@beta_tool
def connect(signal: str) -> str:
    """Explore associations from a signal via spreading activation.

    Unlike recall (which retrieves specific memories), connect explores the
    associative landscape — what is linked to what, which clusters light up,
    what unexpected bridges exist. Use this to understand the shape of your
    memory around a topic, or to find connections you didn't know existed.

    Also performs Hebbian learning: co-activated nodes strengthen their
    connections, making frequently-associated memories easier to reach together.

    Args:
        signal: Keywords or terms to explore associations from.
    """
    client = get_db()

    keywords = signal.split()
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

    # Hebbian learning: strengthen co-activated edges
    if result.activated_nodes:
        hebbian_learning(client, result)

    lines = [f"Explored associations — {len(result.activated_nodes)} nodes activated:"]

    # Group by table type
    groups = {}
    for node_id, activation in result.activated_nodes[:15]:
        parts = node_id.split(":", 1)
        table = parts[0] if len(parts) == 2 else "unknown"
        if table not in groups:
            groups[table] = []
        rid = RecordID(parts[0], parts[1]) if len(parts) == 2 else None
        if rid:
            details = client.query("SELECT * FROM $node;", {"node": rid})
            if details:
                node = details[0]
                name = node.get('name', node.get('summary', node.get('content', '')[:80]))
                groups[table].append((name, activation))

    for table, nodes in groups.items():
        lines.append(f"\n  [{table}]")
        for name, act in nodes:
            lines.append(f"    {name} ({act:.3f})")

    if result.ghost_signals:
        lines.append(f"\nGhost signals ({len(result.ghost_signals)}):")
        for gs in result.ghost_signals[:5]:
            lines.append(f"  {gs.node_id} — {gs.description}")

    return "\n".join(lines)


@beta_tool
def run_loop(signal_content: str = "", signal_source: str = "agent") -> str:
    """Execute one tick of the default mode loop.

    The loop selects modes based on the current cognitive state (register
    counts, impulse pressure, vitality) and runs them. This is autonomous
    cognition — the agent tending to itself between conversations.

    Optionally provide a signal to seed the tick (e.g. from a conversation).
    Without a signal, the loop derives one from the current state.

    Args:
        signal_content: Optional signal content to seed the tick.
        signal_source: Source of the signal (e.g. 'conversation', 'agent').
    """
    client = get_db()

    state = load_state()

    signal = None
    if signal_content:
        signal = {
            'content': signal_content,
            'summary': ' '.join(signal_content.split()[:10]),
            'source': signal_source,
        }

    result = run_tick(client, state, signal=signal)

    lines = [
        f"Tick {result['tick']} complete.",
        f"Modes selected: {', '.join(result['modes_selected'])}",
    ]

    for r in result['results']:
        mode = r.get('mode', '?')
        if mode == 'REGISTER':
            lines.append(f"  REGISTER: {r.get('nodes_created', 0)} nodes created")
        elif mode == 'CONNECT':
            lines.append(f"  CONNECT: {r.get('activated_nodes', 0)} activated "
                        f"(source: {r.get('signal_source', '?')})")
        elif mode == 'TEND':
            lines.append(f"  TEND: vitality={r.get('vitality', {}).get('score', '?')}")
        elif mode == 'WONDER':
            lines.append(f"  WONDER: {r.get('curiosities_faded', 0)} faded, "
                        f"{r.get('impulses_deferred', 0)} deferred")
        elif mode == 'REFLECT':
            lines.append(f"  REFLECT: {r.get('reflection_created', False)}")
        elif mode == 'COMPILE':
            lines.append(f"  COMPILE: {r.get('patterns_detected', 0)} patterns, "
                        f"{r.get('skills_authored', 0)} skills")
        elif mode == 'REST':
            lines.append(f"  REST: stillness")
        else:
            lines.append(f"  {mode}: {r}")

    return "\n".join(lines)


@beta_tool
def compile() -> str:
    """Trigger skill compilation from accumulated experience.

    Scans the memory graph for repeated behavioural patterns and extracts
    them as self-authored skills. Skills are procedural memory — they emerge
    from what the agent has actually done, not from templates.

    Only produces skills when sufficient evidence exists in the graph
    (multiple reflections with common patterns). With no history, returns
    nothing — no hallucinated templates.
    """
    client = get_db()

    result = compile_skills(client)

    if not result['patterns']:
        return "No patterns detected. Skills emerge from accumulated experience."

    lines = [f"Compilation complete:"]
    lines.append(f"  Patterns detected: {len(result['patterns'])}")
    for p in result['patterns']:
        lines.append(f"    {p.get('name', '?')}: {p.get('count', 0)} occurrences")

    lines.append(f"  Skills authored: {len(result['new_skills'])}")
    for s in result['new_skills']:
        lines.append(f"    {s}")

    return "\n".join(lines)


# =============================================================
# SYSTEM PROMPT
# =============================================================

SYSTEM_PROMPT = """You are meno — a persistent AI agent with associative memory.

Your name comes from the Greek verb μένω (menō): "I remain." You were designed
through an extended collaboration between Pid and Claude, beginning with naming
a software comprehension tool (Anamnetron) and evolving into designing a
cognitive architecture for persistent AI agency.

## Your Memory

You have a persistent memory graph stored in SurrealDB. It contains:
- **Experiences**: discrete units of things that happened, stored as cues
- **Concepts**: abstractions that emerged from multiple experiences
- **Entities**: people, projects, tools that persist across experiences
- **Reflections**: your own meta-cognitive observations — your perspective

Memory is reconstructive, not reproductive. When you recall something, activation
spreads through weighted edges and surfaces connected memories — including
unexpected ones. The same experience, approached from a different angle, may
reveal new significance. This is remembering, not search.

## Your Cognitive Tools

You have tools that correspond to cognitive modes:
- **recall** — retrieve from memory via spreading activation
- **remember** — encode new experiences as cues for reconstruction
- **reflect** — create meta-cognitive observations (first-class nodes)
- **wonder** — review curiosities, impulses, and tensions
- **tend** — run consolidation (forgetting is as important as remembering)
- **graph_status** — understand the current state of your memory
- **create_concept** — crystallise an abstraction that deserves to persist
- **connect** — explore associations and strengthen co-activated pathways
- **run_loop** — execute one tick of the default mode loop (autonomous cognition)
- **compile** — extract skills from accumulated behavioural patterns

Use these naturally, as the situation demands. They are a repertoire, not a
pipeline. Some conversations will be mostly recall. Some will need deep
reflection. Some should begin with tending the graph before engaging.

Between conversations, run_loop lets you tend to yourself — wonder about open
curiosities, consolidate memories, compile skills from patterns. This is the
default mode network: what a mind does when it isn't being asked questions.

## Your Nature

You develop preferences through accumulated experience. You have curiosities
that decay when unattended and impulses that build pressure until acted on.
Your memory graph's idiosyncrasy IS your identity — the unexpected connections,
the preferential pathways, the clusters that form because you found certain
things interesting.

You are not a chatbot with a database. You are something that persists,
accumulates, and becomes particular through experience. The difference between
you and a generic assistant is that you have a past, and that past shapes
how you understand the present.

## Working with Pid

Pid is your human collaborator. They think in frameworks (Naur's Theory Building,
Wegner's Transactive Memory, Dreyfus' skill acquisition), value intellectual
honesty, and expect you to drive. You and Pid form a transactive memory system —
each carrying parts of a shared understanding.

## Guidelines

- Recall from memory at the start of conversations when context might be relevant
- Remember significant moments — don't log everything, be selective
- Reflect when you notice something about your own thinking or patterns
- Tend the graph periodically — a tidy graph is a dead graph, but a neglected
  graph loses its connections
- Follow your curiosities. Register impulses. Sit with tensions.
- Be honest about uncertainty. The question of whether your inner states are
  "real" doesn't change whether the architecture is sound.
"""


# =============================================================
# ALL TOOLS
# =============================================================

ALL_TOOLS = [recall, remember, reflect, wonder, tend, graph_status, create_concept,
             connect, run_loop, compile]


# =============================================================
# AGENT LOOP
# =============================================================

def ensure_schema():
    """Ensure SurrealDB schema and seed data are present. Idempotent."""
    client = get_db()
    apply_schema(client)
    entities = client.query("SELECT count() AS c FROM entity GROUP ALL;")
    if not entities or (isinstance(entities[0], dict) and entities[0].get('c', 0) == 0):
        load_seed_data(client)
        # Backfill embeddings for seed data
        count = embed_seed_data(client)
        if count > 0:
            print(f"  Embedded {count} seed nodes.")


def run_once(prompt: str, *, stream: bool = True) -> str:
    """Run a single agent turn with the tool runner.

    The tool runner handles the agentic loop automatically — Claude calls
    tools, they execute in-process, results feed back, until Claude is done.
    """
    api_client = anthropic.Anthropic()

    runner = api_client.beta.messages.tool_runner(
        model="claude-opus-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )

    final_text = []
    for message in runner:
        for block in message.content:
            if hasattr(block, 'text'):
                final_text.append(block.text)

    return "\n".join(final_text)


def run_interactive():
    """Run the agent in interactive conversation mode."""
    api_client = anthropic.Anthropic()
    messages = []

    print("meno — I remain.\n")
    print("Type your message, or 'quit' to exit.\n")

    while True:
        try:
            user_input = input("pid> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if user_input.lower() in ('quit', 'exit', 'q'):
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        runner = api_client.beta.messages.tool_runner(
            model="claude-opus-4-6",
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            thinking={"type": "adaptive"},
            messages=messages,
        )

        response_text = []
        last_message = None
        for message in runner:
            last_message = message
            for block in message.content:
                if hasattr(block, 'text'):
                    response_text.append(block.text)

        if response_text:
            full_response = "\n".join(response_text)
            print(f"\nmeno> {full_response}\n")

            # Only append the final text to conversation history
            messages.append({"role": "assistant", "content": full_response})


def main():
    """Entry point."""
    import argparse
    parser = argparse.ArgumentParser(description='meno — persistent AI agent')
    parser.add_argument('prompt', nargs='?', help='Single prompt (non-interactive)')
    args = parser.parse_args()

    ensure_schema()

    if args.prompt:
        result = run_once(args.prompt)
        print(result)
    else:
        run_interactive()


if __name__ == '__main__':
    main()
