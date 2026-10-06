# 02: Display owned images when an ordinary thought note is absent

Status: claimed
Assignee: /root/txt_oracle_implementer
Approved: 2026-10-06
Specification: [Accepted conversion specification](../spec.md)

**What to build:** Convert a reviewed absent ordinary thought-note declaration using every valid owned note image already in the archive. The owning Obsidian note shows layout A and actionable diagnostics, while all physically present Markdown keeps its existing preservation path.

**Blocked by:** [01 — Exclude forgotten thoughts throughout inspection and conversion](01-forgotten-exclusion.md).

## Acceptance criteria

- [x] Admit only the unique ordinary included-owner Type-1/NoteType-4 canonical Notes.md declaration, SourceType 2, raw state 3, no physical member and a valid owned note-image basis. Preserve scalar/flag/path/length/identity/ownership checks; nonnegative declared length does not establish empty content.
- [x] A valid basis uses same-owner Type-12/NoteType-0, SourceType 2, IsIcon=false images with present state-1 bytes, unique safe paths, correct CRC/declared length/hash and usable decodable supported content with nonzero dimensions. Names, extension, Position, similar pixels and lengths cannot prove ownership or recovered layout. Validation does not impose unrelated new image processing on present-note cases.
- [x] Show every supported available owned image with an actual local embed in the created owner note, copying original bytes without recompression. Use stable canonical asset-identity ordering and simple separation. A Resources link or files copied alone is insufficient. Apply existing redundant-resource rules only where valid.
- [x] Place the brief layout-A notice before the images, without an extra Available note images heading. Say note text is absent and unknown prose/captions/layout were not recovered; link to detailed Migration report evidence. Do not reconstruct an authored table/order.
- [x] Present recognized Markdown always wins, including blank/zero/BOM/prose/caption/table/image-only/multiple-image content and canonical NoteType-0 cases. Compare independently authored expected bodies including Unicode, code literals, nested reference syntax and mixed CR/LF/CRLF. Preserve exact safe originals and all supplied syntax/newlines except accepted destination adaptation/scope removals. No appearance/content/length heuristic activates fallback or fixes source syntax.
- [x] Populate the established version-3 contract with source-neutral source-gap/generated-presentation facts that consistently join the included owner, reviewed finding, absent asset and actual images through inspection, analysis, planning, rendering and record. Deliver the common verified absence-policy/diagnostic/accounting capability reused by the subsequent type-gap slice. Reject inconsistent joins. There is no fabricated Document, absent-byte hash, original payload/backup or authored-reference credit. Plan/count generated embeds separately, bound to input fingerprint, scoped digest and policy.
- [ ] Inspect exposes measured included-source facts and planned obligations without published-output counts or receipts. Completed conversion has matching structured entries, note notices and an optional repair checklist: fingerprint/collection, included thought title/ID/resolving vault target, attachment ID/role/expected owned path/raw state/declared length/physical absence/outcome, and actual ordered image IDs/paths. Use only verified source locators; no guessed launch URI, localhost address or confirmed-producer-bug claim. Conversion needs no source UI/network retrieval.
- [x] Independently failing near-miss fixtures cover every absence/basis predicate: role, NoteType, SourceType, flags, canonical path, nonnegative length, identity, ownership, unique candidate/path, CRC, declared length/hash and usable image content/dimensions. Also refuse unknown state, state-3/present bytes, state-1/absent bytes, ambiguous notes/images, unsupported absence roles, wrong-owner/unavailable/invalid image basis and ordinary absence without valid images. Keep prior narrow TXT/PDF/icon exceptions. Refused conversions preserve caller files and do not leak excluded information.
- [x] End-to-end synthetic one-image and multiple-image cases prove visible embeds, exact asset hashes, source immutability, truthful accounting/reporting, notice order and preserved present-body controls through public workflow and thin CLI. The separate source-free checker accepts valid local embeds and detects deleted image targets without treating its result as preservation proof.
- [x] Update public coverage/diagnostic/schema guidance for the working slice, keep applicable public regression checks green, and record bounded proof. A synthetic success does not satisfy the complete original-input audit.

