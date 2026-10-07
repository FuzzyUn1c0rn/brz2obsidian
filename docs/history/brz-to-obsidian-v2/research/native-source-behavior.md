# Native source behavior and controlled export evidence

Completed 2026-10-04 through the user-authorized Computer skill, including the approved synthetic icon deletion and the PDF import assisted by the user. The bounded checks establish type appearance/override behavior, the unusual note's native role, PDF viewing and control content search, and URL presentation. Some TXT-state and lifecycle meanings remain unknown, as qualified below. These observations do not select an Obsidian representation or change a source acceptance rule.

## Build and evidence boundary

The installed application reports **TheBrain 15.0.624.0**, build **2026-09-15 06:50 UTC**. Source observations used the existing Software Engineering Brain. Edits used only the previously created disposable `CONTROLLED_EXPORT` Brain.

The supplied archive remains SHA-256 `7c533a30439e281b1d51d6617c9f1f3cad9c2c1d67e5a1e056f280bf37709764`; a complete ZIP CRC check passes. A source video's displayed thought identity matches its archived owner identity. Earlier native evidence also matched the Brain, type and typed-member identities. Visible resource URLs, note text and selected payload details corroborate the inspected cases. This is not an exhaustive comparison of the live Brain with the archive, and native preview success does not establish byte-for-byte live/archive equality.

Record-level extracts, identity evidence, screenshots and exports stay in ignored `brz/v2-native-source-ticket/`; earlier source identity evidence stays in `brz/v2-research-native/`. This report contains aggregate observations and synthetic control names only.

## Types, assignment and appearance

A new type was created using **Set Thought Type → New Type** for existing ordinary thought `CHILD`. Its definition is named `V2_TYPE_CONTROL`, marked **Type Thought** in the UI, and exported as `Kind=2`. Assigning the same type to `PEER` produced a second ordinary member. Each member's `TypeId` joins exactly one exported type-to-member link with `(Kind, Relation, Meaning, Direction) = (1, 1, 2, -1)`. These links are distinct from the fixture's ordinary hierarchy/jump relationships.

The type received a stock ladybird icon, foreground `#6070FF`, background `#FFE050`, and label `TYPE LABEL A`. The first member visibly inherited the icon and both colours. The icon appeared both in the Plex and next to the thought's heading; the tested colours affected the Plex/history presentation, while the note heading retained its normal text styling. The member owned no icon file and stored no direct colours.

An explicit butterfly icon, foreground `#FF0000`, background `#A0FFFF`, and label `MEMBER LABEL` were then set on `CHILD`. Its Plex appearance used its own icon and colours. `PEER`, assigned later, retained the type's appearance. The supplied Brain independently contains one assigned ordinary member with an owned icon that displays its own icon rather than its type's icon.

| Export stage | `CHILD` direct colours | `CHILD` label | Owned member icon | Displayed result |
| --- | --- | --- | --- | --- |
| Baseline | Both fields omitted | Field omitted | None | Type icon and both type colours |
| Overrides | Foreground `-65536`, background `-6225921` | `MEMBER LABEL` | One PNG, 8,938 bytes | Member icon and both member colours; own label in note panel |
| Colour/label reset | Both fields omitted again | Field omitted again | Same owned PNG retained | Type colours restored; own icon retained; no member label displayed |
| Icon reset | Both fields still omitted | Field still omitted | None | Type icon restored in Plex and note heading; type colours retained |

Choosing **Default** separately for Text and Fill removes the corresponding direct colour field on export and restores the inherited colour. Palette colours in these samples export as signed 32-bit values corresponding to opaque ARGB: type foreground `0xFF6070FF` (`-10456833`), type background `0xFFFFE050` (`-8112`), direct foreground `0xFFFF0000`, direct background `0xFFA0FFFF`. Translucent colours and other encodings were not tested.

The type owns one PNG icon of 6,914 bytes. Before PDF import, inherited control members have the observed token `ThoughtIconInfo="1::0:False:False:0:"`; an owned stock icon produces `"7::0:False:False:0:"` and an `IsIcon=true`, Type-5 attachment with actual bytes under the owner's `.data/`. Importing the PDF later changes `CHILD`'s token to `"4:pdf-control.pdf:1:False:False:0:"`, while it still owns no icon attachment and displays the type's ladybird in the Plex and note heading. The token therefore also changes with attachment presence; `1` alone cannot be treated as a universal inheritance marker. These are bounded paired observations, not a complete specification of the token grammar or every default/reset state.

**Label qualification:** assigning this labelled type to two existing thoughts did not populate their label editors, create a member `Label` field, or show the type label beneath their native note headings. The explicit member label appeared there; clearing it restored a blank label rather than the type label. The type's own label remained visible on its definition. The earlier supplied typed member likewise had a blank label editor. Do not infer effective member labels with `member.Label or type.Label` from older generic inheritance descriptions. New-instance creation, other settings and historical builds were not tested; a requirement for broader label propagation needs its own evidence.

After the user's explicit approval, **Delete Icon** removed only the synthetic member's butterfly icon. The type's ladybird icon returned in both Plex and note heading. Export retained the member's `TypeId`, restored `ThoughtIconInfo="1::0:False:False:0:"`, and contained no owned member icon attachment or member icon payload. The type's own icon remained present. No non-deleting inherit/reset action was observed. Type appearance changes after explicit member overrides, an entirely blank type label, supertype hierarchies and type-authored content were not tested.

## Nonempty NoteType-0 Markdown

