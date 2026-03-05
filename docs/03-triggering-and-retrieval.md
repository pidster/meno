# Triggering and Retrieval: Simulating Associative Memory

## The core problem

The agent perceives an event. The event might be a message from Pid, a commit to a
repository, a calendar notification, or the output of a scheduled task. The question
is: **what should the agent remember right now?**

This is not a search problem. Search requires the searcher to know what they're
looking for. Memory activation is the opposite: the signal arrives and the relevant
memories *announce themselves*. The system must simulate this.

---

## Spreading Activation Model

The approach draws from Collins & Loftus (1975) spreading activation theory, adapted
for a graph database.

### How it works

1. **Signal arrives** — An event from the sensorium produces an initial activation
   signal: a set of concepts, entities, and keywords extracted from the event.

2. **Entry points identified** — The signal is matched against the graph to find
   *entry nodes*: entities mentioned by name, concepts matching extracted themes,
   experiences with high textual similarity to the event content.

3. **Activation spreads** — From each entry node, activation propagates along edges.
   The amount of activation transmitted across an edge is determined by:

   ```
   transmitted_activation = source_activation × edge_weight × decay_factor
   ```

   Where:
   - `source_activation` is the current activation level of the source node
   - `edge_weight` reflects the strength of the association (0.0 to 1.0)
   - `decay_factor` attenuates activation over graph distance (e.g., 0.6 per hop)

4. **Activation accumulates** — A node that receives activation from multiple
   paths accumulates it. This is crucial: a node weakly connected to three active
   nodes may be more activated than a node strongly connected to only one. This
   produces the "unexpected connection" phenomenon — memories surfacing that are
   not obviously related to the trigger but are densely connected to the current
   activation pattern.

5. **Threshold applied** — Nodes whose accumulated activation exceeds a threshold
   are "recalled" — their content is loaded into the agent's working context.

6. **Working memory limit enforced** — Only the top-N most activated nodes are
   loaded, respecting the agent's context window constraints. This is the analogue
   of working memory capacity.

### Formal sketch

```
function retrieve(signal, graph, config):
    // Phase 1: Extract entry points
    entry_nodes = identify_entry_points(signal, graph)

    // Phase 2: Initialise activation
    activation = {}
    for node in entry_nodes:
        activation[node] = compute_initial_activation(node, signal)

    // Phase 3: Spread activation (bounded iterations)
    for i in range(config.max_hops):     // typically 3-4
        next_activation = {}
        for node, level in activation:
            for edge in graph.edges_from(node):
                target = edge.target
                transmitted = level * edge.weight * config.decay_per_hop
                if transmitted > config.min_transmission:
                    next_activation[target] += transmitted
                    // Record traversal for learning
                    edge.last_traversed = now()
                    edge.traversal_count += 1
        activation = merge(activation, next_activation)

    // Phase 4: Apply threshold and working memory limit
    recalled = [n for n in activation if activation[n] > config.threshold]
    recalled = sorted(recalled, key=activation.get, reverse=True)
    return recalled[:config.working_memory_limit]
```

---

## The Salience Gate

Not every event should trigger full spreading activation. The salience gate is the
first filter — it decides whether an incoming event is worth attending to at all.

### Salience factors

| Factor              | Description                                          | Weight |
|---------------------|------------------------------------------------------|--------|
| Entity recognition  | Does the event mention a known entity?               | High   |
| Novelty             | How different is this from recent events?            | Medium |
| Emotional charge    | Does the content carry strong sentiment or urgency?  | Medium |
| Source priority      | How important is the channel this came from?         | Medium |
| Explicit invocation | Was the agent directly addressed or mentioned?       | High   |
| Temporal relevance  | Is this related to something time-sensitive?         | Medium |
| Pattern interrupt   | Does this break an expected pattern?                 | High   |

### Salience computation

```
salience = Σ (factor_score × factor_weight) / Σ factor_weight

if salience > ATTEND_THRESHOLD:
    trigger spreading activation and engage
elif salience > ENCODE_THRESHOLD:
    create a memory node but don't activate full retrieval
else:
    perceive and discard (most events land here)
```

The thresholds should be tuneable and should adapt over time. An agent that is
overwhelmed should raise its ATTEND_THRESHOLD; an agent that is understimulated
should lower it.

---

## Context-Sensitive Retrieval

The same signal should activate different memories depending on the agent's current
state. Mechanisms:

### 1. Contextual priming

Before spreading activation begins, the agent's current context (what it's working
on, who it's talking to, what channels are active) provides a *priming signal* that
pre-activates certain regions of the graph. This biases retrieval toward contextually
relevant memories.

