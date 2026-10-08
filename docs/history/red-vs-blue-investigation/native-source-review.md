# Red vs Blue source review

Specification: [Support external files, literal angle-bracket prose and sized
image links in BRZ imports](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/78).

Investigation: 2026-10-07; bounded native review: 2026-10-08. No converter fixes
or vault conversion were performed. This report records source evidence for the
requested specification, not acceptance of generated Obsidian presentation.

## Input and reproducible diagnosis

The original private `Red vs Blue 2026-10-07.brz` is 219,504,950 bytes, SHA-256
`bc55f68c9ab3febaa770bfc7a9a90621bcd82107d876664371e1ff8558b4cf68`.
Investigation started at commit `97f525b6af77436d1d998aa618e4f70f2c2f1562`.
The archive contains 756 thoughts, 963 relationships, 1,364 attachment records
and 1,028 ZIP members. Fifteen thoughts are forgotten. Home identifies a live,
included ordinary thought; all ZIP members pass CRC checks.

The original `inspect` operation repeatedly refuses with `invalid_source:
Unsafe or ambiguous local attachment location`. A minimal synthetic BRZ with one
Type-2 absolute Windows file reference reproduces the same refusal. Changing
only its location to a relative name reaches the separate unsupported-role
refusal; changing only its role to supported external-directory Type 8 succeeds.
TheBrain's [staff attachment enum](https://forums.thebrain.com/post/in-links-json-what-are-these-fields-10616870)
defines Type 2 as an external file. The implementation applies archive-local
path validation to this role and does not otherwise support it. Generic Home
guidance is therefore misleading in this case.

There are 17 external-file records across six owners: fourteen MP4 references,
one HTML reference and two PDF references. All have absolute Windows locations,
no local file-state entry and included owners. No archive filename matches were
found for the HTML or videos. The two PDF references share a basename and owner
with a separate intact Type-1 PDF. This does not establish interchangeable
identities or permission to collapse the three attachments.

An in-memory diagnostic projection omitting those records reaches an HTML guard
refusal. Scanning all 360 included present thought notes identifies five notes
with unescaped angle-bracket tokens: `type`, `subtype`, `Enter`, `Password`,
`Value`, `username` and `IP-Adress`. These are Markdown thought notes, not legacy
HTML-note attachment records. Minimal prose with `<Enter>` or
`<type>/<subtype>` reproduces the guard refusal; inline-code controls succeed.

Suppressing that guard only in the diagnostic process exposes image binding
refusals. Checking 619 remaining included active references with the actual
tracer/binder identifies two image destinations ending in `#$width=90p$` and
`#$width=75p$`. Both resolve to present same-owner WebP payloads once only the
fragment is removed from the diagnostic reference value. No original bytes were
changed. This establishes a reference-syntax limitation, not absent image data.

All 1,015 archive-local payload declarations resolve to members. One icon has a
CRC-valid metadata-length discrepancy already allowed by existing policy. The
24 absent local declarations have the existing Type-15 TXT/state-2 shape; this
inventory alone does not certify every existing TXT/PDF policy precondition.
The 41 existing resource/reference workflow tests passed during diagnosis.

## Bounded native batch

The plan selected five subjects, each answering a distinct question: an external
and internal PDF control in one thought, key-like angle notation, slash-separated
angle notation, and the two image-width values in different note contexts. The
limit was these five subjects and fifteen minutes of navigation. The already
open Red vs Blue Brain was inspected without a restore or import. Its Brain
identity and selected thought identities matched the archive. No thought text,
attachment path, content setting, sync setting or security setting was edited.
Navigation and selection can change application activation/UI state.

The installed executable reports TheBrain **15.0.624.0**. Observations used its
light content pane, dark Plex, Rich Text presentation and the existing pane
width. No attachment or external link was opened or executed.

| Subject | Archive thought identity | Observation |
| --- | --- | --- |
| update-alternatives | `be6e8cc2-492a-4a37-aeb8-fc739161cfb9` | The paragraph visibly reads “press 1 and then press <Enter>.” Angle brackets and the word remain literal readable text. |
| File Upload Vulns | `2c9c8d89-9e2d-47b2-aed8-76c0243c4ee7` | The MIME explanation visibly shows `<type>/<subtype>` as prose, alongside its original request screenshot. |
| The Linux Filesystem | `5781ae09-ebf2-4f35-a627-6407b47ba285` | The owned filesystem diagram renders inline. Its source link has the `90p` fragment; original dimensions are 905 × 738. |
| Threat Hunting with Brim: Malware C2 Detection | `5e143d39-3b31-49b5-aac7-7cbc72ee3c32` | The archived screenshot renders between the DNS explanation and subsequent findings. Its source link has the `75p` fragment; original dimensions are 1107 × 1512. |
| Training: Active Defense & Cyber Deception | `c9c4bdd6-85eb-4a40-afcc-b68030272373` | Three same-named PDF entries remain distinct: two have external-reference arrow badges and the third is an internal attachment. All show the same declared 10.48 MB size. The external menu offers moving/copying the file into the Brain. |

The five observations answer the first batch's content and attachment-role
questions. No bulk source recovery or additional subject review was needed.
An attempt to show attachment properties did not produce a usable properties
panel; native path accessibility or external-file existence is not claimed.

## Conversion implications and limits

- Preserve external file references independently of copied archive payloads.
  Their continued accessibility depends on the original external locations.
- Preserve readable angle-bracket prose. Merely accepting it unchanged would
  leave ordinary Markdown HTML interpretation capable of hiding the words.
  Any escaping must be narrowly scoped and recorded, with original bytes kept.
- Resolve sized image links to their original archived image bytes and preserve
  authored placement. Record any change to the sizing declaration explicitly.
  Both images fit the narrow content pane; this observation does **not** establish
  the exact legacy percentage algorithm or approve a destination sizing policy.
- Source observations are references for later native Obsidian verification,
  not user approval of a generated layout. The three unsampled angle-bracket
  notes have byte/parser evidence; their native appearance was not observed.
- Complete conversion/preservation, repeated/reordered results and native
  Obsidian output remain implementation acceptance work. More refusals may be
  discovered once all three confirmed signatures are handled.

TheBrain's [current Markdown reference](https://www.thebrain.com/docs/markdown-info)
distinguishes standard Markdown from its deprecated dialect; it does not justify
assuming this existing Brain was converted to the newer dialect. Source syntax
and the native observations above govern this investigation.

## Private evidence

Disposable diagnostic scripts, raw outcomes, exact per-note failures, the native
plan and screenshots remain under Git-ignored `tmp/red-vs-blue-diagnosis/`.
Native screenshot names are `01-enter-literal`, `02-mime-placeholders`,
`03-filesystem-image-90p`, `04-brim-image-75p`, and
`05-external-and-internal-pdfs`; a sixth capture records the source identity
after attachment review. A private session summary records the app version and
selected cases. These files are supporting local evidence, not required public
test fixtures. The aggregate findings here survive temporary cleanup.
