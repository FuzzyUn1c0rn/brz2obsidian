# Approved implementation route for archive-only conversion

Status: resolved
Drafted: 2026-10-06
Approved: 2026-10-06

The user approved this nine-ticket breakdown and its dependencies on 2026-10-06,
then explicitly requested a local integration branch, a commit of this session's
changes and implement-spec. The accepted [conversion specification](spec.md),
separate [implementation index](README.md) and individual tickets govern execution.
Their number space is independent of the completed Wayfinder decision tickets.

## Approved tickets

1. **Title: Exclude forgotten thoughts throughout inspection and conversion.**
   **Blocked by:** None.
   **What it delivers:** A complete supported conversion with default exclusion:
   no forgotten note, owned payload, reference phrase, provider effect or unsafe
   evidence survives; safe included content and exact copies remain. Includes
   scoped counts, current version contracts and public/alternate-source proof.
   [Acceptance criteria](issues/01-forgotten-exclusion.md).
2. **Title: Display owned images when an ordinary thought note is absent.**
   **Blocked by:** Exclude forgotten thoughts throughout inspection and conversion.
   **What it delivers:** One/multiple valid owned images visibly embedded in the
   absent-note owner's vault note, layout A and actionable inspect/report facts,
   with no fabricated source text or loss of supplied Markdown.
   [Acceptance criteria](issues/02-absent-note-images.md).
3. **Title: Keep category dashboards usable through missing type notes and icons.**
   **Blocked by:** Display owned images when an ordinary thought note is absent.
   **What it delivers:** Category/member conversion with reviewed source gaps,
   unknown absent type text, neutral missing icons, valid explicit overrides and
   distinct provider/affected-member diagnostics; important cards remain intact.
   [Acceptance criteria](issues/03-type-source-gaps.md).
4. **Title: Preserve ordinary-to-category hierarchy in both directions.**
   **Blocked by:** Exclude forgotten thoughts throughout inspection and conversion.
   **What it delivers:** Exact reviewed hierarchy links, all direct parents and
   reciprocal children, category navigation before Members/Gallery and separate
   classification. Can proceed independently of the two source-gap behaviors.
   [Acceptance criteria](issues/04-category-hierarchy.md).
5. **Title: Prove the combined conversion and publication guarantees.**
   **Blocked by:** Keep category dashboards usable through missing type notes and
   icons; Preserve ordinary-to-category hierarchy in both directions.
   **What it delivers:** A complete mixed synthetic workflow, deterministic
   library/CLI/checker behavior and real failure-safe publication, including
   truthful source/presentation accounting and durable post-publication receipts.
   [Acceptance criteria](issues/05-combined-workflow-safety.md).
6. **Title: Extend the independent raw-source audit to the new conversion policy.**
   **Blocked by:** Keep category dashboards usable through missing type notes and
   icons; Preserve ordinary-to-category hierarchy in both directions.
   **What it delivers:** A source-derived independent oracle, meaningful forged-
   receipt corruption controls and four-input driver that can prove exact,
   repeated and reordered complete conversions. Can proceed alongside the
   combined publication-safety proof.
   [Acceptance criteria](issues/06-independent-audit-tooling.md).
7. **Title: Audit complete preservation across all four original archives.**
   **Blocked by:** Prove the combined conversion and publication guarantees;
   Extend the independent raw-source audit to the new conversion policy.
   **What it delivers:** Twelve complete audited outputs, original-input proof
   for all 359 supplied included bodies and 63 affected visible images, 47
   definitions/330 assigned members and cumulative earlier-archive preservation.
   [Acceptance criteria](issues/07-four-archive-preservation.md).
8. **Title: Verify actual converted vaults in native Obsidian.**
   **Blocked by:** Audit complete preservation across all four original archives.
   **What it delivers:** Native rendering/Base/navigation/maintenance observations
   on fresh actual-output copies, with audited baselines intact and a clean
   real-output vault ready for the user's final review.
   [Acceptance criteria](issues/08-native-obsidian-review.md).
9. **Title: Deliver the reviewed release after actual-vault user acceptance.**
   **Blocked by:** Verify actual converted vaults in native Obsidian.
   **What it delivers:** Final specification/standards review, full public/tooling/
   package/example gates, updated guidance and the actual user verdict before
   declaring 0.3.0 delivery complete.
   [Acceptance criteria](issues/09-release-user-acceptance.md).

## Why these edges exist

Exclusion establishes the included identity/graph/evidence policy needed before
new output features are trusted. Ordinary image fallback delivers the common
source-gap/finding/diagnostic/accounting path used by the type-gap behavior;
that is its actual interface dependency, not an arbitrary scheduling preference.
Hierarchy depends on scoped graph identities, independently of image fallback.

The combined workflow and independent audit-tooling tickets require both feature
branches but do not block each other. Full private acceptance needs verified
workflow behavior and a proved independent audit. Native checks use already
audited actual output, followed by final user acceptance and release verification.
Only direct blockers are listed; transitive prerequisites are not repeated.

## Size, prefactoring and completion rules

Each behavior ticket owns a complete path from input facts to public results,
actual vault output, meaningful checks and changed usage guidance. It does not
leave existing tests deliberately broken for a later gate. Small necessary
refactoring belongs before new behavior within that slice; current injectable
source/core/renderer/publisher boundaries already provide the required seams.
There is no known wide mechanical refactor that requires an expand-contract
sequence or a separate horizontal schema-only ticket.

The exclusion slice establishes the accepted common version-3 optional contract
shape with empty gap/presentation facts; later slices populate that shape. Image
fallback owns the common source-gap policy/diagnostic/accounting capability,
which makes the type-gap dependency explicit. The integration gate strengthens
already-green feature behavior rather than deferring known failures. Final
review/repairs and refreshed automated/source/native/package evidence precede
the user's verdict on that exact clean output.

The first exclusion slice is the broadest behavior change because privacy must
hold across notes, evidence and errors at once. It is bounded to the single
forgotten-scope policy and its complete observable result. The standalone tool,
complete-source audit, native application and final acceptance slices keep those
distinct proof obligations from inflating that implementation session. Their
completion is independently verifiable even though they are delivery gates.

The [coverage matrix](specification-coverage.md) and individual ticket criteria
cover the complete accepted specification. Only **Exclude forgotten thoughts
throughout inspection and conversion** is initially unblocked. Ready-for-agent
means fully specified; blockers must be resolved before claiming later tickets.

The planning destination is complete. The user separately authorized full
implementation; migration and release completion still require all source,
native and actual-vault user gates.

## Review and validation

Two independent GPT 6.1 Sol medium reviews checked requirement coverage and
slice size/dependencies against the accepted specification and existing public
boundaries. Both support the nine-ticket route without a mandatory split/merge
or wide prefactor. Their localized clarifications are incorporated: independently
failing fixtures for each absence predicate, exact expected nested/mixed-newline
bodies, unambiguous four-original acceptance, version-shape/shared-capability
ownership, green failure behavior and final-verdict ordering.

Read-only document validation passes for all 70 stories, 25 implementation
decisions and 20 testing decisions, all nine complete candidate files, link
targets and an acyclic dependency order. No private source record identities
occur in the approved breakdown; the original input fingerprint is unchanged. These are
planning checks, not production tests or full-vault acceptance. Individual implementation
tickets and the index are published after the actual approval.

## Comments

- 2026-10-06 (/root): Actual user response: “Okay I approve the tickets so make
  them and get them out of the draft.” Published the approved graph unchanged
  in scope/dependencies. The following branch/commit/implement-spec request
  separately authorizes execution; no full conversion acceptance is inferred.
