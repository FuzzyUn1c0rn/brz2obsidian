# 06: Report known gaps and enforce verified source coverage

Status: resolved

Assignee: /root/implement_06

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Complete the reviewed source profile so verified Brains convert with precise known-gap warnings and unsupported or unreliable input is refused explicitly.

**Blocked by:** [04: Adapt thought and image links without rewriting notes](04-source-note-links.md); [05: Preserve tags using native Obsidian features](05-native-tags.md)

**Specification stories:** 50, 51, 52, 53, 54, 55, 56.

**Boundary and dependency rationale:** Completing the declared profile depends on the graph, resource, reference, and tag behaviors being available; reference and tag slices transitively include the other feature slices.

**Acceptance criteria:**

- [x] Apply the exact accepted absent-TXT predicate, including source role/type/state/length, absent bytes, and an intact PDF under the same owner. Preserve metadata and avoid claiming purpose, optionality, or a TXT/PDF pairing.
- [x] Continue on the precise approved present-icon length discrepancy using CRC-valid actual bytes, preserving actual/declared lengths. Neither rule authorizes missing required notes/files/images or unknown absence patterns.
- [x] Source interpretation emits evidence-backed versioned findings; generic core decides warning/refusal under the reviewed compatible profile. Numeric TheBrain predicates and rule constants stay outside generic core; unknown rules/profile mismatches refuse.
- [x] Warning conversions publish verified output and exit 2 with consistent structured issues in terminal/JSON, report, and record. Add a brief absent-filename notice only to an existing owner note; do not create a fake link/file or a note solely for a warning.
- [x] Complete the exact verified thought/relationship/attachment feature boundary. Retain system/history/deletion/raw metadata without invented navigation meaning; malformed/duplicate keys, corrupt ZIP members, unreliable live identities/references, ambiguous payloads, or unverified semantics cannot silently pass.
- [x] Unsupported format/features, nonempty unverified collections, custom types, HTML/cross-Brain content, unverified direction combinations, and semantic role flags produce stable actionable refusal. Additional uninterpreted metadata remains original evidence.
- [x] Through full-workflow plus source/core seam tests, test every required conjunct of each warning predicate with matched and near-miss examples, and verify stable issue codes, unavailable counts, source accounting, and unchanged destinations on refusal.
- [x] Ordinary name adaptations and agreed arrow simplifications are recorded adaptations, not invented warnings; no caller/CLI arbitrary allowlist is introduced.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.
- 2026-10-03: Claimed by `/root/implement_06` in `codex/brz-v1-06`, based on integration `d95f02b`. Used the invoked implement-spec and TDD workflows at the accepted source/core/workflow/CLI seams. Matched absent-TXT and icon discrepancy tracers failed first, then published verified warning vaults. Source-only versioned predicates now emit immutable evidence-backed findings; the reviewed source profile supplies strict kind/rule/disposition values and explicit absence permission to generic analysis. Stable warning codes are `approved_source_gap` and `approved_metadata_discrepancy`. Unknown/incompatible findings, invented evidence/subjects, and unrecognized absences refuse; no unrestricted rule tuple or CLI allowlist remains.
- 2026-10-03: Added synthetic matched/near-miss coverage for every warning conjunct, corrupt PDF/icon CRCs, other-owner PDFs, unrelated missing/mismatched roles, semantic flags/custom types, nonempty unverified collections, global duplicate live identities, deleted/live overlap, historical nonlive references, foreign setting ownership, ambiguous ZIP directory names, strict normalized ownership/relationship identities/external references, durable source accounting, result counts, and exact CLI/library/report/record issue agreement. Warnings preserve actual bytes/metadata and do not select otherwise empty icon owners. Unicode U+0085/U+2028/U+2029 inside valid JSON strings survive; record splitting now uses CR/LF only. Existing high-precision, omitted/null, raw-date and source lifetime tests remain green. Warning report ordering is stable under attachment record reordering.
- 2026-10-03: Read-only inspection of the exact private A/B inputs verified their accepted SHA-256 fingerprints. A planned 49 notes and 60 payloads with exactly 2 `approved_metadata_discrepancy` warnings; B planned 42 notes and 50 payloads with exactly 9 `approved_source_gap` warnings. This is a preflight smoke, not ticket 09's independent full preservation acceptance. No private titles/IDs/content were committed.
- 2026-10-03: Aggregate parser inspection found exactly two attribute-free `br` tags in accepted A Markdown. The coordinating agent confirmed the narrow interpretation: preserve bare `<br>`/`<br/>` line-break spelling unchanged while refusing attributed tags, other active HTML, declarations/processing instructions, and rich/legacy HTML note roles. Comments/code/literals keep ticket 04 behavior. Focused tests preserve CRLF alongside bare breaks; [source coverage](../../../docs/source-coverage.md) records this boundary without broadening warnings or adding HTML transformations.
- 2026-10-03: Cross-slice schema repair authorized by the coordinator: document/reference facts now live under corresponding `item_targets[*].documents`; system-owner facts remain under original `asset_targets[*].retained_documents`, with null navigation target and preserved original bytes. Versioned anomaly findings/observed state and lengths live under affected asset entries. The migration record's top-level field set exactly matches the accepted v1 specification. Updated ticket 04's public artifact assertions without changing span behavior. The earlier resource negative case now checks an invalid negative icon length, since positive declared/actual icon discrepancies are approved here.
- 2026-10-03: Verification used `C:\Users\stefa\projects\brz2obsidian\.venv\Scripts\python.exe` with `PYTHONPATH=C:\Users\stefa\projects\brz2obsidian-worktrees\ticket-06\src` for every Python invocation. `-m pytest tests/application/test_verified_coverage.py -q --tb=short`: 81 passed. Final `-m pytest -q --tb=short`: 231 passed. `-m ruff check . --no-cache`: passed. `-m ruff format --check .`: 62 files already formatted. `git diff --check`: passed (Git only reported normal CRLF-to-LF normalization for the ticket Markdown). Full native/independent real-export acceptance remains with tickets 09/10.
- 2026-10-03: Final policy guard followed an additional red/green slice: a compatible finding profile cannot downgrade `invalid_source`, `unsupported_feature`, `invalid_reference`, `missing_required_payload` or `source_changed` into warning severity. Only the two accepted generic warning codes can be selected for warning dispositions; source rule identifiers/numeric recognition remain outer-owned. Final full suite: **236 passed**; the focused ticket suite contains 86 cases. Ruff lint/format and `git diff --check` passed after this guard. Integration tip `d95f02b` was merged before completion (`Already up to date`).
