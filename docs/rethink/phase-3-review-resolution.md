# Phase 3 Pre-Implementation Review Resolution

Phase 3 was reviewed before implementation using the adversarial review
protocol. The review found P0 design gaps in the retrieval plan. Implementation
must not begin until the revised Phase 3 contract is used as the build target.

## Resolved Findings

- Retrieval eligibility over Phase 2 status fields was undefined.
  Resolution: Phase 3 now has an eligibility matrix covering candidate kind,
  acceptance status, relation status, epistemic status, and requested scope.

- Privacy/resource scope was absent from the retrieval contract.
  Resolution: Phase 3 now requires scope-aware filtering, scope decisions on
  every result/path step, and redacted ghost signals for scope-disallowed
  material.

- The zombie gate could be passed by keyword search with fabricated paths.
  Resolution: Phase 3 now requires contrastive fixtures with identical labels
  but different evidence/status/edge histories, and exact assertions on paths,
  activation factors, scope decisions, ghost signals, and source refs.

- Activation semantics were not typed.
  Resolution: activation is now defined as typed interpretation recall over
  Phase 2 candidate status, epistemic status, confidence, evidence
  accumulation, edge/relation type, scope, path length, and centrality damping.

- Path explanations could have been prose-only.
  Resolution: Phase 3 now defines structural `RetrievalResult`,
  `ActivatedCandidate`, `ActivationPath`, and `ActivationStep` records.

- Ghost signals were underdefined.
  Resolution: Phase 3 now defines redacted `GhostSignal` records with safe
  metadata only, and blocks ghosted material from normal working memory.

- Confidence risked becoming retrieval weight.
  Resolution: Phase 3 now requires a separate `RetrievalWeight` record and
  explicitly forbids treating Phase 2 confidence as activation strength.

- Direction-aware traversal was too vague.
  Resolution: Phase 3 now defines traversal behavior per edge/relation type,
  including dream, rehearsal, contradiction, correction, and outcome semantics.

- Retrieval idempotency and echo behavior were underspecified.
  Resolution: Phase 3 is explicitly read-only and requires frontier-only
  propagation plus loop/hub tests that catch activation echo.

## Explicit Deferrals

- No retrieval trace persistence in Phase 3.
- No decay, forgetting, vitality, embedding rediscovery, dreaming loops,
  rehearsal generation, autonomous mode selection, SurrealDB integration, or
  legacy retrieval extension.
