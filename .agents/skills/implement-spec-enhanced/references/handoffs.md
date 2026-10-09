# Structured handoffs

Read this common contract once before dispatch or consuming a stage. Then read
only the references required by the current role or transition. The linked
references are authoritative; examples for unrelated stages stay out of the
current reading path.

## Stage reading paths

Every publisher and transition reviewer reads
[requirements/evidence](handoff-evidence.md) and
[transition validation](handoff-validation.md), including the independently
supplied requirements. Add the reference for the current operation:

| Role or operation | Required stage reference |
| --- | --- |
| Coordinator assigning work, inputs or attempts | [Dispatch and commit handshake](handoff-dispatch.md) |
| Implementer publishing a completed candidate | [Candidate](handoff-candidate.md) |
| Independent verifier assessing a candidate and publishing its verdict | [Verification](handoff-verification.md) |
| Merger publishing the inspected integration outcome | [Integration](handoff-integration.md) |
| Coordinator recovering an unchanged candidate | [Retry/carry-forward](handoff-retry.md); then the reference for any fresh stage |
| Reader inspecting v1 evidence | [Historical records](handoff-evidence.md#historical-records-and-retries) |
| Maintainer rehearsing documentation/CLI agreement | [Synthetic workflow rehearsal](handoff-rehearsal.md) |

## Location and ownership

Use a directory for each attempt at a ticket candidate under the shared
integration checkout:
`tmp/<effort>/handoffs/<ticket>/<candidate-commit>/attempt-001/`.
The coordinator assigns the next unused attempt number for that ticket/commit.
The absolute directory path identifies the attempt; new records use schema version 2. Pass that exact path to every agent, including agents in other
worktrees. Temporary records and logs stay here; accepted decisions and
completion results stay in existing tickets.

| Record | Writer | Consumer |
| --- | --- | --- |
| `candidate.json` | Implementer | Verifier |
| `verification.json` | Independent verifier | Merger |
| `integration.json` | Merger | Coordinator |

Use `scripts/write_handoff.py` for every record publication and carry-forward;
the linked stage examples are the required route. Agents supply judgments; the
writer derives bookkeeping and validates before immutable publication. It manages
no drafts, check execution, merges, ticket edits, worktrees, or user acceptance.
Run the independently executable read-only standalone validator at each
transition even after successful writer validation.

Publish each record once, after its evidence is ready, then leave it immutable.
Keep work-in-progress notes and UTF-8 stage inputs elsewhere in the effort
directory, outside published record names. A changed candidate starts at
`attempt-001` beneath its new commit. An unchanged candidate
can have further attempts in [retry/carry-forward](handoff-retry.md); keep previous records for
diagnosis. The coordinator claims/closes tickets so concurrent workers do not
edit the same bookkeeping files.

### Dispatch and commit handshake

Before dispatch or attempt allocation, read the [dispatch contract](handoff-dispatch.md#dispatch-and-commit-handshake).

## Retry an unchanged candidate

When a prerequisite recovers or integration can retry without code changes, read
[retry/carry-forward](handoff-retry.md#retry-an-unchanged-candidate), including
carried requirements and partial-attempt recovery.

## Independent automated-check requirements

For every stage, read [independent requirements](handoff-evidence.md#independent-automated-check-requirements).

## Historical records and retries

For v1 records or checks, read [historical evidence](handoff-evidence.md#historical-records-and-retries).
For byte-preserving v2 carry, read [carried requirements](handoff-retry.md#carried-requirements).

## Record format

New records are UTF-8 JSON objects with `schema_version: 2`, `kind`
(`candidate`, `verification`, or `integration`), `actor` (agent/session ID),
`ticket` (repository-relative path), `candidate_commit` (full Git object ID),
`assessed_checkout` (derived absolute stage checkout), `check_requirements` and
`check_requirements_sha256` (derived from independent input),
`checks`, and `limits` (array of material-limit strings; empty when none).
Use identical ticket and candidate identities throughout an attempt.

### Candidate

For this stage's record fields and judgments, read [candidate](handoff-candidate.md#candidate).

#### Publish a candidate

For exact inputs, examples and exits, read [publication](handoff-candidate.md#publish-a-candidate).

### Verification

For this stage's record fields and judgments, read [verification](handoff-verification.md#verification).

#### Publish independent verification

For exact inputs, examples and exits, read [publication](handoff-verification.md#publish-independent-verification).

### Integration

For this stage's record fields and judgments, read [integration](handoff-integration.md#integration).

#### Publish the actual integration outcome

For exact inputs, examples and exits, read [publication](handoff-integration.md#publish-the-actual-integration-outcome).

## Checks and evidence reuse

For check fields, manual/native evidence or reused outcomes, read
[checks and evidence reuse](handoff-evidence.md#checks-and-evidence-reuse).

## Validate at transitions

After every publication, read and run [standalone transition validation](handoff-validation.md#validate-at-transitions).

### Synthetic workflow rehearsal

When rehearsing the workflow, read the [rehearsal procedure](handoff-rehearsal.md#synthetic-workflow-rehearsal).