## Verification boundary

Public inspect/convert with independently authored synthetic ZIP/expected bytes, thin CLI and separate read-only checker. Focused existing contract seams may test invalid joins. Do not manufacture a public testing endpoint.

## Specification coverage

User Stories 1–20, 24, 40–50, 58–62, 68–70; Implementation Decisions 8–12, 17–23, 25; Testing Decisions 1–6, 9–10, 17, 20.

## Comments

- 2026-10-06 (/root): Reopened the shared diagnostic rendering slice after the
  fresh original matrix at `a622058` stopped on original D's checklist alias.
  Nine A/B/C variants passed. D was published, but its complete source-required
  audit failed; no D repeat/reorder or complete matrix is accepted. Independent
  raw-source diagnosis confirms the target, identities, role and outcome match.
  The manually built checklist alias retains extra whitespace after reserved
  title characters are replaced, unlike the established note-link formatter.
  Repair owner and affected-member diagnostic links through that existing
  renderer boundary with public synthetic TDD; retain the independent oracle
  and all source/body preservation rules. Earlier bounded image/absence proof
  remains retained. All four originals and 562 retained-vault files pass the
  before/after/final preservation guard. Ticket 07 stays claimed and unchecked;
  a fresh complete matrix and native/user gates remain required.

- 2026-10-06 (/root/integration_merger): Integrated exact verified head
  `a6f62b9e37bb193d231cf688e630722fa4f6d06b` from `codex/ml-v3-02` by
  `git merge --ff-only a6f62b9e37bb193d231cf688e630722fa4f6d06b` from clean
  root `e50a638d16b0137b111bffe1fc7f8f9f0875c0c9`.
  Independent `tmp/ml-implementation/02/verification.md` records bounded PASS
  for static review, **21 handwritten raw-ZIP control groups** and **213 focused
  tests in 15.31s** at the exact clean head. Independent controls prove ordered
  original-byte image embeds, notice A/diagnostics, no fabricated original or
  authored-reference credit, present-body precedence, private exclusion,
  complete image-frame decoding, near-miss refusals, repeat/reorder behavior,
  source/caller inventories and read-only checker behavior.

  Merged root command:
  `.venv/Scripts/python.exe -m pytest -q tests/application/test_absent_note_images_workflow.py tests/application/test_categories_workflow.py tests/application/test_category_hierarchy_workflow.py tests/application/test_integrated_v2_workflow.py tests/application/test_alternate_source.py tests/application/test_alternate_v2_source.py --basetemp=tmp/ml-implementation/merger/pytest-02-a6f62b9 -o cache_dir=tmp/ml-implementation/merger/pytest-cache-02-a6f62b9`
  passed **197 tests in 22.54s**, exit 0. Runtime import resolves to root src.
  `git diff --check e50a638d16b0137b111bffe1fc7f8f9f0875c0c9..a6f62b9e37bb193d231cf688e630722fa4f6d06b`
  passed, exit 0. Worker complete **930-test** suite and Ruff/pip/diff results
  remain attributed worker evidence; identical fast-forwarded code was not
  redundantly tested in full. Copied evidence is retained ignored under
  `tmp/ml-implementation/02/worker-evidence-a6f62b9/` before future archival.

  Ticket 03 is now eligible but its claim remains coordinator-owned. This
  completes only the bounded ordinary absent-note image slice; type gaps,
  complete independent four-original preservation, native observations, actual
  user verdict, final review and release remain pending. No PR was created.

- 2026-10-06 (/root): Claimed after ticket 01's independently verified integration
  at `b5d6238`. Implement in its own managed worktree/branch with public-seam TDD;
  coordinate shared rendering/planning changes with category hierarchy.

