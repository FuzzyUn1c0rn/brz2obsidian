# Requirements and evidence

Read this for every publication, carry-forward, and transition validation.
When consuming v1 evidence, also apply [historical records](#historical-records-and-retries).
Carry-forward requirements are in [retry/carry-forward](handoff-retry.md#carried-requirements).

## Independent automated-check requirements

Before completion checks, the coordinator or reviewer supplies a separate UTF-8
JSON requirements file for each stage. Pass its absolute path through
`--requirements` to both publication and standalone validation. Keep this input
outside published records; its selection comes from ticket scope and stage
judgment, independently of submitted outcomes. The writer stores the declaration
and its canonical SHA-256 in the v2 record. Standalone validation compares the
current stage to the independently supplied declaration. Earlier stages retain
their published declarations and original execution context.

```json
{
  "schema_version": 1,
  "ticket": "docs/history/ticket.md",
  "stage": "candidate",
  "candidate_commit": "0123456789abcdef0123456789abcdef01234567",
  "assessed_commit": "0123456789abcdef0123456789abcdef01234567",
  "environment": "gui",
  "checks": [
    {
      "id": "pytest",
      "fresh": true,
      "scope": "focused",
      "selectors": ["tests/test_public_contract.py"],
      "keyword": null,
      "marker": null,
      "require_gui": false
    },
    {"id": "lint", "fresh": false}
  ]
}
```

The stage is `candidate`, `verification`, or `integration`. Both commit IDs are
full IDs: `candidate_commit` identifies the candidate; `assessed_commit` is the
candidate at implementation/verification, and the inspected result at
integration. Supported check IDs are `pytest`, `lint`, `format`, and `dependency`.
Each requirement has an explicit `fresh` boolean. A check may override the stage
`environment` with `base` or `gui`; this allows the same check ID once in each
environment. Optional `requirement_key` strings distinguish multiple scopes of
the same check in one environment: for example `full-suite` and `handoff-tests`
for full pytest and additional focused pytest outside configured testpaths.
Each matching submitted result carries the same key. Duplicate
check/environment/key requirements are refused. A pytest
requirement includes every scope field shown; `full` has empty selectors and
null expressions. A full receipt may cover focused selectors only when it
actually executed their tests. Unknown fields, IDs and versions are errors.
Manual-only scope uses an explicit empty requirements `checks` array.

A covered automated outcome uses `kind: "runner"`, its `check_id`, optional
environment override, and an absolute or attempt-relative `receipt` path in
addition to the ordinary check fields. A successful claim requires an intact
completed passing runner receipt; the validator invokes the runner's public
validation CLI for selection, environment, logs and exact Git content binding.
The claimed exit/status must match the receipt. Fresh results originate from
the stage's actual `assessed_checkout`; an independent verifier supplies its
own invocation and receipt. Use `status: "reused"`, null `exit_code`, original
`source_commit` (the receipt's original run revision, including pre-commit dirty
execution) and nonempty applicability `reason` to reuse a receipt. Reuse
cannot satisfy `fresh: true`. For full runner commands and bootstrap/failure
exceptions, follow [the authoritative testing reference](../../../../docs/testing.md).

Manual/native observations use `kind: "manual"`; they retain their evidence
and acceptance rules and cannot satisfy a required runner check. Missing entries,
plain text logs, and an empty submitted result list cannot erase expected checks.
Failed executed receipts may support honest `failed` entries and held outcomes;
unavailable attempts retain reason/evidence and hold PASS/integration. Neither
qualifies completion. Receipt validation performs no new checks.

## Checks and evidence reuse

Each check has `name`, `status` (`passed`, `failed`, `unavailable`, or `reused`),
`method` (exact command and working directory, or manual procedure), `exit_code`
(integer for executed commands; `null` for manual, unavailable, or reused checks), and `evidence`
(nonempty array of file paths). Paths are absolute or relative to the handoff
directory. Store output or a concise observation receipt; preserve failures.
For unavailable checks the evidence records the attempted procedure and reason.
An empty checks array is allowed only when the independently supplied stage
requirements also contain no covered checks. The reviewer selects requirements
from the ticket and repository testing guidance before accepting results.

For example, a command check can be recorded as:

```json
{
  "kind": "runner",
      "check_id": "pytest",
      "receipt": "C:/absolute/checkout/tmp/checks/run-id/receipt.json",
      "name": "Public acceptance tests",
  "status": "passed",
  "method": "From the candidate checkout: .venv\\Scripts\\python.exe tools/check.py run --check pytest --test tests/test_public_contract.py",
  "exit_code": 0,
  "evidence": ["logs/public-tests.txt"]
}
```

`failed`, `unavailable`, and `reused` also require `reason`. A reused check also
requires `source_commit` (full Git ID). Record the prior evidence and explain why
the changes since that commit cannot affect the checked behavior. Candidate
checks alone do not constitute independent verification. Reuse expensive native
evidence when source inputs, generated output, renderer conditions, and relevant
requirements remain applicable. Rerun affected checks for runtime/output changes
or contradictory evidence. A ticket-closure-only commit can reuse runtime
evidence when its diff demonstrates the limited scope; user acceptance is an
actual verdict, never an inferred check.

## Historical records and retries

Published schema-v1 files remain immutable and readable through the standalone
validator's explicit `--historical` mode. That mode validates historical
structure/state and reports historical evidence, without approving a new
transition. It cannot be combined with `--requirements`. New writers publish
v2, and current transitions reject v1 records. Historical v1 candidates cannot
be carried directly into a new transition.

For explicit historical check reuse in a new v2 record, use `kind: "historical"`,
`check_id`, `status: "reused"`, null `exit_code`, `source_commit`, applicability
`reason`, and the original `source_record` path and zero-based `source_check`
index. Retain the ordinary evidence fields. Validation reads the original v1
check and evidence and verifies its source commit and successful outcome.
This preserves provenance; it cannot satisfy a fresh-execution requirement.

