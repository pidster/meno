# Legacy Implementation Assessment

## Status

The existing implementation is a prototype and evidence source, not the
foundation for the redesign. It validated that the original mechanisms can be
made to run, but it also showed how easily a system can pass tests while
remaining generic or misleading.

## Preserve Conceptually

- Reconstructive memory: store cues and rebuild meaning in context.
- Associative graph: topology matters more than keyword search.
- Layered forgetting: paths should weaken before memories disappear.
- Ghost signals: the system should notice almost-remembered material.
- Curiosity and impulse as distinct drives.
- Reflection as first-class memory.
- REST as deliberate stillness rather than absence of work.
- Task reconstruction as activation over current graph state, not snapshot load.
- Self-authored skills as procedural memory from repeated behavior.
- Cognitive vitality as a theory-health frame.

## Do Not Reuse Mechanically Without Redesign

- `src/retrieval.py`: current spreading activation re-propagates accumulated
  activation and erases edge direction.
- `src/forgetting.py`: decay is uniform rather than use-sensitive; vitality
  includes placeholder metrics.
- `src/modes.py`: default-mode output is prone to formulaic reflection and
  summary-key drift.
- `src/agent.py`: duplicate tool surface and legacy Anthropic runner should not
  be the primary integration path.
- `src/mcp_server.py`: useful as a direction, but currently duplicates agent
  logic and inherits retrieval/reporting defects.
- Phase tests: useful smoke tests, but not proof of non-zombie cognition.

## Known Failure Modes

### Plausible Activation From Bad Math

Repeated propagation from the full activation map can make central nodes look
meaningful because the algorithm echoes itself.

### Semantic Flattening

Treating all relations as bidirectional causes temporal, causal,
participatory, and exemplifying links to behave like generic association.

### Memory Without Evidence

Graph mutations currently become memory without a durable journal of why they
exist or whether they were inferred, dreamed, rehearsed, or observed.

### Rediscovery Not In The Loop

Embedding reconnection exists as a mechanism but is not part of ordinary memory
formation.

### Vitality Theatre

Placeholder scores can make the graph appear healthier than it is.

### Formulaic Reflection

A loop can create reflection nodes regularly without producing real
self-knowledge.

### Runtime Fragility

The current environment/configuration path depends on live SurrealDB, Ollama,
and Python packages that are not enforced by reproducible setup checks.

## Migration Rule

Legacy code may be referenced for lessons and test cases. It should not be
extended during the rethink unless a phase explicitly adopts and rewrites a
bounded piece with new evidence/provenance semantics.

