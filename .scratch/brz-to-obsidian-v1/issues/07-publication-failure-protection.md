# 07: Protect publication against source and I/O failures

Status: resolved

Assignee: /root/implement_07

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Make interrupted, changing-source, and destination-race conversions fail honestly without exposing partial vaults or modifying caller-owned files.

**Blocked by:** [01: Convert a minimal Brain into a fresh vault](01-minimal-brain-vault.md)

**Specification stories:** 8, 9, 10, 11, 67, 71, 72.

**Boundary and dependency rationale:** The minimal slice already copies an original-note payload through a source session and owned staging, so these failure cases can be completed independently of graph/tag/resource feature work.

**Acceptance criteria:**

- [x] Plans, rendered artifacts, and payload access bind to both source fingerprint and normalized snapshot digest. A different session/source cannot supply bytes merely because asset IDs match.
- [x] Detect source mutation/truncation and verify every streamed length/hash plus source consistency before commit. Partial stream, read, write, integrity, or validation failure prevents publication.
- [x] Validate complete artifact manifests, path uniqueness/containment, conservative final path limits, and absence of unexpected files. Recheck destination state at commit; late caller content must remain unchanged.
- [x] Cleanup resolves and checks only converter-owned targets before recursive operations on Windows. If cleanup fails, report the exact owned leftover and retain the original material failure diagnostics.
- [x] Workflow manages session/payload context lifetimes and returns durable values after closure. Access after closure fails explicitly; success/failure paths do not leave required resources open.
- [x] Return truthful outcomes and actual receipts: none before verified commit; if an error occurs after commit, retain the verified receipt and clearly state publication occurred. Failure results preserve available issues/counts and JSON isolation.
- [x] Use real temporary files/directories plus controlled faults through public interfaces for early/late failure, destination appearance, wrong binding, changed source, truncated/mismatched streams, staged validation, cleanup failure, and session teardown.
- [x] Installed CLI and direct workflow calls exhibit the same relevant outcome and diagnostics; assertions inspect actual destination/staging bytes and caller-owned sentinels.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.


- 2026-10-03, /root/implement_07: Implemented publication/source/workflow/CLI failure protection at the accepted public seams. Artifacts and payload sessions require matching complete SourceIdentity (including source fingerprint and snapshot digest); the source hash comes from the same open handle used by ZIP interpretation, with source consistency checked after snapshot interpretation, before copying, after copying and before commit.
- Staging verifies the exact manifest and every generated/copied length and SHA-256. NFC/casefold collisions, file/directory prefix conflicts, unsafe Windows names, reparse ancestors, staged junctions and final absolute paths over 240 UTF-16 units are refused. RenderedVault.reserved_paths additionally reserves uncreated targets for the same path checks without treating them as emitted files; ticket 02 supplies those renderer targets.
- Native Windows empty-destination removal and directory rename preserve late caller files. Converter cleanup checks the original staging path, resolved containment and captured directory identity, and refuses recursive cleanup through reparse paths. Cleanup failures retain original diagnostics plus the exact owned leftover. The real junction test removes its reported leftover only after checking ownership and removing the junction itself.
- Payload streams expire when the source session closes. Session teardown attempts every required close even if one reports an I/O error. Workflow/source context error precedence retains material diagnostics; actual verified receipts survive post-commit and teardown failures, with an explicit publication_occurred issue. Available source/planned/actual counts remain truthful. CLI parse failures return 1 (help returns 0), and installed JSON failure output matches direct workflow output.
- Verification: used C:\Users\stefa\projects\brz2obsidian\.venv\Scripts\python.exe with PYTHONPATH set to this worktree's src for all local pytest/CLI invocations. After merging integration tip 9e65eef (completed ticket 03), python -m pytest tests -q passed 74 tests; python -m ruff check . and python -m ruff format --check . both passed. Red-to-green slices exposed path ambiguity, open-stream lifetime, teardown precedence, late destination classification, staged-junction containment, source CRC translation, source change during staged validation, available failure counts and reserved-path validation before their respective fixes.
- Evidence includes real temporary ZIPs/directories/payload files, actual native Windows junction creation and native directory races; controlled read/write/cleanup/close faults cross source/publication/OS interfaces. Tests inspect exact caller-owned sentinel bytes, absence of published partial vaults, owned leftovers, stream closure and actual receipt/output bytes. Limits: native Windows is the accepted runtime; these checks do not establish cross-platform atomic-directory publication or private full-export/Obsidian presentation acceptance (tickets 09/10).
