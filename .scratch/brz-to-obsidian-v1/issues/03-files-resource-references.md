# 03: Preserve files and resource references

Status: ready-for-agent

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Migrate supported archived files, images, decorative icons, note originals, URLs, and external directory references into useful resource links with byte-preserved local assets.

**Blocked by:** [01: Convert a minimal Brain into a fresh vault](01-minimal-brain-vault.md)

**Specification stories:** 16, 18, 19, 20, 47, 66.

**Acceptance criteria:**

- [ ] Interpret the verified attachment roles and locations; every present archived payload has exactly one preservation assignment, including original-note backups, empty placeholders, generic files, icons, and Markdown image assets.
- [ ] Use actual CRC-valid bytes and their measured lengths/digests, rather than trusting declared length. Preserve generic files regardless of whether Obsidian can preview them; do not classify thought notes by extension alone.
- [ ] Group copies by stable unique owner tokens, resolve resource-name collisions deterministically, preserve extensions, and retain the agreed non-note backup ending for source Markdown originals.
- [ ] Owners with substantive files/images or supported external references qualify for notes through inspect/convert. Decorative icons and empty placeholders alone do not qualify.
- [ ] Additional files and external references become ordinary Resources links. Icons are retained without resource clutter; inline-image assets are preserved and mapped, with actual inline note adaptation owned by the reference slice.
- [ ] External URL/directory content is not fetched or opened. Stream local binaries through the scoped source session instead of loading or duplicating an entire archive in memory.
- [ ] Unaccounted physical payloads, ambiguous note placeholders, missing required bytes, and unsupported attachment roles refuse rather than being silently ignored. The later known-gap slice supplies only the approved exceptions.
- [ ] Use real synthetic archive/temp-vault workflow tests to compare every copied byte/hash, ownership mapping, naming collision, source accounting, external link, and resource-only note selection.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.
