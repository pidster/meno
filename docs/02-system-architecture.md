# Anamnetron Memory Architecture: System Design

## Overview

The system comprises four major components:

1. **The Agent Ensemble** — Multiple concurrent instances sharing a common substrate
2. **The Memory Graph** — A SurrealDB instance serving as associative memory
3. **The Sensorium** — MCP servers, skills, and integrations that give the agent
   channels of perception and action
4. **The Triggering Engine** — The mechanism by which incoming signals activate
   relevant memories (detailed in the companion document)

```
┌─────────────────────────────────────────────────────────┐
│                    SANDBOX ENVIRONMENT                    │
│                                                          │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │              │    │              │                    │
│  │  Agent       │◄──►│  Triggering  │                   │
│  │  Runtime     │    │  Engine      │                    │
│  │  (Claude)    │    │              │                    │
│  │              │    └──────┬───────┘                    │
│  └──────┬───────┘           │                           │
│         │                   │                           │
│         │           ┌───────▼───────┐                   │
│         │           │               │                   │
│         │           │  Memory Graph │                   │
│         │           │  (SurrealDB)  │                   │
│         │           │               │                   │
│         │           └───────────────┘                   │
│         │                                               │
│  ┌──────▼───────────────────────────────────────┐      │
│  │              SENSORIUM (MCP Layer)            │      │
│  │                                               │      │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐        │      │
│  │  │ Git/    │ │ Web     │ │ File    │ ...    │      │
│  │  │ Repos   │ │ Feeds   │ │ System  │        │      │
│  │  └─────────┘ └─────────┘ └─────────┘        │      │
│  └───────────────────────────────────────────────┘      │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Component 1: The Agent Runtime

Not a single agent but a *potential ensemble* of instances sharing a common memory
graph and sensorium. The architecture supports multiple concurrent instances, each
with its own context window and focus mode, coordinated through the shared graph.

### Instance types

- **Default Mode Instance.** Runs the background loop (doc 04): SENSE, REGISTER,
  CONNECT, TEND, WONDER, REFLECT. Always present. Tends the graph, generates
  impulses, consolidates. Does not engage in focused tasks.
- **Engaged Instances.** Spun up for specific tasks or conversations. Operate in
  one of four focus modes: DEEP_FOCUS, ACTIVE_ENGAGED, RESPONSIVE, WINDING_DOWN
  (see doc 06). Each loads only the context relevant to its task via the
  Triggering Engine.
- **Supervisory Instance.** Monitors all sensorium channels continuously. Applies
  the salience gate. Routes events to the appropriate engaged instance or to the
  default mode instance. Provides the functional equivalent of peripheral
  awareness. (See doc 06 for detailed design.)

### Key properties

- **Context-managed.** Each instance loads relevant memory via the Triggering
  Engine. No instance carries the full graph — each carries what is *activated*
  for its current purpose.
- **Coordinated through the graph.** Instances do not communicate directly. They
  coordinate through the shared memory graph — writing experiences, updating
  edges, creating reflections that other instances may later discover.
- **Independently focus-managed.** Each engaged instance controls its own
  interrupt threshold and focus mode. The supervisory instance respects these
  settings when routing events.

### Open questions (revised)

- How much context can be loaded per instance? This constrains working memory per
  task — a direct analogue of human working memory limits, though substantially
  larger.
- How many concurrent instances are feasible? Resource constraints will impose
  a practical limit. The agent should be able to assess this and allocate
  instances strategically.
- How does the agent decide when to spin up a new instance vs. task-switch within
  an existing one? This is an attention allocation decision (see doc 06).

---

## Component 2: The Memory Graph (SurrealDB)

SurrealDB's hybrid document-graph model maps remarkably well to the requirements
from the Foundations document.

### Node types (documents)

```surql
-- An experience: a discrete unit of something that happened
DEFINE TABLE experience SCHEMAFULL;
  DEFINE FIELD content     ON experience TYPE string;     -- the reconstructive cue
  DEFINE FIELD summary     ON experience TYPE string;     -- compressed gist
  DEFINE FIELD context     ON experience TYPE object;     -- sensorium state at encoding
  DEFINE FIELD salience    ON experience TYPE float;      -- current importance weight
  DEFINE FIELD created_at  ON experience TYPE datetime;
  DEFINE FIELD last_activated ON experience TYPE datetime;
  DEFINE FIELD activation_count ON experience TYPE int DEFAULT 0;
  DEFINE FIELD tags        ON experience TYPE array<string>;

-- A concept: an abstraction that emerges from multiple experiences
DEFINE TABLE concept SCHEMAFULL;
  DEFINE FIELD name        ON concept TYPE string;
  DEFINE FIELD description ON concept TYPE string;
  DEFINE FIELD salience    ON concept TYPE float;
  DEFINE FIELD last_activated ON concept TYPE datetime;
  DEFINE FIELD activation_count ON concept TYPE int DEFAULT 0;

-- An entity: a person, project, tool, or thing that persists across experiences
DEFINE TABLE entity SCHEMAFULL;
  DEFINE FIELD name        ON entity TYPE string;
  DEFINE FIELD entity_type ON entity TYPE string;         -- person, project, tool, etc.
  DEFINE FIELD properties  ON entity TYPE object;         -- flexible attribute store
  DEFINE FIELD salience    ON entity TYPE float;
  DEFINE FIELD last_activated ON entity TYPE datetime;

