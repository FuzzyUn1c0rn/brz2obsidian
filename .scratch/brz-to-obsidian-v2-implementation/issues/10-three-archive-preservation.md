# 10: Independently verify complete preservation across all three real archives

Status: claimed

Assignee: /root/v2_implement_10

Labels: ready-for-agent

Published: 2026-10-04 after the user approved the 11-slice breakdown and dependencies.

**Specification:** [Version 2 implementation specification](../spec.md)

**Implementation set:** [Version 2 implementation index](../README.md)

**Source-feature comparison:** [Accepted representations and limitations](../source-feature-mapping.md)

**What to build:** The complete Software Engineering archive and both earlier archives convert into fresh vaults, with source-derived preservation and reproducibility evidence independent of production expectations.

**Blocked by:** [09: Prove the combined v2 workflow, publication safety and source neutrality](09-integrated-v2-publication-reuse.md).

**Specification stories:** 1–33, 41–42, 52–65, 72–74, 78–82.

## Acceptance criteria

- [ ] For each exact fingerprinted archive, run fresh exact, repeated and ZIP/root-record reordered conversions, producing nine complete accepted outputs without modifying source archives.
- [ ] Extend the independent acceptance auditor using raw archives/outputs as expected facts; do not import production normalization/planning or treat production counts/manifests as the oracle.
- [ ] Prove conservation of every record/field/history/identity, present payload hash/length, original backup/authored span/reference, classification assignment, graph/tag membership, created/uncreated target and materialization reason, exact warning conjunct, support/configuration artifact and actual inventory.
- [ ] Independently prove the new archive's seven definitions, all 195 typed members and membership sizes, explicit member icon override, exceptional active note/image, four zero-length source gaps, four intact PDFs and four reviewed videos while auditing all 372 items, 693 relationships, 254 attachment records and 232 present payloads.
- [ ] Verify earlier source tag, hierarchy, note/reference/resource, empty-target, warning and publication behavior under the accepted v2 output/schema additions.
- [ ] Add meaningful corruption proofs showing that independent checks detect missing/altered source material, incorrect assignments/selection, fabricated warnings and missing/tampered support artifacts. Record repeat/reorder equivalence exceptions for original evidence ordering, source fingerprints and explicit run metadata.
- [ ] Keep raw inputs, outputs, receipts and extracts ignored/private; publish aggregate coverage, discrepancies, commands and limitations. Repair failures through the responsible feature boundary and repeat affected/full acceptance as justified.

## Testing boundaries

Independent full-archive exact/repeat/reordered audit and its synthetic corruption controls; use the completed integrated converter, not the prototype or convention checker as preservation proof.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-05 (/root): Claimed after ticket 09 resolved and integrated at `f570a663475266b9c95eb09688f5ccaf29c06af7`, with 671 cumulative tests and all lint/format/dependency/import/diff gates passing. Installed root metadata now matches package/module 0.2.0 and runtime PyYAML; source format and independently versioned schemas are unchanged. Isolated implementation will extend the stdlib/raw-source independent oracle and corruption controls, then produce nine fresh exact/repeat/reordered accepted outputs in a new short ignored destination. Source fingerprints, raw materialization/naming/reference expectations and archive immutability govern acceptance; production counts or manifests are not the expected-fact oracle. Final actual native review and user verdict remain ticket 11.
- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
