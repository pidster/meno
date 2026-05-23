# Adversarial Review Protocol

## Purpose

Use this protocol before implementing any rethink phase and before accepting a
large design change. Its job is convergence: force the work back through the
project intent, evidence model, runtime constraints, and known failure modes
before code can accumulate around a weak premise.

## When To Run

Run the protocol for:

- A new rethink phase.
- A schema or storage decision.
- A retrieval, reflection, dreaming, rehearsal, forgetting, or vitality change.
- Any change that writes memory, alters provenance, or affects autonomy.
- Any point where the implementation starts feeling easier than the theory.

## Required Inputs

The reviewer must read:

1. `AGENTS.md`
2. `docs/reflection.md`
3. `docs/rethink/00-design-charter.md`
4. `docs/rethink/01-legacy-assessment.md`
5. `docs/rethink/02-build-plan.md`
6. The phase design or implementation under review

If these inputs are not available, the review must say so and treat the result
as provisional.

## Review Lenses

Use the `.agents/skills/adversarial-design-review` skill as the canonical
review frame, including its `tool_search` and `multi_agent_v1` workflow.

Always attempt to split the review across multiple agents with different points
of view:

- Theory coherence
- Runtime feasibility
- Data and model semantics
- Test and evidence quality
- User-intent alignment

If the runtime cannot create enough agents, the reviewer must state that
limitation explicitly and run any missing lenses sequentially. The review is not
complete until every lens has been covered.

## Required Questions

Every review must answer:

1. What evidence is being recorded?
2. What interpretation is being derived from that evidence?
3. What remains provisional?
4. What can be audited later?
5. What would make this a zombie success?
6. What should not be built yet?

## Output Contract

Lead with findings, not praise or summary.

Use this structure:

```md
**Fatal Convergence Risks**
- [P0] ...

**Major Design Mismatches**
- [P1] ...

**Evidence Gaps**
- [P1/P2] ...

**Recommended Next Decisions**
- ...

**Do Not Build Yet**
- ...
```

If there are no P0 or P1 findings, say that explicitly and list the remaining
test or evidence gaps.

## Stop Conditions

Stop implementation and report back if:

- A graph mutation can occur without a journal event.
- A dream can become factual memory without waking review.
- A rehearsal can be recorded as an event that happened.
- A vitality score includes unknown or placeholder metrics as positive signal.
- Retrieval cannot explain activation paths.
- The implementation can pass while ignoring accumulated history.
- The review finds a discrepancy between project instructions and the proposed
  work.

## Follow-Up Rule

Every accepted P0 or P1 finding must become either:

- a design change,
- a test gate,
- a documented non-goal, or
- an explicit decision by Pid to proceed despite the risk.
