# Agree missing-content policy and category hierarchy behavior

Status: resolved
Assignee: /root
Type: grilling
Mode: HITL
Labels: wayfinder:grilling
Parent: [Find the implementation route for the Management & Leadership archive](../map.md)
Blocked by: 01, 02, 03

## Question

The user explicitly requires excluding forgotten thoughts (2026-10-05).
Carry that requirement forward; settle how filtering affects owned attachments,
relationships, references and source accounting. Do not ask the user to choose
whether to include them again, or equate forgotten status with attachment state 3.

Given the established source evidence, what exactly counts as successful
conversion of this archive, and which visible behavior and preservation rules
does the user accept for source gaps and hierarchy involving thought types?

Use [Native source verification and controlled exports](../research/native-source-behavior.md)
and its follow-up, [Complete recovery of the active missing-note cohort](../research/native-source-recovery.md),
alongside the earlier research. The initial 13-file recovery was followed by
retrieval of all 60 remaining active notes. The validated fresh backup contains
all 73 in-scope cohort files; only the excluded forgotten note remains absent.
The original remains unchanged. The user now requires automatic conversion from
the BRZ alone; the earlier fresh-input proposal is withdrawn. Recovered bytes
are a reference control for evaluating archive-only behavior, not a required
source-preparation step. Recovery does not define numeric state 3 or establish
historical absent-byte equality.
The forgotten exclusion changes the existing profile's eligibility rule;
settle its boundaries without reopening the user's requirement.

Use both grilling and domain-modeling. Present the actual evidence before asking
the user to choose; do not make the user research facts the agent can establish.
If exact missing bytes can be recovered, distinguish required source preparation
from converter features. If they cannot, choose refusal versus explicit limited
conversion and define what must be visible in inspection, notes, migration
report/record and category appearance. A successful receipt alone must not imply
recovered source content or a complete original archive.

Agree how ordinary Parents/Children navigation connects to category dashboards,
including multiple parents and placement alongside Bases/source content. Keep
membership and inheritance independent unless new evidence specifically changes
that model. Surface any other material feature choices uncovered by research.

Use concrete edge cases: an absent note with a present image; an absent note on
a type; a category with missing icon and 45 collectively affected members; a
type with more than one ordinary parent; and an unknown state with absent or
contradictory bytes. Preserve the cumulative v2 profile's unrelated meanings.

## Completion criteria

- The user has explicitly settled successful-conversion scope, missing-content
  handling, visible limitations and category hierarchy behavior.
- Evidence requirements and refusal boundaries are precise enough to specify
  positive/negative examples; unresolved choices get their own child/fog entry.
- Domain terms are recorded in GLOSSARY.md only if a new meaning is actually
  agreed; create/reopen an ADR only for a qualifying architecture decision.

## Comments

- 2026-10-05: Claimed at the user's request to continue grilling. Start from the
  completed native evidence and the firm forgotten-thought exclusion; policy
  recommendations remain proposals until the user answers and confirms the
  shared understanding.
- 2026-10-05: Opened the first grilling round. Q1 asks whether recovery of the
  newly absent authored notes/icons is required for acceptance, an explicitly
  limited conversion is acceptable, or both outcomes should be supported.
  Existing approved TXT-gap rules remain the cumulative baseline. Q2 asks
  whether forgotten exclusion also removes their content-bearing raw
  metadata/history from generated audit output or retains that evidence there.
  Recommendations are complete-content acceptance and exclusion IDs/reasons/
  counts only for forgotten records. Both answers are pending; no policy is
  approved by presenting a recommendation. A read-only explorer is checking
  current dashboard and audit/reference behavior for later concrete examples.
- 2026-10-05: Added independent Q3 to the same opening round after the explorer
  confirmed the existing shared Parents/Children renderer and the source's
  current endpoint restriction. Q3 asks whether ordinary-to-category hierarchy
  should navigate on both sides, only from ordinary notes, or remain audit-only.
  Recommendation: navigate on both sides, preserve multiple parents and keep
  category membership separate. Dashboard placement depends on that answer
  and belongs to a later round. Q1-Q3 remain unanswered.
