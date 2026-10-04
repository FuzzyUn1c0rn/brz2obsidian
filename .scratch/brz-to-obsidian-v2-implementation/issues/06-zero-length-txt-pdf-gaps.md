# 06: Report the zero-length absent TXT pattern while preserving PDFs

Status: claimed

Assignee: /root/v2_implement_06

Labels: ready-for-agent

Published: 2026-10-04 after the user approved the 11-slice breakdown and dependencies.

**Specification:** [Version 2 implementation specification](../spec.md)

**Implementation set:** [Version 2 implementation index](../README.md)

**Source-feature comparison:** [Accepted representations and limitations](../source-feature-mapping.md)

**What to build:** A reviewed zero-length absent TXT declaration beside its identity-associated intact PDF converts successfully with an explicit source-gap warning and no fabricated file.

**Blocked by:** [01: Convert thought types and all their members into linked category notes](01-typed-category-conversion.md).

**Specification stories:** 8, 54–57, 61–65, 73–74, 80.

## Acceptance criteria

- [ ] Recognize only the specified new versioned rule: correct owner/role/TXT location, zero length, state 2, absent bytes and the unique same-owner filename-stem/PDF-identity association with intact normally verified PDF bytes.
- [ ] Require every predicate conjunct; wrong state/length/stem/owner/role, ambiguous association or absent/corrupt PDF remains a refusal with no publication.
- [ ] Retain the earlier positive-length missing-TXT and icon-length rules unchanged; unknown profile/rule/disposition evidence cannot downgrade failures.
- [ ] Return warnings/exit 2 with each declaration and association recorded individually. Add the source-filename notice only on an existing owner note, without making a note solely for the gap, fake TXT bytes or a usable broken local link.
- [ ] Preserve PDFs byte-for-byte and explain vault Search's PDF-body limitation once in report/guide, separately from source-gap warnings. Do not claim optional-cache purpose, extraction failure or fresh-restore search equivalence.

## Testing boundaries

Workflow accepted/refused synthetic PDF/TXT fixtures with independent mutations for each conjunct and combinations; existing warning/CLI/accounting/byte tests.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-04 (/root): Claimed after resolved ticket 01 and integration of 05 freed the shared attachment boundary. Work preserves the earlier rules while adding the separately versioned zero-length TXT/PDF finding.

- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
