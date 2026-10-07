# Complete recovery of the active missing-note cohort

Observed: 2026-10-05. Follow-up evidence for
[Agree missing-content policy and category hierarchy behavior](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/74).
This extends the earlier [bounded native controls](native-source-behavior.md).

**All 60 remaining non-forgotten notes were retrieved from the live source.**
Together with the earlier controls, a fresh desktop BRZ backup now contains
73 of the original 74 absent files: 63 ordinary notes, two type notes and eight
type icons. The sole remaining absent cohort file belongs to a forgotten thought
and was deliberately never requested. There are no unavailable active notes
left in this cohort. This is a source-preparation result; conversion has not
been run. The user subsequently required archive-only conversion: the fresh
backup is a reference control, not a required migration input or manual step.

## What the 60 notes actually contain

Each exact expected local path was absent before retrieval. In TheBrain, the
initial Rich/Text view appeared blank. Navigating by the original owner identity
and using **Text attachment menu → Show Attachment in Folder** made each actual
file available. All 60 were retrieved successfully; one immediate read required
a short retry after the native request completed asynchronously.

Literal-byte validation establishes the following for every one of the 60 files:

- Exactly 67 bytes, matching its original attachment declaration.
- An actual UTF-8 BOM and exactly one CRLF, with no bare CR or LF.
- One Markdown image embed, with no accompanying Markdown prose or authored
  thought link. Information within the image is separate from this byte-format
  observation; image-only does not establish that the note has no useful content.
- The referenced image payload is already present in the original archive.
- The captured bytes and SHA-256 match the resulting live local file.

A final representative note rendered its image after retrieval. A separately
broken external URL-card thumbnail remained broken; it is not the note image.
No note bodies were synthesized from images or declared lengths. A similarly
named included thought and forgotten thought were distinguished by identity;
the included note was recovered and the forgotten note was left alone.

These observations answer the user's question about whether the 60 notes were
really gone: their actual content was retrievable. Blank display and an absent
backup payload did not establish deletion, an empty note or irrecoverability.
The supported action demonstrates deferred native attachment availability.
The precise cause of the original export omissions and official numeric state-3
meaning remain unproven.

### Practical difference between the two archives

The original and fresh archive contain the same thoughts and relationships.
For each recovered ordinary note, the original already contains the embedded
image bytes. What the fresh archive adds is its literal Notes.md file identifying
the image to display in the note body. These note images are separate source
roles from the eight recovered type icons. The two recovered type-note files
contain only encoding/blank-line bytes.

An image-only note may carry its substantive text and diagrams inside the image.
Its small Markdown file is therefore not evidence of an empty or unimportant
note. Recovering that file restores the source's actual inline embed rather
than relying on the converter to infer note content from available attachments.
The new backup adds 73 files, preserves every original payload and creates no
new thought.

### Actual content and separation from icons

Follow-up visual inspection covers all 63 recovered ordinary-note images,
selected by their actual note references and extracted from the original BRZ.
There are **62 full illustrated technique/reference cards and one workflow
chart**. Every image contains substantive steps, checklists, diagrams or examples;
none is merely a logo, thought icon, cover or decorative thumbnail. The later
60 are all full cards, covering 53 productivity and seven negotiation techniques.
The user confirms that this content is important and must be visible in Obsidian.

All 63 are source Type-12 images with `IsIcon=false`. None of their owners has
a direct Type-5 icon. Sixty-two owners inherit appearance from ten distinct type
providers; no full-card image hash matches any of the 61 available Type-5 icon
payloads checked, including the eight newly retrieved type icons. Sixty-one
owners also have a separate external URL resource. Its link-card thumbnail is
another distinct UI component, not the embedded reference card.

Across the 63 actual note files, 62 are 67-byte UTF-8-BOM embeds ending in CRLF;
one is a 64-byte UTF-8-BOM embed without a newline. None contains other Markdown
prose or authored thought links. Technique names printed within image pixels
are image content, not authored Markdown references. This corrects the earlier
bounded report's newline description for the 64-byte note.

Private coverage, exact original image receipts, source-role correlations and
representative previews are in `tmp/ml-wayfinding/recovered-image-review/`.
All eleven sheets covering the 63 images were inspected. This establishes this
cohort's content; it does not make an owned image or byte length proof of the
contents of an absent note in a future archive.

