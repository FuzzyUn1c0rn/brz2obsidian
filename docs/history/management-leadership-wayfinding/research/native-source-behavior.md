# Native source verification and controlled exports

Observed: 2026-10-05. Question:
[Verify absent content and type hierarchy in native TheBrain](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/73).

**Follow-up:** [Complete recovery of the active missing-note cohort](native-source-recovery.md)
records subsequent retrieval of all 60 remaining active notes and a validated
fresh backup containing all 73 in-scope cohort files. The observations below
describe the earlier bounded controls; their remaining-note counts are historical.

**The live source yielded 13 of the original 74 absent files: all eight type
icons, three ordinary notes and both short type notes.** Their exact local bytes
are preserved in a fresh BRZ backup. Recovery is partial: 61 ordinary notes are
still absent, including one on a forgotten thought. The user's exclusion of
forgotten thoughts leaves **60 unavailable notes on thoughts in scope**. This
does not establish that those remaining notes are irrecoverable.

Native observation also confirms ordinary hierarchy involving thought types,
including a type with six direct ordinary parents. These are separate from type
assignment. No converter behavior or missing-content policy was chosen here.

## Source identity and observation conditions

- Windows desktop **TheBrain 15.0.624.0**; the open Brain's identity matches the
  original archive. Private captures record the exact identifiers and build UI.
- The user confirmed **Desktop Backup to BRZ** as the original export route and
  noticed no export warnings. The original producing build and settings remain
  unverified; the currently installed build cannot establish them retrospectively.
- At observation, **Light sync attachments was unchecked**, automatic sync was
  checked and the status was **Up to date**. These settings were left as found.
  A normal sync request returned to Up to date without downloading the remaining
  files. That status did not certify full attachment availability.
- Original note text, icons, relationships and source identities were not
  edited. Native navigation changes activation timestamps and fetching source
  files changes local availability. No integrity repair was performed.

The supported **Show Attachment in Folder** action disclosed the owned file
store. Correlation used only the 74 expected paths from the completed research
checklist. Exact bytes were copied privately, hashed and compared with re-export;
no note was manufactured from its neighboring image or declared length.

## Representative note and icon observations

| Control | Native observation | Exact-byte result |
| --- | --- | --- |
| Typed ordinary note, declared 67 bytes | Rich and Text views initially appeared blank. After fetching its file and reopening the thought, the image rendered. | 67-byte image-only Markdown with CRLF; its referenced image is already in the original archive. |
| Untyped ordinary note, declared 67 bytes | Initially blank; separate ZIP/PDF resource cards were visible. | Another 67-byte image-only Markdown file, referencing an original present image. |
| Ordinary note, declared 64 bytes | Initially blank; inherited type icon visible. | 64-byte image-only Markdown with UTF-8 BOM and no newline, referencing an original present image. The later literal-byte review corrected the initial newline description. |
| Ordinary note, declared 69 bytes | UUID navigation identified a struck-through forgotten thought; name search had not returned it. Note view was blank. | Not fetched. It is the sole forgotten owner in the original missing-note cohort and is excluded by the user's requirement. |
| Both type-owned notes, declared 5 and 7 bytes | Rich and Text views appeared blank. | UTF-8 BOM plus one and two CRLF sequences respectively. These specific recovered notes contain only encoding/whitespace bytes. |
| All eight type-owned icons | All eight providers showed custom icons; matching member appearance was visible in the Plex. | Eight owned PNG files, all matching their declared lengths; all appear in the fresh backups. Their providers collectively classify 45 ordinary members. |

The three recovered ordinary notes total 198 bytes; the two type notes total 12;
the eight icons total 17,141. All 13 lengths match their original declarations.
Owned paths, attachment/owner identities, source timestamps and SHA-256 values
are recorded privately. The final archive contains exactly the captured local
bytes for all 13, verified by byte comparison and SHA-256.

**Initial blank display was not evidence of an empty or lost note.** The
image-only control rendered after the raw file became available. The short type
notes can be classified as whitespace only because their actual bytes were
read. Neither observation supplies the contents of the 60 remaining active
notes. Direct source recovery establishes the current bytes for the declared
identities; there is no original digest for the absent payloads with which to
prove their equality at the time of the original backup.

## Controlled export comparison

Both full-Brain desktop backups used fresh ignored destinations, with the
existing archive access-control selection left unchanged. Both showed 100% and
**Backup created**, with no warning observed in the completion UI. They are
separate experimental snapshots, not replacements for the supplied archive.

| Measurement | Original | First control: after eight icons and one note | Final control: after all probes |
| --- | ---: | ---: | ---: |
| Compressed bytes | 320,594,486 | 320,606,374 | 320,607,321 |
| Physical payloads | 1,024 | 1,033 | 1,037 |
| Files recovered from the 74-file cohort | 0 | 9 | 13 |
| Cohort files still absent | 74 | 65 | 61 |
| Cohort states | 74 at 3 | 9 at 1; 65 at 3 | 13 at 1; 61 at 3 |
| ZIP CRC failures | None in prior assessment | None | None |

