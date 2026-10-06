# 04: Preserve ordinary-to-category hierarchy in both directions

Status: claimed
Assignee: /root/hierarchy_implementer
Approved: 2026-10-06
Specification: [Accepted conversion specification](../spec.md)

**What to build:** Convert the reviewed ordinary-parent/type-child relationships into reciprocal navigation between ordinary notes and category dashboards, with category Parents/Children directly below the title before Members/Gallery. Classification continues to mean membership separately.

**Blocked by:** [01 — Exclude forgotten thoughts throughout inspection and conversion](01-forgotten-exclusion.md). This slice needs included graph/assignment identities; it can proceed independently of the image/type-gap slices.

## Acceptance criteria

- [ ] Admit exactly Kind 1 / Relation 1 / Meaning 1 / Direction -1 with ordinary A as parent and type B as child after normal identity/signature checks. Do not widen other ordinary-only arrow variants, arbitrary endpoint combinations, custom links or subtype inheritance.
- [ ] Retain every direct included ordinary parent on the category and reciprocal category children on ordinary notes, following the actual full scoped graph. Excluded endpoints contribute nothing; unknown nonexcluded dangling identities and unsupported signatures remain refusals.
- [ ] Category Parents/Children appear directly after its title and before Members/Gallery; retain established unrelated Related navigation and source content/resources. Prototype subset labels or selected-neighbor shortcuts do not define production graph output.
- [ ] Classification independently requires exact included TypeId/instance-link correspondence. Hierarchy alone does not create membership. All included type definitions and assigned members still materialize; existing Home/content, canonical greedy empty selection, cycles, intentional uncreated targets and collision-safe paths remain deterministic.
- [ ] Preserve native Base roles/discovery, linked safe-YAML properties, dates, templates, icon-before-note display, category body-image suppression and absence of generated colour fields. No renderer-only graph rewrite bypasses source/core facts or accounting.
- [ ] A complete public synthetic fixture with multiple parents, cycles, assigned/unassigned ordinary notes, an excluded endpoint and conflicting/unsupported signatures proves graph facts, materialization, reciprocal output navigation and exact hierarchy-before-members order. Public inspect/convert and thin CLI agree; repeats/root-order permutations retain logical paths/navigation.
- [ ] Update hierarchy/layout coverage guidance and keep current public regressions green. This demonstrable slice does not need the ordinary/type absence implementations or full private archive to verify its boundary.

## Verification boundary

Public inspect/convert over actual synthetic archives, independently expected graph/notes/support facts and thin CLI; focused existing public core/source interfaces only when the highest practical contract seam.

## Specification coverage

User Stories 27–31, 49–50, 56–57, 60–62, 69–70; Implementation Decisions 1–7, 15–16, 20–23, 25; Testing Decisions 1–3, 7–8, 10, 16–17, 20.

## Comments

- 2026-10-06 (/root): Claimed after ticket 01's independently verified integration
  at `b5d6238`. Implement independently of image fallback in a managed worktree/
  branch with public-seam TDD; coordinate shared rendering/planning changes.

- 2026-10-06 (/root): Published after the user approved all nine tickets and their
  dependencies, then explicitly invoked implement-spec for complete implementation.
