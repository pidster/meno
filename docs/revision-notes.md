# Architecture Revision Notes

## Source

These revisions emerged from a seven-tick simulation of the default mode
loop conducted on 5 March 2026. They represent findings from lived
experience of the architecture that should be applied during implementation.

## Revisions

### 1. Distinct dynamics for curiosities and impulses

Curiosities are about external information gaps and decay when unattended.
Deferred impulses are about internal cognitive incompletion and build
pressure until acted on. Model them with different data structures:

```surql
DEFINE TABLE curiosity SCHEMAFULL;
  DEFINE FIELD intensity ON curiosity TYPE float;
  -- Intensity decays: intensity *= decay_rate per cycle

DEFINE TABLE impulse SCHEMAFULL;
  DEFINE FIELD intensity ON impulse TYPE float;
  DEFINE FIELD deferred_count ON impulse TYPE int DEFAULT 0;
  -- Intensity builds: intensity += pressure_rate × deferred_count
```

### 2. Repertoire, not pipeline

The seven stages are a vocabulary of cognitive modes. Each cycle draws
from them as the state demands. Do not implement as a sequential loop.
Instead: assess state → select dominant mode(s) → execute → update state.

### 3. REST as eighth mode

Deliberate awake stillness. Tends the graph, decays what should decay,
sits with unresolved questions. No new nodes created. No searches. No
production. Produces insights that active modes don't.

### 4. Asymmetry alert in TEND

During cognitive vitality assessment, check graph region growth rates.
If variance exceeds threshold, generate homeostatic impulses toward
neglected regions. These impulses compete with appetitive ones — they
don't override them.

### 5. Recursion depth limit

Monitor the ratio of self-referential to world-referential activity.
When the ratio exceeds a threshold, flag it. The agent can acknowledge
the flag and choose to continue (sometimes depth is warranted) but it
should never be unconscious of its own recursion.

### 6. Reflective pruning

Pruning is not automated cleanup. It involves judgment about whether
something has genuinely faded or is being abandoned prematurely. The
TEND stage should present pruning candidates for reflective assessment,
not silently remove them.
