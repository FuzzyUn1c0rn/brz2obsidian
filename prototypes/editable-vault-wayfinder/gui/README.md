# Graphical import and update review prototype

Three structurally different presentations of the same synthetic review, on one
standalone route with `?variant=A`, `?variant=B` or `?variant=C`. The design question
is which layout makes whole-update review, explicit decisions and recovery easiest
to understand without Git knowledge. This artifact proposes choices; it records no
human approval.

From the repository root, run:

```powershell
.venv\Scripts\python.exe prototypes/editable-vault-wayfinder/gui/serve.py
```

This opens [variant A](http://127.0.0.1:8766/?variant=A). Use the floating bottom
switcher or the left/right arrow keys to compare variants. Arrow keys retain their
normal behavior inside inputs, textareas, selects and editable content. The current
review state and edited result survive variant switches. The URL variant survives
reload; the simulated review itself resets on reload. Stop the server with Ctrl+C.
Use `--no-open` to serve without opening a browser, or `--port 8767` for another
local port. Double-clicking `index.html` also works.

## Variants and tradeoffs

| Variant | Structure | What it tests | Tradeoff |
| --- | --- | --- | --- |
| A · Guided task sheet | Four operation steps, one review group at a time, persistent task footer | A compact extension of the current Windows task sheet; obvious preparation/review/apply sequence | More navigation between decision groups; large-review context is less persistent |
| B · Review workbench | Persistent decision queue beside the active comparison/editor; counts remain visible | Fast movement between conflicts, mappings and blockers in a large update | A wider window helps; narrow windows turn the queue into horizontal navigation |
| C · Change ledger | Broad expandable groups in one vertical document; comparisons and decisions expand in place | Scan the operation as a whole and revisit decisions without changing screens | Long review pages; multiple open groups can dilute the next required action |

**Recommendation to discuss:** B for a large update, with A's explicit operation
steps before review and at application. B keeps the remaining decision work visible
beside editing. This is an author recommendation, not a user decision. C provides a
useful alternative if reviewing an entire operation as a document feels clearer.

All three use Segoe UI, the current green/grey palette, bordered white task sheet,
native-looking rectangular controls, pale findings panels and a restrained footer.
The comparison reference is `src/brz2obsidian_ui/window.py` at the dispatched base
`e9b5148f6446719db57e41f1f80ec5c5bd4673a4`; its existing styling is context, not
approval of these new screens.

## Review walkthrough

Use the **Scenario** menu above the app. It is prototype tooling, not part of the
proposed product. It resets the synthetic state deliberately.

1. **Choose archive and vault:** select the recognized Brain, an older/partial
   export, or an unrelated first import. Edit the synthetic vault path. For the
   unrelated Brain, inspect the proposed folder and explicit category/tag choices.
2. **Large update:** inspect the 1,741-file summary, retained absences, preserved
   local edits and findings. Approve the compatible group; search representative
   comparisons. Resolve note text by keeping either version or editing the result.
3. **Attachment conflict:** choose keep both, inspect distinct incoming path and
   link consequences, choose the three imported references' destinations, then
   save the decision. Existing vault links keep their current meaning.
4. **Category & tag mapping:** choose each mapping separately. Reuse Method to
   reveal the incompatible tag-dashboard warning and the separately reviewed view
   option. Source category prose/attachments remain in a linked imported reference.
5. **Other choices / blockers:** separately choose vault configuration; inspect
   optional rename and deleted-note restoration. Resolve the ambiguous source
   identity and explicitly consent to tracking the excluded modified attachment.
6. **Older vault / absent history:** choose original-output evidence or uncertain
   review; preserve the representative uncertain vault version, then continue.
7. **Saved / stale review:** use Save & close, then resume after a simulated vault
   edit; or choose the saved-review scenario. Refresh, inspect the later owner line,
   resolve only the invalidated conflict. Unaffected mappings remain.
8. **Resolved review / final check:** inspect scope and exclusions, acknowledge the
   checkpoint, pause editing, then apply. During progress, simulate interruption.
   Review a later edit before either finishing or restoring affected files.
9. **Completed update:** review the most recent operation's Undo, choose how to
   protect the later edit and confirm the brief editing pause before applying.
   History/storage discloses cleanup consequences without deleting anything.

The visible **Prototype state** disclosure below the app exposes all relevant
decisions and unresolved groups after actions and variant changes.

## Evidence and limits

This is a presentation prototype, not production UI or a reconciliation engine.
All paths, sources, previews, file counts, comparison results, identities, checkpoint
sizes and progress are synthetic. It uses no filesystem or network mutation API,
storage API, repository commands, retained vault or actual BRZ content. The local
server serves these source files only. Saved review, stale detection, apply,
recovery, Undo and cleanup are simulations. Reload resets state; no durable review
is written. A small representative inventory stands in for 782 compatible changes;
comparison dialogs use illustrative text. Timings do not establish scale or
responsiveness limits. Native Qt rendering and Obsidian behavior remain unverified.

Support/refusal and history-portability policy belong to
[#248](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/248). GUI guidance explicitly
keeps their unresolved details pending. Actual Git/filesystem recovery evidence
belongs to [#244](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/244).

The floating switcher and scenario tools are part of this standalone prototype
only; there is no production route or bundle into which they can ship.

No production tests were added or run. Browser observations and remaining controls
are recorded in the coordinator's generated handoff under
`tmp/merge-wayfinding/gui/`. The syntax check is:

```powershell
node --check prototypes/editable-vault-wayfinder/gui/prototype.js
```

## Human decisions still required

Select a layout, or specify which structural parts to combine. Correct wording,
prominence and action ordering where needed, especially the uncertainty review,
binary link effects, category-dashboard warning, final editing pause and recovery
choices. Confirming a layout alone does not accept every illustrative detail.
After that verdict, the owning ticket must record exact artifact/reference,
decision-rich requirements with stable presentation IDs, and planned independent
checks. No accepted-presentation IDs have been assigned in this proposal.
