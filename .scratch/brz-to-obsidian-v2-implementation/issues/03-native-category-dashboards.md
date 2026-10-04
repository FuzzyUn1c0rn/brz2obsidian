# 03: Browse categories through rename-safe native dashboards

Status: claimed

Assignee: /root/v2_implement_03

Labels: ready-for-agent

Published: 2026-10-04 after the user approved the 11-slice breakdown and dependencies.

**Specification:** [Version 2 implementation specification](../spec.md)

**Implementation set:** [Version 2 implementation index](../README.md)

**Source-feature comparison:** [Accepted representations and limitations](../source-feature-mapping.md)

**What to build:** Home opens a Categories overview, and category notes embed native Members/Gallery Bases with complete discovery and live icon inheritance.

**Blocked by:** [02: Preserve canonical properties, source dates and editable icon snapshots](02-properties-dates-icon-snapshots.md).

**Specification stories:** 5, 15–20, 23–34, 39, 49–50, 74, 80.

## Acceptance criteria

- [ ] Enable/configure the bundled Bases plugin in this slice's generated vault so its dashboards work before template support lands. Include the required native configuration in verified publication and artifact accounting, without requiring a community plugin or copying unrelated reference settings.
- [ ] Discover actual memberships through linked category properties and the embedding category identity; a hierarchy/prose/provider link alone is not membership.
- [ ] Contextual member queries remain applicable after link-preserving category renames; document that users open member views through the category dashboard rather than a standalone Base without an embedding category.
- [ ] Exclude Templates/Attachments support deliberately; keep legitimate Template-named members. The overview uses the category tag and folder role guard and excludes ordinary source tags or same-basename ordinary notes.
- [ ] Tables start Icon, Note, Inheritance, categories, created, updated, with deterministic note sorting; the overview starts Icon then Category. Gallery uses native images. The decorative Appearance display is absent.
- [ ] Category icon changes update inherited views; member overrides win. Provider reordering/addition does not reselect defaults. Blank opt-out and invalid/dangling/nonmember providers behave as specified, without rewriting body-icon snapshots.
- [ ] Every generated Base/embed/overview and its reserved names is included in publication/accounting; original Home content and entry/bookmark behavior remain available.
- [ ] Perform an early bounded native check on a converter-produced synthetic vault to confirm contextual query, image and rename behavior. Keep that evidence separate from final full-output acceptance.

## Testing boundaries

Workflow-generated Base/frontmatter/guard fixtures plus the prior prototype's native scenarios repeated on this slice's actual output.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-05 (/root): Claimed after ticket 02 was resolved and merged with independent cumulative checks. The implementer owns generated dashboards and their automatic evidence; root performs the required bounded Computer check on a fresh converter-produced synthetic review copy before resolution.

- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
- 2026-10-04 (/root): Independent documentation validation assigned minimum Bases enablement to this dashboard slice, where the first native Base check requires it. Ticket 04 retains that configuration while adding native Templates. Ticket sizes and blockers are unchanged.