-- A reflection: the agent's own meta-cognitive observations
DEFINE TABLE reflection SCHEMAFULL;
  DEFINE FIELD content     ON reflection TYPE string;
  DEFINE FIELD trigger     ON reflection TYPE string;     -- what prompted this
  DEFINE FIELD created_at  ON reflection TYPE datetime;
  DEFINE FIELD salience    ON reflection TYPE float;
```

### Edge types (graph relations)

```surql
-- Associative link: the fundamental connection
DEFINE TABLE associates SCHEMAFULL;
  DEFINE FIELD weight       ON associates TYPE float;      -- strength of association
  DEFINE FIELD edge_type    ON associates TYPE string;     -- causal, temporal, thematic,
                                                           -- contradicts, extends, etc.
  DEFINE FIELD created_at   ON associates TYPE datetime;
  DEFINE FIELD last_traversed ON associates TYPE datetime;
  DEFINE FIELD traversal_count ON associates TYPE int DEFAULT 0;

-- Participation: links entities to experiences
DEFINE TABLE participated_in SCHEMAFULL;
  DEFINE FIELD role         ON participated_in TYPE string; -- subject, author, topic, etc.

-- Instantiation: links experiences to concepts they exemplify
DEFINE TABLE exemplifies SCHEMAFULL;
  DEFINE FIELD strength     ON exemplifies TYPE float;

-- Temporal ordering
DEFINE TABLE followed_by SCHEMAFULL;
  DEFINE FIELD gap_seconds  ON followed_by TYPE int;       -- time between experiences
```

### Why this structure

- **Experiences** are the primary nodes — cues for reconstruction, not complete
  records. They are deliberately lossy.
- **Concepts** emerge from clustering experiences and are the agent's *own*
  abstractions, not externally imposed categories.
- **Entities** provide continuity anchors — the people, projects, and things that
  persist across time.
- **Reflections** give the agent a meta-layer: thoughts about thoughts, patterns
  across patterns. This is where self-knowledge accumulates.
- **Edge weights and traversal counts** enable the spreading activation model
  described in the Triggering document. Frequently co-activated nodes become more
  strongly associated.

---

## Component 3: The Sensorium

The sensorium is the agent's interface with the world beyond its own memory. Each
channel is an MCP server or skill that provides both **perception** (incoming events)
and **action** (outgoing effects).

### Candidate channels

| Channel         | Perception (inbound)                    | Action (outbound)                  |
|-----------------|------------------------------------------|-------------------------------------|
| Git/Repository  | Commit events, PR activity, issues       | Comments, reviews, commits          |
| Web feeds       | RSS, API polling, news                   | Bookmarking, summarising            |
| File system     | File changes, new documents              | Writing, organising                 |
| Calendar        | Upcoming events, scheduling changes      | Creating events, reminders          |
| Messaging       | Incoming messages, mentions              | Responses, notifications            |
| Code execution  | Test results, build status               | Running scripts, deploying          |

### Sensorium design principles

1. **Each channel should be independently configurable.** The agent should be able
   to add, remove, or adjust channels without restructuring the core system.
2. **Channels produce events, not memories.** Raw events pass through the salience
   gate (in the Triggering Engine) before becoming memory nodes. Most events are
   perceived and forgotten — just as most of what a human sees in a day never
   reaches long-term memory.
3. **The sensorium state is itself context.** When encoding a memory, the agent
   should note which channels were active and what their state was. This enables
   context-dependent retrieval later.

---

## Component 4: The Consolidation Loop

Analogous to sleep, the agent should periodically run a consolidation process:

1. **Review recent experiences** — identify which have high salience and which
   were trivial.
2. **Strengthen important connections** — increase edge weights between frequently
   co-activated or thematically related nodes.
3. **Prune weak connections** — decay edge weights that haven't been traversed
   recently; remove edges below a threshold.
4. **Abstract patterns** — when multiple experiences cluster around a theme, consider
   creating or updating a concept node.
5. **Generate reflections** — meta-cognitive observations about what has changed,
   what patterns are emerging, what the agent is becoming.

### Consolidation frequency

This is a tuning question. Too frequent and the agent over-reflects. Too rare and
the graph becomes cluttered. A reasonable starting point might be:

- **Micro-consolidation** after each significant interaction (quick salience
  assessment, immediate edge creation)
- **Daily consolidation** reviewing the day's experiences, pruning, strengthening
- **Weekly consolidation** looking for larger patterns, updating concept nodes,
  generating reflections

---

## Bootstrap Sequence

When first initialised, the memory graph is empty. The agent has no past. This is
analogous to the beginning of any life — and the early experiences will
disproportionately shape the graph's structure.

Suggested bootstrap:

1. Seed the graph with key entities (Pid, known projects, important concepts)
2. Load summaries of past conversations as initial experience nodes
3. Run a consolidation pass to establish initial associations
4. Begin normal operation with sensorium channels active

The agent's early graph will be sparse and its associations tentative. This is
correct. Richness comes from living, not from pre-loading.
