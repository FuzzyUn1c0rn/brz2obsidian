# Transition validation

Read this after publishing the current stage; use its corresponding command.
Apply the [common contract](handoffs.md) and [requirements/evidence](handoff-evidence.md).
For a retry, read [retry/carry-forward](handoff-retry.md).

## Validate at transitions

Run the standalone `validate_handoff.py` with the project `.venv` interpreter
from the integration checkout after publication. Writer validation is additional;
it does not replace this explicit read-only CLI.
Both CLIs emit UTF-8 diagnostics, including Unicode paths on Windows pipes.
Decode captured output as UTF-8 so publication outcomes and exact destination
pointers remain readable. Pass the checkout actually being assessed, which may
be another worktree:

```powershell
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/validate_handoff.py $attempt --stage candidate --checkout $implementationCheckout --requirements $candidateRequirements
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/validate_handoff.py $attempt --stage verification --checkout $verificationCheckout --requirements $verificationRequirements
.venv\Scripts\python.exe .agents/skills/implement-spec-enhanced/scripts/validate_handoff.py $attempt --stage integration --checkout $integrationCheckout --requirements $integrationRequirements
```

`$attempt` is the absolute attempt directory. Candidate and verification stages
require a clean checkout at the candidate commit; integration requires a clean
checkout at the result. The standalone validator reads records and Git state;
it performs no merge, test execution, or ticket edits. Exit `0` allows the transition, `1` means
invalid records or Git state, and `2` means valid records with a failing,
unavailable, or rework verdict that cannot advance. Candidate-stage unavailable
checks may proceed to a verifier, who must resolve them before `PASS`.

Validation covers format, evidence-file existence, actor separation, commit
identity/ancestry, criterion coverage within the records, the verdict digest, and
runner receipt execution facts, scope, result, content binding and evidence
integrity. Reviewers still select appropriate coverage and judge manual evidence
and applicability. Receipts are execution evidence, not a security attestation
against deliberate forgery.

Use ordinary completion messages such as `candidate ready: <path> (<commit>)`,
`verification: <path> REWORK`, or `integration: <path> integrated`. Records carry
the details; the coordinator reads them when the state changes.

When changing the helper, run its self-contained CLI tests from the workspace
root; they create isolated Git repositories under `tmp/implement-spec-enhanced-tests/`:

```powershell
.venv\Scripts\python.exe tools/check.py run --check pytest --test .agents/skills/implement-spec-enhanced/tests
```
