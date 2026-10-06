# 06: Extend the independent raw-source audit to the new conversion policy

Status: claimed
Assignee: /root/independent_audit_implementer
Approved: 2026-10-06
Specification: [Accepted conversion specification](../spec.md)

**What to build:** Independently verify the new converter output against raw original records and payloads, detecting plausible but incomplete or misleading vaults. The acceptance driver can run all four required originals with repeat and reorder proof.

**Blocked by:** [03 — Keep category dashboards usable through missing type notes and icons](03-type-source-gaps.md); [04 — Preserve ordinary-to-category hierarchy in both directions](04-category-hierarchy.md). This reusable audit can proceed alongside the combined publication-safety proof.

## Acceptance criteria

- [ ] Extend the existing standard-library-only independent oracle and preserve its import-boundary checks. Derive included identities, references, safe evidence, selections/paths, graph/assignments, supplied-body expected adaptations, absent-declaration predicates, image eligibility/associations/order and provider effects directly from raw original source facts. Production filtered snapshots/counts/dispositions/manifests are observed output, never expected preservation truth.
- [ ] Audit exact safe originals and all required payload hashes/lengths, every supplied-body edit, authored-reference accounting, explicit generated presentation obligations, resolving diagnostic links, raw state/path/length/outcome, complete category membership/hierarchy/native support and excluded-content absence. Do not infer recovery, emptiness or original-note bytes for absent bodies.
- [ ] Positive public synthetic controls exercise all behavior slices and earlier supported cases independently. Corruption controls falsify included-body text, unsafe/safe evidence, excluded identities/owned bytes/labels, missing/duplicate/misowned/generated-order embeds, gap predicates, fabricated originals/reference credit, neutral/provider/override effects, graph/membership/navigation and diagnostics.
- [ ] Corruption tests recompute counts and file receipts consistently before rejection, proving semantic preservation rather than only manifest mismatch. A structurally valid forged receipt or clean production convention checker cannot mask each corruption. Retain meaningful existing controls and no private archive in public tests.
- [ ] Extend the three-input driver to a fourth mandatory original argument while retaining previous arguments/fingerprint pins. Help, documentation and an executed synthetic example identify all four originals and a fresh short ignored output location; verify selected code import/current version. Do not hard-code 0.2.0 or treat a comparison/recovery backup as the fourth source.
- [ ] Driver supports exact/repeat/ZIP-and-root-record reorder for each input: 12 complete outputs. Independently prove root-record multisets and physical payload equality, and reject changed/omitted/duplicated reordered records/payloads. Hash originals before/after operations and at completion; fail if final fingerprint drifts.
- [ ] Keep source-required oracle behavior distinct from source-free check_vault, mutable UI conventions and production accounting. Real raw records/assets/audit outputs remain local and ignored; public records summarize aggregate gates and honest failures only.
- [ ] Existing public oracle/driver tests stay green. Record reproducible tool usage and bounded synthetic/corruption proof; completing tooling does not claim the four private archives have passed.

## Verification boundary

Existing independent raw-source oracle/driver public callables and CLI with synthetic archives and real files. Standard-library/local independent support only; do not import production interpretation helpers to compute expectations.

## Specification coverage

User Stories 16–20, 32–39, 41–49, 54–65, 68–70; Implementation Decisions 1–25 as independently audited obligations; Testing Decisions 5–10, 12–17, 20.

## Comments

- 2026-10-06 (/root): Claimed after independently verified tickets 03 and 04
  were integrated. Implement the independent raw-source oracle and four-input
  driver in an isolated managed worktree based on integration
  `4d515a62b2ba6552e8e7ca513615cf1b7ffa839c`. Existing independent decoder research
  and bounded host probe inform the implementation; they do not complete the
  full-source gate, which remains ticket 07.

- 2026-10-06 (/root): Published after the user approved all nine tickets and their
  dependencies, then explicitly invoked implement-spec for complete implementation.
