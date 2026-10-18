# Choose checks from the changes

Read before dispatch, before candidate completion checks, and when a repair or
integration changes the assessed result. This selection applies to both handoff
paths; runner execution and evidence binding follow
[the testing contract](../../../../docs/testing.md#automated-check-runner).

## Plan and confirm

The coordinator/reviewer records the proposed scope before development, then
confirms it against the actual diff from the incorporated integration base to
the candidate. Inspect changed content and affected callers, consumers, shared
contracts and test/tool dependencies. File count or a `.md` extension alone
does not establish impact: an executable example or acceptance-rule change can
affect behavior. Keep mandatory ticket/specification checks and user/native gates.

Record a short plan alongside the stage requirements or lightweight record:

- Base/candidate identities and changed files/behaviors.
- Applicable acceptance criteria and dependency risks.
- Each stage's environment, check IDs, pytest selectors/expressions, required GUI
  execution and freshness, with a reason for the selected scope.
- Prior evidence proposed for reuse, its original commit/context and limits.

Choose the smallest coverage that establishes these obligations. Broaden for
shared contracts, cross-cutting behavior, uncertain dependencies or an applicable
acceptance requirement. Broad verification uses the maintained reduced bundle in
`tools/coverage_suite.py`; historical exhaustive requirements are withdrawn by
the repository testing contract. Reassess when repairs
or new findings change impact; preserve superseded requirements and failures.
An intentionally narrow plan still accounts for every mandatory criterion.

| Actual change | Useful coverage |
| --- | --- |
| Factual report/approval record only | Independently compare claims and evidence with the actual verdict/results; check links or report consistency where applicable. |
| Small documentation correction | Compare changed facts with authoritative code/docs; use existing documentation/link checks where relevant. |
| Runtime or parser behavior | Affected public workflows, refusal/preservation controls and dependent consumers; broader regression checks for shared behavior. |
| Rendered output or application UI | Affected output/UI controls plus applicable independent presentation observations. |
| Tests, tools, dependency/configuration or agent workflow rules | Controls for the changed mechanism and its consumers; assess executable examples and documented CLI agreement. |

Select lint, format and dependency checks according to repository requirements.
Documentation alone does not require unrelated converter pytest, GUI execution,
private archive reruns or refreshed native observations. Manual-only verification
is valid when no automated check establishes an affected obligation. In structured
requirements, express that as `checks: []`; record the manual evidence separately.
For skill or agent-guidance changes, inspect activation boundaries, authorization,
reference routing and the affected workflow. Run existing helper/contract tests
when that workflow changes; do not add tests that merely match instruction wording.
For changed agent decisions, use applicable [skill behavior evaluations](../../../../docs/agents/skill-evaluations.md)
with independent rubric review; helper tests alone do not establish prompt behavior.
An unchanged helper protocol can use its existing focused controls alongside
manual instruction review. A read-only audit does not imply running checks that
create receipts or other artifacts when the user's requested scope forbids writes.
When pytest is needed, name explicit surviving selectors or use the maintained
reduced bundle. The runner's legacy selector-omission path invokes configured
discovery and must not be used. Empty/zero-test selections are not passing
evidence. Retired historical cases are not available for additional checks;
author focused checks when a future changed behavior needs them.

## Stage differences and reuse

Implementation checks establish the candidate's changed behavior. Independent
verification reviews the exact diff, coverage and evidence, and freshly executes
checks needed for its independent verdict. Independence comes from a different
reviewer making its own judgments, not from repeating every implementer command.
Explicit fresh-execution requirements still require the verifier's own receipts.

Integration checks address risks introduced by the combined result. For a clean
fast-forward to the exact reviewed candidate, select reuse where existing receipts
validate for that result and environment. A changed merge result or relevant
integration-tip change needs affected combined checks and review; equivalent
trees alone do not establish environment applicability.

Runner reuse requires content binding under the testing contract. Validate against
the assessed candidate/result using the runner and, for structured stages, the
handoff validator. A report edit changes the repository snapshot: unchanged runtime
behavior does not make an earlier whole-snapshot receipt bind to the new commit.
Retain that receipt as original-commit historical evidence with an applicability
rationale, then run any checks required for the current snapshot. Preserve native,
archive and user evidence separately with its original context and limits.

For structured reuse, assign `fresh: false` before accepting reused results and
use the existing reused-check fields from [requirements/evidence](handoff-evidence.md).
Reuse never satisfies `fresh: true`. Revise an overbroad plan only with an explicit
diff-based reason and independent review of the revision; retain the old plan and
interrupted/failed evidence. Reclassifying a failing affected check as unrelated
requires resolution of the finding, not simply removing its requirement.