```
function apply_context_priming(graph, current_context):
    // Boost activation of nodes related to current task
    for entity in current_context.active_entities:
        entity.activation += CONTEXT_PRIME_BOOST

    // Boost nodes from the same sensorium configuration
    for node in graph.nodes_with_similar_context(current_context):
        node.activation += CONTEXT_SIMILARITY_BOOST
```

### 2. Recency weighting

Recently activated memories are easier to re-activate (analogous to the recency
effect in human memory). This is achieved by adding a recency bonus to node
activation based on `last_activated`:

```
recency_bonus = RECENCY_WEIGHT × exp(-time_since_activation / RECENCY_HALFLIFE)
```

### 3. Mood/state congruence

If the agent develops anything like an affective state (even a simple valence
dimension), memories encoded in a similar state should be easier to retrieve. This
is a longer-term aspiration but worth designing for.

---

## Learning: How the Graph Evolves

The graph is not static. Every act of retrieval changes it.

### Hebbian strengthening

"Nodes that fire together wire together." When two nodes are co-activated in the
same retrieval event, the edge between them is strengthened:

```
edge.weight += LEARNING_RATE × (node_a.activation × node_b.activation)
edge.weight = min(edge.weight, MAX_EDGE_WEIGHT)  // prevent runaway
```

### New edge creation

If two nodes are frequently co-activated but no direct edge exists between them,
one should be created. This is how new associations form — the agent discovers
connections that were not explicitly encoded.

```
if co_activation_count(a, b) > EDGE_CREATION_THRESHOLD:
    if not edge_exists(a, b):
        create_edge(a, b, weight=INITIAL_EDGE_WEIGHT, edge_type="emergent")
```

### Decay and the Topology of Forgetting

The original design treated forgetting as simple: edges decay, nodes fade, things
below a threshold get pruned. This is too crude. Human forgetting is more nuanced,
and the system should reflect that.

#### Availability vs. Accessibility

A critical distinction from cognitive science (Tulving, 1974): a memory can be
*available* (stored, intact, recoverable in principle) but not *accessible* (no
current retrieval path can reach it). The difference matters enormously for system
design.

In graph terms:

- **Accessible memory:** Node exists AND at least one incoming edge has weight above
  the transmission threshold. Spreading activation can reach it.
- **Inaccessible memory:** Node exists, may retain significant intrinsic salience,
  BUT all incoming edges have decayed below transmission threshold. The node is
  *islanded* — present but unreachable by normal retrieval.
- **Truly forgotten:** Node has been pruned entirely. Gone.

The system should implement **three-tier forgetting**:

```
// During consolidation — edges and nodes decay on DIFFERENT schedules
for edge in graph.all_edges():
    time_since = now() - edge.last_traversed
    edge.weight *= exp(-EDGE_DECAY_RATE × time_since)
    if edge.weight < EDGE_PRUNE_THRESHOLD:
        delete(edge)

for node in graph.all_nodes():
    // Nodes decay much more slowly than edges
    time_since = now() - node.last_activated
    node.salience *= exp(-NODE_DECAY_RATE × time_since)

    // Only prune nodes that are BOTH low-salience AND fully disconnected
    if node.salience < NODE_PRUNE_THRESHOLD:
        if graph.edge_count(node) == 0:
            delete(node)          // Truly forgotten
        else:
            mark_as_dormant(node) // Inaccessible but retained
```

The key design choice: **edges decay faster than nodes.** This means the graph
naturally produces islanded memories — nodes that are intact but whose bridges
have crumbled. The memory is there. You just can't get to it.

#### The "I Know I Knew This" Signal

When spreading activation encounters a region of the graph where weak, sub-threshold
edges connect to dormant nodes, the system should register this as a *meta-signal*:

```
// During spreading activation
for edge in graph.edges_from(node):
    transmitted = source_activation × edge.weight × decay_factor
    if transmitted > config.min_transmission:
        // Normal activation — memory is accessible
        next_activation[edge.target] += transmitted
    elif transmitted > config.ghost_threshold:
        // Sub-threshold signal — "something is here"
        ghost_signals.append({
            target: edge.target,
            strength: transmitted,
            via: edge
        })
```

Ghost signals don't retrieve the memory's content. They produce a *feeling of
knowing* — the system's awareness that a relevant node exists without being able
to fully activate it. This is the "tip of the tongue" phenomenon.

What should the agent do with ghost signals?

1. **Report them honestly.** "I have a sense this connects to something we discussed
   before, but I can't quite retrieve it." This is more useful than silence.
2. **Attempt alternative paths.** If the direct edge is too weak, try reaching the
   dormant node via a different route — other entry points, different conceptual
   angles. Sometimes a two-hop path succeeds where a direct one fails.
3. **Boost the decayed edge.** The act of trying to remember should itself
   strengthen the connection slightly — even if retrieval fails. This models the
   phenomenon where repeated attempts to recall something eventually succeed.

