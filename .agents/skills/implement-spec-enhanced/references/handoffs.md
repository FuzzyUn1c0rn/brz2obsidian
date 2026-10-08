# Structured handoffs

## Location and ownership

Use a directory for each attempt at a ticket candidate under the shared
integration checkout:
`tmp/<effort>/handoffs/<ticket>/<candidate-commit>/attempt-001/`.
The coordinator assigns the next unused attempt number for that ticket/commit.
The absolute directory path identifies the attempt; the JSON format stays at
schema version 1. Pass that exact path to every agent, including agents in other
worktrees. Temporary records and logs stay here; accepted decisions and
completion results stay in existing tickets.

| Record | Writer | Consumer |
| --- | --- | --- |
| `candidate.json` | Implementer | Verifier |
| `verification.json` | Independent verifier | Merger |
| `integration.json` | Merger | Coordinator |

Publish each record once, after its evidence is ready, then leave it immutable.
Keep work-in-progress notes elsewhere in the effort directory. A changed
candidate starts at `attempt-001` beneath its new commit. An unchanged candidate
can have further attempts as described below; keep previous records for
diagnosis. The coordinator claims/closes tickets so concurrent workers do not
edit the same bookkeeping files.

## Retry an unchanged candidate

A prerequisite becoming available or a temporary integration-check failure
resolving can justify another attempt without a code change. Record the reason
and previous/new attempt paths in the ticket. Allocate `attempt-002` (or the next
unused number) beneath the same candidate commit, leaving the earlier attempt
intact. Carry forward `candidate.json` byte for byte. Ensure its evidence still
resolves in the new directory: retain absolute evidence paths, or copy referenced
relative files with their original layout. Reassess evidence applicability
before reusing it; a new attempt does not require an empty Git commit.

- **Verification was BLOCKED:** dispatch the independent verifier at the same
  candidate commit. It checks the newly available prerequisite and any affected
  criteria, then publishes a fresh `verification.json` in the new attempt.
  Reuse unaffected evidence with the normal rationale. Preserve the earlier
  BLOCKED record in its original directory.
- **Integration failed temporarily:** carry forward the passing verification
  byte for byte, including its referenced evidence, only if it remains valid.
  Otherwise, obtain fresh verification in the new attempt. The merger inspects
  the current integration state and records the actual `previous_tip` and result
  for this attempt. If the candidate is already incorporated, rerun the affected
  checks against the current result; another merge is unnecessary. Publish a new
  `integration.json` with the digest of this attempt's verification record.

Validate each transition against the checkout actually assessed. Resume from
the explicitly selected attempt path, rather than treating an earlier failed
record as approval. A substantive repair still requires a new candidate commit
and verification. A required user verdict still comes from the user.

## Record format

All records are UTF-8 JSON objects with `schema_version: 1`, `kind`
(`candidate`, `verification`, or `integration`), `actor` (agent/session ID),
`ticket` (repository-relative path), `candidate_commit` (full Git object ID),
`checks`, and `limits` (array of material-limit strings; empty when none).
Use identical ticket and candidate identities throughout an attempt.

### Candidate

Additional fields:

- `spec`: repository-relative accepted specification path.
- `base_commit`: integration tip incorporated before final candidate checks.
- `worktree`: absolute path to the implementer's checkout.
- `owned_files`: repository-relative files or directories assigned to the worker.
- `criteria`: nonempty array of distinct acceptance criterion IDs or anchors.
  Reuse accepted presentation IDs where present; reference ticket criteria
  without copying the spec's prose.

The commit includes the completed change. Required failing checks must be fixed
before dispatch; unavailable checks remain explicit for the verifier to resolve.

#### Publish a candidate

Prepare evidence in the coordinator's exact absolute attempt directory, then
publish from one UTF-8 JSON input outside the published record names:

```powershell
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/write_handoff.py candidate $attempt --checkout $implementationCheckout --input $candidateInput
```

The helper can run from the integration checkout while assessing another
checkout. Every Git lookup uses `--checkout`; it derives the full candidate HEAD,
absolute worktree root, schema/kind, and the full commit resolved from `base_ref`.
It normalizes repository-relative `ticket`, `spec`, and `owned_files` paths and
rejects parent traversal. The input file remains unchanged.

The input has exactly these fields; substitute existing repository-relative
ticket/spec files, assigned ownership, actual criterion IDs, and the captured
commit ID in this illustrative input:

```json
{
  "actor": "implementer-session",
  "ticket": "docs/history/ticket.md",
  "spec": "docs/history/spec.md",
  "base_ref": "0123456789abcdef0123456789abcdef01234567",
  "owned_files": ["src/feature.py"],
  "criteria": ["A1"],
  "checks": [
    {
      "name": "Public acceptance tests",
      "status": "passed",
      "method": "From the assessed checkout: .venv\\Scripts\\python.exe -m pytest tests/test_public_contract.py",
      "exit_code": 0,
      "evidence": ["logs/public-tests.txt"]
    }
  ],
  "limits": []
}
```

Capture `base_ref` at integration synchronization: the integration tip
incorporated before final candidate checks. Prefer its full commit ID so a
moving branch cannot change the historical value. The helper resolves that
explicit reference and checks ancestry; ancestry cannot establish when it was
captured. Keep `actor`, ownership, criteria, checks, and material limits explicit,
including permitted empty arrays. Unknown fields (including inside checks),
duplicate JSON keys, and helper-owned fields such as `candidate_commit`,
`base_commit`, `worktree`, `schema_version`, or `kind` are errors.

Evidence paths are absolute or relative to the final attempt directory, including
when the input is elsewhere. Check structures and reuse requirements follow
[Checks and evidence reuse](#checks-and-evidence-reuse). Publication validates
the prospective record with the standalone validator's candidate-stage rules
against this evidence and the assessed clean checkout before creating a record.

Exit `0` reports a complete published record and an allowed transition. Exit `2`
also publishes a complete record, but holds the transition because a candidate
check failed. Candidate unavailable-check behavior remains unchanged: it can
advance to the independent verifier, which must resolve prerequisites before
PASS. Exit `1` reports invalid input/state, an occupied destination, or publication
failure with no new record. Output names the exact published path and separately
states whether the transition may advance; writing supplies no verification or
user verdict.

Publication uses stable UTF-8 JSON and an atomic filesystem operation that refuses
replacement, even for identical existing bytes. Concurrent writers produce one
complete winner and one refusal. Failure or interruption before publication can
leave a hidden `.handoff-*.tmp` sibling; it is disposable and is never a published
record. Cleanup failure after publication leaves the complete record valid.
Correct inputs or prerequisites without editing published records; use the
coordinator's next unused attempt for a retry. The selected filesystem must
support hard links; unsupported publication fails without a partial JSON record.

### Verification

Additional fields:

- `verdict`: `PASS`, `REWORK`, or `BLOCKED`.
- `criteria`: one object for every candidate criterion, with `id`, `status`
  (`satisfied`, `failed`, or `unverified`), and `evidence` (nonempty file paths).
- `findings`: array of blocking findings, with criterion/file pointers.

The verifier is a different actor from the implementer. `PASS` requires every
criterion satisfied, every listed check passed or justifiably reused, and no
blocking findings. `REWORK` means repair is needed; `BLOCKED` means a required
prerequisite or check is unavailable. User/native acceptance required by this
ticket remains unverified until its actual verdict exists. Check coverage against the ticket,
not merely the candidate's list: omitted requirements invalidate approval.

#### Publish independent verification

The independent verifier prepares its observations and publishes from one
UTF-8 JSON input outside the published record names:

```powershell
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/write_handoff.py verification $attempt --checkout $verificationCheckout --input $verificationInput
```

Pass the coordinator's exact absolute attempt path and the clean checkout at
the candidate commit. The command may run elsewhere; Git state always comes
from `--checkout`. The helper copies `ticket` and `candidate_commit` from this
attempt's `candidate.json` and derives schema/kind. The input has exactly these
fields; replace the example observations with the verifier's actual judgments:

```json
{
  "actor": "independent-verifier-session",
  "verdict": "PASS",
  "criteria": [
    {"id": "A1", "status": "satisfied", "evidence": ["logs/independent-review.txt"]}
  ],
  "findings": [],
  "checks": [
    {
      "name": "Independent public acceptance tests",
      "status": "passed",
      "method": "From the assessed checkout: .venv\\Scripts\\python.exe -m pytest tests/test_public_contract.py",
      "exit_code": 0,
      "evidence": ["logs/independent-tests.txt"]
    }
  ],
  "limits": ["Synthetic CLI checks do not demonstrate native or user acceptance"]
}
```

Every criterion object contains exactly `id`, `status`, and `evidence`, and
every candidate criterion appears once. Evidence paths are absolute or relative
to the final attempt, including when the input is elsewhere. Arrays and judgments
remain explicit. Supplied helper-owned fields, unknown fields (including inside
criteria/checks), duplicate JSON keys, missing evidence, and invalid candidate
state fail before publication. The input and prior records remain unchanged.

For repair, supply `verdict: "REWORK"`, the actual `failed` or `unverified`
criterion statuses, blocking findings with criterion/file pointers, and the
observed checks and evidence. For an unavailable prerequisite, supply
`verdict: "BLOCKED"`, the affected `unverified` criteria, and checks with
`status: "unavailable"`, `exit_code: null`, `reason`, and attempted-procedure
evidence. A required user acceptance criterion stays unverified until the actual
user verdict exists. Reused checks retain their explicit source commit and
applicability rationale under [Checks and evidence reuse](#checks-and-evidence-reuse).

Valid PASS publishes with exit `0` when the candidate transition is allowed;
valid REWORK and BLOCKED publish with exit `2` and hold the transition. Existing
candidate failures continue to hold it. Contradictory PASS claims (unsatisfied
criteria, blocking findings, or failing/unavailable verification checks) fail
with exit `1` and publish nothing. Writing JSON or passing checks supplies no
omitted verdict, requirement, evidence-applicability judgment, or user acceptance.
Actor separation checks distinct IDs; the verifier is responsible for independent
review and coverage against the ticket's actual requirements.

Verification reuses the candidate command's stable serialization and atomic,
no-overwrite publication. Output reports the exact published path separately
from permission to advance. Run the standalone validator at the verification
transition; its format/state result does not establish evidence quality. Correct
input before publication; for an occupied record or changed judgment, follow the
coordinator's retry procedure and leave the prior attempt immutable.

### Integration

Additional fields:

- `status`: `integrated` or `failed`.
- `previous_tip`: full integration-branch commit before this merge.
- `integration_commit`: full resulting commit; record the inspected HEAD for
  a failed attempt too.
- `verification_sha256`: SHA-256 of the exact `verification.json` bytes used.

For `integrated`, both `previous_tip` and `candidate_commit` must be ancestors of
the result, verification must pass, and all integration checks must pass or have
documented evidence reuse. Capture the digest after the verifier finishes;
the validator rejects changed verdict files. A failed attempt never closes work.

## Checks and evidence reuse

Each check has `name`, `status` (`passed`, `failed`, `unavailable`, or `reused`),
`method` (exact command and working directory, or manual procedure), `exit_code`
(integer for executed commands; `null` for manual, unavailable, or reused checks), and `evidence`
(nonempty array of file paths). Paths are absolute or relative to the handoff
directory. Store output or a concise observation receipt; preserve failures.
For unavailable checks the evidence records the attempted procedure and reason.
An empty checks array is allowed when criterion evidence alone is sufficient;
the verifier still assesses all required checks from the ticket and repo docs.

For example, a command check can be recorded as:

```json
{
  "name": "Public acceptance tests",
  "status": "passed",
  "method": "From the candidate checkout: .venv\\Scripts\\python.exe -m pytest tests/test_public_contract.py",
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

## Validate at transitions

Run the helper with the project `.venv` interpreter from the integration checkout.
Pass the checkout actually being assessed, which may be another worktree:

```powershell
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/validate_handoff.py $attempt --stage candidate --checkout $implementationCheckout
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/validate_handoff.py $attempt --stage verification --checkout $verificationCheckout
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/validate_handoff.py $attempt --stage integration --checkout $integrationCheckout
```

`$attempt` is the absolute attempt directory. Candidate and verification stages
require a clean checkout at the candidate commit; integration requires a clean
checkout at the result. The helper reads records and Git state; it performs no
merge, test execution, or ticket edits. Exit `0` allows the transition, `1` means
invalid records or Git state, and `2` means valid records with a failing,
unavailable, or rework verdict that cannot advance. Candidate-stage unavailable
checks may proceed to a verifier, who must resolve them before `PASS`.

Validation covers format, evidence-file existence, actor separation, commit
identity/ancestry, criterion coverage within the records, and the verdict digest.
It cannot judge evidence quality, discover omitted spec requirements, or prove
that commands were run. The independent review supplies those judgments.

Use ordinary completion messages such as `candidate ready: <path> (<commit>)`,
`verification: <path> REWORK`, or `integration: <path> integrated`. Records carry
the details; the coordinator reads them when the state changes.

When changing the helper, run its self-contained CLI tests from the workspace
root; they create isolated Git repositories under `tmp/implement-spec-enhanced-tests/`:

```powershell
.venv\Scripts\python.exe -m unittest discover -s .agents/skills/implement-spec-enhanced/tests -v
```
