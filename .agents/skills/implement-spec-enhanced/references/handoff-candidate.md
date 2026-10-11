# Candidate publication

Before this stage, read the [common contract](handoffs.md),
[requirements/evidence](handoff-evidence.md), and
[transition validation](handoff-validation.md). For an occupied record or a
temporary prerequisite recovery, read [retry/carry-forward](handoff-retry.md).

### Candidate

Additional fields:

- `spec`: repository-relative accepted specification path or canonical GitHub issue URL.
- `source_snapshots`: required for URL sources; the input maps `ticket`/`spec` to
  attempt-relative captured issue JSON. The helper derives each path/digest pair
  in the record. Read [GitHub scope snapshots](issue-sources.md) for retrieval,
  publication and review rules.
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
It normalizes repository-relative paths and preserves canonical issue URLs.
URL sources bind to captured snapshots; parent traversal is refused. The input
file remains unchanged.

The input requires the fields below, plus `source_snapshots` for URL references.
Substitute existing repository-relative files or the issue references and
snapshots described above, assigned ownership, actual criterion IDs, and the
captured commit ID in this illustrative manual-only local-file input. Here
`checks: []` requires no covered automated checks in the independent requirements;
when checks are assigned, insert actual check objects using the
[shared runner example](handoff-evidence.md#shared-runner-check-example) or manual/reuse fields.

```json
{
  "actor": "implementer-session",
  "ticket": "docs/history/ticket.md",
  "spec": "docs/history/spec.md",
  "base_ref": "0123456789abcdef0123456789abcdef01234567",
  "owned_files": ["src/feature.py"],
  "criteria": ["A1"],
  "checks": [],
  "limits": []
}
```

Capture `base_ref` at integration synchronization: the integration tip
incorporated before final candidate checks. Prefer its full commit ID so a
moving branch cannot change the historical value. The helper resolves that
explicit reference and checks ancestry; ancestry cannot establish when it was
captured. `candidate_commit`, `base_commit`, `worktree`, `schema_version` and
`kind` are helper-owned fields. Input, evidence and publication rules follow the
[common publication contract](handoffs.md#publication-contract).

Exit `0` reports a complete published record and an allowed transition. Exit `2`
also publishes a complete record, but holds the transition because a candidate
check failed. Candidate unavailable-check behavior remains unchanged: it can
advance to the independent verifier, which must resolve prerequisites before
PASS. Invalid input/state or publication failure returns `1` without a new record
under the common contract.
