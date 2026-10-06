# 04: Preserve ordinary-to-category hierarchy in both directions

Status: resolved
Assignee: /root/hierarchy_implementer
Approved: 2026-10-06
Specification: [Accepted conversion specification](../spec.md)

**What to build:** Convert the reviewed ordinary-parent/type-child relationships into reciprocal navigation between ordinary notes and category dashboards, with category Parents/Children directly below the title before Members/Gallery. Classification continues to mean membership separately.

**Blocked by:** [01 — Exclude forgotten thoughts throughout inspection and conversion](01-forgotten-exclusion.md). This slice needs included graph/assignment identities; it can proceed independently of the image/type-gap slices.

## Acceptance criteria

- [x] Admit exactly Kind 1 / Relation 1 / Meaning 1 / Direction -1 with ordinary A as parent and type B as child after normal identity/signature checks. Do not widen other ordinary-only arrow variants, arbitrary endpoint combinations, custom links or subtype inheritance.
- [x] Retain every direct included ordinary parent on the category and reciprocal category children on ordinary notes, following the actual full scoped graph. Excluded endpoints contribute nothing; unknown nonexcluded dangling identities and unsupported signatures remain refusals.
- [x] Category Parents/Children appear directly after its title and before Members/Gallery; retain established unrelated Related navigation and source content/resources. Prototype subset labels or selected-neighbor shortcuts do not define production graph output.
- [x] Classification independently requires exact included TypeId/instance-link correspondence. Hierarchy alone does not create membership. All included type definitions and assigned members still materialize; existing Home/content, canonical greedy empty selection, cycles, intentional uncreated targets and collision-safe paths remain deterministic.
- [x] Preserve native Base roles/discovery, linked safe-YAML properties, dates, templates, icon-before-note display, category body-image suppression and absence of generated colour fields. No renderer-only graph rewrite bypasses source/core facts or accounting.
- [x] A complete public synthetic fixture with multiple parents, cycles, assigned/unassigned ordinary notes, an excluded endpoint and conflicting/unsupported signatures proves graph facts, materialization, reciprocal output navigation and exact hierarchy-before-members order. Public inspect/convert and thin CLI agree; repeats/root-order permutations retain logical paths/navigation.
- [x] Update hierarchy/layout coverage guidance and keep current public regressions green. This demonstrable slice does not need the ordinary/type absence implementations or full private archive to verify its boundary.

## Verification boundary

Public inspect/convert over actual synthetic archives, independently expected graph/notes/support facts and thin CLI; focused existing public core/source interfaces only when the highest practical contract seam.

## Specification coverage

User Stories 27–31, 49–50, 56–57, 60–62, 69–70; Implementation Decisions 1–7, 15–16, 20–23, 25; Testing Decisions 1–3, 7–8, 10, 16–17, 20.

## Comments

- 2026-10-06 (/root/integration_merger): Integrated exact verified branch head
  `f42a900563be235aae85da8a047b7ae9a384948e` from `codex/ml-v3-04` using
  `git merge --ff-only f42a900563be235aae85da8a047b7ae9a384948e` on the clean
  root integration branch at `a29e8a088d7d288e663dd633a2bd0ca939864a87`.
  Independent report `tmp/ml-implementation/04/verification.md` records PASS
  for bounded static review, ten handwritten raw-ZIP public control groups and
  63 focused tests in 6.58s at that exact clean head. It covers reciprocal
  full scoped graph, hierarchy/classification separation, category ordering,
  source/caller privacy, exact authored bodies/assets, repeat/reorder behavior,
  unsupported signature refusal and read-only checker inventory preservation.

  Root merged command:
  `.venv/Scripts/python.exe -m pytest -q tests/application/test_category_hierarchy_workflow.py tests/application/test_categories_workflow.py tests/application/test_dashboards_workflow.py tests/application/test_graph_modules.py tests/application/test_graph_workflow.py tests/application/test_alternate_source.py tests/application/test_alternate_v2_source.py --basetemp=tmp/ml-implementation/merger/pytest-04-f42a900 -o cache_dir=tmp/ml-implementation/merger/pytest-cache-04-f42a900`
  passed **113 tests in 13.34s**, exit 0. Runtime imports resolve to the root
  checkout. `git diff --check a29e8a088d7d288e663dd633a2bd0ca939864a87..f42a900563be235aae85da8a047b7ae9a384948e`
  passed, exit 0. Worker complete suite **828 passed in 148.34s**, Ruff and pip
  results remain attributed worker evidence; identical fast-forwarded code did
  not need a redundant full run. Copied worker evidence remains ignored under
  `tmp/ml-implementation/04/worker-evidence-f42a900/`.

  This resolves only the bounded hierarchy slice. Ticket 02 remains claimed;
  source-gap/type behavior, complete scoped independent four-original audits,
  actual native rendering, user verdict, cumulative final review and release
  remain separate pending gates. No other ticket claim or PR was made here.

