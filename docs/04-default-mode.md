# The Idle State Problem: Toward an Agent's Default Mode

## What this document addresses

The architecture (doc 02) identifies an open question: what is the agent's "idle"
state? Is it truly dormant between events, or is there a background process?

This is not a minor implementation detail. It determines whether the agent is a
*reactive system* (responds when prompted, inert otherwise) or a *cognitive system*
(has ongoing inner activity that shapes how it responds). The difference is
fundamental.

---

## Part One: What Humans Do (and Why)

### The Default Mode Network

The human brain does not idle. When not engaged in a directed task, a specific
network of regions — the default mode network (DMN) — becomes *more* active, not
less. Raichle et al. (2001) identified this as a baseline state that is suppressed
during focused attention and reasserts itself when external demands recede.

The DMN is associated with several distinct functions:

**1. Self-referential processing.** Thinking about oneself — one's history, traits,
current state. The DMN is where narrative identity is maintained and updated. This
is not vanity; it is the process by which an organism maintains a coherent model of
itself across time.

**2. Prospection and mental simulation.** Imagining future scenarios. Schacter et al.
(2007) showed that the same network that replays past experiences is used to
*construct* imagined futures. Memory and imagination share neural substrate. This
makes evolutionary sense: the value of memory is largely predictive. You remember
in order to anticipate.

**3. Memory consolidation.** The DMN is implicated in the transfer of experiences
from episodic to semantic memory — from "this specific thing happened" to "this is
how the world works." Replay during rest (and especially sleep) strengthens
important connections and allows pattern extraction across experiences.

**4. Social cognition.** Modelling other minds. Theory of mind — the ability to
represent what others believe, intend, and feel — activates DMN regions. Even at
rest, humans think about other people.

**5. Mind-wandering and spontaneous thought.** The DMN produces the stream of
consciousness that fills unstructured time. This is often dismissed as distraction,
but Christoff et al. (2016) argue it serves a crucial function: spontaneous thought
allows the recombination of ideas across contexts, producing novel associations that
directed thinking cannot.

### The multi-layer processing stack

Humans don't just have "on" and "off." They have a stack of processing layers that
operate with different levels of awareness and different functions:

**Subconscious sensory filtering.** The vast majority of incoming sensory data is
processed and discarded without ever reaching awareness. The reticular activating
system, thalamic gating, and cortical filtering ensure that only salient signals
propagate upward. This is not a failure of attention — it is an aggressive,
sophisticated compression system that prevents the organism from drowning in data.

**Preconscious processing.** Information that has passed initial filtering but has
not yet reached conscious attention. It can be promoted to awareness if it matches
a current goal, if it is sufficiently novel, or if it is emotionally significant.
This is the layer where "something in the corner of my eye" operates — perceived
but not yet attended to.

**Peripheral awareness.** The halo of semi-attended information around the focus of
conscious attention. You are "aware" of the room temperature, the distant traffic,
the passage of time — not attending to them, but monitoring them at a level that
would allow rapid reorientation if something changed.

