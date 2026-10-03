# 02: Preserve hierarchy and empty thought targets

Status: ready-for-agent

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Convert a graph Brain into simple linked notes while leaving unnecessary empty thoughts uncreated and materializing only the Home and hierarchy parents that need files.

**Blocked by:** [01: Convert a minimal Brain into a fresh vault](01-minimal-brain-vault.md)

**Specification stories:** 21, 22, 23, 24, 25, 26, 27, 28, 33, 34, 41, 42, 43, 44, 45, 46, 57.

**Acceptance criteria:**

- [ ] Inspect predicts, and convert emits, the accepted content/Home selections and greedy parent coverage. An empty A→B→C chain creates B alone; cycles/multiple parents terminate and preserve all hierarchy edges.
- [ ] Recognize verified hierarchy/jump meanings, including ordinary-parent to tag-child hierarchy. Parent/child orientation comes from verified endpoints rather than arrow values; visual arrow/one-way details remain in original evidence.
- [ ] Created notes show the original heading and optional label plus Parents, Children, and Related lists with empty sections omitted. Repeated rendered targets are deduplicated while original edges/mappings remain complete.
- [ ] Reserve unique readable targets for created and uncreated nonsystem items together. Apply the accepted NFC/safety/device-name policy, case-insensitive collisions, stable seed suffixes, supporting-name reservations, truncation, and path-limit behavior.
- [ ] Recompute uncovered-edge selection after each parent choice with the accepted incident-edge score and source-key ties. Source/ZIP reordering does not change selections or targets.
- [ ] Labels, icons, colors, dates, and empty placeholders alone do not force files. Forgotten live thoughts stay eligible; historical/deleted objects are retained without resurrection.
- [ ] Generate focused conditional uncreated listings for otherwise unrepresented isolated thoughts and Related pairs with no endpoint files. Ordinary linked empty thoughts remain uncreated; Home remains at root even empty.
- [ ] Through synthetic full-workflow and public core/rendering tests, cover duplicate/unsafe/reserved/long names, natural suffix-like names, short-seed/truncation collisions, cycles, multiple parents, empty Home, and orphan/Related cases. All emitted internal links name the assigned targets.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.
