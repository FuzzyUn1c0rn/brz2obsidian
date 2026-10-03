# 02: Preserve hierarchy and empty thought targets

Status: resolved

Assignee: /root/implement_02

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Convert a graph Brain into simple linked notes while leaving unnecessary empty thoughts uncreated and materializing only the Home and hierarchy parents that need files.

**Blocked by:** [01: Convert a minimal Brain into a fresh vault](01-minimal-brain-vault.md)

**Specification stories:** 21, 22, 23, 24, 25, 26, 27, 28, 33, 34, 41, 42, 43, 44, 45, 46, 57.

**Acceptance criteria:**

- [x] Inspect predicts, and convert emits, the accepted content/Home selections and greedy parent coverage. An empty A→B→C chain creates B alone; cycles/multiple parents terminate and preserve all hierarchy edges.
- [x] Recognize verified hierarchy/jump meanings, including ordinary-parent to tag-child hierarchy. Parent/child orientation comes from verified endpoints rather than arrow values; visual arrow/one-way details remain in original evidence.
- [x] Created notes show the original heading and optional label plus Parents, Children, and Related lists with empty sections omitted. Repeated rendered targets are deduplicated while original edges/mappings remain complete.
- [x] Reserve unique readable targets for created and uncreated nonsystem items together. Apply the accepted NFC/safety/device-name policy, case-insensitive collisions, stable seed suffixes, supporting-name reservations, truncation, and path-limit behavior.
- [x] Recompute uncovered-edge selection after each parent choice with the accepted incident-edge score and source-key ties. Source/ZIP reordering does not change selections or targets.
- [x] Labels, icons, colors, dates, and empty placeholders alone do not force files. Forgotten live thoughts stay eligible; historical/deleted objects are retained without resurrection.
- [x] Generate focused conditional uncreated listings for otherwise unrepresented isolated thoughts and Related pairs with no endpoint files. Ordinary linked empty thoughts remain uncreated; Home remains at root even empty.
- [x] Through synthetic full-workflow and public core/rendering tests, cover duplicate/unsafe/reserved/long names, natural suffix-like names, short-seed/truncation collisions, cycles, multiple parents, empty Home, and orphan/Related cases. All emitted internal links name the assigned targets.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.
- 2026-10-03 (/root/implement_02): Claimed after ticket 01 resolved. TDD used the accepted workflow/core/rendering seams. Observed red failures for the empty hierarchy chain, conditional Uncreated listing, naming safety/natural suffix reservation, fallback plan fields, renderer binding, relationship target mappings, and live/deleted overlap; each became green after its implementation slice. `PYTHONPATH=<ticket-02>/src` and the root `.venv/Scripts/python.exe` were used on every Python invocation. Intermediate full-suite result: 36 passed, one expected pending failure for uncreated-target absolute path feasibility. Coordinated `RenderedVault.reserved_paths` with ticket 07 so publication checks future click-to-create paths as well as emitted paths; completion waits for that integration. Native Obsidian review belongs to ticket 10.

- 2026-10-03 (/root/implement_02): All eight acceptance criteria satisfied. Hierarchy/jump signatures decode from verified endpoints; ordinary-to-tag hierarchy and retained-only system connections are represented correctly, with original fields and every edge retained. Generic core selects content/Home first, recomputes uncovered incident scores after each greedy parent, and uses source-key ties. Created/uncreated targets share deterministic NFC, safety, device, supporting-name, case-fold, natural-suffix and UTF-16 truncation reservations. Exhausted short seeds suffix a natural-name contender where possible; truly indistinguishable full seeds refuse with source guidance. Labels/decorative icons/empty BOM placeholders alone remain uncreated. Core plans focused isolated/Related fallbacks, including readable document-reference exclusion; renderer emits qualified `.md` targets, escaped original headings, source labels/body, deduplicated relationship sections, complete destination relationship mappings and simplification adaptations.
- Integrated resource ticket 03 and publication ticket 07 before completion; their behavior was retained, including resource-driven content eligibility, single resource assignments, Resources before relationship sections, and reserved uncreated paths for native click-to-create feasibility. The previously red long-uncreated-path workflow case is now green. Retained-only historical objects never receive targets; live/deleted overlap is refused.
- Final verification on branch `codex/brz-v1-02`, after merging integration `cb3d2dc`: set `$env:PYTHONPATH = 'C:\Users\stefa\projects\brz2obsidian-worktrees\ticket-02\src'`; `C:\Users\stefa\projects\brz2obsidian\.venv\Scripts\python.exe -m pytest -q` → **97 passed**; the same interpreter with `-m ruff check .` → **all checks passed** and `-m ruff format --check .` → **50 files already formatted**. Synthetic ZIP/temp-folder workflow and public core/rendering tests cover all listed graph/naming/fallback cases. No private source input or GUI was needed. Native Obsidian acceptance and full real-export proof remain tickets 10 and 09, respectively; source tag assignments and authored source-local adaptation remain tickets 05 and 04.