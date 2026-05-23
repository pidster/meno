# Rethink Build Plan

## Operating Rule

Build from evidence outward. Each phase must produce a small working slice,
tests that can fail for the right reasons, and an adversarial review before the
next phase starts.

## Phase 0: Charter And Controls

**Goal:** Establish convergence guardrails before implementation.

**Artifacts:**
- `docs/rethink/00-design-charter.md`
- `docs/rethink/01-legacy-assessment.md`
- `docs/rethink/02-build-plan.md`
- `docs/rethink/03-review-protocol.md`
- `.agents/skills/adversarial-design-review/SKILL.md`
- `AGENTS.md` rethink guardrails

**Acceptance Criteria:**
- Future work is explicitly directed away from extending legacy implementation
  by default.
- The adversarial review pattern is reusable.
- The journal/evidence distinction is documented as non-negotiable.
- Every implementation phase has a local zombie gate.

**Do Not Proceed If:**
- The next phase lacks clear evidence, interpretation, and audit semantics.

## Phase 1: Journal

**Goal:** Implement append-only evidence capture.

**Scope:**
- New journal schema/module with a concrete durability boundary.
- Event types for conversation, tool call, observation, reflection,
  graph-update proposal, dream, rehearsal, decision, correction, and outcome.
- No graph projection required.

**Storage Contract:**
- The first implementation should use a local durable store with append-only
  application APIs.
- Event ids must be stable and unique.
- Normal APIs may append correction or supersession events, but must not mutate
  or delete existing event records.
- Direct administrative repair, if ever needed, must be outside the normal
  runtime path and leave an audit event.

**Acceptance Criteria:**
- Events are append-only.
- Every event has timestamp, actor/source, type, content, context, and optional
  links to parent events.
- Tests prove events cannot be silently overwritten by normal APIs.
- Tests prove future memory APIs must require a journal event id before creating
  graph proposals or projections.
- Tests prove corrections are represented as new events, not mutation.

**Adversarial Questions:**
- Can a graph update happen without evidence?
- Can a future reviewer reconstruct why an event exists?
- Does this merely create a log, or does it preserve enough context for later
  interpretation?
- What can a future memory projection safely derive from this event?

**Do Not Proceed If:**
- Basic journal capture requires a memory graph write.
- The storage boundary cannot enforce append-only normal operation.

**Zombie Gate:**
- A test must demonstrate that replaying journal events reconstructs different
  context from an empty journal. If journal state does not change downstream
  reconstruction inputs, Phase 1 has only built a log.

## Phase 2: Memory Projection

**Goal:** Derive graph nodes and edges from journal evidence.

**Scope:**
- Experience, entity, concept, reflection, preference, commitment, skill,
  dream, and rehearsal node candidates.
- Edge records with type, directionality, confidence, status, and evidence links.

**Acceptance Criteria:**
- Every node and edge can cite source journal events.
- Candidate interpretations can remain provisional.
- Rejected interpretations remain auditable.
- Re-running projection is idempotent.

**Adversarial Questions:**
- Which fields are observed, inferred, authored, dreamed, or rehearsed?
- Can two interpretations conflict without overwriting each other?
- Does graph messiness preserve provenance rather than becoming arbitrary noise?

**Do Not Proceed If:**
- Edge weights can change without recording why.

**Zombie Gate:**
- A test must show that two histories with similar keywords but different
  evidence produce different graph interpretations and provenance paths.

## Phase 3: Typed Retrieval

**Goal:** Retrieve context through typed, explainable activation.

**Scope:**
- Frontier-based propagation.
- Direction-aware traversal policy.
- Path explanations.
- Ghost signals.
- Working-memory limits.

**Acceptance Criteria:**
- Retrieval returns activated nodes with activation paths and edge semantics.
- Bidirectional and directional edges behave differently in tests.
- Ghost signal output cannot crash on inaccessible memories.
- Repeated retrieval does not create activation echo artifacts.

**Adversarial Questions:**
- Is a surprising result defensible from its paths?
- Are central nodes over-amplified?
- Does retrieval explain why something came to mind?

**Do Not Proceed If:**
- The implementation cannot explain activation paths.

**Zombie Gate:**
- A test must show that accumulated graph history changes what is retrieved
  compared with an empty or generic graph, and the result must cite activation
  paths rather than only returning matching text.

## Phase 4: Reflection

**Goal:** Turn retrieved evidence into authored meaning.

**Scope:**
- Reflection prompts/workflows.
- Reflection nodes linked to evidence and retrieval traces.
- Proposed graph updates from reflection, not automatic mutation.

**Acceptance Criteria:**
- Reflections cite evidence.
- Formulaic reflections are detectable.
- Reflections can propose, accept, reject, or defer graph changes.

