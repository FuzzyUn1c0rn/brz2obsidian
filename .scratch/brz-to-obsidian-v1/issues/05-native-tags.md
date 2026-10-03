# 05: Preserve tags using native Obsidian features

Status: resolved

Assignee: /root/implement_05

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Convert source tag assignments into native vault tags and preserve tag-authored content and otherwise hidden memberships without duplicating Obsidian search.

**Blocked by:** [02: Preserve hierarchy and empty thought targets](02-hierarchy-empty-targets.md)

**Specification stories:** 30, 31, 32.

**Acceptance criteria:**

- [x] Recognize only the verified source-tag assignment meaning and retain every original membership. Generated native tags appear on created assigned items; do not infer memberships from unrelated fields or invent a tag's self-membership.
- [x] Apply the agreed flat token sanitization, numeric/empty-name handling, case-insensitive collision policy, and stable identity suffixes. Keep exact original tag names in migration evidence.
- [x] Tag-authored content remains in a normal note with the same content/resource/hierarchy eligibility rules. Tag hierarchy is preserved independently of classification.
- [x] Generate the conditional focused tag-membership listing for assignments on uncreated targets and otherwise unrepresented/unused tags; omit unnecessary duplicate listings for native search.
- [x] Inspect/convert counts, source-to-tag mappings, conditional-page links, JSON result, and migration record account for all memberships and created/uncreated tag items.
- [x] Exercise the full synthetic workflow plus public planning/rendering seams for tags on created/uncreated items, authored/empty/unused tags, sanitization/collision cases, no self-membership, and ordinary-to-tag hierarchy.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.
- 2026-10-03: Claimed and implemented by `/root/implement_05` in the isolated `codex/brz-v1-05` worktree. Tests use the already accepted workflow, public analysis/planning and rendering seams. No new package was needed; every Python command uses the root project `.venv` interpreter with `PYTHONPATH` set to this worktree's `src`.
- 2026-10-03: Red/green evidence: the first complete native/hidden membership workflow initially failed because verified `(Kind, Relation, Meaning, Direction)=(1,1,5,-1)` tag-to-ordinary assignments were refused, then passed after decoding/planning/rendering support. Focused red tests exposed underscore punctuation/numeric Unicode handling, invalid classifier/self-membership acceptance, YAML boolean/null serialization, a numeric-only token produced by truncation, and missing unused-tag token mapping; each passed after its corresponding implementation. Stable suffix regression cases cover shared seed prefixes, natural suffix contenders, short/exhausted seeds, truncation and source reordering.
- 2026-10-03: Verification: `$env:PYTHONPATH='C:\Users\stefa\projects\brz2obsidian-worktrees\ticket-05\src'; & C:\Users\stefa\projects\brz2obsidian\.venv\Scripts\python.exe -m pytest -q` passed **115 tests** (18 added tag tests). The same interpreter's `-m ruff check src tests` and `git diff --check` passed. Synthetic workflows independently check created/uncreated assignments, unused tags, retained original evidence, duplicate membership retention with deduplicated native display, original tag Markdown bytes, file/URL/icon eligibility and hierarchy independence.
- 2026-10-03: Record v1 keeps its specified top-level fields. Item targets retain exact original names and an optional `vault_tag_token`, including unused tags; tag-membership entries link each original relationship/evidence to its native or conditional-page representation. Inspection exposes mappings, memberships and the conditional page path. Counts preserve each original membership even when multiple records generate one displayed token. Strict complete source-profile enforcement, known anomaly warnings and real-export/native Obsidian acceptance remain in their subsequent tickets.
