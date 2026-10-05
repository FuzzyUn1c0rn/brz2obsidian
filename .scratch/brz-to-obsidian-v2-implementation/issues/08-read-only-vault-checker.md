# 08: Check editable vault conventions through a read-only library and command

Status: resolved

Assignee: /root/v2_implement_08

Labels: ready-for-agent

Published: 2026-10-04 after the user approved the 11-slice breakdown and dependencies.

**Specification:** [Version 2 implementation specification](../spec.md)

**Implementation set:** [Version 2 implementation index](../README.md)

**Source-feature comparison:** [Accepted representations and limitations](../source-feature-mapping.md)

**What to build:** A human or agent checks a generated or manually edited vault and receives deterministic structural diagnostics without needing the source archive or modifying any note.

**Blocked by:** [04: Create and extend objects with native templates and a maintenance guide](04-native-templates-maintenance.md).

**Specification stories:** 30–31, 44, 48, 51, 66–72, 74–75, 78–80.

## Acceptance criteria

- [x] Implement the specified source-independent public check_vault behavior and thin check-vault text/JSON command with the distinct strict versioned result envelope and clean/issues/failed outcomes and 0/2/1 exit semantics.
- [x] Check known property cardinality/types, safe data-only frontmatter including malformed/duplicate keys, category role, provider membership/resolution, required Base/image targets and imported identity pairs/duplicates.
- [x] Resolve qualified references deterministically; accept shortened links only when unambiguous and report ambiguous required category/provider/media references without choosing or rewriting a target.
- [x] Permit unrelated custom properties, native date variables in template scope and intentional uncreated ordinary targets. Preserve blank provider opt-out versus invalid-provider diagnostics.
- [x] Enforce contained reads, report unsafe required references without following them outside the vault, continue other readable notes after per-note problems, and expose unavailable measurements honestly on failures.
- [x] Evaluate actual mutable vault state rather than trusting migration records; prove unchanged file bytes/inventory and document structural scope, deterministic diagnostics and separation from preservation verification.

## Testing boundaries

Public check_vault with real filesystem fixtures, command wrapper checks, malformed/ambiguous/custom/uncreated/template/containment/read-failure controls and before/after byte inventory comparisons.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-05 (/root/v2_implement_08): Implemented the public source-free `brz2obsidian.vault_check.check_vault` package, separate strict/closed/frozen `brz2obsidian.vault-check` version-1 contracts and thin check-vault text/JSON command. Migration wiring is lazy and retained only for inspect/convert. Public synthetic real-filesystem tracers cover properties/data-only YAML, nested/merge duplicates, role-before-membership rules, provider opt-out/invalid states, paired opaque identities/duplicates, dotted/qualified/shortened/NFC-colliding references, active Base/images versus code/comments, native punctuation, contained relative/encoded images, drive/UNC/device/file traversal, linked files and actual Windows child/root junctions. Per-note/Base/enumeration read failures continue readable files, retain known diagnostics and report null unavailable totals; unreadable category roles do not fabricate invalid membership/provider conclusions. Complete inventory and byte-hash comparisons prove normal/problem/failure runs preserve arbitrary caller files, with equal repeat results and JSON round-trips.
- 2026-10-05 (/root/v2_implement_08): Final checks used `C:/Users/stefa/projects/brz2obsidian/.venv/Scripts/python.exe` with this isolated worktree's `src` on process PYTHONPATH; import location was confirmed. `-m pytest -q --tb=short`: **564 passed** (including **69** checker/CLI controls). `-m ruff check --no-cache .`: passed; `-m ruff format --check .`: **102 files formatted**; `-m pip check`: no broken requirements; `git diff --check`: passed. Installed console and module check-vault agree with the API on 0/2/1 outcomes; import barriers preserve inward dependencies. Final integration `0e9d4b1090dac87bec4043e71d75f26b4f1d9d6b` was verified and merged (already contained). A temporary public synthetic typed/template conversion followed by check_vault returned clean over 21 files, 11 Markdown, 4 Bases, 1 category and 3 imported notes with unchanged bytes/inventory; this bounded compatibility smoke does not complete ticket 09.
- 2026-10-05 (/root/v2_implement_08): PyYAML's existing 6.0.3 exact pin remains coherent while its family moves from dev extras into needed runtime dependencies; no install or shared editable repoint occurred. [Checker usage/schema/codes/counts/limits](../../../docs/vault-checker.md), README, architecture/testing docs and the actual generated Vault guide now document read-only current-state structural checks, custom/uncreated/template allowances and preservation separation. Native quoted ISO date variables are supported without substitution; an unquoted-variable preprocessing extension is not included. Image decoding/native rendering, complete Base query semantics, all-purpose broken-link checking, continuing dates, exact configuration and atomic snapshots remain outside the documented structural scope. No private archive or GUI work was performed; 09–11 and final v2 delivery remain open.

- 2026-10-05 (/root): Claimed after ticket 04's complete native template gate and integration at 3b120c9. The corrected quoted date variables survived native category rename and subsequent insertion. Implement in an isolated worktree using the public source-free checker/CLI seam and project virtual environment; no full-v2 acceptance is inferred.

- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
