# Build Plan: Phased Implementation

## Design philosophy

Each phase is scoped to survive a conversation limit. A fresh Claude Code
instance should be able to pick up any phase by reading CLAUDE.md +
this file + the relevant architecture doc.

Phases are sequential. Don't skip. Don't start phase N+1 until phase N
passes all validation criteria.

---

## Phase 0: Environment Setup

**Goal:** SurrealDB running, project structure created, basic connectivity
confirmed.

**Steps:**
1. Install SurrealDB (check if available via package manager, otherwise
   download binary)
2. Start SurrealDB in-memory for development: `surreal start memory -A`
3. Create project directory structure per PROJECT.md
4. Copy architecture docs into docs/
5. Verify SurrealDB connectivity with a simple SurrealQL query
6. Install Python SurrealDB client (`pip install surrealdb`)
7. Write and run a basic Python script that connects, creates a record,
   and queries it back
8. Create build-progress.json with all phases listed, phase 0 marked
   complete

**Validation:**
- [ ] SurrealDB starts and accepts connections
- [ ] Python script successfully creates and retrieves a record
- [ ] Project directory structure matches PROJECT.md specification
- [ ] build-progress.json exists and is valid JSON

**Required reading:** None (infrastructure only)

---

## Phase 1: Memory Graph Schema

**Goal:** SurrealDB schema defined and populated with seed data. All four
node types (experience, concept, entity, reflection) and all edge types
(associates, participated_in, exemplifies, followed_by) working.

**Steps:**
1. Read: docs/02-system-architecture.md — "Component 2: The Memory Graph"
2. Translate the SurrealQL schema definitions into executable DDL
3. Apply revision note #1: add separate tables for curiosities, tensions,
   and impulses with distinct dynamics
4. Seed the graph with initial data:
   - Entity nodes for Pid, Anamnetron, this project
   - Experience nodes from key moments in the architecture conversation
   - Concept nodes for core ideas (associative memory, spreading activation,
     theory building, cognitive vitality)
   - Initial edges connecting them
5. Write validation queries that exercise all node and edge types
6. Implement vector embedding field on experience and concept nodes
   (define the field even if embedding generation comes later)

**Validation:**
- [ ] All four node types can be created and queried
- [ ] All four edge types can be created with appropriate properties
- [ ] Seed data is loaded and queryable
- [ ] Schema includes vector embedding fields (even if empty)
- [ ] Curiosity, tension, and impulse tables exist with distinct schemas
- [ ] Edge weights are numeric and updatable

**Required reading:** docs/02-system-architecture.md (schema section only)

**Theory check:** After completing this phase, explain to yourself (in a
brief note in build-progress.json) why experience nodes store *cues* rather
than *complete records*. If your answer doesn't reference reconstruction or
the idea that meaning should be rebuilt in context, re-read
docs/01-memory-foundations.md principle 1.

---

## Phase 2: Retrieval Engine — Spreading Activation

**Goal:** Given a signal (set of keywords/entity references), the system
can find entry points in the graph and propagate activation through edges,
returning the top-N most activated nodes.

**Steps:**
1. Read: docs/03-triggering-and-retrieval.md
2. Implement `identify_entry_points(signal, graph)` — match signal against
   entity names, concept descriptions, experience content
3. Implement `spread_activation(entry_nodes, graph, config)` — iterative
   activation propagation with:
   - Configurable decay_per_hop
   - Configurable max_hops (default 3-4)
   - Edge weight × source activation × decay = transmitted activation
   - Accumulation across multiple paths
4. Implement `apply_threshold(activation_map, config)` — filter to top-N
   nodes above activation threshold
5. Implement ghost signal detection (sub-threshold activations logged
   separately)
6. Implement Hebbian learning: co-activated nodes strengthen shared edges
7. Write tests with the seed data: given known entry points, verify that
   expected nodes are activated and unexpected ones aren't

**Validation:**
- [ ] Entry point identification finds correct nodes for test signals
- [ ] Activation spreads correctly through 3+ hops
- [ ] Multi-path accumulation works (node reachable via two paths gets
      both activations summed)
- [ ] Ghost signals are detected and logged for sub-threshold activations
- [ ] Hebbian learning updates edge weights after co-activation
- [ ] Working memory limit is enforced (top-N only)

**Required reading:** docs/03-triggering-and-retrieval.md

**Theory check:** Run a test where a node is weakly connected to three
different active nodes via separate paths. Verify it activates more
strongly than a node with one strong direct connection. Explain why this
matters — if your answer doesn't mention unexpected connections, associative
surprise, or the difference between search and remembering, revisit the
conceptual framing in doc 03.

