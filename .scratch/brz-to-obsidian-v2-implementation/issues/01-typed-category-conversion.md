# 01: Convert thought types and all their members into linked category notes

Status: claimed

Labels: ready-for-agent

Assignee: /root/v2_implement_01

Published: 2026-10-04 after the user approved the 11-slice breakdown and dependencies.

**Specification:** [Version 2 implementation specification](../spec.md)

**Implementation set:** [Version 2 implementation index](../README.md)

**Source-feature comparison:** [Accepted representations and limitations](../source-feature-mapping.md)

**What to build:** Inspect and convert a small reviewed Brain containing a type and typed members, including an otherwise empty member, into a verified fresh vault with distinct category/member notes and linked memberships. Ordinary native links and Backlinks make the objects navigable before later dashboard presentation lands.

**Blocked by:** None (can start immediately).

**Specification stories:** 2–4, 5–9, 11–22, 61–65, 76–79.

## Acceptance criteria

- [ ] Public inspect and its CLI command remain read-only, reporting consistent planned results without a publication receipt. Public convert and its CLI command publish the tiny typed fixture into a verified fresh vault, reporting consistent actual results and a durable receipt. Use version-2 contract/profile/renderer/result/migration schemas while retaining existing commands, workflow signatures and outcome/exit behavior.
- [ ] Validate type/instance field-link correspondence in both directions; conflicting, duplicate, missing, dangling or wrong-role assignments refuse without publication. Unreviewed subtype/custom-link meanings remain refused.
- [ ] Materialize every definition and typed ordinary member; preserve Home, ordinary graph/tags, the untyped-empty selection policy, source identity and deterministic collision-safe naming. Definition-owned authored content/resources survive as their own data, with no content inheritance into members.
- [ ] Retain system-to-type connections only as evidence; category names follow source identity/title rather than inferred pluralization or remapping.
- [ ] Demonstrate actual payload copying, original evidence, typed targets/counts/creation reasons and fresh-destination protection. Reserve the new support naming namespace needed by later slices without weakening Windows/path/collision protections.
- [ ] Update the test-only alternate source to the current strict contract; retain inward dependencies and opaque generic identities. Install any needed packages only inside the project environment.

## Testing boundaries

Workflow/CLI synthetic typed conversion and assignment-corruption controls; existing public naming/graph/tag/source/contract/architecture checks.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
- 2026-10-04 (/root): Independent documentation validation clarified that inspect remains read-only and only convert publishes. The approved behavior and dependencies are unchanged.
- 2026-10-04 (/root): Claimed for implementation in an isolated worktree based on codex/brz-to-obsidian-v2. The user invoked implement-spec; approved TDD seams are already confirmed in the specification.