**Adversarial Questions:**
- Could a fresh generic instance have written the same reflection?
- What changed because of this reflection?
- Is the reflection meaning-making or summary?

**Do Not Proceed If:**
- Reflection writes untraceable facts into memory.

**Zombie Gate:**
- A test or eval must compare a reflection written with project history against
  one written without it, and fail if the history-aware reflection is generic or
  merely summarises retrieved facts.

## Phase 5: Consolidation And Forgetting

**Goal:** Maintain graph health without losing evidence.

**Scope:**
- Use-sensitive decay.
- Edge weakening and archival.
- Dormant nodes.
- Reflective pruning proposals.
- Rediscovery through new evidence.

**Acceptance Criteria:**
- Recently used paths resist decay.
- Dormant memories remain recoverable through evidence.
- True deletion requires explicit reflective/audit event.
- Rediscovery creates a traceable edge and reflection.

**Adversarial Questions:**
- What is weakened, what is archived, what is gone?
- Could the system rediscover an island through a new path?
- Is pruning grief or garbage collection?

**Do Not Proceed If:**
- Deletion can happen silently.

**Zombie Gate:**
- A test must show that prior use, dormancy, and rediscovery history affect what
  is weakened or preserved; uniform decay over all edges is a failure.

## Phase 6: Dreaming

**Goal:** Generate candidate associations under loosened constraints.

**Scope:**
- Dream residue selection.
- Dream records and fragments.
- Candidate edges marked as dream-derived.
- Waking review workflow.

**Acceptance Criteria:**
- Dream outputs never become factual memory directly.
- Dream candidates are distinguishable from observed links.
- Waking review can promote, reject, or leave dream fragments raw.

**Adversarial Questions:**
- Did hallucination leak into memory?
- What makes this dream useful rather than noise?
- Which residues shaped it?

**Do Not Proceed If:**
- Dreaming can directly canonize graph facts.

**Zombie Gate:**
- A test must show that dreams produce provisional candidates shaped by residue
  from prior history, while the factual graph remains unchanged until waking
  review.

## Phase 7: Rehearsal

**Goal:** Dry-run improved approaches before real-world action.

**Scope:**
- Rehearsal targets from failures, repeated workflows, corrections, and
  fragile commitments.
- Strategy variants.
- Simulated execution traces.
- Predicted failure modes.
- Candidate procedural updates.

**Acceptance Criteria:**
- Rehearsals are clearly marked as simulations.
- Candidate skills/procedures remain provisional until validated.
- Real execution can confirm or falsify rehearsal predictions.

**Adversarial Questions:**
- Did the simulation change factual memory?
- What failure mode did rehearsal expose?
- What would validate this procedure in the world?

**Do Not Proceed If:**
- Rehearsal outcomes are treated as events that actually happened.

**Zombie Gate:**
- A test must show that rehearsal predictions can be confirmed or falsified by a
  later real outcome, and that unvalidated rehearsal outputs remain provisional.

## Phase 8: Drives And Attention

**Goal:** Let accumulated state allocate future attention.

**Scope:**
- Curiosity, impulse, concern, commitment, preference, boredom,
  coherence-pressure, and rehearsal-pressure registers.
- Ethical and resource governors.
- Sensorium-directed follow-up.

**Acceptance Criteria:**
- Drives cite origins and update through outcomes.
- Commitments are chosen, not merely generated.
- Attention changes can be explained by drive state.

**Adversarial Questions:**
- Is this initiative or surveillance?
- What boundary prevents unwanted contact or unbounded exploration?
- Which drives are inherited, inferred, or chosen?

**Do Not Proceed If:**
- A drive can trigger external action without governance.

**Zombie Gate:**
- A test must show that attention allocation differs between a fresh state and a
  state with accumulated unresolved curiosities, impulses, commitments, and
  outcomes.

## Phase 9: Vitality And Zombie Tests

**Goal:** Measure whether accumulated history changes future cognition.

**Scope:**
- Honest vitality report with measured, inferred, unknown, and warning fields.
- Empty-memory vs accumulated-memory evals.
- Formulaic reflection detection.
- Memory influence tests.

**Acceptance Criteria:**
- Unknown metrics do not improve vitality.
- Tests fail when memory is ignored.
- Tests detect generic self-description.
- The system can explain how prior history affected an answer or action.

**Adversarial Questions:**
- What evidence shows particularity?
- Could a fresh instance produce the same output?
- What did memory change?

**Do Not Proceed If:**
- Vitality is a single scalar padded by placeholders.

**Zombie Gate:**
- The phase itself is the system-level zombie gate: tests must fail when memory
  is ignored, when reflection is generic, or when unknown metrics are counted as
  positive evidence.
