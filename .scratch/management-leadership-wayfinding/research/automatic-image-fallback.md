# Archive-only presentation of images beside absent notes

Investigated: 2026-10-05. Evidence for
[Agree missing-content policy and category hierarchy behavior](../issues/04-conversion-policy.md).
The user requires conversion from the original/future BRZ alone, without
manual retrieval in TheBrain. Important images must be visible in the vault,
and included Markdown supplied by the archive must not be lost.

**The original archive contains enough information to associate and display
all 63 affected ordinary-note images automatically. It does not contain enough
information to reconstruct arbitrary absent authored Markdown exactly.**
A generated available-image section can meet the image-visibility requirement,
while preserving every physically present Markdown body and explicitly reporting
source omissions. The user accepted this route and disclosed type-note/icon
gaps, adding actionable diagnostics for optional source investigation. The
[policy answer](../issues/04-conversion-policy.md#answer) owns the accepted rules.
No fallback implementation has been made or tested in this investigation.

## Archive-only facts

Investigation read the original supplied archive, its attachment/thought/history
records and actual present payloads. It did not use the Brain UI or recovered
note bodies to select the 63 missing ordinary-note owners or their available
images. The recovered files and visual review are independent reference controls.

- All 63 non-forgotten ordinary missing-note owners have exactly one owned
  source Type-12/NoteType-0 image and no direct Type-5 icon.
- Every image has physical state-1 bytes, passes ZIP CRC, matches its declared
  length and fully decodes with nonzero dimensions. Formats are 62 WEBP and
  one PNG. The existing source owner identity and image attachment role establish
  association without remote retrieval or title/filename guessing.
- The absent note declarations are Type 1, NoteType 4, SourceType 2,
  Position 0 and raw state 3. Declared lengths are 62 at 67 bytes and one at
  64 bytes. State 3 remains an observed raw value, not an authoritative definition.
- Image records contain no missing-body bytes, explicit Markdown reference
  spans, captions or authored layout. Names/locations are GUID image filenames;
  `Position=0` does not identify their position within the authored note.
- The 64 history entries associated with these missing note attachments omit
  both `OldValue` and `NewValue`; they provide no missing Markdown text.

The [complete recovery reference](native-source-recovery.md) proves that this
specific cohort's real bodies each contain only one image embed. The
[visual review](native-source-recovery.md#actual-content-and-separation-from-icons)
establishes 62 substantive cards and one workflow chart; the user confirms their
importance. This supports the requested fallback, but future missing bodies
cannot be certified image-only from ownership, an image and a byte length alone.

## Controls and the preservation boundary

The original contains 273 present image-bearing note controls. Of these, 110
have a single image embed; all are image-only. There are 163 with two images:
162 use a Markdown table-row layout, while one separates the embeds only with
whitespace. None of these controls contains extra prose. All their image records
use Position 0, so those records cannot reproduce the authored order/table layout
on their own. The only present 64/67-byte control is a 67-byte image-only note.
No same-length prose counterexample was found in this finite archive.

This evidence gives two distinct guarantees:

1. **For Markdown actually in the BRZ**, preserve its content, including table
   syntax, image order, prose, captions and line endings, through the established
   exact-source reference-adaptation path. A fallback must never replace a
   physically present body, including a blank body. The separately settled
   forgotten-thought exclusion still governs content intentionally removed.
2. **For an absent Markdown payload**, preserve the declared omission as a source
   gap and show the valid available owned images in a generated section. Do not
   claim an exact authored body, fabricate an original-note backup, count
   generated embeds as authored references or imply unseen prose was recovered.

Absent content was already outside the input archive; conversion cannot recover
unknown prose from pixels or attachment ownership. Byte-length similarity is
supporting evidence, not proof. The success report must distinguish preservation
of supplied content from completeness of the live Brain's unavailable content.

## Existing implementation seams

Version 2 currently refuses state 3 before these cases can reach a plan, and
requires authored-note payloads to be physically present. The reviewed absence
rules cover other roles, not these notes. A source rule and corresponding
reviewed disposition are therefore required; blanket state acceptance would
not implement the requested behavior safely.
See [source normalization](../../../src/brz2obsidian/sources/thebrain/attachments.py)
and [reviewed profile](../../../src/brz2obsidian/sources/thebrain/profile.py).

The source-neutral Asset contract can already represent an absent declaration,
but a Document requires its owner's present original-note Asset. A truthful
fallback must retain the missing note as absent and generate destination
presentation from available image Assets, rather than invent a Document.
See [contracts](../../../src/brz2obsidian/contracts.py) and
[analysis invariants](../../../src/brz2obsidian/core/analysis.py).

Present owned images already create eligible owners, receive copy targets and
appear as Resources links when no authored reference uses them. The required
change is to make them visually embedded for the agreed missing-note case,
with separate generated-presentation evidence. Existing authored references
continue using their original text/span path.
See [resource planning](../../../src/brz2obsidian/core/resources.py),
[resource presentation](../../../src/brz2obsidian/obsidian/resources.py),
[authored Markdown adaptation](../../../src/brz2obsidian/obsidian/documents.py)
and [vault/report rendering](../../../src/brz2obsidian/obsidian/rendering.py).

Missing icons require their own outcome: appearance currently refuses a declared
absent icon even if asset absence is permitted. Do not repurpose full-card images
as category icons. The original's eight absent type icons and two absent type
notes therefore need an explicit source-gap policy alongside image fallback.
See [appearance](../../../src/brz2obsidian/core/appearance.py).

The original-note-retention claim in the migration report must be qualified
when source note bytes are absent. Inspect findings, generated-note notices,
report/record accounting, preserved asset hashes and publication receipt must
agree. Forgotten content must not re-enter through unfiltered source evidence.

## Proposed verification and remaining decisions

The subsequent specification should require conversion of the **unaltered
original BRZ**, with no live Brain dependency. The recovered backup supplies
comparison evidence only. No conversion or new production tests were run in
this policy investigation.

Meaningful independent controls include:

- Missing note plus one valid owned image: an image is visible, original image
  hash is preserved, source absence is reported and no authored bytes are invented.
- A present blank/prose/table/multiple-image note: content and authored layout
  survive, with no missing-note fallback replacing it.
- Missing note with multiple images: if supported, generated order is explicit
  and no authored order/caption is claimed.
- Missing note without available images, absent/invalid images, wrong-owner
  images, ambiguous note declarations and unknown/contradictory states: follow
  separately specified limits rather than silently creating reassuring empty notes.
- Forgotten owners/resources/references: no generated image, record or notice
  bypasses the settled exclusion.
- Original type-note/icon omissions: any accepted warning/neutral-appearance
  outcome is verified separately from preservation of the important card images.

The [independent raw-source acceptance driver](../../../tests/local_acceptance/facts.py)
currently requires present note bodies; its
[checker](../../../tests/local_acceptance/checker.py) likewise needs new predicates
and presentation/accounting checks. Converter-generated expectations cannot
substitute for independent source evidence. Regression against prior accepted
archives and native Obsidian image visibility remain implementation gates.

The policy ticket resolves automatic fallback reporting and the absent
icon/type-note outcome. The representative prototype next reviews the visible
result before to-spec and to-tickets.

## Actionable diagnosis without mandatory source repair

The user's added requirement is to identify affected included thoughts so they
can optionally investigate or repair them in TheBrain. The migration report
needs a readable source repair checklist and matching structured record entries:
archive/Brain identity, original thought title/ID, missing attachment role/ID,
expected archive path, raw state/length/physical absence, vault-note link and
the chosen fallback. Icon providers and their affected included members must be
distinguished. These are observed gaps, not confirmed diagnoses of a vendor bug.

Existing item targets carry original title/identity and destination path, and
source identity supplies the Brain ID. The current human warning report does
not render Issue affected/evidence fields as owner-labelled diagnostic rows;
actionable mapping is an implementation requirement, not an existing feature.
See [report/record renderer](../../../src/brz2obsidian/obsidian/rendering.py).

Source IDs and titles provide a reliable identification fallback. A clickable
native source locator may be provided where verified; acceptance of a brain://
reference by the importer does not itself prove native app launch or Brain
selection. Do not fabricate an unverified locator. Inspection/repair remains
optional, with no native access needed to produce the vault. Forgotten subjects,
dependent details and unsafe raw history must not enter the checklist.

Private scripts/aggregate receipts and code-seam findings are under
`tmp/ml-wayfinding/automatic-image-fallback/`. Literal image inspection evidence
is under `tmp/ml-wayfinding/recovered-image-review/`. Durable findings above use
aggregate counts and structural examples, without publishing private source IDs,
titles, URLs or note text. Original archive reads did not alter its bytes.