- 2026-10-05: Read-only code check for the grilling baseline: category bodies
  currently put Members/Gallery before authored content/Resources and then the
  shared Parents/Children/Related sections
  ([renderer](../../../src/brz2obsidian/obsidian/rendering.py:135),
  [navigation](../../../src/brz2obsidian/obsidian/relationships.py:11)).
  `migration-record.json.original_evidence` retains all recognized root record
  collections, including history, independently of note creation
  ([reader](../../../src/brz2obsidian/sources/thebrain/reader.py:242),
  [record renderer](../../../src/brz2obsidian/obsidian/rendering.py:391));
  this is preserved JSON values rather than byte-identical root files. Present
  original-note assets are also copied independently of note creation
  ([resource planning](../../../src/brz2obsidian/core/resources.py:58)).
  Authored links currently reserve wikilinks for eligible uncreated targets
  ([document renderer](../../../src/brz2obsidian/obsidian/documents.py:16)).
  Forgotten exclusion is not implemented, so Q2 concerns explicit filtering
  across these outputs, rather than merely suppressing generated note files.
  These are current behavior facts, not approved future choices.
- 2026-10-05: User answers to the opening round:
  - Q1: No success/recovery mode chosen. The user needs the agent to establish
    what the missing material is and whether it is actually unavailable in the
    Brain. Conditional preference: skip content if it is genuinely gone. The
    60 thoughts themselves are present; absent payloads are their Notes.md
    files, with one present image per owner. Earlier representative retrieval
    proves blank display alone is insufficient. A native-observation subagent
    is checking all 60 non-forgotten remaining files before further policy
    questions on this branch.
  - Q2: Rejected retention of forgotten details even as exclusion IDs/counts:
    "forgotten thoughts for me are as if they were deleted. I don't want
    anything about them anymore". Generated destination content and migration
    records must omit forgotten items and their owned content and relationships;
    no per-item forgotten audit/exclusion list. The original source remains
    intact. Authored references and the scope of the default still require
    concrete boundary questions.
  - Q3: Accepted Parents/Children navigation on both sides of ordinary/category
    hierarchy. Preserve multiple parents and keep classification membership
    independent. Section placement remains an open presentation choice.
  Captured the domain term Excluded item in the root glossary; source Forgotten
  thought retains its existing live-source meaning. No source deletion is part
  of this rule. The overall policy ticket remains claimed, not resolved.
- 2026-10-05: Next independent frontier opened while source recovery is being
  checked. Q4 asks whether category Parents/Children sections go directly below
  the title before Members/Gallery (recommended), or remain after source
  content/Resources. Q5 asks whether forgotten exclusion is the normal default
  for future archives (recommended), or specific to this migration. Both are
  pending. The first additional native attempt recovered an actual 67-byte
  image-only note; this is evidence for that owner, not yet for the whole cohort.
- 2026-10-05: User accepted Q4: category Parents/Children go below the title,
  before Members/Gallery. User accepted Q5: forgotten exclusion is the default
  for future conversions of all archives. Q1 and reference/history boundary
  questions await the factual checks. No complete or limited conversion mode
  has been chosen, and the ticket is not resolved.
- 2026-10-05: Q6 response strengthens the already settled exclusion boundary:
  "I don't want any references or any visual artifacts or anything that refers
  to forgotten thoughts. You should pretend that a forgotten thought does not
  exist at all." No further retention-choice questions are needed on this
  branch. Excluded items must contribute no generated note, owned payload,
  copied original, decorative/inherited artifact, category/tag membership,
  relationship, authored target/link label, stub, individual audit identity,
  raw record or affiliated history to the destination. Included authored
  references to them are removed; a generated exact-source copy that would
  reintroduce such a reference is omitted, with the original archive remaining
  separate. History/evidence that cannot be safely scoped must not bypass this
  rule. This changes the related v2 retention boundary explicitly; it does not
  delete the source or require keyword-based deletion of unrelated prose.
- 2026-10-05: Available-content/history fact check, retained privately under
  `tmp/ml-wayfinding/policy-facts/`: production tracing parsed all 359 original
  present note payloads, finding one thought reference to an included target
  and 436 image references. No forgotten target occurs in available authored
  notes; absent/recovered content was outside that check. In addition to
  direct ownership records and incident links, forgotten identifiers occur
  in 109 edit logs and associate with 14 tombstoned dependent objects. The
  meta file-state map also holds eight forgotten-owned attachment keys.
  Raw history string values may contain prose that identity correlation alone
  cannot attribute. These collections require deliberate scoped handling,
  not retention of the complete original evidence blob. Original archive hash
  remained unchanged. Native recovery progress: 15/60 retrieved, all 67-byte
  image-only notes; full-cohort claim awaits completion and re-export checks.
- 2026-10-05: Additional source control at 20/60 recovered: an included
  67-byte thought with a similar name to the forgotten 69-byte thought is a
  distinct identity and was recovered correctly. Exclusion follows source
  identity/ownership/reference association, not title similarity or matching
  visual bytes on a separately included item. This avoids deleting included
  content merely because an excluded thought has similar words or an image.