- 2026-10-06 (/root/hierarchy_implementer): Resolved the bounded hierarchy slice
  in implementation commit `0e1119ca2d90965288f521cc0846de92c3349558`, based on
  integrated ticket 01 at `a29e8a088d7d288e663dd633a2bd0ca939864a87`. Merged
  `codex/management-leadership-v3` before handoff (already up to date). No index,
  specification, other ticket, source-gap implementation or native/private
  acceptance changes.
  - Public TDD cycle 1: `test_ordinary_parent_and_category_child_preserve_reciprocal_graph`
    failed at inspection with `unsupported_feature`; after admitting only the
    exact `(1,1,1,-1)` ordinary/type endpoint pair, it passed.
  - Public TDD cycle 2: the complete hierarchy fixture failed because category
    Parents followed Gallery; after moving only category Parents/Children above
    Bases, both hierarchy tests passed. All direct parents remain visible;
    duplicate graph edges retain accounting while visible neighbors deduplicate.
  - Independent rich-fixture control initially failed at its raw signature
    oracle. The independently maintained signature/body/adaptation/report/guide
    expectations now admit only the new tuple and layout; that control passes
    with exact authored mixed-newline content, original/icon/image/resource bytes,
    category dates and member icon behavior preserved.
  - Focused final command: `python -m pytest -q tests/application/test_category_hierarchy_workflow.py tests/application/test_categories_workflow.py --basetemp=tmp/pytest-hierarchy-final-focused`
    → **50 passed**. The complete public fixture proves created/uncreated targets,
    multiple parents, cycles, assigned/unassigned notes, excluded endpoint privacy,
    independent membership, thin CLI agreement and original/repeat/reordered
    navigation. Sixteen near-miss signature/identity cases refuse inspection and
    conversion without publication; a TypeId without its instance link refuses.
    An opaque Folio workflow control proves category Children placement and
    preservation of later Related navigation through the source-neutral pipeline.
  - Final complete command: `python -m pytest -q --basetemp=tmp/pytest-hierarchy-final`
    → **828 passed in 148.34s**. `python -m ruff check --no-cache .` → all checks
    passed; `python -m ruff format --check .` → 118 files already formatted;
    `python -m pip check` → no broken requirements; `git diff --check` → clean.
    Every Python command used
    `C:/Users/stefa/projects/brz2obsidian/.venv/Scripts/python.exe` with
    `$env:PYTHONPATH = Join-Path (Get-Location) 'src'` in the hierarchy worktree.
  - Boundary: the existing independent oracle still assumes whole raw evidence.
    Its new hierarchy/layout behavior is audited on an independently authored
    included-only complete control; exclusion is proved separately by literal
    public workflow expectations and matching included-control note bytes. Full
    scoped oracle expansion remains ticket 06. No personal archive, native UI or
    actual-user acceptance claim is made by this slice.

- 2026-10-06 (/root): Claimed after ticket 01's independently verified integration
  at `b5d6238`. Implement independently of image fallback in a managed worktree/
  branch with public-seam TDD; coordinate shared rendering/planning changes.

- 2026-10-06 (/root): Published after the user approved all nine tickets and their
  dependencies, then explicitly invoked implement-spec for complete implementation.
