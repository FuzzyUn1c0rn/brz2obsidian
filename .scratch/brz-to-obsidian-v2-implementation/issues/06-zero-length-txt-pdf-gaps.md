# 06: Report the zero-length absent TXT pattern while preserving PDFs

Status: resolved

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

- [x] Recognize only the specified new versioned rule: correct owner/role/TXT location, zero length, state 2, absent bytes and the unique same-owner filename-stem/PDF-identity association with intact normally verified PDF bytes.
- [x] Require every predicate conjunct; wrong state/length/stem/owner/role, ambiguous association or absent/corrupt PDF remains a refusal with no publication.
- [x] Retain the earlier positive-length missing-TXT and icon-length rules unchanged; unknown profile/rule/disposition evidence cannot downgrade failures.
- [x] Return warnings/exit 2 with each declaration and association recorded individually. Add the source-filename notice only on an existing owner note, without making a note solely for the gap, fake TXT bytes or a usable broken local link.
- [x] Preserve PDFs byte-for-byte and explain vault Search's PDF-body limitation once in report/guide, separately from source-gap warnings. Do not claim optional-cache purpose, extraction failure or fresh-restore search equivalence.

## Testing boundaries

Workflow accepted/refused synthetic PDF/TXT fixtures with independent mutations for each conjunct and combinations; existing warning/CLI/accounting/byte tests.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-05 (/root/v2_implement_06): Implemented the separate `thebrain-format5/zero-length-absent-txt/v1` recognition and exact reviewed disposition. All existing scalar/identity/ownership/role/path/state/present-byte/CRC/length guards remain. Deferred zero-length recognition joins the TXT stem to exactly one same-owner ordinary PDF attachment identity after normal verification. Each finding retains the TXT record, meta state, associated PDF record and payload evidence, filename/identity association, declared and actual PDF length, SHA-256 and verified CRC fact. The older positive-length rule retains its earlier same-owner PDF semantics and the icon discrepancy rule is unchanged.

- 2026-10-05 (/root/v2_implement_06): Public synthetic ZIP tests in [the zero-length workflow suite](../../../tests/application/test_zero_length_txt_workflow.py) cover accepted read-only inspection and verified publication, forty independent/combined source-corruption controls, multiple-PDF identity-versus-filename matching, eleven public analysis policy/evidence controls, JSON/text CLI exit 2, per-declaration record/notice/no-fabrication, byte-exact PDF/icon copying and repeated/reordered output alongside both earlier warning rules. A zero-byte normally verified file plus absent declaration on an otherwise empty owner proves the finding alone creates no note. The first accepted fixture failed with the earlier rule before implementation; a separate report-limit fixture failed before adding its paragraph. All source bytes and empty destinations remain unchanged on refusal.

- 2026-10-05 (/root/v2_implement_06): A single conditional PDF-body vault Search paragraph appears in the human migration report before individual Source warnings. It explains preserved/native-openable PDFs without claiming extraction, indexing, equivalent body search or the cause/purpose of absent TXT bytes. The coverage table documents the separate rule and limits. Native actual-PDF opening and all-three-archive preservation remain later delivery gates; no private source content, native acceptance or finished-v2 claim is made here.

- 2026-10-05 (/root/v2_implement_06): Project interpreter `C:/Users/stefa/projects/brz2obsidian/.venv/Scripts/python.exe`, per-process worktree `PYTHONPATH`, import confirmed in this worktree; no shared installation mutation. After merging current integration `a8e54a2`: `pytest -q` **443 passed**; Ruff lint passed; Ruff format check **74 files** passed; `pip check` clean; `git diff --check` clean. The feature/earlier verified-coverage subset passed **143 cases** before the metadata integration. All acceptance criteria are satisfied at their specified public boundaries.

- 2026-10-04 (/root): Claimed after resolved ticket 01 and integration of 05 freed the shared attachment boundary. Work preserves the earlier rules while adding the separately versioned zero-length TXT/PDF finding.

- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
