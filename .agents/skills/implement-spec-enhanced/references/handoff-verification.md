# Independent verification

Before this stage, read the [common contract](handoffs.md),
[requirements/evidence](handoff-evidence.md), and
[transition validation](handoff-validation.md). For an occupied record or a
temporary prerequisite recovery, read [retry/carry-forward](handoff-retry.md).

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

Review the actual diff's impact and the coordinator's scope/reuse rationale under
[check selection](check-scope.md). Independently execute each check assigned as
fresh; other checks may use qualifying evidence under the requirements contract.
Independent judgment is required even for a manual-only verification stage.

#### Publish independent verification

The independent verifier prepares its observations and publishes from one
UTF-8 JSON input outside the published record names:

```powershell
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/write_handoff.py verification $attempt --checkout $verificationCheckout --input $verificationInput --requirements $verificationRequirements
```

Pass the coordinator's exact absolute attempt path and the clean checkout at
the candidate commit. The command may run elsewhere; Git state always comes
from `--checkout`. The helper copies `ticket` and `candidate_commit` from this
attempt's `candidate.json` and derives schema/kind. The input has exactly these
fields; replace the example observations with the verifier's actual judgments.
This manual-only example uses `checks: []` only when independent requirements
assign no covered automated checks. For assigned checks, use actual objects under
[requirements/evidence](handoff-evidence.md#shared-runner-check-example).

```json
{
  "actor": "independent-verifier-session",
  "verdict": "PASS",
  "criteria": [
    {"id": "A1", "status": "satisfied", "evidence": ["logs/independent-review.txt"]}
  ],
  "findings": [],
  "checks": [],
  "limits": ["Synthetic CLI checks do not demonstrate native or user acceptance"]
}
```

Every criterion object contains exactly `id`, `status`, and `evidence`, and
every candidate criterion appears once. Apply the common
[input/evidence/publication rules](handoffs.md#publication-contract).

For repair, supply `verdict: "REWORK"`, the actual `failed` or `unverified`
criterion statuses, blocking findings with criterion/file pointers, and the
observed checks and evidence. For an unavailable prerequisite, supply
`verdict: "BLOCKED"`, the affected `unverified` criteria, and checks with
`status: "unavailable"`, `exit_code: null`, `reason`, and attempted-procedure
evidence. A required user acceptance criterion stays unverified until the actual
user verdict exists. Reused checks retain their explicit source commit and
applicability rationale under [Checks and evidence reuse](handoff-evidence.md#checks-and-evidence-reuse).

Valid PASS publishes with exit `0` when the candidate transition is allowed;
valid REWORK and BLOCKED publish with exit `2` and hold the transition. Existing
candidate failures continue to hold it. Contradictory PASS claims (unsatisfied
criteria, blocking findings, or failing/unavailable verification checks) fail
with exit `1` and publish nothing. Writing JSON or passing checks supplies no
omitted verdict, requirement, evidence-applicability judgment, or user acceptance.
Actor separation checks distinct IDs; the verifier is responsible for independent
review and coverage against the ticket's actual requirements.