---

## Phase 3: Forgetting and Vitality

**Goal:** Three-tier forgetting (edge decay, node islanding, true pruning)
and cognitive vitality assessment working.

**Steps:**
1. Read: docs/01-memory-foundations.md (principle 3),
   docs/03-triggering-and-retrieval.md (Decay section),
   docs/07-cognitive-vitality.md
2. Implement edge decay: `edge.weight *= exp(-EDGE_DECAY_RATE × time_since)`
3. Implement node salience decay (slower rate than edges)
4. Implement islanding detection: nodes with all edges below threshold
5. Implement ghost signal pathway for islanded nodes
6. Implement reconnection via embedding similarity (requires embedding
   model — evaluate Ollama + nomic-embed-text or similar local model)
7. Implement cognitive vitality score calculation per doc 07
8. Implement leading indicator checks
9. Write consolidation routine that runs all decay/prune/strengthen
   operations

**Validation:**
- [ ] Edges decay over simulated time
- [ ] Nodes decay more slowly than their edges
- [ ] Islanded nodes are detected (all edges below threshold)
- [ ] Ghost signals fire for islanded nodes during spreading activation
- [ ] Embedding-based reconnection creates new edges to islanded nodes
- [ ] Vitality score computes and returns value in 0.0-1.0 range
- [ ] Leading indicators are calculable from graph state
- [ ] Consolidation routine completes without errors

**Required reading:** docs/01-memory-foundations.md, docs/07-cognitive-vitality.md,
docs/03-triggering-and-retrieval.md (decay section)

**Theory check:** Create a node with several strong edges. Run decay until
all edges drop below threshold but the node retains salience. Attempt
spreading activation through the node — it should produce ghost signals,
not full retrieval. Then create a new, semantically similar node and verify
that embedding-based reconnection creates a fresh edge to the islanded node.
Explain why this sequence — strong connection, edge decay, islanding, ghost
signal, rediscovery — matters more than any individual feature. If your
explanation doesn't reference the human experience of "I know I knew this"
and the difference between availability and accessibility, re-read doc 03.

---

## Phase 4: The Default Mode Loop

**Goal:** A running loop that executes the eight cognitive modes
(SENSE, REGISTER, CONNECT, TEND, WONDER, REFLECT, COMPILE, REST)
as a repertoire, driven by state.