- 2026-10-06 (/root): Published after the user approved all nine tickets and their
  dependencies, then explicitly invoked implement-spec for complete implementation.


- 2026-10-06 (/root/image_fallback_implementer): Implemented the reviewed ordinary
  note fallback on `codex/ml-v3-02`, initially based on `a29e8a0`; merged verified
  integration tip `e50a638` through `e2af2a0` before final checks. Adapter admission
  remains limited to this ticket. The shared source-neutral gap validation,
  target diagnostics and report helper expose the established version-3 shapes
  for the subsequent type-gap ticket without adding another contract family.

  The first public workflow tracer failed on state 3 before implementation.
  Subsequent red/green tracers covered forged generated destinations, aligned
  noncanonical owner targets, gap counts, text CLI generated-count wording and
  existing TXT owner diagnostics. Canonical joins validate owner/absent asset/
  reviewed finding/evidence and the complete canonical owned-image set. Generic
  core keeps original evidence JSON opaque; valid-format fabricated measurements
  are checked against actual streams at the injected workflow/publisher seam.

  Bounded public fixtures cover a real one-pixel PNG and two-pixel WebP, one and
  multiple images, reversed records/ZIP order, zero/positive absent declared
  lengths, distinct owners with identical title/pixels, and excluded absent
  subjects. Near misses include every declaration/basis role, scalar, flag,
  state, ownership and safe-path boundary; absent/mixed invalid/duplicate images,
  competing blank/BOM notes, wrong owner roles, actual length/ZIP CRC, invalid
  pixels and dimensions. A CRC-valid PNG with structurally valid chunks but bad
  compressed pixels proves the full pixel-decoding gate. Existing exact-body,
  mixed-newline, nested-span, TXT/PDF/icon, scope, alternate-source, publication,
  checker and preservation-oracle regressions remain green.

  Pillow 12.3.0 is the runtime decoder, added to the dependency manifests and
  already available in the root project virtual environment. Official primary
  guidance: [Image.open/verify/load and frame APIs](https://pillow.readthedocs.io/en/stable/reference/Image.html)
  and [format support](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html).
  Open alone is lazy; fallback checks verify the stream, reopen it, then load
  every frame with positive dimensions. Decoding is confined to accepted absent
  note candidates. Archived images are streamed/copied without recompression;
  present-note synthetic image controls receive no blanket new decoding.

  Final commands used the exact interpreter
  `C:/Users/stefa/projects/brz2obsidian/.venv/Scripts/python.exe` with
  `PYTHONPATH=C:/Users/stefa/.codex/worktrees/ml-v3-images/brz2obsidian/src` from
  the worker checkout; the editable install was never redirected:

  - `-m pytest -q --basetemp=tmp/pytest-02-merged --tb=short`: **930 passed**,
    including the combined category/fallback behavior and source-free checker.
  - `-m ruff check src tests`: passed.
  - `-m ruff format --check src tests`: passed; 109 files formatted.
  - `-m pip check`: no broken requirements.
  - `git diff --check`: passed.

  An earlier broad run overlapped a targeted pytest run using the default
  basetemp; it was discarded and final runs use distinct directories. Another
  broad run exposed legacy TXT report fingerprint instability under reorder.
  Those old reports now point to migration-record provenance while new gaps
  retain explicit report provenance; the 156 relevant repeat/reorder regressions
  and final full suite pass. The resolving report links distinguish actual owner
  notes from prior TXT assigned uncreated targets without materializing them.

  Temporary local output remains under `tmp/ml-images/`; durable behavior and
  verification conclusions are recorded here. This ticket proves the bounded
  synthetic/runtime slice only. The four-original independent audit, native
  Obsidian review and actual user acceptance remain later delivery gates;
  independent ticket verification and the integration merger gate follow this
  implementation report. No original/private export or retained user vault was
  changed, and no PR was created.