Archive SHA-256 fingerprints:

- Original: `2b24c1d21b4090f3b0ed3ec0227f269b8c7a4e5b6832ada0e244a1dcfc941ced`
- First control: `6614aecfc26dd07e2c2b0db2c98b171e410921a8c1282f9a2a631480359dc953`
- Final control: `49825b5ff837d232dd9f18074ef79fc21b15fc364f03596d11188abfffa17335`

Both controls preserve every one of the original 1,024 payloads byte for byte,
remove none and retain the same Brain identity, 586 thoughts, 753 links and
1,568 attachment records. All record identity sets remain unchanged. Record
field differences are `SyncSentId` resets and thought `ActivationDateTime`
changes from navigation (12 thoughts in the first control, 13 in the final).
The only changed `meta.json` property is `AttachmentFileStates`. Attachment
declarations, content modification metadata and relationship meanings are
unchanged. The separate 13 absent state-2 TXT declarations remain present as
declarations and absent as payloads.

For these 13 files, the observed transition is **absent/state 3 → available/state
1** after source retrieval. This is an experimental association, not an
authoritative definition of the producer's numeric enum. A successful backup
receipt alone did not guarantee that every declared file was included.

A separate native **Markdown Files** control used the existing defaults:
include title and attachments, CommonMark off, local Brain links, full export.
It completed and produced 330 Markdown files. Only one of the 64 missing-note
owners' image filenames appeared in exported Markdown—the already recovered
ordinary note at that point. The local-file inventory remained at nine after
this export. It did not recover additional missing raw files. Its title and
image-path rewrites also make it transformed output, not an exact Notes.md
recovery route.

## Hierarchy and forgotten-thought accounting

Native controls show an ordinary parent above a thought type, with assigned
members below the type and classification displayed independently in a member's
Type field. The multiple-parent control has **six direct ordinary parents** in
the raw relationships. Its Plex also displays a shared ordinary ancestor as
context; that seventh visible label is not a seventh direct parent. A converter
must derive direct edges from records, not count all visible Plex labels.

The original and both controls retain 54 ordinary-to-type hierarchy links,
connecting seven distinct ordinary parents to 46 type children. Their fields
are `Kind=1`, `Relation=1`, `Meaning=1`, `Direction=-1`, with an ordinary A endpoint
and a type B endpoint. The separate 332 instance-of links remain unchanged;
there are no subtype links (`Meaning=3`). These observations support hierarchy
navigation alongside category membership; they do not introduce type inheritance
or choose the destination layout.

The original records mark **16 ordinary thoughts forgotten**, owning 11
attachment declarations and touching 23 distinct relationships. Seven of their
payloads are present, three declarations are external URL resources and one is
the absent 69-byte note. The user explicitly requires excluding forgotten
thoughts. This is a new scope constraint relative to the existing profile,
where [forgotten live thoughts stay eligible](../../../source-coverage.md).
It is independent of attachment state 3: 60 still-unavailable notes belong to
thoughts that are not forgotten. Filtering of dependent resources, relationships,
references and reporting remains a policy/specification question.

## Limits and handoff

- Bulk recovery of the remaining 60 active notes was not performed. They remain
  unverified; no irrecoverability conclusion is warranted. If the next decision
  requires complete active content, source preparation needs a separately
  verified recovery/export result before complete migration can be claimed.
- An isolated restore was not performed. The signed-in profile already owns the
  source Brain identity, and no isolated offline/non-sync profile was verified.
  The [prior primary-source research](state-three-evidence.md#what-primary-sources-establish)
  explains why a renamed import is insufficient isolation. No original identity
  was changed and no restore/merge was attempted.
- Numeric state-3 semantics, the cause of the original omissions and the original
  exporter build/settings remain unresolved. Current Light Sync status does not
  establish the settings at original export. No cloud API, online archive or
  vendor-support request was used.
- This task does not make either archive convertible with v2. The
  [original assessment](archive-coverage.md) still establishes refusal and the
  separate hierarchy gap. No production code, accepted specification or
  implementation tickets were changed.

Private captures, raw bytes, exports and one-off verification scripts are under
`tmp/ml-wayfinding/native-source/`; the preceding correlation checklist is under
`tmp/ml-wayfinding/state3/`. The first control's legacy folder name
`backup-before-fetch` means before the later note probes: it already contains the
eight fetched icons and one note. These private artifacts are active evidence,
not reusable test dependencies. The aggregate facts above survive their eventual
cleanup.

Verification used the project interpreter:

```powershell
.venv\Scripts\python.exe tmp\ml-wayfinding\native-source\compare_backup.py backup-before-fetch
.venv\Scripts\python.exe tmp\ml-wayfinding\native-source\compare_backup.py backup-after-probes
.venv\Scripts\python.exe tmp\ml-wayfinding\native-source\verify_receipt.py
```

The next ticket,
[Agree missing-content policy and category hierarchy behavior](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/74),
can now separate proven source recovery, remaining source gaps, required
forgotten filtering and destination hierarchy choices. It remains open for the
user's decisions.
