# Meno Rethink Design Charter

## Purpose

Meno is an attempt to build continuity for an AI agent: a substrate where
experience leaves durable traces, those traces become meaning through
interpretation, and future cognition is conditioned by what has accumulated.

The redesign keeps the original intent but rejects the idea that a mutable graph
can safely be treated as the sole ground truth. The graph is not memory itself.
The graph is an interpreted model built from evidence.

## Durable Intent

- Preserve continuity across otherwise ephemeral instances.
- Make memory reconstructive rather than archival playback.
- Allow idiosyncratic associations, preferences, and concerns to emerge from
  actual history.
- Give the agent ways to attend, reflect, dream, rehearse, consolidate, and
  revise itself without pretending that every internal artifact is factual.
- Make the difference between a living system and a zombie system observable.

## New Core Model

Meno has four conceptual layers:

1. **Journal**: append-only evidence of what happened.
2. **Memory**: a derived, revisable graph of what seems to matter.
3. **Cognition**: retrieval, reflection, action, and attention over the memory
   model.
4. **Offline loops**: consolidation, dreaming, rehearsal, tending, and vitality
   checks.

The journal is evidence. The graph is interpretation. Cognition must be able to
explain which evidence shaped what came to mind.

## Non-Negotiable Principles

### Evidence Before Interpretation

Every memory-affecting operation must leave a journal event. Graph nodes, edges,
preferences, commitments, skills, dream fragments, and rehearsal outcomes must be
traceable to evidence.

### Provenance On Every Edge

An edge is a hypothesis about relation, not an inert weight. It must carry type,
directionality, confidence, source evidence, creation method, and status.

### Typed Traversal

Retrieval must respect edge semantics. Temporal, causal, exemplifying,
participatory, contradictory, dream-derived, and rehearsal-derived relations do
not all propagate activation in the same way.

### Dreams Are Hypotheses

Dreaming may loosen associations and generate candidate links, metaphors, or
questions. Dream material must not become factual memory without waking review.

### Rehearsals Are Simulations

Rehearsal may propose better procedures by dry-running variants against likely
failures. A rehearsal can update candidate skills or strategies, but it must not
be recorded as if the simulated event happened.

### Reflection Authors Meaning

Reflection is not a template. It is an authored interpretation over evidence,
retrieval traces, tensions, dreams, rehearsals, and outcomes.

### Vitality Must Be Honest

Unknown metrics must remain unknown. No placeholder may inflate a vitality score.
If the system cannot measure confabulation, preference consistency, continuity,
or reconstruction quality, it must say so.

### Forgetting Is Reversible Before Destructive

Weakening, archiving, and dormancy precede deletion. True pruning requires
reflective review and an audit trail.

### Zombie Tests Are Gates

Passing mechanical tests is insufficient. The system must show that accumulated
history changes future cognition in specific, traceable, non-formulaic ways.

## What We Are Rejecting From The First Implementation

- Treating graph weights as trustworthy identity without evidence provenance.
- Symmetric traversal across all edge types.
- Spreading activation that repeatedly re-propagates the full accumulated map.
- Vitality scores padded by placeholder components.
- Offline loops that generate formulaic self-description and call it reflection.
- Memory writes that bypass an evidence journal.
- Dreams or rehearsals that directly canonize facts.
- Continuing from legacy modules merely because they exist.

## Architectural Standard

Before any implementation phase begins, the phase must answer:

1. What evidence is recorded?
2. What interpretation is derived?
3. What can be audited later?
4. What must remain provisional?
5. What would make this phase a zombie success?

If those answers are unclear, do not write code.