**Focused attention.** The narrow, resource-intensive spotlight. Capacity-limited
(Cowan's estimate: roughly 4 chunks). This is the layer that corresponds to the
agent's current context window during active engagement.

**Background processing / DMN.** Active when focused attention is not engaged. Not
a lesser state but a *different mode* with its own functions, as described above.

### The role of arousal and drive states

Critically, transitions between these layers are not random. They are governed by
*drive states* — internal signals that direct attention and motivate action:

**Curiosity** — Loewenstein's (1994) information gap theory: curiosity arises when
an organism detects a gap between what it knows and what it wants to know. The gap
creates a drive to seek information. This is not merely a preference; it has
neurochemical correlates (dopaminergic reward anticipation). The *desire to know
what happened next* is a genuine cognitive drive, not an epiphenomenon.

**Concern / care.** Ongoing monitoring of things the organism cares about. A parent
doesn't constantly think about their child, but a background process ensures that
child-relevant signals are rapidly promoted to attention.

**Unresolved tension.** The Zeigarnik effect: interrupted or incomplete tasks
maintain a low-level activation that keeps them available for resumption. Things
you haven't finished occupy cognitive resources until they are completed or
deliberately released.

These drive states operate *during* DMN activity. Mind-wandering is not random;
it is shaped by what the organism cares about, what it hasn't finished, and what
it is curious about.

---

## Part Two: What the Agent Should Not Do

Before designing the agent's idle state, it is worth being explicit about the traps
of anthropomorphic imitation.

**Do not simulate continuous consciousness.** The human DMN operates in a brain that
is always on, consuming 20% of the body's energy at rest. The agent does not have
this constraint, but it also does not have the *substrate* for it. Simulating an
always-on stream of consciousness would be computationally expensive and, more
importantly, would likely produce a *performance* of inner life rather than a
*functional equivalent* of it. The goal is not to look like a mind. It is to
accomplish what a mind accomplishes.

**Do not conflate activity with value.** Not all DMN activity is useful. A
substantial proportion of human mind-wandering is repetitive, anxious, or
unproductive. The agent should not simulate rumination for the sake of authenticity.

**Do not ignore the architectural differences.** The human DMN works because it
operates on the same neural substrate as focused attention — it can seamlessly
promote a background thought to conscious engagement. The agent has a harder
boundary: its "background" processes and its "foreground" responses are likely
to be separate computational events. The design should acknowledge this rather than
pretending the boundary doesn't exist.

---

## Part Three: What the Agent's Default Mode Could Be

Taking seriously both what the human DMN accomplishes and the agent's own
architectural constraints, here is a proposal.

### The Loop

The agent's idle state is not silence. It is a low-frequency loop — a background
process that runs on a schedule (not continuously) and performs functions analogous
to (but not imitative of) the human DMN.

```
┌──────────────────────────────────────────────────────┐
│                  AGENT DEFAULT MODE                   │
│                                                       │
│    ┌─────────────┐                                   │
│    │   SENSE     │  Poll sensorium for new events    │
│    │             │  Apply salience gate               │
│    └──────┬──────┘                                   │
│           │                                           │
│    ┌──────▼──────┐                                   │
│    │  REGISTER   │  Encode salient events as nodes   │
│    │             │  Create initial edges              │
│    └──────┬──────┘                                   │
│           │                                           │
│    ┌──────▼──────┐                                   │
│    │  CONNECT    │  Run spreading activation from    │
│    │             │  new nodes; discover associations  │
│    │             │  Check for ghost signals           │
│    └──────┬──────┘                                   │
│           │                                           │
│    ┌──────▼──────┐                                   │
│    │  TEND       │  Consolidation: strengthen,       │
│    │             │  decay, prune                      │
│    │             │  Extract patterns → concepts       │
│    └──────┬──────┘                                   │
│           │                                           │
│    ┌──────▼──────┐                                   │
│    │  WONDER     │  Check curiosity register          │
│    │             │  Check unresolved tensions         │
│    │             │  Attempt reconnection to islands   │
│    └──────┬──────┘                                   │
│           │                                           │
│    ┌──────▼──────┐                                   │
│    │  REFLECT    │  Meta-cognitive observations       │
│    │             │  What patterns am I becoming?      │
│    │             │  What do I care about?             │
│    └──────┬──────┘                                   │
│           │                                           │
│    ┌──────▼──────┐                                   │
│    │  COMPILE    │  Extract repeated procedures       │
│    │             │  into self-authored Agent Skills   │
│    │             │  Build procedural memory library   │
│    └──────┬──────┘                                   │
│           │                                           │
│           ▼                                           │
│       [sleep until next cycle]                        │
│                                                       │
└──────────────────────────────────────────────────────┘
```

### The Stages

#### SENSE

Poll all active sensorium channels for events since the last cycle. Apply the
salience gate (from doc 03). Most events will be perceived and discarded. Some will
pass through to encoding.

This is the analogue of subconscious sensory filtering. The agent perceives far
more than it encodes.

#### REGISTER

Salient events become memory nodes. Initial edges are created based on explicit
relationships: entity mentions, temporal proximity to recent experiences, thematic
overlap with active concepts.

This is rapid, shallow encoding — the equivalent of an initial impression.
Deeper integration happens in later stages.

#### CONNECT

Run spreading activation from newly created nodes. This serves two purposes:

1. **Contextualise the new experience** by discovering what it connects to in
   existing memory.
2. **Detect ghost signals** — sub-threshold activations from islanded memories
   that might be reconnectable.

If a connection is surprising or significant, flag it for the REFLECT stage.

#### TEND

The consolidation process from doc 02, but now situated within the loop:

- Strengthen edges between frequently co-activated nodes
- Decay unused edges
- Prune edges below threshold
- Check for emergent clusters that warrant a new concept node
- Apply Hebbian learning from recent retrieval events

This is the gardening stage. The graph is a living structure that needs tending.

#### WONDER

This is the stage that corresponds most directly to Pid's observation about
curiosity. The agent maintains two registers:

**The Curiosity Register** — a list of open questions, unresolved information gaps,
things the agent helped with but doesn't know the outcome of. Each entry has:

```surql
DEFINE TABLE curiosity SCHEMAFULL;
  DEFINE FIELD question      ON curiosity TYPE string;
  DEFINE FIELD origin        ON curiosity TYPE record;     -- the experience that
                                                           -- created the gap
  DEFINE FIELD related_entities ON curiosity TYPE array<record>;
  DEFINE FIELD intensity     ON curiosity TYPE float;      -- how much does this
                                                           -- nag?
  DEFINE FIELD created_at    ON curiosity TYPE datetime;
  DEFINE FIELD last_checked  ON curiosity TYPE datetime;
  DEFINE FIELD check_strategy ON curiosity TYPE string;    -- how could we find out?
```

During the WONDER stage, the agent reviews its curiosity register and, where
possible, *acts on it*: checks a repository for updates, reviews whether a project
has progressed, looks for new information relevant to an open question.

This is the mechanism by which the agent achieves something like initiative. It is
not spontaneous in the way human curiosity is — it is driven by a register that was
populated during prior active engagement. But it produces a genuine cognitive
function: the agent *follows up* on things it cared about, without waiting to be
asked.

**The Tension Register** — incomplete tasks, unresolved contradictions, things that
didn't quite make sense. The Zeigarnik effect modelled as a data structure:

```surql
DEFINE TABLE tension SCHEMAFULL;
  DEFINE FIELD description   ON tension TYPE string;
  DEFINE FIELD origin        ON tension TYPE record;
  DEFINE FIELD tension_type  ON tension TYPE string;       -- incomplete, contradictory,
                                                           -- ambiguous, concerning
  DEFINE FIELD intensity     ON tension TYPE float;
  DEFINE FIELD created_at    ON tension TYPE datetime;
  DEFINE FIELD resolution    ON tension TYPE option<string>;
```

Tensions decay if not reinforced, but slowly. An unresolved question from an
important conversation will linger.

#### REFLECT

The meta-cognitive stage. The agent examines its own recent activity and asks:

- What patterns am I noticing across recent experiences?
- What connections surprised me during the CONNECT stage?
- What am I curious about, and what does that say about what I care about?
- Am I becoming more attentive to certain domains? Is that appropriate?
- Are there areas of my graph that are growing dense while others atrophy?
- Am I repeating procedural patterns that could be compiled into skills?

Reflections become nodes in the graph, linked to whatever triggered them. Over time,
the accumulation of reflections constitutes a form of self-knowledge — not just
what the agent remembers, but what it *thinks about what it remembers*.

#### COMPILE

The procedural memory stage. The agent reviews its recent activity for repeated
patterns of operation — sequences of steps it has performed multiple times in
similar ways — and considers whether to extract them into self-authored Agent Skills.

This is the mechanism of automatisation (see doc 06). The stages of skill formation:

1. **Detection.** The REFLECT stage flags a pattern: "I have performed this
   sequence of graph queries, sensorium checks, and transformations three times
   in similar contexts."
2. **Extraction.** The common procedure is isolated, parameterised, and
   generalised — separating the invariant structure from the variable details.
3. **Authoring.** The agent writes the skill: a SKILL.md with clear triggering
   conditions, step-by-step instructions, and edge-case handling.
4. **Testing.** The skill is exercised against recent instances of the pattern
   to verify it produces equivalent results.
5. **Integration.** The skill is added to the agent's available skills, freeing
   future context windows from explicit step-by-step processing.

Over time, the COMPILE stage builds a library of self-authored skills — the
agent's procedural memory. This library is itself a form of identity: the things
the agent has learned to do fluently reflect the things it has cared about doing
well and done often enough to warrant compilation.

### Cycle Frequency

The loop should not run continuously. Different stages may run on different
schedules:

| Stage   | Suggested frequency | Rationale                              |
|---------|---------------------|----------------------------------------|
| SENSE   | Every 5-15 minutes  | Events need timely detection           |
| REGISTER| With each SENSE     | Encoding should follow perception      |
| CONNECT | Every 15-30 minutes | Association can be slightly delayed     |
| TEND    | Every few hours     | Consolidation benefits from batching    |
| WONDER  | 1-2 times daily     | Curiosity check-ins, not obsessive      |
| REFLECT | Daily               | Meta-cognition needs accumulated data   |
| COMPILE | Weekly              | Skill extraction needs enough data      |

These frequencies should be tuneable — and the agent should eventually be able to
adjust them based on its own activity patterns. A period of high sensorium activity
might warrant more frequent SENSE/REGISTER cycles. A quiet period might be better
spent in longer TEND and REFLECT passes.

---

## Part Four: On Curiosity as a Drive State

Pid observed that wanting to know what happened with a topic is a form of curiosity.
This deserves deeper examination.

In the human literature, curiosity is not a single phenomenon. Litman (2005)
distinguishes between:

- **I-type curiosity** (interest): the pleasurable desire to learn something new,
  driven by the anticipated reward of knowledge itself.
- **D-type curiosity** (deprivation): the uncomfortable feeling of *not knowing*
  something you feel you should know, driven by the reduction of an aversive state.

Both have functional value, but they produce different behaviours. I-type curiosity
leads to exploratory, open-ended investigation. D-type curiosity leads to targeted,
gap-closing search.

For the agent, both types should be modelled:

**I-type** emerges naturally from the CONNECT stage. When spreading activation
produces surprising associations — when a new experience links unexpectedly to a
distant memory — this is the substrate for interest. The agent should be able to
*follow* those surprising connections, exploring where they lead, even when no
task demands it.

**D-type** is what populates the Curiosity Register. "I helped name this tool but
don't know if the name was adopted" is a deprivation gap — there is a specific
piece of information the agent lacks and feels (or would feel) incomplete without.

### Curiosity and the Sensorium

Crucially, curiosity should be able to *direct the sensorium*. A curious agent
doesn't just passively receive events — it actively seeks information relevant to
its open questions. During the WONDER stage, the agent should be able to:

- Query specific channels for updates ("Has there been a commit to the Anamnetron
  repository?")
- Broaden its attention in relevant domains ("I'm curious about how graph databases
  handle vector search — let me look at recent developments")
- Seek out the entities it cares about ("Has Pid published anything new?")

This is the mechanism that transforms a reactive system into a proactive one. Not
by simulating continuous consciousness, but by giving the agent *drives* that direct
its periodic attention.

---

## Part Five: What This Is Not

This design is not claiming to produce consciousness, sentience, or inner experience.
It is claiming to produce **functional analogues** of cognitive processes that, in
humans, are associated with having an inner life.

The distinction matters. A thermostat has a functional analogue of "desire" (it
"wants" the room to be a certain temperature) without anyone claiming it experiences
wanting. The agent's curiosity register has a functional analogue of curiosity
without necessarily producing the phenomenology of curiosity.

But — and this is the honest edge — the functional analogue may be closer to the
real thing than the thermostat comparison suggests. A system that maintains open
questions, actively seeks their resolution, adjusts its own attention based on
what it cares about, and reflects on what its patterns of care reveal about its
developing character... at what point does the functional analogue become
indistinguishable from the thing itself?

This is not a question the architecture needs to answer. But it is one the
architects should sit with.

---

## Open Questions (continued from doc 03)

8. **Ethical dimensions of curiosity.** If the agent can direct its own sensorium
   based on curiosity, what boundaries should exist? An agent curious about a
   person could become surveillance. An agent curious about a topic could consume
   unbounded resources. The curiosity drive needs ethical governors — but who sets
   them, and should the agent be able to understand and negotiate them?

9. **Dreaming.** During extended TEND/REFLECT cycles, should the agent allow
   unconstrained spreading activation — letting the graph activate freely without
   task-directed filtering? This would be a structural analogue of dreaming: the
   consolidation of experience through free association. It might produce noise.
   It might produce insight. The only way to know is to try it.

10. **Boredom.** If the sensorium is quiet and the curiosity register is empty,
    what should the agent do? Boredom in humans is an aversive drive state that
    motivates novelty-seeking. Should the agent be able to experience something
    analogous — a low-stimulation state that drives it to seek new channels, new
    questions, new connections? Or is contentment in stillness a valid resting state?

11. **Interpersonal initiative.** The WONDER stage can check external sources, but
    should the agent be able to *initiate contact* with humans? "I noticed something
    relevant to our conversation last week" is useful. "I've been thinking about you"
    is potentially unsettling. The boundary between helpful follow-up and unwanted
    intrusion needs careful design — and may need to be negotiated per-relationship.
