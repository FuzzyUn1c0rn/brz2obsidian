# 11: Resolve final Standards and Spec review findings

Status: claimed

Assignee: /root/review_repairs

**Specification:** [Accepted first version](../spec.md)

**Review:** [Final two-axis review](../research/final-review.md)

**Blocked by:** All implementation tickets 01–10 (resolved).

**What to build:** Repair the two reproduced Spec defects and three Standards maintenance findings without widening the accepted source coverage or public interfaces.

**Acceptance criteria:**

- [x] Corrupt compressed ZIP data and unsupported compression return durable structured refusals through source/Workflow/CLI seams, with actionable diagnostics and no publication.
- [x] Authored trailing Markdown block contexts cannot silently absorb generated Resources or relationship navigation; preserve authored text or explicitly refuse unsupported contexts.
- [x] Share collision decisions and suffix-width progression between note and tag naming while retaining their presentation and diagnostics.
- [x] Share the common readable filename sanitation while retaining resource basename extraction and intentional distinctions.
- [x] Renderer consumes planned inline-resource eligibility without rescanning snapshot image references.
- [ ] Meaningful public regression tests and the full applicable public gates pass; independent real-export acceptance remains valid, and affected native observations are repeated if emitted behavior changes.

**Testing seam:** Accepted public source, Workflow, CLI, core and renderer interfaces. Use synthetic real ZIPs and temporary destinations; never assert private helper calls or modify pristine/private native acceptance vaults.

## Comments

- 2026-10-04: The implement-spec final parallel review reported two reproduced P2 Spec defects and three nonblocking Duplicated Code judgments. One implementer will repair all five findings in an isolated worktree based on the complete integration branch. This is review repair, not additional feature scope.
- 2026-10-04 (/root/review_repairs): Claimed on `codex/brz-v1-review-repairs`, based on the complete integration head `21f3d28`; applied the TDD skill at the accepted public source/Workflow/CLI/core/renderer seams. Each reproduced Spec defect failed a real-input regression before its repair. Corrupt DEFLATE now yields `invalid_source`; method 99 yields `unsupported_feature`. Both are durable structured refusals through the source, inspect/convert Workflow, and JSON CLI, with guidance, no receipt and no publication.
- 2026-10-04 (/root/review_repairs): Markdown composition preserves authored characters and newline spelling, inserting a generated matching fence or comment terminator only when CommonMark parsing shows the next document/navigation would be swallowed. The reusable renderer applies this between documents and before Resources/relationships. Independent parser assertions cover a four-backtick fence, tilde fence, unclosed comment, quote/list containers, indented code and closed fences; the complete Workflow also verifies original backup bytes and visible Resources/Children. An unprovable protected context is explicitly refused with `unsupported_feature` and guidance to close its source block. This is a conservative composition limit, not expanded HTML-note support (TheBrain HTML notes remain unsupported).
- 2026-10-04 (/root/review_repairs): The three Standards judgments are repaired by shared collision decisions/seed-width progression, shared readable filename sanitation (caller-owned resource basename extraction and note-only Unicode control replacement retained), and resource rendering from planned `resource_link`. Existing public behavior tests cover these refactors without private-helper tests.
- 2026-10-04 (/root/review_repairs): Public gates pass with `PYTHONPATH` pointing to this worktree's `src`, using only the root `.venv/Scripts/python.exe`: `-m pytest -q` (287 passed), `-m ruff check .`, `-m ruff format --check .`, `-m pip check`, and `git diff --check`. Latest integration branch merged before completion. The final checkbox remains pending until root integrates these repairs and reruns the six independent private real-export conversions, compares emitted content, and repeats any affected native observations. No private archive or native acceptance vault was changed here.
- 2026-10-04 (/root/review_repairs): Continued the same implementer cycle after independent Spec verification reproduced escaping `lzma.LZMAError`. Merged integration head `63b506d` first. Checked the installed Python 3.14 ZIP decoder set (stored, DEFLATE, BZIP2, LZMA, Zstandard); real synthetic corrupt LZMA, BZIP2 and Zstandard members each failed before repair. LZMA and Zstandard decoder exceptions now become `invalid_source`; member-by-member streaming CRC validation translates only the exact plain BZIP2 `OSError("Invalid data stream")` on a BZIP2 member. A real archive with an injected OS read error still produces an operational failure, and the public scoped payload API translates recognized late decoder failures into `payload_read_failure` rather than leaking raw exceptions. All four compressed forms first inspect cleanly before corruption and then refuse at source/Workflow/JSON CLI boundaries without publication. This adds no dependency, source semantic coverage, or successful artifact changes.
- 2026-10-04 (/root/review_repairs): Follow-up public gates pass under the same interpreter/`PYTHONPATH` discipline: `-m pytest -q` (295 passed), Ruff lint and format, pip check and Git diff check. Latest integration merged before completion. Root reports the six private acceptance runs passed after the earlier repair integration; output comparison and final integration verification remain root-owned and pending in the last criterion.