- 2026-10-05: Full source fact check completed: all 60 remaining non-forgotten
  notes were retrieved as actual 67-byte image-only Markdown files, with BOM
  and CRLF. Every image already exists in the original archive; there are no
  other authored references in these notes. A fresh full-Brain desktop backup
  contains all 73 recovered cohort files, preserves all 1,024 original payloads
  byte for byte and matches the captured local bytes/hashes for all 73 additions.
  Identity sets and content/relationship fields are preserved; only sync
  bookkeeping, 74 activation times and the attachment file-state map change.
  The single remaining absent cohort member is deliberately excluded forgotten
  content. See [Complete recovery of the active missing-note cohort](../research/native-source-recovery.md).
  Q1's conditional genuinely-gone case is not established: the active content
  was retrievable. Proposed next decision: use the verified fresh input with
  complete included-content acceptance and retain strict handling of unverified
  missing selected bytes, preserving previously approved v2 exceptions. The
  input/success decision and final shared-understanding confirmation are pending.
- 2026-10-05: Final grilling round Q7 proposes using the verified fresh full-Brain
  backup as the migration input while retaining the original as comparison
  evidence. Success requires preserving the included current-source content;
  unverified missing selected note/resource bytes and unknown or contradictory
  states retain strict refusal outside previously accepted v2 exceptions.
  No new limited mode, synthetic recovery or general state-3 allowance is
  proposed. Forgotten exclusion is the default for all archives and must remove
  their generated content, resources, visual/reference artifacts and hidden
  metadata/history, without an individual exclusion list or retained IDs/counts.
  Unscopable evidence must be omitted rather than bypass the exclusion rule.
  Ordinary/category Parents/Children navigation appears on both sides; category
  sections go below the title before Members/Gallery, with multiple parents
  preserved and classification independent. User confirmation is pending;
  presenting this combined proposal does not accept it or resolve the ticket.
- 2026-10-05: Before answering Q7, the user asked what the recovered notes
  contain and whether that content is important. The literal Markdown consists
  of image embeds, but that alone does not establish the images' information
  value. A read-only follow-up is inspecting all recovered ordinary-note images
  so the user can judge concrete examples. Q7 remains unanswered; no input or
  success policy is accepted from this factual question.
- 2026-10-05: The user additionally asked whether the referenced images were
  already in the original BRZ and what recovery did. Clarified that every
  referenced image was already an original payload: the absent objects were
  tiny Notes.md files containing their note-body embed instructions. Supported
  native attachment retrieval made those literal files available locally, and
  a fresh desktop backup included them. No pixels or Markdown were synthesized,
  and no source note was edited. The export-omission mechanism remains unknown;
  current-source recovery and historical original-byte equality are distinct.
- 2026-10-05: The user requested a clearer original-versus-fresh comparison.
  Clarified that no thoughts were created: the fresh backup adds 63 ordinary
  Notes.md embed files, two whitespace type-note files and eight type icons.
  All ordinary-note image pixels already exist in the original. The difference
  is the presence of the source note-body instructions alongside those pixels,
  plus the separately absent type icons; all original payload bytes are unchanged.
- 2026-10-05: Complete visual inspection covers all 63 recovered ordinary-note
  images: 62 substantial illustrated technique/reference cards and one workflow
  chart. The later 60 are full cards, including 53 productivity and seven
  negotiation techniques. None is merely a logo, thought icon, book cover or
  decorative thumbnail. All images have source Type 12 and IsIcon=false;
  the separate type icons have another source role. The user confirms the card
  images are important content.
- 2026-10-05: User requires a solution for original/future BRZ archives that
  automatically preserves and displays available note images when Notes.md is
  missing. Repeated clicking/retrieval in TheBrain is explicitly infeasible and
  rejected as a conversion prerequisite. Q7's proposed fresh-input/strict-refusal
  route is withdrawn, not accepted. The verified fresh backup remains only a
  reference control. Archive/code fact investigation is checking the automatic
  association evidence, conservative fallback boundaries and counterexamples;
  default forgotten exclusion and category navigation decisions remain settled.
- 2026-10-05: User clarified the success criterion: "I do actually see those
  images in my Obsidian vault" and "not lose any other Markdown content".
  Preserve included archive-present Markdown through its existing source-content
  path; any image fallback applies only to absent note payloads, without
  overwriting physically present bodies, including blank/prose/multiple-image
  controls. Unknown content of an already absent source body must not be
  silently claimed recovered. The exact source-gap acceptance/reporting boundary
  awaits the archive-only fact check and the next user decision round.
