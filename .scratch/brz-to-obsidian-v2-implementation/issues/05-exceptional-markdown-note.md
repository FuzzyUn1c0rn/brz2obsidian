# 05: Convert the evidenced differently marked thought note safely

Status: resolved

Assignee: /root/v2_implement_05

Labels: ready-for-agent

Published: 2026-10-04 after the user approved the 11-slice breakdown and dependencies.

**Specification:** [Version 2 implementation specification](../spec.md)

**Implementation set:** [Version 2 implementation index](../README.md)

**Source-feature comparison:** [Accepted representations and limitations](../source-feature-mapping.md)

**What to build:** The sole unambiguous nonempty canonical NoteType-0 thought-note case becomes readable active Markdown with a working local image and exact original backup.

**Blocked by:** [01: Convert thought types and all their members into linked category notes](01-typed-category-conversion.md).

**Specification stories:** 6–10, 52–53, 61–63, 74, 80.

## Acceptance criteria

- [x] Promote only the specified thought-owned Type-1/NoteType-0 canonical Notes.md candidate on an ordinary owner, with normal state, ownership, length, CRC, decoded-content and supported-reference checks.
- [x] Preserve original bytes and numeric-marker evidence; adapt supported local image/thought references without changing other authored spans, code or line endings.
- [x] Retain empty-placeholder behavior and refuse competing active candidates, ambiguous roles, invalid required references and corrupt/missing payloads rather than selecting content by guesswork.
- [x] Do not promote arbitrary Markdown file attachments or infer that the different marker represents UI selection.
- [x] Show active-content eligibility/materialization, backup/copy obligations and reference adaptations consistently in inspection, conversion, reports and records.

## Testing boundaries

Workflow/CLI fixtures for accepted and competing/integrity/refusal cases, with existing public note/span boundaries for exact edits.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-04 (/root/v2_implement_05): Implemented on isolated branch `codex/brz-v2-05` from integration `c29382f`, with production/test commit `9050272`. The TheBrain attachment adapter admits the sole canonical nonempty NoteType-0 note only on an ordinary owner; existing integrity, candidate-conflict, reference, backup, accounting and publication machinery remains in force. No source-specific facts entered generic core/renderer contracts. Updated the scoped source-coverage row and limits.
- 2026-10-04 (/root/v2_implement_05): The first public Workflow test failed with the earlier nonempty-placeholder refusal, then passed after the ordinary-owner guard change. The dedicated synthetic-archive suite verifies both input orders, exact BOM/original backup/manifest hashes, CRLF/CR/LF and code/blockquote preservation, working image/thought edits, planned versus actual counts/receipt, retained numeric markers and report/record facts. It also proves competing marked candidates (including empty/BOM-only), definition/tag/system owners, missing bytes/state, length/CRC, invalid UTF-8, identity/ownership/role conflicts and unsupported/missing references refuse. Arbitrary/nested/lowercase Markdown files stay resources. The former unconditional whitespace-refusal test now verifies retained whitespace backup without forced materialization; existing BOM-only placeholder behavior is retained.
- 2026-10-04 (/root/v2_implement_05): Before and after merging the latest integration branch (already up to date), `C:/Users/stefa/projects/brz2obsidian/.venv/Scripts/python.exe` with this worktree's `src` on per-process `PYTHONPATH` passed all **359 tests**. Worktree import location was confirmed. Ruff lint passed, Ruff formatting checked 68 files, `pip check` found no broken requirements, and `git diff --check` passed. Thin CLI JSON inspect/convert tests verify clean/refused exits, planned obligations, verified actual receipt and no publication on conflict. No private archive, complete-conversion audit or native acceptance is claimed here; those remain later delivery gates.

- 2026-10-04 (/root): Claimed after ticket 01 was merged and independently checked on the integration branch. Isolated implementation owns the exceptional active-note candidate rule and its public tests; canonical properties are owned separately by ticket 02.

- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
