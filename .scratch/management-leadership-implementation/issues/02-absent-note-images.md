# 02: Display owned images when an ordinary thought note is absent

Status: ready-for-agent
Approved: 2026-10-06
Specification: [Accepted conversion specification](../spec.md)

**What to build:** Convert a reviewed absent ordinary thought-note declaration using every valid owned note image already in the archive. The owning Obsidian note shows layout A and actionable diagnostics, while all physically present Markdown keeps its existing preservation path.

**Blocked by:** [01 — Exclude forgotten thoughts throughout inspection and conversion](01-forgotten-exclusion.md).

## Acceptance criteria

- [ ] Admit only the unique ordinary included-owner Type-1/NoteType-4 canonical Notes.md declaration, SourceType 2, raw state 3, no physical member and a valid owned note-image basis. Preserve scalar/flag/path/length/identity/ownership checks; nonnegative declared length does not establish empty content.
- [ ] A valid basis uses same-owner Type-12/NoteType-0, SourceType 2, IsIcon=false images with present state-1 bytes, unique safe paths, correct CRC/declared length/hash and usable decodable supported content with nonzero dimensions. Names, extension, Position, similar pixels and lengths cannot prove ownership or recovered layout. Validation does not impose unrelated new image processing on present-note cases.
- [ ] Show every supported available owned image with an actual local embed in the created owner note, copying original bytes without recompression. Use stable canonical asset-identity ordering and simple separation. A Resources link or files copied alone is insufficient. Apply existing redundant-resource rules only where valid.
- [ ] Place the brief layout-A notice before the images, without an extra Available note images heading. Say note text is absent and unknown prose/captions/layout were not recovered; link to detailed Migration report evidence. Do not reconstruct an authored table/order.
- [ ] Present recognized Markdown always wins, including blank/zero/BOM/prose/caption/table/image-only/multiple-image content and canonical NoteType-0 cases. Compare independently authored expected bodies including Unicode, code literals, nested reference syntax and mixed CR/LF/CRLF. Preserve exact safe originals and all supplied syntax/newlines except accepted destination adaptation/scope removals. No appearance/content/length heuristic activates fallback or fixes source syntax.
- [ ] Populate the established version-3 contract with source-neutral source-gap/generated-presentation facts that consistently join the included owner, reviewed finding, absent asset and actual images through inspection, analysis, planning, rendering and record. Deliver the common verified absence-policy/diagnostic/accounting capability reused by the subsequent type-gap slice. Reject inconsistent joins. There is no fabricated Document, absent-byte hash, original payload/backup or authored-reference credit. Plan/count generated embeds separately, bound to input fingerprint, scoped digest and policy.
- [ ] Inspect exposes measured included-source facts and planned obligations without published-output counts or receipts. Completed conversion has matching structured entries, note notices and an optional repair checklist: fingerprint/collection, included thought title/ID/resolving vault target, attachment ID/role/expected owned path/raw state/declared length/physical absence/outcome, and actual ordered image IDs/paths. Use only verified source locators; no guessed launch URI, localhost address or confirmed-producer-bug claim. Conversion needs no source UI/network retrieval.
- [ ] Independently failing near-miss fixtures cover every absence/basis predicate: role, NoteType, SourceType, flags, canonical path, nonnegative length, identity, ownership, unique candidate/path, CRC, declared length/hash and usable image content/dimensions. Also refuse unknown state, state-3/present bytes, state-1/absent bytes, ambiguous notes/images, unsupported absence roles, wrong-owner/unavailable/invalid image basis and ordinary absence without valid images. Keep prior narrow TXT/PDF/icon exceptions. Refused conversions preserve caller files and do not leak excluded information.
- [ ] End-to-end synthetic one-image and multiple-image cases prove visible embeds, exact asset hashes, source immutability, truthful accounting/reporting, notice order and preserved present-body controls through public workflow and thin CLI. The separate source-free checker accepts valid local embeds and detects deleted image targets without treating its result as preservation proof.
- [ ] Update public coverage/diagnostic/schema guidance for the working slice, keep applicable public regression checks green, and record bounded proof. A synthetic success does not satisfy the complete original-input audit.

## Verification boundary

Public inspect/convert with independently authored synthetic ZIP/expected bytes, thin CLI and separate read-only checker. Focused existing contract seams may test invalid joins. Do not manufacture a public testing endpoint.

## Specification coverage

User Stories 1–20, 24, 40–50, 58–62, 68–70; Implementation Decisions 8–12, 17–23, 25; Testing Decisions 1–6, 9–10, 17, 20.

## Comments

- 2026-10-06 (/root): Published after the user approved all nine tickets and their
  dependencies, then explicitly invoked implement-spec for complete implementation.
