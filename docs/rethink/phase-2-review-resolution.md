# Phase 2 Review Resolution

Phase 2 used the adversarial review protocol before and after implementation.
The implementation review found no P0 issues. P1 findings were resolved as
design changes, tests, or explicit deferrals before treating the phase as
complete.

## Resolved Findings

- Factual projection must not treat observed conversation text as world evidence.
  Resolution: conversation truth claims are rejected as factual candidates;
  factual candidates require observation/tool-style evidence.

- Candidate identity must thicken through accumulated evidence rather than
  overwrite source refs, scope, or confidence.
  Resolution: candidate rows now merge evidence refs, confidence summaries, and
  privacy/resource scopes across repeated projection evidence.

- Projection run identity must separate content keys from attempt lifecycle.
  Resolution: projection attempts are append-only run rows with a stable
  `projection_key` for the source snapshot.

- Contradictions must be auditable transitions, not direct row mutation.
  Resolution: conflicted candidates now receive projection decisions and
  candidate transition records.

- Dream and rehearsal projections must preserve their future loop interfaces.
  Resolution: dream refs retain generated candidates, uncertainty, salience,
  and tension residue; rehearsal refs retain target, strategy, simulated trace,
  and predicted failure modes.

- Evidence refs must cover every projected source field and be validated beyond
  event-level citation.
  Resolution: tests validate refs across decisions, edges, relations,
  rejections, and persisted evidence-ref rows, including negative stale-hash and
  event-level-only cases.

- The zombie gate needed absence checks and accumulation checks.
  Resolution: tests cover dream-only non-promotion, rehearsal non-promotion,
  isolated preference self-report, repeated weak preference accumulation, and
  decision-backed preference promotion.

- Failed-run behavior needed rollback after partial writes, not only failure
  before writes.
  Resolution: tests inject failure after the first candidate write and assert no
  accepted partial candidates remain.

- Observation projections needed evidence refs for every field they used.
  Resolution: observed entity candidates now cite `payload.subject`; observed
  evidence candidates cite `payload.evidence`; co-occurrence edges cite both.

- Projection run summaries were overstating retained candidates as newly
  created.
  Resolution: run `created_candidate_ids` now records only candidates first
  created in that attempt; replay attempts keep a stable `projection_key` but
  have separate attempt ids.

- Relation records needed direct scope and confidence, not only an indirect
  decision link.
  Resolution: relation rows now persist privacy/resource scope, confidence,
  projection run, projection rule, and projection version.

- Schema checks were too narrow.
  Resolution: tests now inspect and exercise foreign keys for edges, decisions,
  transitions, relations, rejections, and evidence refs.

## Explicit Deferrals

- Reflection, commitment, and skill projection remain ontology targets but are
  not implemented in this fixture-first Phase 2 slice.
- Retrieval, activation, decay, autonomous dreaming, rehearsal generation, and
  SurrealDB integration remain out of scope until later phases.
