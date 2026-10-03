# 09: Verify complete preservation on both real exports

Status: ready-for-agent

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Convert the exact two real archives and independently prove complete content, file, graph, identity, and metadata preservation for the agreed first-version coverage.

**Blocked by:** [06: Report known gaps and enforce verified source coverage](06-verified-coverage-source-gaps.md); [07: Protect publication against source and I/O failures](07-publication-failure-protection.md)

**Specification stories:** 14, 15, 16, 46, 53, 55, 58, 70.

**Acceptance criteria:**

- [ ] Select the exact A/B acceptance inputs using the specification's recorded paths/fingerprints and perform complete conversions. Normal automated checks remain synthetic and work without private inputs.
- [ ] Independently compare every present archived payload and original-note backup byte-for-byte, every original JSON record/field semantically including omitted/null/raw dates, every identity/target assignment, accepted relationship/tag representation, and actual local reference.
- [ ] Verify source Markdown outside approved edits, complete item/resource accounting, exact warning predicates, conditional listings, native configuration, Home/root behavior, and valid created/uncreated targets. Do not rely solely on the converter's report/manifest or summary counts.
- [ ] Confirm expected thought-note totals 49/42 including root Home, hierarchy-only additions 5/2, present preserved payloads 60/50 with original-note backups included, and known warning items 2/9. Both runs exit 2; reports/support pages are excluded from thought-note totals.
- [ ] Exercise repeated conversions and equivalent record/ZIP reorderings: logical selections/names/content/resource bytes and graph/tag presentation remain unchanged, with only the documented provenance/run-metadata exceptions.
- [ ] Record full applicable public behavioral tests, native dependency versions, and independent acceptance results. Fail acceptance on unexplained discrepancies rather than widening warning coverage or changing baselines silently.
- [ ] Keep private archives, titles, IDs, note text, and generated vaults local in ignored storage. Checked-in fixtures are synthetic; shareable acceptance reports contain aggregates and reproducible commands without private content.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.
