# 09: Verify complete preservation on both real exports

Status: resolved

Assignee: /root/implement_09

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Convert the exact two real archives and independently prove complete content, file, graph, identity, and metadata preservation for the agreed first-version coverage.

**Blocked by:** [06: Report known gaps and enforce verified source coverage](06-verified-coverage-source-gaps.md); [07: Protect publication against source and I/O failures](07-publication-failure-protection.md)

**Specification stories:** 14, 15, 16, 46, 53, 55, 58, 70.

**Acceptance criteria:**

- [x] Select the exact A/B acceptance inputs using the specification's recorded paths/fingerprints and perform complete conversions. Normal automated checks remain synthetic and work without private inputs.
- [x] Independently compare every present archived payload and original-note backup byte-for-byte, every original JSON record/field semantically including omitted/null/raw dates, every identity/target assignment, accepted relationship/tag representation, and actual local reference.
- [x] Verify source Markdown outside approved edits, complete item/resource accounting, exact warning predicates, conditional listings, native configuration, Home/root behavior, and valid created/uncreated targets. Do not rely solely on the converter's report/manifest or summary counts.
- [x] Confirm expected thought-note totals 49/42 including root Home, hierarchy-only additions 5/2, present preserved payloads 60/50 with original-note backups included, and known warning items 2/9. Both runs exit 2; reports/support pages are excluded from thought-note totals.
- [x] Exercise repeated conversions and equivalent record/ZIP reorderings: logical selections/names/content/resource bytes and graph/tag presentation remain unchanged, with only the documented provenance/run-metadata exceptions.
- [x] Record full applicable public behavioral tests, native dependency versions, and independent acceptance results. Fail acceptance on unexplained discrepancies rather than widening warning coverage or changing baselines silently.
- [x] Keep private archives, titles, IDs, note text, and generated vaults local in ignored storage. Checked-in fixtures are synthetic; shareable acceptance reports contain aggregates and reproducible commands without private content.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.

- 2026-10-04: Claimed and completed by `/root/implement_09` on `codex/brz-v1-09`, based on integration `5ccb171`, then merged integration `10761bb` before final gates. Ownership was independent acceptance support/proofs/report only; no production code changed. Applied the invoked implement-spec workflow and TDD at the accepted workflow/artifact seam; synthetic corruption checks observed red before adding payload, metadata, note/graph/tag, reference/resource, finding/accounting/listing and result/receipt checks.
- 2026-10-04: Exact recorded A/B size and SHA-256 checks passed. Six complete CLI conversions (exact, repeat, reversed-record/ZIP for each) all exited 2. Independently accepted A: 49 thought notes including Home, 5 hierarchy-only selections, 60 present payloads including 43 originals, 2 exact icon warnings. B: 42/2/50/34 with 9 exact absent-TXT warnings across 7 owners. All fields/records, raw dates, omitted/null distinction, decimal precision, every source identity/target/graph/tag/local reference, body bytes outside edits, resource bytes, accounting, reserved paths, focused listings and native configuration passed; real structured receipts were audited against the actual files.
- 2026-10-04: Repeat and reordered logical records/names/selections and all content/resource bytes passed with only documented provenance/source-order and run-clock exceptions. Preserved pre-click accepted vaults under ignored local `brz/v1-acceptance-full/A` and `/B`; native review must use fresh copies. The independent oracle imports no production modules, and private artifacts were not committed.
- 2026-10-04: Full public gates used the root project virtual-environment interpreter with `PYTHONPATH` set to this worktree's `src`: `python -m pytest -q` **277 passed** (including 22 synthetic independent-checker proofs); `python -m ruff check --no-cache .`, `python -m ruff format --check .`, `python -m pip check` and `git diff --check` passed. Private driver: `python -m tests.local_acceptance.run --source-a <exact-A> --source-b <exact-B> --output <new-short-ignored-directory>`; an additional direct checker/receipt audit passed for all six preserved outputs after the final checker strengthening. Commands, measured aggregates, native package versions, privacy and reproducibility boundaries are recorded in [the complete preservation report](../research/real-export-acceptance.md). Obsidian GUI presentation acceptance remains the separate ticket 10 gate.