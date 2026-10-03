# 03: Preserve files and resource references

Status: resolved

Assignee: /root/implement_03

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Migrate supported archived files, images, decorative icons, note originals, URLs, and external directory references into useful resource links with byte-preserved local assets.

**Blocked by:** [01: Convert a minimal Brain into a fresh vault](01-minimal-brain-vault.md)

**Specification stories:** 16, 18, 19, 20, 47, 66.

**Acceptance criteria:**

- [x] Interpret the verified attachment roles and locations; every present archived payload has exactly one preservation assignment, including original-note backups, empty placeholders, generic files, icons, and Markdown image assets.
- [x] Use actual CRC-valid bytes and their measured lengths/digests, rather than trusting declared length. Preserve generic files regardless of whether Obsidian can preview them; do not classify thought notes by extension alone.
- [x] Group copies by stable unique owner tokens, resolve resource-name collisions deterministically, preserve extensions, and retain the agreed non-note backup ending for source Markdown originals.
- [x] Owners with substantive files/images or supported external references qualify for notes through inspect/convert. Decorative icons and empty placeholders alone do not qualify.
- [x] Additional files and external references become ordinary Resources links. Icons are retained without resource clutter; inline-image assets are preserved and mapped, with actual inline note adaptation owned by the reference slice.
- [x] External URL/directory content is not fetched or opened. Stream local binaries through the scoped source session instead of loading or duplicating an entire archive in memory.
- [x] Unaccounted physical payloads, ambiguous note placeholders, missing required bytes, and unsupported attachment roles refuse rather than being silently ignored. The later known-gap slice supplies only the approved exceptions.
- [x] Use real synthetic archive/temp-vault workflow tests to compare every copied byte/hash, ownership mapping, naming collision, source accounting, external link, and resource-only note selection.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.

- 2026-10-03 (/root/implement_03): Implemented verified attachment normalization in a private source helper, source-neutral resource selection/assignment, and ordinary Resources rendering. Present binary inventory is streamed with measured length/SHA-256; every payload maps to one scoped copy. Note originals and BOM-only placeholders retain `.md.original`; icons do not qualify notes or clutter Resources. Unreferenced images qualify notes and receive a usable Resources link; canonical inline image spans suppress duplicate links after ticket 04 supplies adaptation. External URLs and Windows directories retain link destinations without fetch/open. Owner and resource collision tokens extend deterministically, including non-UUID/short generic seeds; generic Markdown attachments remain files.
- Verification: with `$env:PYTHONPATH=(Join-Path (Get-Location) 'src')`, ran `C:\Users\stefa\projects\brz2obsidian\.venv\Scripts\python.exe -m pytest -q` (40 passed), `-m ruff check .` (passed), and `-m ruff format --check .` (43 files already formatted). The 22 added public workflow/core/contract tests compare expected copied bytes, a literal independently calculated digest, ownership/accounting, extension-preserving collisions, ordering, external destinations, resource-only selection, CRC corruption, stream-only binary reads, and strict refusal cases.
- Scope limits: present Type 15/absent TXT and icon length anomalies refuse until ticket 06 supplies the reviewed exceptions. Actual source-local Markdown reference adaptation explicitly refuses until ticket 04; its image asset assignment is already shared. No real archive was opened or copied for this slice.
