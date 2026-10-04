# 04: Create and extend objects with native templates and a maintenance guide

Status: ready-for-agent

Labels: ready-for-agent

Published: 2026-10-04 after the user approved the 11-slice breakdown and dependencies.

**Specification:** [Version 2 implementation specification](../spec.md)

**Implementation set:** [Version 2 implementation index](../README.md)

**Source-feature comparison:** [Accepted representations and limitations](../source-feature-mapping.md)

**What to build:** A user opens the generated vault, selects a full template for a new note, sees it discovered in the dashboard and can add a future category using documented starters.

**Blocked by:** [03: Browse categories through rename-safe native dashboards](03-native-category-dashboards.md).

**Specification stories:** 14, 19–20, 28, 32, 34–50, 74, 79–80.

## Acceptance criteria

- [ ] Retain and verify the bundled Bases configuration established by ticket 03; enable/configure bundled Templates, native property types, required Home/link preferences and template-folder/date insertion settings. Account for configuration without copying unrelated reference toggles or requiring community plugins.
- [ ] Deliver a generic template and complete templates for the actual categories with linked membership/provider, blank overrides, insertion-date variables and no imported source IDs or invented domain-specific schema.
- [ ] Deliver category-note, member-template and contextual Base starter examples that discover a manually classified future note using the same native mechanisms.
- [ ] Document template selection, lookup before creation, meaningful entity links, canonical vocabulary, source versus new identity, existing-note membership editing and explicitly maintained update dates.
- [ ] Existing memberships are edited directly; do not ship additive category-only templates or promise native protection against arbitrary full-template scalar overwrites.
- [ ] Native insertion on a new note initializes membership/dates, whereas a membership edit on an existing note preserves its established dates, content, provider and identity. User/agent extension does not depend on folders as the type system or registry fields.
- [ ] Document deliberate reference adaptations, dashboard entry points and editable snapshots; prove all support/configuration artifacts are manifested and collision-safe.

## Testing boundaries

Workflow actual template/configuration/starter bytes and a bounded Computer check of native insertion, existing-note property edits and future-category discovery.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
- 2026-10-04 (/root): Independent documentation validation moved first Bases enablement to ticket 03 so dashboards are independently usable; this slice preserves/verifies it and adds Templates and maintenance configuration. The approved dependencies are unchanged.
