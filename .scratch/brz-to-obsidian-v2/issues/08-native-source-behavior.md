# Verify the new source behaviors in native TheBrain

Status: resolved
Type: task
Labels: wayfinder:task
Parent: [Find the route to version 2 for the Software Engineering Brain](../map.md)
Blocked by: 01, 09
Assignee: /root

## Question

What native observations and small controlled exports are needed to settle the remaining source meanings before choosing version 2's representations and supported coverage?

Use the user-authorized Computer skill in TheBrain. Read the complete source findings, record the actual application build, and check these bounded cases:

- Thought types: confirm assignment, effective icon/foreground/background appearance, inherited label versus a stored label, and the encodings for explicit overrides, defaults and resets that the converter would need to distinguish. Use a tiny disposable controlled Brain for edits/exports; check both native behavior and exported records. The earlier read-only observation corroborates one inherited icon/colour case but does not establish precedence or reset rules.
- The nonempty `Notes.md` recorded as Type 1 / NoteType 0: inspect the actual owner's native note and attachment surfaces to establish whether the payload is active thought-note content, an ordinary attachment or another role. Compare with the archived bytes without changing the supplied Brain. Create a controlled equivalent only if the original observation cannot settle the role.
- The four absent TXT records with declared length zero: investigate their purpose and state, and whether their absence has any effect on the present PDFs or native content. Separate observed behavior from an assumption that they are harmless derived data. Do not broaden the existing warning rule before a reviewed policy is agreed.
- The four external references with `VideoHtml`: establish how TheBrain presents the URL and iframe data and whether they are independent representations of one resource. Retain the distinction between remote playback and archived bytes; no video downloading is required.

Keep record-level evidence, exports and screenshots in ignored `brz/`. Publish a concise aggregate observation/record comparison linked from this ticket, with evidenced meanings, remaining limits and reproducible controlled steps. Recheck archive identities when comparing live user data; live identity alone is not full live/archive equality.

Do not expand these experiments to supertype hierarchies, type-authored files or custom relationship types absent from this archive unless a later coverage decision requires them. If an experiment exposes a new prerequisite, add a focused evidence ticket rather than guessing. Completing this task supplies facts for the human's decisions; it does not select the Obsidian representation or approve a new source-gap rule.

## Comments

- 2026-10-04: Graduated from the map's source-behavior fog after complete archive research identified precise uncertainties. The user explicitly authorized native checks through Computer.
- 2026-10-04: Claimed for native observations and controlled exports. Preserve the supplied Brain and archives; edits belong to the disposable controlled Brain.
- 2026-10-04: Native PDF viewing alone does not establish Type-15 purpose/state. Added the parallel documentation prerequisite, [Verify the purpose and state of attachment text records](09-attachment-text-meaning.md); continue the independent native checks while it runs.
- 2026-10-04: Saved [working native evidence](../research/native-source-behavior.md) and a [reproducible aggregate comparison](../research/inspect_native_controls.py). Installed build verified; active presentation of the unusual note, all four PDF viewers, all four URL resources, type assignment, colour/icon precedence and colour/label reset encodings checked. Type labels did not propagate to the two existing control members; this qualifies older generic inheritance descriptions. The source archive's fingerprint remains unchanged.
- 2026-10-04: Remaining controlled actions require confirmation under the Computer skill: **Upload File** for the prepared 611-byte synthetic PDF into `CONTROLLED_EXPORT`, and **Delete Icon** for the synthetic `CHILD` member's own butterfly icon (already preserved in two private exports). Check PDF content search/export and icon fallback/reset after approval, then update the working report. Ticket remains claimed; no Obsidian mapping or missing-file policy has been selected.
- 2026-10-04: User approved both controlled actions. Icon deletion restored the inherited icon; a separate CRC-verified export removes the member's icon attachment/payload and restores its baseline icon token while retaining `TypeId`. PDF file selection is still pending: Computer rejects the owned picker target and its accessible actions. The user offered to help; the picker is open for the prepared `brz/v2-native-source-ticket/pdf-control.pdf` into `CONTROLLED_EXPORT` → `CHILD`. Continue native content search/export after that selection.
- 2026-10-04: The user completed the approved PDF upload, using the file picker's address bar for the containing folder followed by visual selection. Native preview and content search both find the control's text. Completed the fifth export and the bounded comparison below. The supplied archive's hash remains unchanged; all five controlled exports and the source pass full ZIP CRC checks. Source-specific identities, screenshots and exports remain private. No converter behavior or source-gap policy changed.
- 2026-10-04: Final documentation checks passed: evidence-script syntax, identical aggregate output on repeated runs, local artifact links, blocker references and dependency acyclicity. A public-artifact scan found no source thought/attachment/Brain identities or source resource URLs. The type-representation and other-coverage tickets are now unblocked and unclaimed.

## Answer

Completed the bounded native investigation on **TheBrain 15.0.624.0**, build **2026-09-15 06:50 UTC**. The [native observation and record comparison](../research/native-source-behavior.md) records the evidence and its limits; the [reproduction script](../research/inspect_native_controls.py) rechecks the five private exports and supplied archive using the project `.venv` interpreter.

- Type definitions export as `Kind=2`; both controlled assignments join the member's `TypeId` to the observed assignment-link tuple. Type icon/colours are inherited when direct values are absent. Explicit member icon/colours override them; colour defaults and approved icon deletion restore inheritance and remove the corresponding direct fields or owned icon payload. Type labels did not propagate to the two existing members. PDF import changes the member's icon token without creating an owned icon or changing the visible inherited icon, so the token observations are qualified rather than a universal grammar.
- The particular nonempty Type-1 / NoteType-0 Markdown payload is displayed as active thought-note content in primary Rich Text and Text views. This establishes that case's role, not every Markdown file's eligibility.
- All four supplied PDFs open natively. Each absent zero-length TXT declaration joins its PDF by filename stem equal to attachment identity and shared owner. The synthetic PDF is viewable and searchable by a unique content token; its export creates the same Type-15 / NoteType-0 identity pattern with declared length **37**, file state **2**, and absent TXT bytes. The original PDF bytes remain present and byte-equal. This supplies controlled evidence of association with PDF text processing and shows that an omitted, positive-length TXT declaration can coexist with working live content search.
- All four `VideoHtml` cases present one external URL resource, with no separately archived video. Remote YouTube content loads in their native panes; the observed consent screens do not establish playback or execution of the exact stored iframe HTML.

The [documentation prerequisite](09-attachment-text-meaning.md) and control leave the universal numeric definitions, state-2 meaning, original zero-length cause, original PDF content search and fresh-restore behavior unresolved. Those are explicit inputs to [Choose version 2 coverage for the other archive differences](04-version-two-coverage.md), where the user can require further evidence or select an honest preservation/limitation policy. They are not silently treated as harmless data or an approved warning rule. Live/archive identity and selected content checks also do not establish exhaustive equality of the entire live Brain.

Verification: the evidence script passes for all five snapshots and the source; the source retains SHA-256 `7c533a30439e281b1d51d6617c9f1f3cad9c2c1d67e5a1e056f280bf37709764`. The PDF control's sentinel occurs in no other exported resource. Production code was unchanged, so no production test suite was required for this task. The evidence unblocks the type-representation and other-coverage conversations without deciding them for the user.