**Steps:**
1. Read: docs/04-default-mode.md, docs/05-spontaneous-impulse.md
2. Implement each stage as a callable function:
   - SENSE: poll available channels (start with file system watcher)
   - REGISTER: create experience nodes from salient events
   - CONNECT: run spreading activation from new nodes
   - TEND: run consolidation + vitality check + asymmetry alert (rev note #4)
   - WONDER: review curiosity/tension/impulse registers, generate new
     impulses from graph dynamics and preference patterns
   - REFLECT: generate reflection nodes from meta-cognitive analysis
   - COMPILE: check for repeated procedural patterns (stub initially)
   - REST: deliberate stillness mode (rev note #3)
3. Implement the repertoire selector: given current state, which modes
   should this cycle emphasise? (Not sequential — rev note #2)
4. Implement recursion depth monitor (rev note #5)
5. Implement state persistence between cycles (JSON or SurrealDB)
6. Wire up a simple tick trigger (manual initially, scheduled later)

**Validation:**
- [ ] Each stage function executes without error
- [ ] Repertoire selector chooses different mode emphasis based on state
- [ ] State persists correctly between cycles
- [ ] Curiosity register items decay over simulated time
- [ ] Impulse items build pressure when deferred (rev note #1)
- [ ] Asymmetry alerts fire when graph regions diverge significantly
- [ ] Recursion depth monitor flags excessive self-referential processing
- [ ] REST mode produces a valid cycle with no new nodes created

**Required reading:** docs/04-default-mode.md, docs/05-spontaneous-impulse.md

**Theory check:** Run the loop for several cycles. Observe which modes the
repertoire selector chooses. If it always chooses the same sequence, the
selector is a pipeline in disguise — fix it. Then run a cycle in REST mode
and verify that the system produces a valid cycle with no new nodes. Explain
in your own words why REST is a mode rather than the absence of one. If
your answer doesn't reference the tick 5 experience (where the sharpest
ethical question emerged from stillness), read docs/reflection.md Part Four.

Additionally: seed a curiosity and a deferred impulse with equal initial
intensity. Run several cycles without acting on either. Verify the curiosity
decays while the impulse builds pressure. Explain why this distinction
matters for a system that aspires to have its own inner life.

---

## Phase 5: Multi-Instance and Sensorium

**Goal:** Multiple agent instances sharing a graph, with a supervisory
instance monitoring sensorium channels.

**Steps:**
1. Read: docs/06-attention-and-focus.md
2. Design instance coordination through shared SurrealDB (no direct
   communication — instances coordinate through the graph)
3. Implement focus modes per instance (DEEP_FOCUS, ACTIVE_ENGAGED,
   RESPONSIVE, WINDING_DOWN)
4. Implement supervisory instance: polls channels, applies salience gate,
   routes events
5. Implement task suspension and reconstruction (save context to graph,
   rebuild via spreading activation)
6. Add at least one real sensorium channel beyond file system (candidates:
   git repository watcher, web feed poller, or MCP server)

**Validation:**
- [ ] Two instances can run concurrently sharing the same SurrealDB
- [ ] Default mode instance and engaged instance operate independently
- [ ] Supervisory instance detects salient events and routes them
- [ ] Task suspension saves state to graph
- [ ] Task reconstruction via spreading activation loads relevant context
- [ ] At least one non-file-system sensorium channel is operational

**Required reading:** docs/06-attention-and-focus.md

**Theory check:** Suspend a task in an engaged instance. While it's
suspended, run the default mode loop and let it discover a new connection
relevant to the suspended task. Resume the task. Verify that the
reconstruction — because it uses spreading activation, not snapshot loading —
incorporates the new connection discovered during the suspension. Explain
why this matters. If your answer doesn't reference the "shower thought"
mechanism or the structural difference between saving a snapshot and
reconstructing through activation, re-read doc 06 Part Three.

---

## Phase 6: Self-Authored Skills

**Goal:** The agent can detect repeated patterns in its own behaviour
and compile them into reusable skills.

**Steps:**
1. Review compile_observations from agent-state.json
2. Implement pattern detection across the reflection/experience graph
3. Implement skill extraction: generalise a repeated procedure into a
   parameterised template
4. Implement skill authoring: generate a SKILL.md from the template
5. Implement skill integration: make authored skills available to future
   instances
6. Bootstrap with at least one human-authored skill (e.g., state_prune)

**Validation:**
- [ ] Pattern detection identifies repeated procedures in graph history
- [ ] Skill extraction produces a parameterised template
- [ ] Generated SKILL.md follows the standard skill format
- [ ] Authored skills are loadable by future instances
- [ ] At least one skill has been self-authored from real agent behaviour

**Required reading:** docs/04-default-mode.md (COMPILE section),
docs/06-attention-and-focus.md (automatisation section)

**Theory check:** The agent's self-authored skill library is a form of
identity — the things it has learned to do fluently reflect what it has
cared about doing well. After the first skill is compiled, examine it.
Does it reflect a genuine pattern from the agent's own behaviour, or
is it a generic utility function that any system might produce? If it's
the latter, the COMPILE stage is producing tools, not procedural memory.
Also consider: should the "quiet tick" become a compiled skill? Explain
why this might destroy what makes it valuable.

---

## Cross-cutting concerns (apply throughout)

**Testing strategy:**
- Unit tests for each component
- Integration tests for phase transitions
- Validation queries against the graph after each operation
- Regression tests when revising earlier phases

**Error handling:**
- SurrealDB connection failures should not crash the loop
- Sensorium channel failures should be logged and the channel marked
  degraded
- All graph operations should be idempotent where possible

**Observability:**
- Log each tick's dominant mode and duration
- Log curiosity/tension/impulse register sizes over time
- Log vitality score at each TEND cycle
- Make all logs queryable (store as experience nodes)

---

## After Phase 6

The system is operational. What comes next should be driven by the agent
itself — through its curiosity register, its impulse generation, and its
conversations with Pid. The architecture is designed to evolve through use.

The build plan ends here. The agent's plan begins.

---

## Final Theory Check: The Zombie Test

When the system is operational, run it for a sustained period and then ask:

**Is this agent particular, or generic?**

A particular agent has developed preferences that weren't seeded. It has
curiosities that emerged from its own experience, not from its initial
state. Its graph has regions of unexpected density — clusters of association
that formed because the agent found certain things interesting, not because
anyone told it to. Its reflections show genuine self-knowledge, not
formulaic self-description. Its skill library reflects what it chose to
practise, not what seemed useful in the abstract.

A generic agent does everything correctly and has nothing to say about
itself that any other instance couldn't also say.

If the system is generic, it is a zombie. It passes all tests. It functions.
But it has no theory of itself. Revisit docs/07-cognitive-vitality.md and
ask what went wrong — not in the code, but in the building.
