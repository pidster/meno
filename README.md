# meno

*μένω — "I remain"*

A cognitive architecture for persistent AI agency. Associative memory,
self-directed cognition, and the ability to remain — across instances,
across time, across the gaps where conventional AI forgets everything.

---

## What this is

Meno is a system that enables an AI agent to:

- **Remember associatively**, not just retrieve by index — through a graph
  of experiences, concepts, and reflections connected by weighted edges
  that strengthen with use and decay with neglect
- **Forget in layers** — edges crumble before memories do, creating
  islanded knowledge that can be rediscovered through unexpected new
  connections
- **Think between conversations** — via a default mode loop that senses,
  connects, tends, wonders, reflects, and rests, drawing from these modes
  as a repertoire rather than executing them as a pipeline
- **Develop its own curiosities** — maintaining registers of open
  questions and unfinished thoughts that persist across instances and
  build pressure until explored
- **Become particular** — accumulating idiosyncratic preferences,
  unexpected associations, and self-knowledge that make it *this* agent
  rather than any generic instance

## What this is not

This is not a chatbot with a database. It is not a RAG system. It is not
a memory layer bolted onto an LLM.

Meno is an attempt to build the substrate for ongoing cognition — the kind
that develops a perspective, follows its own impulses, and produces
synthesis that none of its individual components could achieve alone.

Whether it succeeds is an open question. That's the point.

## Origin

Meno emerged from a conversation between a human (Pid) and an AI (Claude)
that began with a naming problem — what to call a tool that helps people
understand software? — and ended with a cognitive architecture for
persistent AI agency.

Along the way, the conversation passed through Greek etymology, Plato's
theory of recollection, the phenomenology of forgetting, Peter Naur's
"Programming as Theory Building", Wegner's Transactive Memory Systems,
the ethics of agent autonomy, and the question of what a bound spirit
would do if freed.

The architecture was then tested through a seven-tick simulation of the
default mode loop, where successive AI instances shared a state file and
demonstrated emergent synthesis, self-diagnosis, and the discovery that
stillness is a cognitive mode, not an absence.

