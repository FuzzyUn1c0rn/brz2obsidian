# 02: Preserve canonical properties, source dates and editable icon snapshots

Status: claimed

Assignee: /root/v2_implement_02

Labels: ready-for-agent

Published: 2026-10-04 after the user approved the 11-slice breakdown and dependencies.

**Specification:** [Version 2 implementation specification](../spec.md)

**Implementation set:** [Version 2 implementation index](../README.md)

**Source-feature comparison:** [Accepted representations and limitations](../source-feature-mapping.md)

**What to build:** Converted objects expose the documented linked metadata and source-derived calendar dates, with preserved local icon images and migration-time body-icon references that users can edit.

**Blocked by:** [01: Convert thought types and all their members into linked category notes](01-typed-category-conversion.md).

**Specification stories:** 6–10, 13–14, 28–33, 41–44, 61, 74, 78–80.

## Acceptance criteria

- [ ] Serialize the complete agreed canonical property core safely for every created imported source-item note, including ordinary thoughts, type definitions and materialized source-tag thoughts. Retain source tags and imported identity pairs without inferring semantic fields or aliases from prose or treating a source tag as a category. A synthetic authored source-tag case proves that its source IDs, source-derived calendar dates and existing native tag behavior survive together.
- [ ] Imported dates use valid source thought calendar components; missing values stay empty, populated invalid values do not receive invented dates, and full timestamp strings/migration time remain distinct evidence.
- [ ] Preserve declared icons/colours and own labels, including the member-owned icon precedence and opaque token evidence; no synthesized inherited member label or unsupported colour interpretation.
- [ ] Copy icons once through preserved ownership, reference the migration-time effective image inside created notes, keep decorative assets out of Resources, and leave untyped icon-only items under the existing materialization policy.
- [ ] Explicit member icon, optional provider and declared colour fields remain distinguishable from inherited defaults; record provenance/adaptations and byte obligations without changing authored Markdown outside permitted spans.
- [ ] Existing authored headings, original backups, code, blockquotes, Unicode and newline spelling remain preserved alongside the generated additions.

## Testing boundaries

Actual converted frontmatter/body/resources and evidence through Workflow, including an authored source-tag case with populated source dates and identity; focused existing reference-span/public renderer contracts where necessary.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-04 (/root): Claimed after ticket 01 was merged and independently checked on the integration branch. Isolated implementation owns canonical properties, dates and icon snapshots; the attachment candidate change runs separately in ticket 05.

- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
- 2026-10-04 (/root): Independent documentation validation made materialized source-tag notes explicit in canonical metadata/date coverage and its synthetic verification case. This preserves the existing source-tag semantics and does not expand the agreed source feature boundary.