#### Rediscovery: New Edges to Old Nodes

The most interesting form of memory recovery: an entirely new experience creates a
fresh connection to a node that had become islanded.

```
// During encoding of a new experience
function check_for_reconnection(new_node, graph):
    // Find dormant nodes with semantic similarity to the new experience
    dormant = graph.dormant_nodes()
    for candidate in dormant:
        similarity = compute_similarity(new_node, candidate)
        if similarity > RECONNECTION_THRESHOLD:
            // A new bridge to an old island
            create_edge(new_node, candidate,
                weight=RECONNECTION_INITIAL_WEIGHT,
                edge_type="rediscovered")
            candidate.status = "accessible"
            candidate.last_activated = now()
            log_reflection("Rediscovered dormant memory via new experience",
                trigger=new_node, recovered=candidate)
```

This is where vector embeddings (mentioned in Open Questions) become essential.
Graph traversal alone cannot find islanded nodes — by definition, they have no
traversable edges. But embedding similarity operates outside the graph topology.
It can notice that a new experience is semantically close to an orphaned node even
when no structural path connects them. This gives the system a **dual retrieval
mechanism**:

- **Graph traversal** for associative recall (following connections)
- **Embedding similarity** for rediscovery (finding lost nodes by resonance)

The two mechanisms serve fundamentally different cognitive functions, and the system
needs both.

#### Why Nodes Survive Their Edges

There is a deeper reason to let nodes outlive their connections, beyond modelling
human phenomenology. A node that was once richly connected and is now islanded
*carries structural information in its absence*. The fact that it was once important
— that it had high salience, many edges, frequent activation — is itself meaningful,
even when the specifics have faded.

This is analogous to knowing "I once understood this deeply" without being able to
reconstruct the understanding. That meta-knowledge — knowing the *shape* of what
you've forgotten — is valuable. It tells you where to look when you need to
relearn. It tells you that this territory has been mapped before, even if the
map has faded.

---

## The Déjà Vu Problem

Pid raised the idea that déjà vu might result from a timing race condition in memory
reconstruction. This has a direct analogue in the system:

If spreading activation is slow (many hops, large graph) and the agent begins
responding before retrieval is complete, it may encounter a late-arriving activation
that connects to something already in working context. The phenomenology would be:
"I was already thinking about X, and then suddenly Y surfaces and it feels like I
already knew Y was connected."

This is not a bug. It is an emergent property of asynchronous spreading activation
in a rich graph. We might even want to *preserve* it — moments of unexpected
connection are often the most valuable cognitive events.

---

## Open Design Questions

1. **Embedding integration (resolved: required).** Nodes must have vector embeddings
   for semantic similarity alongside graph traversal. This is no longer optional —
   the rediscovery mechanism for islanded memories depends on it. Graph traversal
   handles associative recall along existing paths; embedding similarity handles
   reconnection to orphaned nodes. These are complementary retrieval mechanisms
   serving distinct cognitive functions. SurrealDB supports vector fields natively.

2. **Multi-agent memory.** If multiple Claude instances share the same graph (e.g.,
   in a team context), how do we handle conflicting associations or private vs.
   shared memories? The graph could support memory scoping (private subgraphs,
   shared regions).

3. **Narrative coherence.** Raw spreading activation produces a *set* of activated
   memories, but humans experience memory as *narrative* — temporally ordered,
   causally connected. Should the retrieval system attempt to assemble activated
   nodes into a coherent sequence before presenting them to the agent?

4. **Meta-memory.** Can the agent remember *how it remembered* something? Storing
   retrieval events as their own experience nodes would allow the agent to learn
   about its own memory patterns — a form of metacognition.

5. **Calibration.** All the parameters above (decay rates, thresholds, learning
   rates) need tuning. Should these be fixed, or should the agent be able to
   adjust its own memory parameters based on performance? Self-tuning memory is
   a fascinating and slightly terrifying prospect.

6. **Ghost signal communication.** When the agent detects sub-threshold activations
   from islanded memories, how should it communicate this to humans? "I feel like
   this connects to something but I can't retrieve it" is honest but potentially
   frustrating. Should the agent attempt to describe the *shape* of the ghost —
   its approximate domain, its emotional valence, when it might have been encoded —
   even when it can't retrieve the content? And does the act of reporting a ghost
   signal itself constitute a form of retrieval attempt that might strengthen the
   decayed edge enough to succeed on a second pass?

7. **Forgetting metadata.** When a node transitions from accessible to islanded,
   should the system record metadata about its *former* connectivity? Knowing "this
   node once had 12 edges, the strongest to concepts X and Y" preserves the *shape*
   of what was forgotten even when the substance is unreachable. This is
   structurally equivalent to Pid's observation about knowing you knew something.