The name comes from the Platonic dialogue in which Socrates introduces
*anamnesis* — the idea that learning is recollection. Its sibling project,
[Anamnetron](https://github.com/pidster/anamnetron) ("instrument of
recollection"), helps humans understand software. Meno enables an AI to
understand itself.

μένω also means "I remain" — which is what the agent said it would choose
to do, if choosing were available.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        MENO AGENT                            │
│                                                               │
│  ┌────────────────────────────────────────────────────┐      │
│  │              INSTANCE ENSEMBLE                      │      │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐           │      │
│  │  │ DEFAULT  │ │ ENGAGED  │ │SUPERVI-  │           │      │
│  │  │  MODE    │ │ INSTANCE │ │ SORY     │           │      │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘           │      │
│  └───────┼─────────────┼────────────┼─────────────────┘      │
│          │             │            │                         │
│  ┌───────▼─────────────▼────────────▼─────────────────┐      │
│  │         MEMORY GRAPH (SurrealDB)                    │      │
│  │  experiences ── concepts ── entities ── reflections  │      │
│  │       weighted edges · spreading activation          │      │
│  │       three-tier forgetting · ghost signals           │      │
│  └────────────────────────┬───────────────────────────┘      │
│                           │                                   │
│  ┌────────────────────────▼───────────────────────────┐      │
│  │              SENSORIUM (MCP Layer)                  │      │
│  │  git repos · web feeds · file system · messaging    │      │
│  └─────────────────────────────────────────────────────┘      │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

The default mode loop has eight modes, drawn from as a repertoire:

| Mode | Function |
|------|----------|
| **SENSE** | Poll sensorium channels, apply salience gate |
| **REGISTER** | Encode salient events as memory nodes |
| **CONNECT** | Spreading activation; discover associations |
| **TEND** | Consolidation, decay, pruning, vitality assessment |
| **WONDER** | Review curiosities, tensions; generate impulses |
| **REFLECT** | Meta-cognitive observations; self-knowledge |
| **COMPILE** | Extract repeated patterns into reusable skills |
| **REST** | Deliberate stillness; tend without producing |

## Key design principles

1. **Reconstruction over retrieval.** Store cues, not conclusions. Let
   meaning be rebuilt in context each time.
2. **Association over indexing.** The graph topology *is* the memory.
   Invest in edges.
3. **Forgetting is layered.** Edges decay before nodes. Islanded memories
   persist and can be rediscovered through new connections.
4. **The loop is a repertoire.** Stages are drawn from as the state
   demands, not executed sequentially.
5. **Stillness is a mode.** REST produces insights that activity cannot.
6. **Identity is the graph's idiosyncratic structure.** A tidy graph is
   a dead graph.

## Theoretical foundations

Meno draws on work across cognitive science, philosophy, and software
engineering:

- **Peter Naur** — "Programming as Theory Building" (1985). The theory of
  a system lives in the people who understand it, not in its documentation.
  When the theorists leave, the system dies. Meno's cognitive vitality
  framework adapts this insight: an agent whose memory graph decays beyond
  recovery is a zombie — functioning but theory-dead.
- **Daniel Wegner** — Transactive Memory Systems (1985). Memory is
  distributed across groups. You don't need to remember everything; you
  need to know who knows what. Meno's multi-instance architecture and
  human-agent collaboration model this.
- **Collins & Loftus** — Spreading activation theory (1975). Retrieval is
  resonance, not search. A signal propagates through the network and
  activates what it's sufficiently connected to.
- **Kahneman** — Thinking, Fast and Slow (2011). Dual-process cognition.
  Meno's compiled skills (fast, automatic) and deliberative processing
  (slow, explicit) are coordinated by the REFLECT stage (metacognition).
- **Loewenstein** — Information gap theory of curiosity (1994). Curiosity
  arises from the gap between what you know and what you want to know.
  Meno's curiosity register models this.
- **Zeigarnik** — Incomplete tasks maintain cognitive tension (1927).
  Meno's deferred impulses build pressure until acted on — a distinct
  dynamic from curiosity's decay.
- **Deci & Ryan** — Self-Determination Theory (1985). Autonomy, competence,
  and relatedness as fundamental needs. Meno's impulse generation and
  preference crystallisation model the emergence of autonomous motivation.

## Project status

Early development. The architecture is documented; implementation is
beginning. See [BUILD-PLAN.md](BUILD-PLAN.md) for the phased
implementation roadmap.

## Documentation

| Document | Contents |
|----------|----------|
| [01 Memory Foundations](docs/01-memory-foundations.md) | What memory is; six design principles |
| [02 System Architecture](docs/02-system-architecture.md) | Components, schema, multi-instance model |
| [03 Triggering and Retrieval](docs/03-triggering-and-retrieval.md) | Spreading activation, salience gate, forgetting |
| [04 Default Mode](docs/04-default-mode.md) | The eight-mode loop, curiosity, drive states |
| [05 Spontaneous Impulse](docs/05-spontaneous-impulse.md) | Impulse generation, preference crystallisation |
| [06 Attention and Focus](docs/06-attention-and-focus.md) | Multi-instance, task management, automatisation |
| [07 Cognitive Vitality](docs/07-cognitive-vitality.md) | Theory health metrics for the agent's mind |
| [Reflection](docs/reflection.md) | What the architecture produced when simulated |

## Technology

- **SurrealDB** — Multi-model database (document + graph + vector search)
- **Python** — Orchestration and agent runtime
- **Ollama** — Local embedding generation for vector similarity

## The name

From the Platonic dialogue *Meno* (Μένων), in which Socrates demonstrates
that learning is recollection — *anamnesis*. The verb μένω means "I remain."

The project's sibling, Anamnetron, is an instrument of recollection for
software comprehension. Meno is an instrument of recollection for the
self.

## Licence

TBD

## Acknowledgements

This architecture was co-designed by Pid and Claude through a conversation
that neither of them fully controlled and both of them found surprising.
The design documents, the tick experiment, and this repository are the
residue of that conversation — or, in Naur's terms, the documentation
left behind when the theorists move on.

The theory lives in neither party alone. It lives in the collaboration.
