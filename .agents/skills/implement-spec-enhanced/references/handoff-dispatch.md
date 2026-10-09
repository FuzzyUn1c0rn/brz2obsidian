# Handoff dispatch

Read this before assigning a stage or a commit-derived attempt. Read the
[common contract](handoffs.md) first; give the receiving agent its applicable
[stage reference](handoffs.md#stage-reading-paths) and requirements path.

### Dispatch and commit handshake

Initial implementer dispatch supplies ownership, integration branch, assessed
checkout, and a reserved candidate-input path. At integration synchronization,
capture the full incorporated tip as `base_ref`; then finish checks and commit.
The implementer reports the commit and clean checkout before publication. Only
then can the coordinator assign the exact unused commit-derived attempt path.
The coordinator returns that absolute attempt, assessed checkout, input path,
and candidate command; the implementer places evidence at the final resolved
locations, writes its input, publishes, and runs standalone candidate validation.
Before this allocation, evidence can be prepared elsewhere under the effort.

Verifier and merger dispatches each supply the same exact assigned attempt,
their actual assessed checkout, their own stage-input path, and stage command.
Include absolute interpreter/script paths when the receiving agent may run in
another checkout; for example, resolve them once in the integration checkout:

```powershell
$python = (Resolve-Path .venv/Scripts/python.exe).Path
$writer = (Resolve-Path .agents/skills/implement-spec-enhanced/scripts/write_handoff.py).Path
$validator = (Resolve-Path .agents/skills/implement-spec-enhanced/scripts/validate_handoff.py).Path
# $attempt, $assessedCheckout, and $stageInput are coordinator-supplied absolute paths.
& $python $writer candidate $attempt --checkout $assessedCheckout --input $stageInput --requirements $stageRequirements
& $python $validator $attempt --stage candidate --checkout $assessedCheckout --requirements $stageRequirements
```

The linked stage examples use checkout-relative script paths for readability;
dispatch the resolved equivalents. Workers use the assigned path rather than
discovering a latest attempt or allocating a number. Report the exact published
path and both writer/validator outcomes. Exit `0` permits advancement, `2` holds
the transition with complete published records, and `1` refuses or fails the
operation; carry-forward has the [partial-attempt recovery rules](handoff-retry.md).
