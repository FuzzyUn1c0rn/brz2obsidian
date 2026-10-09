# Candidate publication

Before this stage, read the [common contract](handoffs.md),
[requirements/evidence](handoff-evidence.md), and
[transition validation](handoff-validation.md). For an occupied record or a
temporary prerequisite recovery, read [retry/carry-forward](handoff-retry.md).

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
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/write_handoff.py candidate $attempt --checkout $implementationCheckout --input $candidateInput --requirements $candidateRequirements
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
      "kind": "runner",
      "check_id": "pytest",
      "receipt": "C:/absolute/checkout/tmp/checks/run-id/receipt.json",
      "name": "Public acceptance tests",
      "status": "passed",
      "method": "From the assessed checkout: .venv\\Scripts\\python.exe tools/check.py run --check pytest --test tests/test_public_contract.py",
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
[Checks and evidence reuse](handoff-evidence.md#checks-and-evidence-reuse). Publication validates
the prospective record with the standalone validator's candidate-stage rules
against this evidence, independent stage requirements, and the assessed clean checkout before creating a record.

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
