# 10: Accept the first version in Obsidian and document usage

Status: resolved

Assignee: /root/implement_10

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Review the actual complete converter outputs in standard Obsidian and finish installation, library, CLI, architecture, and testing guidance for first-version use.

**Blocked by:** [08: Prove reuse with an alternate source](08-alternate-source-reuse.md); [09: Verify complete preservation on both real exports](09-real-export-preservation.md)

**Specification stories:** 3, 23, 29, 30, 38, 59, 69.

**Acceptance criteria:**

- [x] Open fresh test copies of both actual generated real vaults, preserving pre-click output for comparisons. Never test in the user's normal vault; record the native Obsidian version used.
- [x] Verify root Home, startup selection/native bookmark, representative Parents/Children/Related navigation, uncreated-target click-to-create, and native backlinks/Graph/tag discovery without community plugins or replacement features.
- [x] Check selected actual inline PNG/WebP, PDF, generic file, and external-reference links from root and ordinary notes. This representative native review complements full preservation checks and does not claim every page/note was reviewed.
- [x] Fix converter output defects through the responsible public seam, rerun affected automatic/independent checks, and repeat affected native observations before claiming acceptance.
- [x] Verify installation, console/module commands, direct reusable workflow examples, inspect/convert text/JSON and exit behavior, fresh-vault restrictions, known warnings, intentional uncreated targets, and source coverage are documented accurately.
- [x] Document reusable module interfaces, inward dependency rules, source/profile composition, private/public test commands, native-review procedure, resolved dependency/runtime versions, and conservative platform/app-version claims.
- [x] Record that all approved slice criteria, applicable automated tests, alternate-source reuse, complete real-source preservation, and native-review gates passed before declaring the first version accepted. The earlier prototype and completed Wayfinder map cannot substitute for these results.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.

- 2026-10-04 (/root/implement_10): Claimed on `codex/brz-v1-10` from integration `4eae088`; blockers 08/09 are resolved. Ownership covers usage/architecture/testing/source-coverage documentation and aggregate native report. `/root` owns actual native UI observations and fresh copies; native criteria remain unchecked until its confirmed evidence arrives. No production code changed.
- 2026-10-04: Replaced outdated minimal-only documentation with full reviewed scope, project-venv install commands, console/module text/JSON usage and 0/2/1 exits, truthful postpublication receipt behavior, fresh-vault/path constraints, native/uncreated target usage, exact warning rule IDs/conditions, source refusals, version boundaries and private/public/native verification procedure. Architecture documents actual public composition, direct module calls, inward dependencies, metadata/source lifetime/binding and the actual nested document/finding record schema. Test-only Folio is explicitly not a supported production format.
- 2026-10-04: Executed all three documented Python examples against the checked-in synthetic archive through real Workflow and public analyze/plan/render/publish boundaries; each published a verified one-note vault. Console and module entry points both passed text/JSON inspect and fresh convert, result JSON roundtrip, pending inspect checks/null actual counts, nonempty destination refusal (1), help (0), and argument error (1). Windows piped-output verification set `PYTHONIOENCODING=utf-8`; README documents that setting for UTF-8 capture. Temporary example outputs were owned and removed. Existing slice tests/private six-run acceptance verify approved warning exits; no test was added to mirror documentation text.
- 2026-10-04: Root project `.venv` interpreter with `PYTHONPATH` set to this worktree's `src`: `python -m pytest -q` passed **277 tests**; `python -m ruff check --no-cache .`, `python -m ruff format --check .`, `python -m pip check` and `git diff --check` passed. All 15 local documentation link destinations exist. Installation manifests/commands retain the verified ticket 01 environment/bootstrap procedure.

- 2026-10-04: `/root` confirmed native acceptance complete in **Obsidian 1.13.7**, using fresh ignored `ui-A` / `ui-B` copies. All 114/96 files matched pristine SHA-256/inventory before opening; pristine accepted outputs were checked unchanged afterward. Both root Homes opened in Reading, native Home bookmarks returned from ordinary notes, representative Parents/Children/Related links reached assigned paths, selected targets were absent before click and exact `.md` files existed afterward with no doubled extension. B's representative parent was itself intentionally uncreated and was created by that navigation click. Native Backlinks showed authored/generated hierarchy mentions and Graph displayed existing/dim uncreated neighbors in both vaults. A native tag search returned 15 files including the focused membership listing; B showed no tags, matching zero assignments.
- 2026-10-04: Actual A inline PNG rendered and generic Type 1 PNG Resources link opened the native image viewer; B inline WebP rendered and actual PDF Resources link opened the native 100-page viewer (B's generic file class is PDF). A ordinary URLs, B root/ordinary URLs and B directory `file:///` reference were visible without opening/fetching external destinations. Neither root owns local inline images/files; actual ordinary owners supplied those checks and synthetic renderer tests cover root-local paths. No community plugins or normal user vault were used. No converter defects were found, so repair/retest criterion required no change. Aggregate observations and limits are in [native acceptance](../research/native-acceptance.md); screenshots/private assigned paths remain ignored.
- 2026-10-04: Tickets 01–09 are resolved, with alternate-source proof, complete six-run independent preservation and public checks passed; this native/documentation gate now also passed. Overall index/specification closure remains `/root`'s responsibility after final two-axis code review. The completed Wayfinder map and earlier prototype were not used as acceptance substitutes.
- 2026-10-04: Merged latest integration before final closure (`git merge codex/brz-to-obsidian-v1`: already up to date at `4eae088`). Final post-native-documentation gates using the root `.venv` with this worktree's `PYTHONPATH`: **277 tests passed** in 20.77s, Ruff lint/format, `pip check`, `git diff --check`, and all **16** final local documentation link destinations passed. Working-tree changes remain documentation and aggregate ticket evidence only.
