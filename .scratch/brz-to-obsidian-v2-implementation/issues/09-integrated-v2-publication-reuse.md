# 09: Prove the combined v2 workflow, publication safety and source neutrality

Status: ready-for-agent

Labels: ready-for-agent

Published: 2026-10-04 after the user approved the 11-slice breakdown and dependencies.

**Specification:** [Version 2 implementation specification](../spec.md)

**Implementation set:** [Version 2 implementation index](../README.md)

**Source-feature comparison:** [Accepted representations and limitations](../source-feature-mapping.md)

**What to build:** One complete synthetic conversion combines the new concepts with existing graph/tags/resources, passes the convention checker, and remains safe and reusable through public interfaces.

**Blocked by:** [05: Convert the evidenced differently marked thought note safely](05-exceptional-markdown-note.md), [06: Report the zero-length absent TXT pattern while preserving PDFs](06-zero-length-txt-pdf-gaps.md), [07: Present reviewed video resources without changing their source URLs](07-native-video-resources.md), [08: Check editable vault conventions through a read-only library and command](08-read-only-vault-checker.md).

**Specification stories:** 2–14, 17–22, 27–33, 38–42, 49–55, 58–65, 66–80.

## Acceptance criteria

- [ ] Publish and independently inspect a mixed-feature synthetic vault exercising classification/materialization, empty targets, graph/tags, icon/provider cases, canonical dates, dashboards/templates, exceptional active note, PDF/TXT gap and video URL metadata.
- [ ] Verify the full versioned library/CLI/report/record/configuration/count/manifest contracts, classification/support accounting, expected warnings and no hidden feature-specific partial successes.
- [ ] Extend source-change, path/collision, staging/stream/I/O, destination-race and teardown-failure controls to the new generated artifacts while preserving caller data, owned cleanup and honest retained receipts.
- [ ] Retain alternate-source substitution and inward-import proofs using opaque non-UUID identities and compatible current contracts; exercise new shared meanings independently of TheBrain decoding where applicable.
- [ ] Run cumulative public regression, lint/format and environment consistency checks; document intended v2 schema/output changes rather than weakening earlier acceptance behavior.

## Testing boundaries

Combined Workflow/CLI/checker actual-output fixture; existing public failure-protection, source-substitution and architecture boundaries. No private archive is required for these tests.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