## Fresh full-Brain backup and preservation comparison

The native desktop Backup to BRZ action reported green **100% — Backup created**,
with no warning observed. The pre-existing archive access-control selection was
left unchanged. A successful receipt was followed by independent ZIP, identity,
payload and record comparisons.

| Measurement | Original supplied archive | Fresh backup after complete active recovery |
| --- | ---: | ---: |
| Compressed bytes | 320,594,486 | 320,623,812 |
| Physical payloads | 1,024 | 1,097 |
| Recovered files from the original 74-file cohort | 0 | 73 |
| Active ordinary cohort notes still absent | 63 | 0 |
| Forgotten cohort notes still absent | 1 | 1 |
| State-1 entries | 1,024 | 1,097 |
| State-2 entries | 13 | 13 |
| State-3 entries | 74 | 1 |
| Full ZIP CRC failures | None | None |

Archive fingerprints:

- Original `brz/Management & Leadership 2026-10-05.brz`:
  `2b24c1d21b4090f3b0ed3ec0227f269b8c7a4e5b6832ada0e244a1dcfc941ced`.
- Fresh experimental input
  `tmp/ml-wayfinding/remaining-notes/backup/Management & Leadership 2026-10-05.brz`:
  `ff0e7f2d0df844aa89652b00b3d02bb0577857d8621943769a533570a13475b2`.

The fresh archive has the same Brain identity and format 5. All **1,024 original
payloads are byte-identical**, with none removed. All **73 recovered payloads
equal the final captured local bytes and hashes**. The 586 thoughts, 753 links
and 1,568 attachment records retain their identity sets and record counts.
Root-record field changes are limited to `SyncSentId` resets and 74 thought
`ActivationDateTime` values caused by navigation. No content/note/attachment
modification timestamps changed. The only changed `meta.json` property is
`AttachmentFileStates`.

The independent 13 absent state-2 TXT declarations are unchanged. Their
previously accepted v2 handling remains the baseline; this investigation neither
recovered them nor changed that policy. The sole absent state-3 cohort note is
excluded by the user's forgotten-thought requirement, independently of whether
its source bytes could be retrieved.

The fresh backup is still a full-source archive containing forgotten source
records. It requires the proposed converter exclusion feature. It is a distinct
current snapshot, not a repair of the original supplied ZIP. No original digest
exists for its formerly absent payloads, so current-source/local/export equality
cannot prove their bytes at the time of the original export.

## Investigation boundaries and verification evidence

The source app remains TheBrain 15.0.624.0. No source content, identity, sync
settings, permissions or access control were edited. No restore or repair was
performed. Native navigation changes activation times; attachment retrieval
changes local availability. Phase-created Explorer windows were closed and the
Brain returned to its initial home, preserving pre-existing windows and unsaved
user content.

Private owner IDs, note/image paths, exact bytes, screenshots, native receipts
and detailed comparisons are retained under
`tmp/ml-wayfinding/remaining-notes/`. Aggregate validation comes from
`validation-private.json`, `backup-comparison.json` and
`backup-bytes-validation-private.json`; all 60 live/captured comparisons and
all 73 final local/export comparisons passed. These are temporary evidence,
not reusable test dependencies. The original archive remains unchanged.

Verification used the project's interpreter and read-only comparison scripts:

```powershell
.venv\Scripts\python.exe tmp\ml-wayfinding\remaining-notes\validate_recovered.py
.venv\Scripts\python.exe tmp\ml-wayfinding\native-source\compare_backup.py ..\remaining-notes\backup
.venv\Scripts\python.exe tmp\ml-wayfinding\remaining-notes\validate_backup.py
```

This result supplies an independent reference control for an automatic route.
The user requires routine conversion from the original/future BRZ alone, with
relevant images visible and included Markdown preserved. Manual native retrieval
is not an acceptable conversion prerequisite. This evidence does not establish
version-2 convertibility, define unknown attachment states or prove generic
exact reconstruction of absent note bodies. The policy ticket is evaluating
an archive-only fallback before the prototype and specification stages.
