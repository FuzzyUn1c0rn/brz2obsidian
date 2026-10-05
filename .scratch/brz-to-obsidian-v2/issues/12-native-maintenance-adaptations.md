# Choose maintenance adaptations exposed by the native vault trial

Status: resolved
Type: grilling
Labels: wayfinder:grilling
Parent: [Find the route to version 2 for the Software Engineering Brain](../map.md)
Blocked by: 05
Assignee: /root

## Question

Which adaptations should the implementation specification adopt for the three maintenance limits demonstrated in the [native trial](../research/vault-trial.md)?

1. Full native templates overwrite existing scalar dates. Direct membership editing preserves them, and the demonstrated categories-only insertion candidate merges membership without replacing dates, identity or the appearance provider. Decide whether v2 should generate these additive templates alongside the accepted full templates for new objects, and document the safe existing-note workflow.
2. Native category renames update ordinary links but leave literal Base filter category names unchanged. Contextual embedded queries survived the rename, with different standalone context. Choose the generated query pattern and the human maintenance recipe, retaining the reference behavior and explicit tradeoff.
3. Native editing can shorten qualified links. Agree how the read-only checker should distinguish a uniquely resolved native link from an ambiguous target, while generation retains deterministic collision-safe links and imported identity stays stable.

Use demonstrated behavior rather than assumptions about native editing. The user accepted the prototype presentation and requested Icon before Note; that feedback does not accept these maintenance candidates. Settle this focused follow-up before the required to-spec handoff. No creation, rename or repair automation is implied.

## Answer

The user answered **Agreed** to Q1-Q3 in the live grilling round. All three branches are settled; these choices refine the earlier conventions using demonstrated native behavior.

### Q1: New-note templates and existing-note edits

Deliver the accepted generic and full category templates for new notes. Do not add a second set of additive category-only templates to v2. For an existing note, edit its linked `categories` property directly; changing membership updates Base discovery without inserting a full template again. Preserve established dates, authored content, imported identity and the explicit appearance provider. If a membership edit invalidates the provider, the accepted checker reports it without reselection or repair.

Explain that native full-template insertion can overwrite scalar properties, including dates. The safe documented workflow avoids that operation on existing notes; it does not claim the Templates plugin prevents arbitrary overwrites. Later `updated` changes remain explicitly maintained as already agreed. The demonstrated additive template remains disposable evidence, not a production deliverable.

### Q2: Rename-safe category dashboards

Generate category-member queries that use the identity of the category note embedding the Base, rather than a category name written into the filter. View members through the category dashboard. Native link-preserving category renames must retain membership discovery and icon-provider behavior, with imported identity stable.

This deliberately adapts the reference's native category/query/embed pattern using the contextual mechanism demonstrated in the trial. A standalone Base without an embedding category cannot identify which category's members to display; document opening the category dashboard as the supported entry point. Do not silently choose another category or introduce the withdrawn registry fields. Exact query serialization and artifact layout belong in the required specification.

### Q3: Shortened links and read-only checking

Generation retains deterministic collision-safe links and qualification where needed. Human/native editing may shorten a link. Accept a shorter link when it resolves unambiguously to its target; do not report it merely because its spelling differs from the generated form. Report ambiguous category, appearance-provider and local-image references without rewriting them. Existing checks for invalid roles/memberships and missing required category/Base/image targets still apply.

Intentional links to ordinary notes that have not been created remain allowed. Imported identity is stable through renames; the checker does not merge entities, rename files or repair references. Define deterministic resolution, ambiguity and diagnostic contracts through to-spec rather than requiring native Obsidian during routine checking.

### Handoff

The prototype presentation is already accepted: Icon first, Note second, with the decorative Appearance display removed. These maintenance decisions complete its outstanding follow-up. [Agree the version 2 specification and conversion acceptance checks](06-version-two-specification.md) is now unblocked and must use to-spec, including live agreement on the highest practical testing seams. Then use to-tickets for the implementation frontier. This decision does not publish a specification, implement the converter or establish final converted-vault acceptance.

## Comments

- 2026-10-04 (/root): The user answers **Agreed** to all three recommendations. Recorded the accepted design tree above and resolved this ticket; no maintenance candidates remain pending in the prototype review. The specification is the next unblocked frontier, and its testing-seam agreement remains required. No production code or prototype data was changed in this decision session.

- 2026-10-04 (/root): Claimed as the next unblocked decision ticket when the user asks what follows the accepted prototype. The opening frontier contains three independent choices, all grounded in completed native checks. Recommendations remain proposals: Q1 retain full templates for new objects and use direct category-property editing for existing notes, omitting extra additive templates from v2; Q2 use contextual category-dashboard queries to survive category renames, explicitly accepting that these member views are entered through the embedding category note rather than a standalone Base with no category context; Q3 accept shortened links that resolve unambiguously and report ambiguous category/provider/media references without rewriting, retaining the accepted allowance for intentional uncreated ordinary targets. Pause for the user's answers before recomputing the frontier or publishing any specification.
- 2026-10-04 (/root): Created from the completed disposable trial. The three candidates were already recorded in its review findings and remain unanswered. This ticket carries them forward without treating the user's positive visual verdict as maintenance-policy approval.
