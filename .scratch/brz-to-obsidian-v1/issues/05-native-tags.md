# 05: Preserve tags using native Obsidian features

Status: ready-for-agent

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Convert source tag assignments into native vault tags and preserve tag-authored content and otherwise hidden memberships without duplicating Obsidian search.

**Blocked by:** [02: Preserve hierarchy and empty thought targets](02-hierarchy-empty-targets.md)

**Specification stories:** 30, 31, 32.

**Acceptance criteria:**

- [ ] Recognize only the verified source-tag assignment meaning and retain every original membership. Generated native tags appear on created assigned items; do not infer memberships from unrelated fields or invent a tag's self-membership.
- [ ] Apply the agreed flat token sanitization, numeric/empty-name handling, case-insensitive collision policy, and stable identity suffixes. Keep exact original tag names in migration evidence.
- [ ] Tag-authored content remains in a normal note with the same content/resource/hierarchy eligibility rules. Tag hierarchy is preserved independently of classification.
- [ ] Generate the conditional focused tag-membership listing for assignments on uncreated targets and otherwise unrepresented/unused tags; omit unnecessary duplicate listings for native search.
- [ ] Inspect/convert counts, source-to-tag mappings, conditional-page links, JSON result, and migration record account for all memberships and created/uncreated tag items.
- [ ] Exercise the full synthetic workflow plus public planning/rendering seams for tags on created/uncreated items, authored/empty/unused tags, sanitization/collision cases, no self-membership, and ordinary-to-tag hierarchy.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.
