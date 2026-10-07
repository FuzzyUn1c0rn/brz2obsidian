# State-3 declarations: evidence and recovery routes

Checked: 2026-10-05. Question: [Establish state-3 evidence and recovery routes](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/72).

**The supplied archive establishes absent bytes, but the producer meaning of
state `3` remains unknown.** Current first-party sources offer concrete export
and restore controls; none found in this bounded investigation defines the BRZ
`AttachmentFileStates` enum. This resolves the research question, not the
missing-content policy or the native-observation prerequisite.

## Measured archive facts

The read-only correlation examined every state-3 declaration in
`brz/Management & Leadership 2026-10-05.brz`, SHA-256
`2b24c1d21b4090f3b0ed3ec0227f269b8c7a4e5b6832ada0e244a1dcfc941ced`.
It independently decoded the raw JSON records and compared the expected member
paths with the ZIP directory. The file fingerprint remained unchanged.
The [existing assessment](archive-coverage.md#source-identity-and-integrity)
establishes format 5, CRC validity and complete accounting of physical payloads.
Private per-record correlation, script and aggregate receipt are retained under
`tmp/ml-wayfinding/state3/`; durable conclusions follow here.

| Declared role | Records | Physical availability | Declared size |
| --- | ---: | --- | --- |
| Ordinary-thought Markdown note: SourceType 2, Type 1, NoteType 4 | 64 | All absent | Nonzero |
| Thought-type Markdown note: SourceType 2, Type 1, NoteType 4 | 2 | Both absent | 5 and 7 bytes |
| Thought-type icon: SourceType 2, Type 5, NoteType 0 | 8 | All absent | Nonzero |

All 74 have integer state `3`, affecting 72 distinct owners. No expected member
exists, including case-insensitive path comparison. Affected note owners have
no present alternative marked/canonical note payload. The 66 notes declare
4,299 bytes: 62 declare 67 bytes, and one each declares 5, 7, 64 and 69. The
eight icons declare 17,141 bytes. Sixty-three ordinary missing-note owners are
typed members; the icon providers collectively classify 45 ordinary members.
These are record and membership counts, not measured absent-content sizes or
evidence of what the native application currently displays. Source: raw archive,
private `correlate.py`, `state3-private.json` and `aggregate.json` in the path above.

Every one of the 64 affected ordinary-note owners has one present Markdown image;
both affected thought-type-note owners have none. This refines the
[assessment's image correlation](archive-coverage.md#state-3-payloads).
A present 67-byte image-only note elsewhere supplies a plausible structural
example. It does not identify missing-note text, reference spelling, newline or
encoding, or explain omission. Matching filenames, declared lengths, neighboring
image bytes or retained modification history do not authenticate replacement
bytes. No authenticated replacement was established by this investigation.

Keep the separate 13 state-2 records distinct: all are absent, positive-length
TXT declarations with SourceType 2 / Type 15 / NoteType 0 and a present PDF on
the same owner. They fit the existing reviewed absent-TXT warning rule; they are
not the state-3 authored-note/icon cases. State-2 producer semantics likewise
remain unproven. Sources: raw correlation; [existing coverage](../../../source-coverage.md);
[earlier attachment-state research](../../brz-to-obsidian-v2/research/attachment-text-evidence.md).

## What primary sources establish

| Primary source | Established finding | Limit for this archive |
| --- | --- | --- |
| [Current official OpenAPI JSON](https://api.bra.in/v1/docs.json), API version 1.0.5 | A direct unauthenticated HTTP fetch succeeded on 2026-10-05. `AttachmentDto` exposes integer attachment type/source type and nullable `int64` `dataLength`. `AttachmentType` lists 0–15 and 100 without symbolic names. No component property containing `state` or file-state schema was found. | This public API schema does not define BRZ file states. It cannot explain state 3 or prove that absent notes are empty. The web-reader fetch failed; the direct fetched snapshot/result is retained privately under this effort. |
| [Vendor Blazor attachment model](https://github.com/TheBrainTech/thebrain-api-quickstart-blazor/blob/master/TheBrainApiQuickstart/Data/Attachment.cs) | The linked vendor example has integer `type`/`sourceType`, nullable `dataLength`, and no archive file-state member. | An API example cannot provide the missing export enum. |
| [Staff explanation of BRZ JSON export](https://forums.thebrain.com/post/exporting-brain-possible-9725592) | File → Backup to Brain Archive exports a container whose extracted contents include JSON, notes and internal attachments. | General export intent does not certify this particular declaration set or give an omission-state mapping. |
| [Staff guidance on Light Sync and BRZ](https://forums.thebrain.com/post/backup-to-brz-13843490) | Harlan explains that desktop archiving requires disabling Light Sync because locally unavailable attachment bytes cannot be backed up. Rico confirms the online archive workaround. Harlan states that Light Sync is per device. | This supports checking export route/local availability and an online-export control. It does **not** show that this archive used Light Sync, that it was incomplete for that reason, or that 3 means deferred download. |
| [Staff integrity-scan explanation](https://forums.thebrain.com/post/integrity-scans-on-tb14-and-tb15-differ-13796998) | An attachment reference can persist when its file is absent locally and on the server. The scan removes such references; it also removes duplicate references. | Record presence differs from byte availability. A scan would change the evidence and is not a recovery experiment for the original Brain. No numeric state definition is supplied. |
| [Staff restore/GUID explanation](https://forums.thebrain.com/post/restore-from-brain-archive-9622169), [staff import/GUID explanation](https://forums.thebrain.com/post/import-json-archive-9936925) | An archive preserves Brain identity; an imported copy can sync with the corresponding cloud Brain, and an existing identity can prevent import. | A restore control must use an isolated disposable environment rather than assuming that a renamed Brain is isolated. Do not change the original Brain's identity or delete it to make a control import succeed. These are historical explanations; confirm actual prompts in the installed build. |

## Proven meanings, hypotheses and unresolved questions

Proven for this input: integer `3` is present in the archive's file-state map,
the 74 corresponding expected payload members are absent, and the roles and
nonzero declarations above are recorded. The user noticed no warnings during
export. That observation does not certify bytes for each declared attachment.
The archive contains format information, but does not establish the producing
desktop/web build or exact export choices. Sources: raw records and the
[assessment](archive-coverage.md).

Plausible questions to test, **not adopted enum meanings**, are: locally/cloud
unavailable source files; an export omission/failure despite live display; a
special producer convention for short or image-only notes; stale metadata;
different behavior by exporter/build. The image correlation is evidence for
choosing controls, not for reconstructing note content. The Light Sync guidance
is evidence for a full-content control, not a diagnosis.

Unresolved: why this producer wrote `3`; whether affected source notes/icons
still exist; whether a fresh export includes exact source bytes; whether native
restoration reproduces the same gaps; and whether omission is intentional.
No authoritative numeric mapping was found after targeted official/vendor
searches for `AttachmentFileStates`, `FileState`, BRZ state 3, archive missing
files, Light Sync and archive restore, plus direct current API/example reads.
Empty searches establish only this bounded negative result, not that no vendor
documentation exists. No private API requests, native UI actions, Brain repairs
or re-exports were performed.

## Native observation and controlled-export checklist

This is the bounded evidence request for the native-observation child. Record
actual results and failures; do not replace them with assumptions. Use the
private `native-review-private.csv` for exact owner/attachment IDs and expected
member paths, avoiding public publication of titles/content.

1. **Identify source and route.** Record OS, exact desktop or web version/build,
   Brain identity and whether this archive came from desktop backup or online
   export. Capture all selected export options, full-Brain versus selection,
   Light Sync state on that device, sync/download completion status, progress,
   completion message and log errors/warnings. Preserve the original archive.
2. **Read representative notes in the original source.** Inspect the typed
   67-byte cohort, its sole untyped ordinary control, the 64- and 69-byte
   ordinary notes, and both thought-type notes (5/7-byte declarations). For
   each, record rendered content, whether its image loads, any pending download
   indicator/error, and raw file availability through the supported native
   file/folder view. Preserve raw bytes privately if readable and record a
   SHA-256, identity/path and how they were obtained. A screenshot or copied
   rendered text proves display, not exact Markdown bytes. Expand to all 66
   notes before claiming complete recovery.
3. **Inspect all eight icon providers.** Record the thought type's explicit
   icon configuration and displayed icon, a representative assigned member's
   inherited appearance, and availability of the declared owned icon file.
   Read/copy exact owned bytes when available; record identity/path/hash. A
   displayed fallback or inherited icon does not authenticate the missing file.
4. **Make one controlled full export when native availability permits.** Keep
   original content intact. Record the required per-device sync/full-download
   transition; let it finish before desktop backup, following the staff
   guidance above. If unavailable locally but readable online, a separate
   online archive is an evidenced comparison route. Record its build, options,
   completion and fingerprint; compare all 74 declarations, states, membership,
   physical paths and payload hashes with the supplied archive. Do not quietly
   substitute a later edited snapshot for the original input.
5. **Restore into an isolated disposable environment.** Disable cloud sync for
   the control and use separate disposable storage/profile or a separate
   environment; verify isolation before import. Choose new-Brain import.
   Never merge into or delete/change the original Brain to bypass identity
   prompts. Record build/prompts/logs, inspect the same notes/icons, and capture
   exact restored bytes if any. Re-exporting that control is optional: use it
   only to distinguish archive round-trip behavior from original-source/cloud
   availability. If isolation or build behavior is uncertain, leave this test
   unperformed and record the reason.
6. **Use small synthetic controls only if needed.** In a disposable Brain on
   the producing build, compare an empty note, short text note, image-only note
   with one image, thought-type note and owned type icon. Export fully available
   controls, then compare raw notes/icons and states. This can establish that
   build's observed convention; it cannot prove what the missing real notes
   contained. Do not manufacture missing files or run integrity scans on the
   original Brain to produce a desired state.

## Recovery routes and byte authentication

| Route | Evidence needed | What it can establish |
| --- | --- | --- |
| Complete fresh export | Known source identity/build/version; recorded full-export options; all affected declarations correlated to supplied bytes; original-source bytes and hashes where readable | A complete new migration input for that source snapshot. Changes since the original export must be disclosed; a new snapshot does not prove equality with the unavailable original payloads. |
| Exact local/cloud or backup files | Proven attachment/owner/path and source snapshot provenance; readable bytes; SHA-256; source version/digest where available | Provenance-backed recovery. A hash of newly found bytes records them; it proves equality to the original absent bytes only if compared with an authenticated digest/version record for those original bytes. Name, size and timestamps alone are insufficient. |
| Isolated native restore | Exact original archive fingerprint, isolated build/profile, recorded native result, exact output-file hashes and provenance | Observed producer restoration behavior. If native restoration generates bytes, label them as reconstructed/derived until their identity as originals is established. If still absent, it does not establish why the source lost/omitted them. |
| Vendor clarification | Build/format-specific definition of `AttachmentFileStates`, export omission behavior and recovery mechanism tied to this case | Authoritative numeric semantics and potentially a supported recovery route. A future support request needs explicit user authorization before sending private data. |

The archive alone currently cannot guarantee restoration of the absent original
notes/icons. Metadata, matching lengths, present image assets or visually
similar icons cannot supply that guarantee. If these routes yield no exact
source bytes, the next human decision must choose the explicit allowed outcome
and reporting for unavailable content, or retain refusal. This research does
not choose that policy, broaden the state allowlist or approve silent losses.
