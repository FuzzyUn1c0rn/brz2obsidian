# Structured handoffs

Use this contract for the structured path selected in `SKILL.md`. Eligible
report/documentation corrections follow [lightweight handoffs](lightweight-handoff.md)
instead; their Markdown review records are outside the structured schemas and
CLI validators. Both paths use [change-scoped check selection](check-scope.md).

Read this common contract once before structured dispatch or consuming a stage. Then read
only the references required by the current role or transition. The linked
references are authoritative; examples for unrelated stages stay out of the
current reading path.

## Stage reading paths

Every structured publisher and transition reviewer reads
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

Keep work-in-progress notes and stage inputs elsewhere in the effort directory,
outside published record names. A changed candidate starts at
`attempt-001` beneath its new commit. An unchanged candidate
can have further attempts in [retry/carry-forward](handoff-retry.md); keep previous records for
diagnosis. The coordinator owns ticket claims and completion under
[PR delivery and issue completion](../../../../docs/agents/issue-tracker.md#pr-delivery-and-issue-completion)
so concurrent workers do not edit the same bookkeeping files.

## Record format

New records are UTF-8 JSON objects with `schema_version: 2`, `kind`
(`candidate`, `verification`, or `integration`), `actor` (agent/session ID),
`ticket` (repository-relative path or canonical GitHub issue URL), `candidate_commit` (full Git object ID),
`assessed_checkout` (derived absolute stage checkout), `check_requirements` and
`check_requirements_sha256` (derived from independent input),
`checks`, and `limits` (array of material-limit strings; empty when none).
Use identical ticket and candidate identities throughout an attempt.
For URL references, read [GitHub scope snapshots](issue-sources.md); candidate
records preserve the assessed issue content in hashed attempt-local evidence.

## Publication contract

Before publication, prepare evidence and an explicit UTF-8 JSON input, using the
assigned absolute attempt, assessed checkout and independent requirements paths.
The filesystem must support hard links; unsupported publication fails without a
partial JSON record. Candidate/verification assess a clean candidate checkout;
integration assesses its clean inspected result. Git lookups use `--checkout`
even when the helper runs elsewhere.

Keep all stage input fields, arrays and judgments explicit, including permitted
empty arrays. Unknown fields, duplicate JSON keys and helper-owned overrides are
errors, including within checks/criteria. Evidence paths are absolute or relative
to the final attempt, even when the input lives elsewhere. Missing evidence or
invalid stage/Git state fails before record publication. The helper preserves
inputs and prior records; it validates the prospective record against stage
requirements before publishing. Stage references define their additional fields,
derived identities and outcomes; [requirements/evidence](handoff-evidence.md)
defines common check objects and reuse.

Publish each record once after evidence is ready, then leave it immutable. Stable
UTF-8 JSON is published atomically without replacement, even for identical bytes.
Concurrent writers produce one complete winner and one refusal. Correct inputs
before publication; an occupied record or changed judgment needs the coordinator's
next unused attempt under [retry/carry-forward](handoff-retry.md).

For ordinary stage publication, exit `0` publishes and allows advancement; `2`
publishes a complete held outcome; `1` refuses or fails without a new record.
Candidate unavailable checks may advance to verification; contradictory verifier
PASS claims publish nothing. Read the applicable stage for these outcome rules.
Output reports the exact published path separately from permission to advance.
Writing supplies no independent judgment, evidence-quality or user verdict.
Run [standalone transition validation](handoff-validation.md#validate-at-transitions)
after every publication; writer validation does not replace it.

If publication is interrupted, a hidden `.handoff-*.tmp` sibling may remain;
it is disposable and never a published record. Cleanup failure after publication
leaves the complete record valid. Carry-forward has distinct per-file publication
and [partial-attempt recovery rules](handoff-retry.md#retry-an-unchanged-candidate);
exit `1` can leave an incomplete attempt requiring a new assignment.
