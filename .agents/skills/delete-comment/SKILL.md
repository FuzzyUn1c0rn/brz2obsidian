---
name: delete-comment
description: Audit and retire Python comments with the repository's shrinking lint baseline. Use for comment cleanup or when invoking /delete-comment.
---

# Delete comment

Review the requested files in the current checkout. Use Python's tokenizer to
find standalone and inline comments. Read the surrounding code, its consumers
or tests, and the applicable ADR before deciding what each comment contributes.
A hash in a string or fixture is program data.

- **Tautology** repeats what the code already shows. Delete it.
- **Stale** describes superseded code or context. Verify the discrepancy and
  delete it.
- **Excuse** explains away a concrete implementation problem. Check the existing
  issues, then file or link a focused fix with evidence and acceptance checks.
  Delete the prose and leave the implementation repair to that issue.
- **Decision Record** preserves a meaningful trade-off or an otherwise invisible
  constraint. Add it to the closest ADR or create one following the
  [domain guidance](../../../docs/agents/domain.md), then delete the prose.

For a tool directive or encoding marker, establish its effect before retiring
it. Leave it in the baseline when this pass cannot safely replace its effect.
Use the [issue-tracker convention](../../../docs/agents/issue-tracker.md) for
follow-up issues. Keep an inventory under `tmp/<effort>/` when auditing a large
scope, with the original path and line, category, disposition, and ADR or issue
where applicable.

From the repository root, prune retired entries using the project interpreter:

```powershell
.\.venv\Scripts\python.exe -m tools.check_lint --prune-comments
```

Use [the check runner](../../../docs/testing.md#automated-check-runner) for lint,
format, and any affected tests. Inspect the diff for changes to code and fixture
bytes. Report standalone lines removed, inline comments removed, and the
remaining baseline. A partial pass may leave existing comments for a later
review.
