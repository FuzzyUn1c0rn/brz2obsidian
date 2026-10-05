# 09: Prove the combined v2 workflow, publication safety and source neutrality

Status: resolved

Assignee: /root/v2_implement_09

Labels: ready-for-agent

Published: 2026-10-04 after the user approved the 11-slice breakdown and dependencies.

**Specification:** [Version 2 implementation specification](../spec.md)

**Implementation set:** [Version 2 implementation index](../README.md)

**Source-feature comparison:** [Accepted representations and limitations](../source-feature-mapping.md)

**What to build:** One complete synthetic conversion combines the new concepts with existing graph/tags/resources, passes the convention checker, and remains safe and reusable through public interfaces.

**Blocked by:** [05: Convert the evidenced differently marked thought note safely](05-exceptional-markdown-note.md), [06: Report the zero-length absent TXT pattern while preserving PDFs](06-zero-length-txt-pdf-gaps.md), [07: Present reviewed video resources without changing their source URLs](07-native-video-resources.md), [08: Check editable vault conventions through a read-only library and command](08-read-only-vault-checker.md).

**Specification stories:** 2–14, 17–22, 27–33, 38–42, 49–55, 58–65, 66–80.

## Acceptance criteria

- [x] Publish and independently inspect a mixed-feature synthetic vault exercising classification/materialization, empty targets, graph/tags, icon/provider cases, canonical dates, dashboards/templates, exceptional active note, PDF/TXT gap and video URL metadata.
- [x] Verify the full versioned library/CLI/report/record/configuration/count/manifest contracts, classification/support accounting, expected warnings and no hidden feature-specific partial successes.
- [x] Extend source-change, path/collision, staging/stream/I/O, destination-race and teardown-failure controls to the new generated artifacts while preserving caller data, owned cleanup and honest retained receipts.
- [x] Retain alternate-source substitution and inward-import proofs using opaque non-UUID identities and compatible current contracts; exercise new shared meanings independently of TheBrain decoding where applicable.
- [x] Run cumulative public regression, lint/format and environment consistency checks; document intended v2 schema/output changes rather than weakening earlier acceptance behavior.

## Testing boundaries

Combined Workflow/CLI/checker actual-output fixture; existing public failure-protection, source-substitution and architecture boundaries. No private archive is required for these tests.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-05 (/root): Integrated at `f570a663475266b9c95eb09688f5ccaf29c06af7`; merger independently reconfirmed all 671 tests, Ruff lint/format (108 files), pip consistency and clean ancestry/import/diff checks. After worker/merger completion, refreshed the same root editable installation using the project interpreter and `-m pip install --no-build-isolation --no-deps -e .`. Installed distribution, project and module versions now agree at 0.2.0; editable origin/imports remain root `src`; runtime requirements correctly include PyYAML and the installed 6.0.3 satisfies it. `pip check` passes and tracked checkout stays clean. This clears the deferred metadata refresh without redirecting a shared active-worker installation; the full archive and native/user gates remain 10–11.
- 2026-10-05 (/root/v2_implement_09): Completed in isolated `codex/brz-v2-09`, implementation commit `2db9aa4`, merged latest root integration `9c83397` through `c74a698`. Combined actual synthetic ZIP independently verifies all 12 source items/9 relationships, exact materialization/intentional targets, seven imported notes, eight byte-preserved payloads, 19 support artifacts and all 34 actual manifest hashes/lengths. It includes category/default and member/override icons, source calendar dates/raw timestamp/token evidence, graph/source tags, exceptional BOM/CRLF Markdown and image adaptation, the independently associated absent TXT/intact PDF and exact timed video URL. Complete original root records, physical payload accounting, classifications, support/configuration/report/record/result schema contracts and whole-conversion conflict refusals are checked. Exact/repeat/reordered output remains logically/byte stable. Library/CLI migration warnings retain exit 2; the independent source-free checker is clean with exit 0 and equal repeat results/unchanged bytes. All final template dates remain quoted `"{{date:YYYY-MM-DD}}"`; full `Templates/Concept.md` has no imported identities.
- 2026-10-05 (/root/v2_implement_09): Added 83 focused public publication/session cases. Controls reach the selected generic/category template, Base, configuration or guide before partial real writes, deletion/truncation/same-length mutation or late source changes. Binding, reserved/case/NFC/file-parent/long-path collisions, support obligations/digests, real Windows `Templates`/`.obsidian` junctions, native rename/rmdir races, selected category/member-icon open/read/short/close faults and owned cleanup denial preserve caller inventory/bytes, safe cleanup and actual retained-leftover evidence. Rich workflow teardown/post-commit failures retain complete verified receipts/actual counts and `publication_occurred`; material failures retain no receipt or invented actual counts.
- 2026-10-05 (/root/v2_implement_09): Additive Folio/BRZ pair independently authors opaque category definitions/assignments, owned icons, Folio year/month/day dates and explicit video facts. It preserves the original v1 fixture and demonstrates five imported notes/seven payloads/19 support files, the complete 31-file inventory, exact source-ID pairs and CRLF-sensitive corresponding bodies/properties. Nine malformed classification/icon/evidence cases and snapshot/policy versions 1/3 refuse through existing public boundaries. Direct analyze/plan/render/publish and alternate result presentation work without argument parsing/exits; a fresh subprocess performs rich conversion while TheBrain/CLI/wiring imports are actively blocked. No inward import allowance was weakened.
- 2026-10-05 (/root/v2_implement_09): TDD red/green observed default converter/package `0.1.0` against required `0.2.0`, then consistently updated `pyproject.toml` and module version; rich Folio classification initially refused before its test-only adapter accepted independently authored v2 facts. No production behavior correction was needed. Migration schemas stay 2 and checker schema stays 1; usage/architecture/testing guidance documents the release/version changes. Final after-merge gates, using `C:/Users/stefa/projects/brz2obsidian/.venv/Scripts/python.exe` and this worktree's `src` as process `PYTHONPATH`: `python -m pytest -q --tb=short` **671 passed in 66.00 seconds**; `python -m ruff check --no-cache .` passed; `python -m ruff format --check .` **108 files already formatted**; `python -m pip check` no broken requirements; `git diff --check` clean; loaded `brz2obsidian.__file__` points into this worktree and `__version__` is `0.2.0`. Shared editable installation was not repointed/reinstalled; root owns final metadata refresh. Only synthetic temporary archives/vaults were used. Full private three-archive audits, native/user actual-vault acceptance and final v2 delivery remain tickets 10–11.

- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
- 2026-10-05 (/root): Claimed after all four linked blockers resolved and integrated. Baseline `f9c097a6c7b7defcaa9b34f539fd3259bfa40d2a` passes 564 cumulative tests, Ruff lint/format and environment/diff checks. The public checker additionally passes on the frozen actual Obsidian-edited template review copy with all 38 file hashes/inventory unchanged and equal repeated results. Isolated implementation will use the confirmed public workflow, CLI, checker, publication and alternate-source seams; full private archive preservation and final native/user acceptance remain tickets 10–11.
