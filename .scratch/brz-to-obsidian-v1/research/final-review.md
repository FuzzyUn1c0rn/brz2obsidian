# Final two-axis implementation review

Reviewed on 2026-10-04 with the code-review skill. Fixed initial baseline: `816de2b27614e3ae53a11877781befe563b37619`; complete implementation head: `4f3773c45fb670ac3227bbf34cf45702b4438178`. Diff: `git diff 816de2b...HEAD`; commits: `git log 816de2b..HEAD --oneline`. Independent reviewers inspected the complete implementation against documented standards and the accepted specification. Private inputs were not used for review reproductions.

## Standards

No verified hard violations of documented standards. Three nonblocking **possible Duplicated Code** judgments:

- `core/items.py:95` and `core/tags.py:42` repeat collision grouping, contender selection and suffix growth. Both contain `natural = [key for key in group if not widths[key]]` followed by `collisions.update(extendable or natural or group)`. Extract the shared collision decision and seed-width progression while keeping note/tag formatting and diagnostics separate. A collision-policy change currently requires editing both implementations.
- `core/items.py:16` and `core/resources.py:54` duplicate filename sanitation: colon/bracket replacements, prohibited-character substitution, whitespace trimming and Windows device-name handling. Both contain `value = " ".join(value.split()).strip(" .") or "Untitled"`. They differ in control-character treatment. Extract the common readable-name transformation, retaining resource basename extraction and any intentional distinctions at callers.
- `core/resources.py:69` and `obsidian/resources.py:10` independently collect `(document.owner, reference.target)` for image references. Planning already suppresses their `resource_link`; rendering repeats suppression after checking `target.resource_link is None`. Consume the planned resource decision to avoid rescanning the snapshot for every rendered owner.

## Spec

- **P2: Generated navigation can disappear into authored code blocks.** `obsidian/rendering.py:80` appends relationships without ending source Markdown block context. The specification requires: “Every created endpoint lists its Parents, Children, and Related targets.” A synthetic Home ending in an unclosed Python fence converts cleanly, but Children and Resources become code text rather than native links. Preserve authored bytes while ensuring generated sections render outside trailing source blocks, or refuse the unsupported context explicitly.
- **P2: Damaged compressed archives bypass structured failure results.** `sources/thebrain/reader.py:125` omits decompressor failures from source-boundary translation. The specification requires: “Unsupported features are refusals, not generic crashes,” and CRC validation/rejection of corrupt input. Corrupt DEFLATE bytes raise raw `zlib.error`; compression method 99 raises raw `NotImplementedError` through public Workflow inspection. Translate recognized exceptions into actionable structured refusals.

Initial findings: Standards 3 maintenance judgments, no hard violations; Spec 2 P2 defects, no additional scope creep. The worst issue within Standards is duplicated naming policy; both Spec defects have P2 severity.

## Repair verification

Implemented in [review repair ticket 11](../issues/11-final-review-repairs.md) by `/root/review_repairs` on `codex/brz-v1-review-repairs`, based on complete integration head `21f3d28`. The original reviewer findings above remain separate from this repair evidence.

**Standards repair:** Note and tag targets now share collision grouping, contender selection and seed-width progression while retaining their formatting, reserved-name handling and diagnostics. Note/resource names share readable filename sanitation; resource basename extraction and note-only Unicode control replacement remain intentional caller decisions. Resource rendering consumes planned `resource_link` eligibility and no longer rescans document image references. Existing public naming, resource and image regressions pass.

**Spec repair:** Real synthetic ZIP regressions first reproduced escaping `zlib.error` and `NotImplementedError`, then passed with structured `invalid_source` and `unsupported_feature` refusals at source/Workflow/JSON CLI boundaries (no receipt or destination publication). Renderer composition now preserves authored text and newline bytes while adding a generated fence/comment closing boundary only where parsing proves later content would otherwise be absorbed. A complete source-to-vault regression independently parses visible Resources and Children after an unclosed four-backtick fence and verifies the original backup. Reusable renderer regressions cover following authored documents, tilde fences, comments, quote/list containers, indented code and closed fences. Unprovable trailing block contexts are explicitly refused with actionable `unsupported_feature` diagnostics; this conservative limit does not widen TheBrain HTML-note coverage.

**Public verification:** Root project `.venv/Scripts/python.exe`, with worktree `src` in `PYTHONPATH`: `-m pytest -q` (287 passed), `-m ruff check .`, `-m ruff format --check .`, `-m pip check`, and `git diff --check` pass. Latest integration branch merged before completion. Private archives and native acceptance vaults were not modified by the repair implementer.

**Initial integration verification:** The first repair was integrated at `63b506d`; all six independent real-export conversions passed. Follow-up verification and final closure are recorded below.

**Independent repair follow-up:** The Spec reviewer confirmed the original DEFLATE/method-99 and Markdown repairs, then reproduced the same structured archive-boundary defect with corrupt ZIP LZMA. The same implementer merged integration head `63b506d` and checked the installed Python 3.14 decoder set. Real corrupt LZMA, BZIP2 and Zstandard regressions first failed, then passed with `invalid_source` refusals through source/Workflow/JSON CLI. BZIP2 corruption previously became an access/write failure; streamed member validation now distinguishes only its exact plain decoder `OSError("Invalid data stream")` on a BZIP2 member. A standard-library archive I/O fault remains an operational failure. Scoped payload API regressions also prove late recognized decoder exceptions yield structured `payload_read_failure`. Valid archives using each compressed method inspect cleanly before corruption. No dependencies or source semantic coverage were added; successful rendered artifacts are unchanged by this follow-up.

**Follow-up public gates:** Full pytest (295 passed), Ruff lint/format, pip check and Git diff check pass with the root project interpreter and worktree `src` in `PYTHONPATH`. Root reports all six private acceptance conversions passed after the earlier repair integration; final output comparison and integration closure remain pending with root. The repair implementer did not modify private inputs or native vaults.

## Final closure

Final repair integration: `93cdcceb8f645b041c21ae09fc924b56947f46f6`, verified on 2026-10-04. Root public gates passed: 295 tests, Ruff lint/format, pip check and diff check. All six exact/repeat/reordered private conversions passed again after this final merge, with the original note/payload/warning counts and no unexplained discrepancies.

The final A/B vaults match the native-reviewed pristine output in assigned names, rendered notes/reports/listings/configuration, copied resource bytes and logical migration records. Only permitted explicit run metadata and bookmark time differ. Pristine inventories and all 114/96 file hashes remain unchanged. Native observations are still applicable because emitted presentation did not change; no affected native observation required repetition.

**Standards:** The original reviewer independently confirmed all three findings resolved; no relevant regression or hard documented-standard violation remained.

**Spec:** The original reviewer independently confirmed both findings resolved, including the LZMA follow-up, with 48 focused tests. No concrete relevant regression remained.

Final findings: Standards 0 outstanding; Spec 0 outstanding. Ticket 11 and the complete first-version specification are resolved.
