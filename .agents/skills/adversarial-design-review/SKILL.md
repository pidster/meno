---
name: adversarial-design-review
description: Use when reviewing a design, architecture, implementation plan, or substantial code change for convergence risks, theory mismatches, runtime feasibility, data/model semantics, and evidence quality. Especially useful before implementing major phases or when the user asks for adversarial review, specialist review, or standardised review patterns.
---

# Adversarial Design Review

Use this skill to review whether work is likely to converge on the intended
system rather than pass local tests while drifting from the design.

## Review Lenses

Run the review through these lenses using multiple agents with different points
of view. Assign one lens per specialist agent whenever possible. If the runtime
cannot create enough agents, state that limitation explicitly and cover the
missing lenses yourself rather than skipping them.

1. **Theory Coherence**
   - Does the work preserve the stated intent?
   - Does it confuse evidence, interpretation, simulation, and fact?
   - Does it create a zombie success: mechanically correct but conceptually dead?

2. **Runtime Feasibility**
   - Can it run end to end in the actual environment?
   - Are dependencies, services, config, startup, and failure paths explicit?
   - Are there duplicated surfaces that can drift?

3. **Data And Model Semantics**
   - Are schemas honest about provenance, confidence, status, and direction?
   - Do algorithms preserve the meaning of the data they operate on?
   - Can every inferred structure cite evidence?

4. **Test And Evidence Quality**
   - Do tests prove the central claim or only smoke-test mechanics?
   - Would tests catch known failure modes?
   - Are placeholder metrics or synthetic outputs being treated as evidence?

5. **User-Intent Alignment**
   - Does this support the collaborator's actual goal?
   - Are autonomy, initiative, privacy, and resource boundaries explicit?
   - What should not be built yet?

## Tool Workflow

Use the multi-agent tools, not an informal simulation, when they are available.

1. Discover the tool if it is not already visible:
   - Call `tool_search` with a query like `spawn manage subagents multi agent
     specialist review`.
   - Use the returned `multi_agent_v1` tools.
2. Spawn one specialist per review lens with `multi_agent_v1.spawn_agent`.
   - Use `fork_context: true` when the agents need the same conversation and
     workspace context as the lead reviewer.
   - When using `fork_context: true`, omit `agent_type`, `model`, and
     `reasoning_effort`; forked agents inherit those settings.
   - Tell each agent which lens it owns, which files to review, to use
     findings-first severity output, and not to edit files.
3. Continue any non-overlapping local review while agents run.
4. Wait with `multi_agent_v1.wait_agent`, passing all active agent ids.
5. Consolidate the results into one findings-first review. Deduplicate repeated
   findings, preserve the strongest severity, and call out disagreements.
6. Close completed agents with `multi_agent_v1.close_agent`.

If `tool_search` cannot expose `multi_agent_v1`, or spawning fails after a
tool-correct retry, state the exact limitation in the review and run the missing
lenses sequentially. Do not let subagents claim the tools were unavailable if
the lead reviewer successfully spawned them.

### Specialist Prompt Pattern

Use this shape for each spawned agent:

```text
Run the adversarial-design-review lens: <lens name>.
Review <target files/change>.
Focus only on <lens-specific concerns>.
Use findings-first output with P0/P1/P2 severity.
Do not edit files.
```

## Output Shape

Lead with findings, ordered by severity.

Use this structure:

```md
**Fatal Convergence Risks**
- [P0] Finding with file/line or design reference.

**Major Design Mismatches**
- [P1] Finding with consequence and recommended correction.

**Evidence Gaps**
- [P1/P2] What is claimed but not measured.

**Recommended Next Decisions**
- Decision needed before implementation continues.

**Do Not Build Yet**
- Work that would create premature complexity or lock in bad assumptions.
```

## Severity

- `P0`: likely to invalidate the design or make outputs misleading.
- `P1`: likely to cause significant drift, runtime failure, or false confidence.
- `P2`: important but not blocking.

## Meno-Specific Checks

For meno redesign work, always check:

- Journal entries are evidence; graph structures are interpretation.
- Dream outputs remain hypotheses.
- Rehearsal outputs remain simulations.
- Vitality metrics do not include placeholder score inflation.
- Retrieval can explain why something came to mind.
- Memory-affecting changes are traceable to evidence.
- The system has a zombie test, not just passing unit tests.
