# Create the approved version 2 implementation tickets with to-tickets

Status: resolved
Type: grilling
Labels: wayfinder:grilling
Parent: [Find the route to version 2 for the Software Engineering Brain](../map.md)
Blocked by: 06
Assignee: /root

## Question

What approved, dependency-ordered implementation breakdown will deliver the agreed version 2 specification through independently demonstrable slices?

Use the explicitly required [to-tickets skill](C:/Users/stefa/.agents/skills/to-tickets/SKILL.md). Read the generated implementation specification and current codebase, identify any genuinely necessary prefactoring, and draft vertical slices sized for fresh implementation sessions. Each slice should deliver usable end-to-end behavior with acceptance criteria and tests at the agreed public seams. Include full new-archive preservation, earlier-archive regressions and native final acceptance in the coverage; avoid splitting the work solely by technical layer.

Present the concrete breakdown, blocker edges and deliverables for the user's review, as required by to-tickets. Iterate until approved, then publish one `ready-for-agent` implementation ticket per slice in the separate version 2 implementation area, with an index and story/acceptance coverage. Dependencies between implementation tickets belong to that index and those files, not this Wayfinder child's local number space.

Link the published index from this answer. Specify how the map advances through the implementation frontier, and add precise delivery/final-acceptance gates now that their prerequisites are known. Ticket publication does not complete the map; the user requires a finished, verified version 2.

## Answer

The user approved the concrete 11-slice breakdown and genuine blocker edges on 2026-10-04 with “Agreed”. The [implementation index](../../brz-to-obsidian-v2-implementation/README.md) publishes every slice as its own ready-for-agent ticket, with acceptance criteria, public testing boundaries and coverage of all 82 specification stories. No standalone prefactoring is necessary; the existing reusable boundaries support incremental vertical slices. Only [Convert thought types and all their members into linked category notes](../../brz-to-obsidian-v2-implementation/issues/01-typed-category-conversion.md) is initially eligible.

The route advances through that separate implementation frontier. [Prove the combined v2 workflow, publication safety and source neutrality](../../brz-to-obsidian-v2-implementation/issues/09-integrated-v2-publication-reuse.md) joins the feature slices. [Independently verify complete preservation across all three real archives](../../brz-to-obsidian-v2-implementation/issues/10-three-archive-preservation.md) requires nine exact/repeated/reordered full conversions and complete source-derived conservation evidence. [Accept actual v2 vaults in Obsidian and finish delivery guidance](../../brz-to-obsidian-v2-implementation/issues/11-native-v2-acceptance-delivery.md) requires actual audited vault review, final guidance/checks and the user's converted-vault verdict. The map remains active until those delivery gates are satisfied.

The user subsequently requested independent sub-agent validation and corrections. The [documentation validation report](../../brz-to-obsidian-v2-implementation/research/ticket-spec-validation.md) records the findings and recheck. Small clarifications distinguish read-only inspection from publication, restore the agreed operational layout, enable Bases in the first dashboard slice and make imported source-tag metadata coverage explicit. The approved 11 slices and their dependencies remain intact; implementation has not started.

Parent records were correctly preserved during to-tickets publication. This resolution and the map's navigation update are a separate bookkeeping correction during the later user-requested validation pass.

## Comments

- 2026-10-04 (/root): Claimed for navigation-state reconciliation during the user-requested validation/correction pass, after approved to-tickets publication. That publication correctly left parent issues unchanged; this separate bookkeeping operation records its completed handoff and the implementation delivery route.
- 2026-10-04 (/root): Resolved the completed planning/publication handoff and linked its separate implementation frontier and precise delivery gates. The map remains ready-for-agent with a finished-v2 destination; no implementation ticket is claimed or resolved.
- 2026-10-04 (/root): The prerequisite is resolved. Read the [published ready-for-agent specification](../../brz-to-obsidian-v2-implementation/spec.md) and [source-feature comparison](../../brz-to-obsidian-v2-implementation/source-feature-mapping.md), covering 82 user stories and the confirmed testing boundaries. This is the next unclaimed frontier; use to-tickets and obtain the concrete breakdown review before publishing implementation tickets.
- 2026-10-04: Added after the user specified to-spec followed by to-tickets and clarified that delivery belongs within the map's destination.
