---
name: handoff
description: Compact the current conversation into a handoff document for another agent to pick up.
argument-hint: "What will the next session be used for?"
disable-model-invocation: true
---

Write a handoff document summarising the current conversation so a fresh agent can continue the work. Save under `tmp/<effort>/` in the current checkout, following [workspace housekeeping](../../../docs/workspace.md).

For covered automated checks, include assessed checkout, interpreter and runner
pointers, independently recorded requirements, receipt path and outcome, and any
reuse reason. Follow [the check contract](../../../docs/testing.md#automated-check-runner);
text output alone is not completion evidence. Keep manual/native observations separate.

Include a "suggested skills" section in the document, naming which skills the next agent should call the Skill tool for.

Do not duplicate content already captured in other artifacts (specs, plans, ADRs, issues, commits, diffs). Reference them by path or URL instead.

Redact any sensitive information, such as API keys, passwords, or personally identifiable information.

If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.
