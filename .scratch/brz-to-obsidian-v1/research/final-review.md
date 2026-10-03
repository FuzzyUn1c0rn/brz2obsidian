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

Pending [review repair ticket 11](../issues/11-final-review-repairs.md). Overall specification closure waits for verified repair integration.
