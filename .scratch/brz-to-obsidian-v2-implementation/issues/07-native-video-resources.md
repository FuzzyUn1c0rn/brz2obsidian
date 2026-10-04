# 07: Present reviewed video resources without changing their source URLs

Status: ready-for-agent

Labels: ready-for-agent

Published: 2026-10-04 after the user approved the 11-slice breakdown and dependencies.

**Specification:** [Version 2 implementation specification](../spec.md)

**Implementation set:** [Version 2 implementation index](../README.md)

**Source-feature comparison:** [Accepted representations and limitations](../source-feature-mapping.md)

**What to build:** Converted reviewed YouTube resources retain exact clickable URLs and provide a usable native embed with the evidenced timing intent.

**Blocked by:** [01: Convert thought types and all their members into linked category notes](01-typed-category-conversion.md).

**Specification stories:** 8–10, 58–63, 74, 80.

## Acceptance criteria

- [ ] Preserve original URL spelling/query parameters and VideoHtml evidence while deriving native presentation from validated reviewed provider facts, not executing archived iframe HTML.
- [ ] Offer the embed alongside the retained original link and account separately for any derived embed URL and timing adaptation, including the demonstrated 18-second start.
- [ ] Do not fetch/download remote resources during inspection/conversion, invent a local video payload or silently support unreviewed video semantics/providers.
- [ ] Explain remote/offline/service dependence once in report/guide, without treating an unavailable remote preview as missing archived bytes or hiding the original link.
- [ ] Verify native rendering/playback/timing on a review copy of converter-produced output when service availability permits; record material limits honestly and leave playback paused.

## Testing boundaries

Workflow/CLI exact URL/evidence/native-embed fixtures and no-fetch behavior; bounded Computer comparison using the established resource scenarios.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
