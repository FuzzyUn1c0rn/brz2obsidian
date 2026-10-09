# Retry and carry-forward

Read the [common contract](handoffs.md), [requirements/evidence](handoff-evidence.md),
and [transition validation](handoff-validation.md) before carrying an unchanged
candidate. For the next fresh publication, read only its applicable
[candidate](handoff-candidate.md), [verification](handoff-verification.md), or
[integration](handoff-integration.md) reference.

## Retry an unchanged candidate

A prerequisite becoming available or a temporary integration-check failure
resolving can justify another attempt without a code change. Record the reason
and previous/new attempt paths in the ticket. The coordinator allocates
`attempt-002` (or the next unused number) beneath the same candidate commit,
leaving the earlier attempt
intact. Select the exact source attempt explicitly and assess the clean unchanged
candidate commit. Use the helper from the integration checkout:

```powershell
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/write_handoff.py carry-forward $newAttempt --from $previousAttempt --checkout $candidateCheckout --input $carryInput --requirements $retryRequirements
```

Both attempt paths must be absolute, distinct and non-nested. The helper accepts
the coordinator's assignment; it never discovers the latest attempt, increments
numbers, merges code or edits tickets. Keep the UTF-8 input outside the destination
attempt. For prerequisite recovery, use:

```json
{
  "reason": "The unavailable prerequisite is now available",
  "carry_verification": false
}
```

For a temporary integration failure with still-applicable independent PASS:

```json
{
  "reason": "The integration check prerequisite has recovered",
  "carry_verification": true,
  "verification_reuse_rationale": "The candidate, assessed inputs and verification conditions are unchanged"
}
```

Supply a nonempty reason and an actual JSON boolean. True requires a nonempty
applicability rationale; false accepts no reuse rationale. Unknown, duplicate or
helper-owned fields are errors. Choosing true is the coordinator's attestation
of applicability; machine validation establishes structure/state, not that
judgment. The auxiliary `carry-forward.json` receipt contains `reason`,
`source_attempt`, `destination_attempt`, `carry_verification` and, only for
reuse, `verification_reuse_rationale`. It uses stable JSON without timestamps
and remains outside the immutable records. Keep the durable conclusion in GitHub.

The helper copies `candidate.json` and any requested PASS `verification.json`
byte for byte, preserving the original actors and context. It carries every
check/criterion evidence reference in those records. Absolute references remain
intact and resolvable; relative files retain their layout and bytes. Evidence
paths are relative to the final attempt, including `..` paths accepted by the
validator. A parent-relative path that resolves to an occupied file in the new
layout is a collision even if its bytes match the source. Select an unused layout
that preserves the reference; the helper leaves the reference unchanged. Rooted
or drive-relative Windows references lacking an absolute drive/root combination
are ambiguous and refused. Equivalent references to the same source/destination
file are copied once. Evidence aliases of record/receipt names, planned
file/ancestor collisions and paths into the source attempt are refused.

Known collisions, missing evidence, invalid reuse and invalid Git state fail
before copying. Existing files/directories at any destination remain unchanged;
an occupied attempt, including an interrupted staging file, requires a new
assignment. All requested evidence and the receipt publish before records, with
candidate last. Each file is atomic without replacement; directory-wide rollback
is unnecessary. Exit `0` means complete carry and an allowed transition; `2`
means complete carry with the corresponding candidate/verification transition
held; `1` means failure. An ordinary I/O failure reports the exact destination
and warns that any partial attempt is not ready. The helper prints its assigned
destination before copying, so a forced process termination still leaves an
exact inspection pointer even though the killed process cannot print a final
diagnostic. Preserve partial attempts and have the coordinator assign another
unused attempt. A later invocation refuses the occupied partial directory.
Candidate presence alone does not prove a completed carry: all requested records,
evidence, and the receipt must be present and the selected transition validated.

- **Verification was BLOCKED:** dispatch the independent verifier at the same
  candidate commit after carrying with `carry_verification: false`. It checks
  the newly available prerequisite and any affected
  criteria, then publishes a fresh `verification.json` in the new attempt.
  Reuse unaffected evidence with the normal rationale. Preserve the earlier
  BLOCKED record in its original directory.
- **Integration failed temporarily:** carry the passing verification using
  `carry_verification: true` and the explicit applicability rationale.
  Otherwise, obtain fresh verification in the new attempt. The merger inspects
  the current integration state and records the actual `previous_tip` and result
  for this attempt. If the candidate is already incorporated, rerun the affected
  checks against the current result; another merge is unnecessary. Publish a new
  `integration.json` with the digest of this attempt's verification record.
  Integration records are always fresh; the helper never carries the earlier one.
  Carry uses the clean candidate checkout even when integration has moved ahead;
  retain the current integration result and assess it for fresh integration.
  Capture its full HEAD as `previous_tip_ref` immediately before this retry's
  integration operation, including when no additional merge is needed.

Validate each transition against the checkout actually assessed. Resume from
the explicitly selected attempt path, rather than treating an earlier failed
record as approval. A substantive repair still requires a new candidate commit
and verification. A required user verdict still comes from the user.

## Carried requirements

Carry-forward preserves original v2 candidate/PASS bytes and runner provenance.
Its `--requirements` file supplies the current candidate or verification stage
requirements, according to `carry_verification`. When carrying PASS, supply
`--candidate-requirements` with a separate current candidate declaration to
relax original fresh demands into justified reuse. Omitting it retains the
source candidate's effective declaration. The auxiliary carry receipt
stores the current declarations; carried executions require `fresh: false`.
When carrying PASS, candidate requirements retain their published declaration
and must also permit reuse. Relative runner receipts and their digest-referenced
logs retain their layout; absolute receipts keep their original context.
Fresh requirements require new publication with newly executed evidence rather
than a byte-preserving carry. Every integration outcome remains fresh.
