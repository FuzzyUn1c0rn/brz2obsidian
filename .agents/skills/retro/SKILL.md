---
name: retro
description: "Review a coding session and recommend evidence-backed improvements to agent guidance, tooling, checks, and information access. Use when the user requests a retrospective."
---

# Retro

Identify changes to the coding agent's environment that would improve future
sessions. A retrospective produces recommendations; implement changes only when
the user's request also authorizes them.

## Gather evidence

Use the session the user specifies, defaulting to the current conversation.
Read relevant primary evidence: messages, tool results, diffs, check receipts,
and the guidance in effect during that session. Search session logs only when
needed to resolve a specific gap, and limit retrieval to the relevant session.
If evidence is unavailable, state the limitation and qualify the finding.

Distinguish observed failures or delays from inferred causes. Check applicable
instructions and existing tooling before proposing a replacement. An instruction
added after the session cannot explain the agent's earlier behavior.

## Identify useful improvements

Consider the categories supported by the evidence; there is no required quota.

- **Navigation:** repeated searches, hidden dependencies, or missing pointers
  that delayed finding relevant code or guidance.
- **Automated checks:** mistakes a reliable check could catch, or existing checks
  that were skipped, unwired, or broken. Read
  [the repository runner contract](../../../docs/testing.md#automated-check-runner)
  and relevant CI configuration before evaluating coverage. Run covered checks
  through that runner when execution is needed. Prefer extending existing checks;
  weigh new automation against recurrence, impact, and maintenance cost.
- **Coding standards:** ambiguous or missing guidance that contributed to a
  mistake. Prefer deterministic checks for mechanical rules when practical;
  document judgement calls with enough context for implementation and review.
- **Agent guidance:** conflicting, duplicated, outdated, or ineffective
  instructions. Keep broadly applicable constraints and navigation in
  `AGENTS.md`; move substantial task-specific detail to relevant documentation
  or skills when that improves discovery. Length alone is not a defect.
- **Tool economy:** repeated or oversized calls whose time or context cost can
  be reduced without losing evidence needed for the task.
- **Information access:** missing logs, documentation, or read access that blocked
  a decision. Recommend the minimum useful access and identify any permission
  needed before it can be granted.

Choose the smallest change that addresses the observed cause. Reuse existing
documentation and tools. Do not turn an isolated incident into a universal rule
without explaining why the broader rule is warranted. Preserve successful
practices when they help explain what should continue.

## Report recommendations

Present actionable candidates in order of impact, using concise plain language.
For each, include:

- The observed problem and a specific evidence pointer.
- The likely cause, with uncertainty stated where relevant.
- The proposed change and its target file, tool, or workflow.
- The expected benefit, material cost or tradeoff, and how to verify improvement.

Report only supported findings. If the session provides no worthwhile candidates,
say so. Follow the repository's existing workflow if the user also requests
implementation or issue tracking; a retrospective alone does not authorize
changes to shared services, global configuration, or access permissions.
