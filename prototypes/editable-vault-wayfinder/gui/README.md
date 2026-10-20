# Graphical import and update review prototype

Three structurally different presentations of the same synthetic review, on one
standalone route with `?variant=A`, `?variant=B` or `?variant=C`. The design question
is which layout makes whole-update review, explicit decisions and recovery easiest
to understand without Git knowledge. On 2026-10-20 the human selected
**“B — Review workbench”** as the layout direction. This accepts the persistent
review queue beside the active decision workspace; illustrative details remain
outside that verdict.

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

**Selected direction:** B keeps the review queue visible beside the active
comparison/editor. A and C are retained for provenance. The earlier suggestion to
combine B with A's outer stages was an author proposal; the human selected B and
did not approve that hybrid.

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

Support/refusal and history-portability policy follow the accepted
[#248 matrix](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/248#issuecomment-6298978563):
ordinary complete local vault-root repositories, including dirty/staged work, are
conditional targets; built-in normalization/encoding requires specific exact-byte
storage consent; applicable custom storage/execution rules and advanced/shared
layouts are initially refused. Missing history offers verified restore of a
matching complete copy or separately reviewed preservation-first onboarding;
interruptions must be resolved first, and unavailable previous recovery/Undo is
disclosed. Actual capability and Git/filesystem recovery evidence remain for
[#244](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/244) and final specifications.
The guidance performs no repository discovery, backup validation or restoration.

The floating switcher and scenario tools are part of this standalone prototype
only; there is no production route or bundle into which they can ship.

No production tests were added or run. Browser observations and remaining controls
are recorded in the coordinator's generated handoff under
`tmp/merge-wayfinding/gui/`. The syntax check is:

```powershell
node --check prototypes/editable-vault-wayfinder/gui/prototype.js
```

## Accepted presentation scope

The human's exact answer on 2026-10-20, Europe/Paris, was **“B — Review workbench”**.
The question asked for layout direction and explicitly excluded blanket approval
of illustrative details. The selected artifact is commit
`fc98f9b90afcdc45da916ee48b6966cf7ed9f6fd`, `gui/?variant=B`;
the representative capture is
`tmp/merge-wayfinding/prototype-review/gui-B.png`. The owning #245 resolution is
the canonical durable record; this is its local mirror.

| ID | Accepted distinguishing layout detail | Planned implementation check |
| --- | --- | --- |
| GUI-B01 | In the desktop review layout, place a persistent review queue on the left and the active decision/comparison/editor workspace adjacent on the right. | Assert two distinct regions at the public UI seam; independently observe the production desktop layout against the selected artifact. |
| GUI-B02 | Selecting a review group updates the adjacent workspace while retaining the queue as the primary review navigation and the current proposal's decision context. | Exercise queue navigation across compatible changes, conflicts and mappings; independently observe queue persistence, selected content and retained decisions. |

Exact text, queue labels/order/count presentation, colours/spacing, secondary
actions, narrow-window behavior, storage numbers, timing and simulation mechanics
are illustrative. B's selection does not establish backend capability or approve
every screen. #240 and #248 govern already accepted product/support behavior;
their policy is distinct from this layout verdict.

No further material layout question is needed to resolve this prototype activity.
Final specifications in #247 must carry GUI-B01/GUI-B02 and define the production
contracts, remaining detailed presentation and acceptance checks. Independent
actual-production presentation review, including narrow/overflow/scrollbar
usability and applicable hidden states, remains required by the presentation
procedure. Those implementation checks do not require another prototype-choice
approval.