- 2026-10-05: Archive-only investigation confirms all 63 missing ordinary-note
  owners have one valid present owned embedded image. Metadata and history
  contain no missing body, explicit inline order or captions. Present controls
  include two-image Markdown table layouts using the same image Position 0;
  single-image controls support the observed pattern but do not prove generic
  absent-body contents. See [Archive-only presentation of images beside absent
  notes](../research/automatic-image-fallback.md) for guarantees, existing seams
  and independent acceptance requirements. Proposed behavior is generated image
  display only for absent notes, preservation of all present bodies, source-gap
  warnings and no fabricated original. Separate remaining choice: absent type
  notes/icons can use disclosed omission/neutral appearance rather than block
  this archive. Neither proposal is implemented or approved yet.
- 2026-10-05: Opened the revised frontier after the archive-only findings.
  Q8 recommends automatic visible image sections for absent notes, preservation
  of every present included body, brief note/report source-gap notices and no
  fabricated originals. Q9 independently recommends proceeding with category
  dashboards/navigation despite absent type notes/icons, reporting unknown note
  bodies and using neutral appearance rather than missing/recreated icon pixels.
  These replace the withdrawn Q7 route. Both user answers are pending. The
  inspection/report and subsequent acceptance must demonstrate preservation of
  all 359 original-present note payloads through the permitted adaptation path,
  plus visible original card images, without a live TheBrain dependency.
- 2026-10-05: User answered both Q8 and Q9 with "Okay" and the requirement
  for enough logging/information to identify which thoughts have source problems
  and investigate or repair them in TheBrain. Accepted the automatic fallback
  and disclosed type-note/icon outcomes with this added diagnostic obligation.
  Conversion remains archive-only; optional source investigation is not a
  prerequisite. A producer bug is a user hypothesis, not an established cause.
  Default forgotten exclusion and category hierarchy/placement remain approved.
  Recorded the agreed policy in the Answer; the next ticket reviews presentation.
- 2026-10-05: During native source verification, the user specified: "I don't want
  to convert forgotten thoughts." This is an accepted scope constraint; the
  remaining policy questions are still open.
- 2026-10-05: Created during charting. The earlier suggested Parents/Children
  adaptation is a candidate, not a user-approved design or type-inheritance rule.

## Answer

### Successful conversion and input

Use the supplied, unaltered `brz/Management & Leadership 2026-10-05.brz`
(SHA-256 `2b24c1d21b4090f3b0ed3ec0227f269b8c7a4e5b6832ada0e244a1dcfc941ced`).
Routine conversion must work from the archive alone, without live TheBrain,
manual attachment requests or a newly prepared backup. The retrieved note bytes
and fresh backup are independent investigation/reference evidence only.

The user confirms the full card images are important. Success means that the
relevant available images are actually visible in their corresponding vault
notes and included Markdown supplied by the archive is preserved through the
existing permitted reference adaptations. Original-present prose, blank content,
captions, tables, image ordering and line endings must not be replaced by a
fallback. Intentional forgotten-thought exclusion remains the separate settled
scope rule. For this original input, independent acceptance must account for
all 359 present thought-note payloads and all 63 affected original card images.

Conversion may finish with explicit source warnings for the accepted absences.
That outcome must not imply exact recovery of unavailable authored bytes or
certify completeness of the live Brain. Unknown source content cannot be silently
classified as empty, inferred from length or credited as preserved content.

### Automatic available-image presentation

When an included ordinary thought's recognized note declaration lacks physical
bytes and valid owned note images are present, show those images automatically
in a generated section of the thought's vault note. Use source attachment
ownership and the reviewed embedded-image role; no title matching, OCR,
Pip-Decks-specific recognition or native retrieval is required.

For the observed source shape this means absent Type-1/NoteType-4 Notes.md,
SourceType 2 and raw state 3, with present state-1 Type-12 owned image bytes.
The source profile must review this precise absence separately; it is not
blanket state-3 acceptance or an authoritative enum definition. Preserve the
normal owner, scalar, path, declaration and payload-integrity checks.

Present Markdown always takes precedence, including a physically present blank
body. Render it through the existing exact-source path, adapting only approved
references. For absent bodies, generated image order must be deterministic and
must not be represented as recovered authored order, captions or layout. All
valid available owned note images in the supported case must be visible; an
image merely copied into Attachments or listed as a Resources link is insufficient.

Give the generated section a brief source-gap notice and report the absent
original. Keep absent authored content separate from generated presentation:
do not fabricate a Document, original-note backup, original byte hash or authored
reference count. Available image bytes retain their real hashes and normal
copy/preservation accounting.

