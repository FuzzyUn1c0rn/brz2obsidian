# 03: Keep category dashboards usable through missing type notes and icons

Status: resolved
Assignee: /root/type_gap_implementer
Approved: 2026-10-06
Specification: [Accepted conversion specification](../spec.md)

**What to build:** Convert the reviewed missing type-note/icon declarations into usable category dashboards and member notes. Unknown category text is disclosed; missing pixels yield neutral appearance and practical provider diagnostics while important card bodies remain visible.

**Blocked by:** [02 — Display owned images when an ordinary thought note is absent](02-absent-note-images.md). This slice uses the source-gap policy, verified diagnostic links and scoped absence/accounting path delivered by that ticket.

## Acceptance criteria

- [x] Permit only reviewed type-owned Type-1/NoteType-4 Notes.md and Type-5/NoteType-0 icon absence with SourceType 2, raw state 3 and no member, retaining scalar/flag/path/owner/role checks. Icon flags agree. Neither recovered whitespace controls nor declared length establish absent type text as empty.
- [x] Create included category definitions/assigned members under cumulative materialization rules despite these gaps. Type-note absence is unknown content with a notice/report entry, not an image reconstruction or fabricated Document/original/hash.
- [x] Missing type icons give dashboards and inheriting included members neutral valid icon properties, without a broken image target, fake effective icon or full-card substitute. Keep membership and appearance_category links so later dashboard-icon edits use native Bases. A valid explicit member icon wins; other available inheritance/static snapshots remain intact.
- [x] Structured inspect/conversion facts, category/member notices and repair checklist distinguish each missing provider from affected included members. Retain exact declaration/state/length/path, source identity and real resolving output targets. Do not multiply missing declarations per member or invent source locators/vendor conclusions.
- [x] Preserve present icon actual hashes/lengths and the existing narrow metadata-length discrepancy rule; preserve prior TXT/PDF findings and no-note behavior. Prior TXT-gap owners are not materialized just to supply diagnostic links; distinguish assigned uncreated targets from real notes honestly.
- [x] Independently failing near-miss fixtures cover every type-absence predicate: role, NoteType, SourceType, flags, canonical path, nonnegative declared length, identity, ownership, candidate uniqueness, raw state and physical presence. Unsupported ordinary-icon/tag/system absence, unknown/contradictory state and mismatches refuse through public workflow without partial publication or excluded identity leakage.
- [x] Synthetic absent type body alone, icon alone and both together demonstrate usable category/member output, intact note cards, neutral providers, valid explicit overrides, unaffected icons and accurate distinct diagnostics. Included/excluded provider and reference cases preserve the default scope.
- [x] Preserve native v2 membership/discovery, Icon-before-Note columns, provider/default/opt-out/template/date semantics, category introductory body-icon suppression and no generated colour fields. The source-free checker stays read-only, accepts neutral valid properties and catches genuine missing local image files.
- [x] Update guidance and public contract expectations for these supported gaps. Existing applicable regression/oracle tests remain green; record bounded behavior proof rather than final archive acceptance.

## Verification boundary

Actual synthetic ZIPs through public inspect/convert and thin commands; observed notes, property/Base support, diagnostics and image bytes. The source-free checker is independent and supplementary.

## Specification coverage

User Stories 19–26, 31, 40–50, 58–62, 69–70; Implementation Decisions 13–14, 16–23, 25; Testing Decisions 1–4, 8–10, 16–17, 20.

## Comments

- 2026-10-06 (/root/type_gap_implementer): Implemented the bounded type-gap slice
  on `codex/ml-v3-03`, based on verified integration
  `296b3af67a2dc9590f0a97080200723b7adf50b8`. Runtime, public fixtures and guidance
  are committed at `6b82b9c866719895c4fa85eed4279f8ff0a2f1af`.
  `git merge codex/management-leadership-v3` after that commit reported already
  up to date. Only this ticket's evidence is changed; the root owns the index,
  specification and subsequent acceptance claims.

  Public TDD tracers failed before the corresponding implementation and then
  passed: absent type text without an image basis; a neutral missing icon provider
  with genuinely affected included members; combined gaps preserving explicit
  overrides/card originals without absent-icon Resources clutter; the generic
  missing-icon declaration join; canonical diagnostic ordering under reversed
  records/ZIP order; and renderer rejection of forged missing-icon and affected
  member destinations. The shared `core/source_gaps.py` and `obsidian/gaps.py`
  capability is reused. BRZ numeric admission stays in the adapter; existing
  version-3 closed contracts carry provider/member diagnostics without another
  model family.

  The 99 new public controls use actual synthetic ZIPs through inspect/convert,
  thin JSON commands and existing analyze/render seams for forged joins. They
  cover type-note/icon absence separately and together, zero/positive declared
  lengths, present empty/whitespace/BOM/prose category bodies, category-owned
  cards without reconstruction, member-authored cards and exact originals,
  explicit overrides, unaffected inherited icons, and present-icon length
  discrepancies with actual bytes retained. Included/excluded provider/member
  cases, independent same-title included controls and reversed records prove
  scoped diagnostics without excluded identity leakage. Each absent declaration
  remains one gap with no fake Document, original, actual hash/length or target.
  Native membership/appearance_category links remain available with empty valid
  icon properties; genuine missing local images still fail the read-only checker.

  Independent one-conjunct refusal controls exercise role, NoteType, SourceType,
  icon/special flags, unsafe/noncanonical paths, nonnegative integer length,
  identity/ownership, competing present/absent declarations, missing/unknown
  states and state/payload contradictions. Ordinary-icon and tag/system absence
  remain refused. The earlier ordinary-note test no longer rejects Kind 2 as an
  unsupported owner: that outcome is now explicitly authorized here, and the new
  category-owned-card control proves it does not become ordinary image fallback.
  Prior TXT no-note behavior and the narrow present-icon warning remain covered
  by the complete public regressions.

  Final commands used the exact interpreter
  `C:/Users/stefa/projects/brz2obsidian/.venv/Scripts/python.exe` with
  `PYTHONPATH=C:/Users/stefa/.codex/worktrees/ml-v3-type-gaps/brz2obsidian/src`;
  a runtime import check confirmed that worker source path. No shared editable
  install was redirected and no packages were installed:

  - `-m pytest -q tests/application/test_type_source_gaps_workflow.py tests/application/test_absent_note_images_workflow.py --basetemp=tmp/pytest-type-gaps-green6`: **200 passed in 15.67s**.
  - `-m pytest -q --basetemp=tmp/pytest-type-gaps-complete --tb=short`: **1,028 passed in 139.08s**.
  - `-m ruff check --no-cache .`: all checks passed.
  - `-m ruff format --check .`: 123 files already formatted.
  - `-m pip check`: no broken requirements.
  - `git diff --check`: clean.

  Disposable archives/vaults are under this checkout's ignored
  `tmp/pytest-type-gaps-*`; no original export, retained vault or native UI was
  changed. This proves the bounded synthetic/runtime ticket only. Independent
  exact-head ticket verification and integration merger remain required after
  this handoff; ticket 06's raw-source oracle, the four-original audit, native
  Obsidian observations, actual user verdict and release/PR gates remain pending.

- 2026-10-06 (/root): Claimed after independently verified image fallback and
  category hierarchy were integrated at `8ca6874`. Build on the existing common
  source-gap/diagnostic/accounting capability in a separate managed worktree,
  using the already approved public seams for TDD.

- 2026-10-06 (/root): Published after the user approved all nine tickets and their
  dependencies, then explicitly invoked implement-spec for complete implementation.