The unusual Type-1 / NoteType-0 `Notes.md` (352 bytes) appears in its owner's primary **Rich Text** thought-note surface. The native **Text** view shows a `Notes.md` breadcrumb and the same archived Markdown: an image reference, heading and two paragraphs. No source edit was made. This supplies direct evidence that this particular payload is presented as thought-note content, rather than establishing a general rule for all NoteType-0 files.

The future coverage decision must determine its narrowly supported eligibility, preservation and reporting. The filename alone is insufficient to classify arbitrary Markdown attachments.

## Absent TXT records beside PDFs

All four Type-15 / NoteType-0 TXT declarations have zero declared length and no archive bytes. **Each TXT filename stem equals a PDF attachment identity under the same owner**; all four corresponding PDF payloads are present and their lengths match the declarations. This identity correlation is newly checked evidence, stronger than merely sharing an owner.

Their two owners list the PDFs and external URLs as normal native resources, with no separate TXT entry on the primary thought surfaces. All four PDFs open in the native PDF viewer: observed page counts are 337, 337, 342 and 411. Opening the PDFs establishes working viewing in the live Brain on this build. It does not establish the availability of omitted TXT bytes in the live store, extraction provenance, completeness of Brain content search, or the result of importing this BRZ into a fresh Brain.

The [documentation investigation](attachment-text-evidence.md) establishes general PDF text extraction/indexing but found no authoritative definition of numeric Type 15 or archived file state 2. The four archived records have state 2; its meaning remains unknown. Do not reinterpret zero declared length as proof of an optional cache, failed extraction or harmless absence.

The user uploaded the approved one-page synthetic `pdf-control.pdf` (611 bytes) into `CONTROLLED_EXPORT` → `CHILD`. Native preview displays its unique text, `V2PDFCONTROL7429 extraction sentinel`. Searching for `V2PDFCONTROL7429` returns the PDF under **Notes and Attachments**, with no thought-name/link result. The sentinel is absent from thought names, the filename and every other exported resource, supporting PDF content search in this control. The primary thought surface lists the PDF alone, with an empty thought note and no TXT resource entry.

The controlled export adds exactly two attachment records: the PDF and a Type-15 / NoteType-0 TXT declaration. The TXT filename stem equals the PDF attachment identity, and both share an owner. Its declared length is **37 bytes**, compatible with the PDF's 36-byte ASCII text plus a newline; the TXT bytes themselves are **absent everywhere in the ZIP**, so their exact content cannot be read or asserted. The PDF bytes are present, byte-equal to the uploaded file, and marked file state **1**; the TXT is marked **2**. All ZIP CRCs pass.

Together, the controlled import, identity join, text-sized declaration and successful content search support an association of this Type-15 record with PDF text processing. They demonstrate that this build can export an absent, positive-length TXT declaration while live PDF content search works. They do not prove that the index consumes that exact TXT record, define Type 15 universally, define state 2, explain the supplied zero lengths, or guarantee search after a fresh archive restore. The original four PDFs' content search was not tested. Those limits remain inputs to the coverage decision; the existing version-1 warning rule for positive-length missing TXT files has not been broadened.

Computer rejected input to the owned native file picker, so the user completed selection by pasting the containing folder into its address bar, visually selecting the PDF and confirming. Use that folder-navigation method when a future picker requires human assistance.

## URL resources carrying VideoHtml

All four owners display a single external URL resource corresponding to each archived Type-3 attachment with `VideoHtml`. One owner also displays its independent Markdown thought note below the URL. No second resource entry represents the iframe, and no archived video file is present.

Opening each URL shows **External URL**, the original URL (including its query parameters), and a remote content pane. YouTube content loads in that pane; the final observed states show its consent screen. Playback completion, availability without a network, and cookie/account-dependent behavior were not tested. No login, consent change or video download was performed.

The observed presentation and archive structure support treating the URL and iframe metadata as two aspects of one resource, rather than two independently archived videos. The UI does not expose which rendering path consumes the stored `VideoHtml`; remote page loading alone does not prove that exact HTML was executed. Preserve that distinction when deciding whether the vault should use a link, an optional embed or retained metadata.

## Reproduction and verification

The five private snapshots are `baseline/CONTROLLED_EXPORT 2026-10-04.brz`, `overrides/CONTROLLED_EXPORT 2026-10-04.brz`, `reset/CONTROLLED_EXPORT 2026-10-04.brz`, `icon-reset/CONTROLLED_EXPORT 2026-10-04.brz` and `pdf-import/CONTROLLED_EXPORT 2026-10-04.brz` beneath the evidence directory. Each was generated through **File → Backup to Brain Archive** into its own folder. The final PDF snapshot has SHA-256 `5fe8ca73eff7534eba21c9254e829e6b7caceec238dc1189dd5fe4950f3b299f`.

Run the [bounded comparison script](inspect_native_controls.py) using the project's interpreter:

```powershell
& '.venv\Scripts\python.exe' '.scratch\brz-to-obsidian-v2\research\inspect_native_controls.py' 'brz\v2-native-source-ticket' --source 'brz\Software Engineering 2026-10-04.brz'
```

It validates CRCs, assignment joins, owned icon payload lengths, paired direct-field changes/resets, the PDF-related icon-token change, the four source TXT/PDF identity joins and states, and the controlled PDF/TXT pair, states, byte equality and omitted TXT payload. It also checks that no other exported resource contains the control's search sentinel. It emits hashes and aggregate/synthetic facts without private owner names, identities or URLs. Results are saved privately as `comparison.json`. This tooling is not a production parser or new acceptance policy. No converter code was changed or production test suite run for these evidence-only changes.