### Type-note and icon gaps

Permit the observed missing type-note/icon shapes to continue with source
warnings. Produce category dashboards, membership, available content and
navigation. An absent type-note body remains unknown; the two recovered
whitespace controls do not justify an empty-note rule based on declared length.

Use neutral appearance when a declared type icon's bytes are unavailable,
including members that would inherit it. Preserve other available appearance
metadata under existing rules. Do not create broken icon links, fabricate pixels
or promote full card images into substitute icons. Report the missing provider
and its affected included members. This is separate from automatic card display.

Unknown states, contradictory physical/state declarations, ambiguous note
declarations, wrong-owner images, unavailable required image bytes and other
unsupported missing-resource shapes retain refusal. An ordinary absent note
without the available-image basis does not silently pass as an empty note under
this rule. The accepted type-note outcome and prior reviewed TXT/icon-length
rules have their own evidence predicates.

### Actionable source diagnostics

Inspection and completed conversion must provide enough information to locate
each affected included thought and its unavailable attachment. Provide a readable
source repair checklist in the migration report and corresponding structured
entries in the migration record, with consistent warnings/notices. At minimum:

- Input archive identity/fingerprint and source collection identity.
- Thought title, original source thought ID and corresponding vault-note link.
- Missing attachment ID/role, expected owned archive path, raw file state,
  declared length and actual physical absence.
- What the converter did: generated available-image presentation, unavailable
  type-note notice or neutral appearance. Identify the available image assets
  used, without claiming to recover unseen Markdown.
- For a missing inherited icon, its type provider and affected included members,
  distinguishing the provider's missing file from member appearance effects.
- A source locator where verified and practical guidance to inspect the affected
  note/attachment in TheBrain, optionally retrieve/re-export and compare the
  source gaps. Source IDs remain available if a clickable locator is unavailable.

Source investigation/repair is optional and human-directed. Do not perform
source mutation, integrity repair or remote retrieval as part of conversion.
Describe observed absence and fallback rather than diagnose a confirmed vendor
bug. The precise export-omission cause and numeric state meaning remain unknown.

### Forgotten exclusion and category navigation

Exclude forgotten thoughts by default for all archives. Treat them as nonexistent
in generated destination output: no note, owned payload, exact-source copy,
decorative/inherited artifact, membership, relationship, authored target/link
label, stub, individual audit ID, forgotten count/list, raw record or affiliated
history. Remove included authored references to forgotten targets. An exact
source copy that would reintroduce those references must stay outside the vault;
the original BRZ remains separate. Omit unscopable evidence/history that would
bypass the exclusion. All repair diagnostics cover included subjects only.

Exclusion follows identity, ownership and reference association, not matching
titles or visual bytes on an independently included item. It does not delete
source objects. The root glossary's Forgotten thought and Excluded item preserve
that distinction; no additional architecture decision is required here.

Show Parents/Children navigation on both ordinary notes and linked category
dashboards. Preserve all direct ordinary parents. On category dashboards, put
Parents/Children directly below the title, before Members/Gallery. Keep category
membership separate from ordinary hierarchy; no type inheritance is introduced.

### Positive and negative examples for specification

- Missing ordinary Notes.md plus a valid owned card image: create the eligible
  note, visibly embed the original image, disclose absent text and record an
  actionable included-thought diagnostic; no live source access or invented
  authored bytes. Multiple available images use disclosed generated ordering.
- Present prose/table/multiple-image Markdown plus images: preserve authored
  content/layout and permitted reference changes; do not invoke absence fallback.
- Missing type note/icon: category/member navigation remains usable, appearance
  is neutral where necessary and the checklist identifies the provider/affected
  included subjects. Do not claim empty notes or repaired pixels.
- A category with multiple ordinary parents: ordinary Children and category
  Parents contain all direct links; membership remains independent.
- Forgotten owner or reference: no generated artifact, hidden record or repair
  checklist entry reintroduces it. Similar-looking included content survives.
- Unknown/contradictory shape or required unavailable image: refuse under the
  profile boundary rather than silently fabricate an apparently complete note.

See [Archive-only presentation of images beside absent notes](../research/automatic-image-fallback.md)
and [Complete recovery of the active missing-note cohort](../research/native-source-recovery.md)
for source facts, controls, preservation comparison and implementation seams.
No converter implementation or full-original conversion was performed here.
The next step is [Review the agreed behavior in a representative vault
prototype](05-vault-prototype.md), then the map's specification and ticket stages.
