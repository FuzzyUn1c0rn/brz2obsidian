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

**Pending integration verification:** Root will integrate the repair commit, rerun the six independent real-export acceptance conversions, compare emitted content with prior output, and repeat native observations if emitted behavior changed. Overall specification closure and ticket 11's final criterion remain pending until those checks are recorded.
