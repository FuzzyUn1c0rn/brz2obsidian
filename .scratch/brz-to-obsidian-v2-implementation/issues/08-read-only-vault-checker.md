# 08: Check editable vault conventions through a read-only library and command

Status: ready-for-agent

Labels: ready-for-agent

Published: 2026-10-04 after the user approved the 11-slice breakdown and dependencies.

**Specification:** [Version 2 implementation specification](../spec.md)

**Implementation set:** [Version 2 implementation index](../README.md)

**Source-feature comparison:** [Accepted representations and limitations](../source-feature-mapping.md)

**What to build:** A human or agent checks a generated or manually edited vault and receives deterministic structural diagnostics without needing the source archive or modifying any note.

**Blocked by:** [04: Create and extend objects with native templates and a maintenance guide](04-native-templates-maintenance.md).

**Specification stories:** 30–31, 44, 48, 51, 66–72, 74–75, 78–80.

## Acceptance criteria

- [ ] Implement the specified source-independent public check_vault behavior and thin check-vault text/JSON command with the distinct strict versioned result envelope and clean/issues/failed outcomes and 0/2/1 exit semantics.
- [ ] Check known property cardinality/types, safe data-only frontmatter including malformed/duplicate keys, category role, provider membership/resolution, required Base/image targets and imported identity pairs/duplicates.
- [ ] Resolve qualified references deterministically; accept shortened links only when unambiguous and report ambiguous required category/provider/media references without choosing or rewriting a target.
- [ ] Permit unrelated custom properties, native date variables in template scope and intentional uncreated ordinary targets. Preserve blank provider opt-out versus invalid-provider diagnostics.
- [ ] Enforce contained reads, report unsafe required references without following them outside the vault, continue other readable notes after per-note problems, and expose unavailable measurements honestly on failures.
- [ ] Evaluate actual mutable vault state rather than trusting migration records; prove unchanged file bytes/inventory and document structural scope, deterministic diagnostics and separation from preservation verification.

## Testing boundaries

Public check_vault with real filesystem fixtures, command wrapper checks, malformed/ambiguous/custom/uncreated/template/containment/read-failure controls and before/after byte inventory comparisons.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
