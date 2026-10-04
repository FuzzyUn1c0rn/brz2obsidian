# Version 2 implementation tickets

Status: claimed

Labels: ready-for-agent

Assignee: /root

Integration branch: `codex/brz-to-obsidian-v2`

Implementation baseline: `f4627d9cbadb2bec4b97c946dce4cc9f9946adb0` (completed v1).

Validated planning commit: `d71fac34f412fe0871ca0e9b81b25e98f604a213`.

The user approved the 11-ticket breakdown and dependencies on 2026-10-04. Each ticket below was published separately with ready-for-agent status, acceptance checkboxes, specification-story coverage and the confirmed testing boundaries. The user invoked implement-spec to begin the complete implementation on the integration branch. Ticket files record current claims and verified completion. This index tracks implementation toward a **finished, verified version 2**, rather than treating ticket publication as delivery.

Read the accepted [implementation specification](spec.md), [source-feature comparison](source-feature-mapping.md) and [approved breakdown](ticket-breakdown.md). The [Wayfinder map](../brz-to-obsidian-v2/map.md) and its research remain decision evidence. The specification and parent planning issues are unchanged by this to-tickets publication.

## Ticket index

| Ticket | Blocked by | Demonstrable result |
| --- | --- | --- |
| [01: Convert thought types and all their members into linked category notes](issues/01-typed-category-conversion.md) | None | Inspect and convert a small reviewed Brain containing a type and typed members, including an otherwise empty member, into a verified fresh vault with distinct category/member notes and linked memberships. Ordinary native links and Backlinks make the objects navigable before later dashboard presentation lands. |
| [02: Preserve canonical properties, source dates and editable icon snapshots](issues/02-properties-dates-icon-snapshots.md) | [01](issues/01-typed-category-conversion.md) | Converted objects expose the documented linked metadata and source-derived calendar dates, with preserved local icon images and migration-time body-icon references that users can edit. |
| [03: Browse categories through rename-safe native dashboards](issues/03-native-category-dashboards.md) | [02](issues/02-properties-dates-icon-snapshots.md) | Home opens a Categories overview, and category notes embed native Members/Gallery Bases with complete discovery and live icon inheritance. |
| [04: Create and extend objects with native templates and a maintenance guide](issues/04-native-templates-maintenance.md) | [03](issues/03-native-category-dashboards.md) | A user opens the generated vault, selects a full template for a new note, sees it discovered in the dashboard and can add a future category using documented starters. |
| [05: Convert the evidenced differently marked thought note safely](issues/05-exceptional-markdown-note.md) | [01](issues/01-typed-category-conversion.md) | The sole unambiguous nonempty canonical NoteType-0 thought-note case becomes readable active Markdown with a working local image and exact original backup. |
| [06: Report the zero-length absent TXT pattern while preserving PDFs](issues/06-zero-length-txt-pdf-gaps.md) | [01](issues/01-typed-category-conversion.md) | A reviewed zero-length absent TXT declaration beside its identity-associated intact PDF converts successfully with an explicit source-gap warning and no fabricated file. |
| [07: Present reviewed video resources without changing their source URLs](issues/07-native-video-resources.md) | [01](issues/01-typed-category-conversion.md) | Converted reviewed YouTube resources retain exact clickable URLs and provide a usable native embed with the evidenced timing intent. |
| [08: Check editable vault conventions through a read-only library and command](issues/08-read-only-vault-checker.md) | [04](issues/04-native-templates-maintenance.md) | A human or agent checks a generated or manually edited vault and receives deterministic structural diagnostics without needing the source archive or modifying any note. |
| [09: Prove the combined v2 workflow, publication safety and source neutrality](issues/09-integrated-v2-publication-reuse.md) | [05](issues/05-exceptional-markdown-note.md), [06](issues/06-zero-length-txt-pdf-gaps.md), [07](issues/07-native-video-resources.md), [08](issues/08-read-only-vault-checker.md) | One complete synthetic conversion combines the new concepts with existing graph/tags/resources, passes the convention checker, and remains safe and reusable through public interfaces. |
| [10: Independently verify complete preservation across all three real archives](issues/10-three-archive-preservation.md) | [09](issues/09-integrated-v2-publication-reuse.md) | The complete Software Engineering archive and both earlier archives convert into fresh vaults, with source-derived preservation and reproducibility evidence independent of production expectations. |
| [11: Accept actual v2 vaults in Obsidian and finish delivery guidance](issues/11-native-v2-acceptance-delivery.md) | [10](issues/10-three-archive-preservation.md) | The user reviews the actual independently verified vaults in standard Obsidian and receives the final installation, library/CLI, maintenance and limitations guidance for a finished v2. |

## Working the frontier

**Current work: [01: Convert thought types and all their members into linked category notes](issues/01-typed-category-conversion.md), claimed for isolated implementation.** No other ticket is eligible until it resolves. Ready-for-agent means specified; blockers still govern when a ticket can start.

After 01 resolves, 02, 05, 06 and 07 become eligible. Metadata/icons lead to dashboards (03), native templates (04) and the read-only checker (08). Dashboard ticket 03 enables Bases for its first native check; ticket 04 preserves that configuration and adds Templates. Ticket 09 joins 05, 06, 07 and 08; their transitive prerequisites already include 01–04. The independent full-archive audit (10) follows integration, and native final acceptance (11) follows the audit. Dependencies are acyclic and numbered blockers-first; redundant transitive edges are omitted.

Logical independence does not authorize overlapping concurrent edits to shared modules. Execute the approved frontier sequentially unless parallel work is separately authorized and isolated appropriately. Follow the [claim and completion process](../../docs/agents/issue-tracker.md#implementation-operations): save Status: claimed and the assignee before implementation; record evidence and check satisfied criteria; set Status: resolved only when all criteria pass. Update the index's frontier as work completes. Implementation numbers are local to this feature and have no dependency on planning ticket numbers.

## Shape and testing boundaries

Eleven slices progressively add observable conversion/maintenance behavior. The current source adapter, pure core, renderer, publisher and workflow already expose the required boundaries. No standalone prefactoring or wide expand–contract migration is needed: evolve the versioned contracts through the first working typed conversion, and keep small naming/property/rendering refactors inside the slice whose output proves them. Update affected existing public tests for explicitly changed v2 schemas and output, preserving their underlying behavior checks.

Use public inspect/convert workflow calls with actual synthetic ZIPs and temporary vaults as the main automatic seam. Thin CLI checks verify serialization and exits. The checker has its own public library/command seam. Focused existing source/core/renderer/publication boundaries remain available for contract, reference-span and failure cases. Public tests use synthetic inputs; independent real-archive acceptance and native Computer evidence stay private. The project virtual environment remains mandatory.

Each feature slice must leave its applicable public regression checks green and demonstrate its result independently. Early slices are usable subsets of v2, not claims that the full Software Engineering archive already converts. Update the relevant migration record/report, artifact accounting and usage guidance as behavior lands. The last three slices establish integrated, independently audited and natively accepted delivery.

Keep the [domain glossary](../../GLOSSARY.md), [accepted architecture decision](../../docs/adr/0001-source-neutral-core.md), cumulative first-version behavior and confirmed public testing seams. All supplied archives use the same TheBrain version; v2 expands feature coverage rather than inferring a format-version transition. All Python execution and package installation uses the project's virtual environment.

## Specification-story ownership

All 82 stories have primary owners below; the individual tickets include additional overlapping coverage where preservation, presentation, maintenance and final review need separate evidence. This table ensures that features are not left solely to the final review gate.

| Specification stories | Primary owner(s) |
| --- | --- |
| 1 | [10: Independently verify complete preservation across all three real archives](issues/10-three-archive-preservation.md), [11: Accept actual v2 vaults in Obsidian and finish delivery guidance](issues/11-native-v2-acceptance-delivery.md) |
| 2–4 | [01: Convert thought types and all their members into linked category notes](issues/01-typed-category-conversion.md), [09: Prove the combined v2 workflow, publication safety and source neutrality](issues/09-integrated-v2-publication-reuse.md) |
| 5 | [01: Convert thought types and all their members into linked category notes](issues/01-typed-category-conversion.md), [03: Browse categories through rename-safe native dashboards](issues/03-native-category-dashboards.md) |
| 6–10 | [02: Preserve canonical properties, source dates and editable icon snapshots](issues/02-properties-dates-icon-snapshots.md), [05: Convert the evidenced differently marked thought note safely](issues/05-exceptional-markdown-note.md), [09: Prove the combined v2 workflow, publication safety and source neutrality](issues/09-integrated-v2-publication-reuse.md) |
| 11–14 | [01: Convert thought types and all their members into linked category notes](issues/01-typed-category-conversion.md), [09: Prove the combined v2 workflow, publication safety and source neutrality](issues/09-integrated-v2-publication-reuse.md) |
| 15–22 | [01: Convert thought types and all their members into linked category notes](issues/01-typed-category-conversion.md), [03: Browse categories through rename-safe native dashboards](issues/03-native-category-dashboards.md) |
| 23–27 | [03: Browse categories through rename-safe native dashboards](issues/03-native-category-dashboards.md) |
| 28–33 | [02: Preserve canonical properties, source dates and editable icon snapshots](issues/02-properties-dates-icon-snapshots.md), [03: Browse categories through rename-safe native dashboards](issues/03-native-category-dashboards.md) |
| 34 | [03: Browse categories through rename-safe native dashboards](issues/03-native-category-dashboards.md), [04: Create and extend objects with native templates and a maintenance guide](issues/04-native-templates-maintenance.md) |
| 35–40 | [04: Create and extend objects with native templates and a maintenance guide](issues/04-native-templates-maintenance.md) |
| 41–43 | [02: Preserve canonical properties, source dates and editable icon snapshots](issues/02-properties-dates-icon-snapshots.md), [04: Create and extend objects with native templates and a maintenance guide](issues/04-native-templates-maintenance.md) |
| 44–48 | [04: Create and extend objects with native templates and a maintenance guide](issues/04-native-templates-maintenance.md), [08: Check editable vault conventions through a read-only library and command](issues/08-read-only-vault-checker.md) |
| 49–50 | [03: Browse categories through rename-safe native dashboards](issues/03-native-category-dashboards.md), [04: Create and extend objects with native templates and a maintenance guide](issues/04-native-templates-maintenance.md) |
| 51 | [08: Check editable vault conventions through a read-only library and command](issues/08-read-only-vault-checker.md) |
| 52–53 | [05: Convert the evidenced differently marked thought note safely](issues/05-exceptional-markdown-note.md) |
| 54–57 | [06: Report the zero-length absent TXT pattern while preserving PDFs](issues/06-zero-length-txt-pdf-gaps.md) |
| 58–60 | [07: Present reviewed video resources without changing their source URLs](issues/07-native-video-resources.md) |
| 61–65 | [01: Convert thought types and all their members into linked category notes](issues/01-typed-category-conversion.md), [05: Convert the evidenced differently marked thought note safely](issues/05-exceptional-markdown-note.md), [06: Report the zero-length absent TXT pattern while preserving PDFs](issues/06-zero-length-txt-pdf-gaps.md), [07: Present reviewed video resources without changing their source URLs](issues/07-native-video-resources.md), [09: Prove the combined v2 workflow, publication safety and source neutrality](issues/09-integrated-v2-publication-reuse.md) |
| 66–72 | [08: Check editable vault conventions through a read-only library and command](issues/08-read-only-vault-checker.md), [10: Independently verify complete preservation across all three real archives](issues/10-three-archive-preservation.md) |
| 73 | [09: Prove the combined v2 workflow, publication safety and source neutrality](issues/09-integrated-v2-publication-reuse.md), [10: Independently verify complete preservation across all three real archives](issues/10-three-archive-preservation.md) |
| 74–75 | [01: Convert thought types and all their members into linked category notes](issues/01-typed-category-conversion.md), [02: Preserve canonical properties, source dates and editable icon snapshots](issues/02-properties-dates-icon-snapshots.md), [03: Browse categories through rename-safe native dashboards](issues/03-native-category-dashboards.md), [04: Create and extend objects with native templates and a maintenance guide](issues/04-native-templates-maintenance.md), [05: Convert the evidenced differently marked thought note safely](issues/05-exceptional-markdown-note.md), [06: Report the zero-length absent TXT pattern while preserving PDFs](issues/06-zero-length-txt-pdf-gaps.md), [07: Present reviewed video resources without changing their source URLs](issues/07-native-video-resources.md), [08: Check editable vault conventions through a read-only library and command](issues/08-read-only-vault-checker.md), [09: Prove the combined v2 workflow, publication safety and source neutrality](issues/09-integrated-v2-publication-reuse.md) |
| 76–78 | [01: Convert thought types and all their members into linked category notes](issues/01-typed-category-conversion.md), [08: Check editable vault conventions through a read-only library and command](issues/08-read-only-vault-checker.md), [09: Prove the combined v2 workflow, publication safety and source neutrality](issues/09-integrated-v2-publication-reuse.md) |
| 79–80 | [01: Convert thought types and all their members into linked category notes](issues/01-typed-category-conversion.md), [02: Preserve canonical properties, source dates and editable icon snapshots](issues/02-properties-dates-icon-snapshots.md), [03: Browse categories through rename-safe native dashboards](issues/03-native-category-dashboards.md), [04: Create and extend objects with native templates and a maintenance guide](issues/04-native-templates-maintenance.md), [05: Convert the evidenced differently marked thought note safely](issues/05-exceptional-markdown-note.md), [06: Report the zero-length absent TXT pattern while preserving PDFs](issues/06-zero-length-txt-pdf-gaps.md), [07: Present reviewed video resources without changing their source URLs](issues/07-native-video-resources.md), [08: Check editable vault conventions through a read-only library and command](issues/08-read-only-vault-checker.md), [09: Prove the combined v2 workflow, publication safety and source neutrality](issues/09-integrated-v2-publication-reuse.md), [10: Independently verify complete preservation across all three real archives](issues/10-three-archive-preservation.md), [11: Accept actual v2 vaults in Obsidian and finish delivery guidance](issues/11-native-v2-acceptance-delivery.md) |
| 81 | [11: Accept actual v2 vaults in Obsidian and finish delivery guidance](issues/11-native-v2-acceptance-delivery.md) |
| 82 | [Approved breakdown/publication](ticket-breakdown.md), [10: Independently verify complete preservation across all three real archives](issues/10-three-archive-preservation.md), [11: Accept actual v2 vaults in Obsidian and finish delivery guidance](issues/11-native-v2-acceptance-delivery.md) |

## Delivery gates

- Individual slices demonstrate actual output and leave applicable public regression checks green. Update versioned contracts, report/record/artifact accounting and usage guidance as behavior lands.
- Ticket 09 proves a combined synthetic v2 conversion, CLI/checker behavior, failure-safe publication and alternate-source reuse through the accepted public boundaries.
- Ticket 10 independently audits all three complete real archives, each in exact, repeated and reordered form: nine accepted full conversions. It checks every record, present payload, authored span, reference, classification and generated artifact against independently source-derived facts, including meaningful corruption controls.
- Ticket 11 reviews actual audited outputs in standard Obsidian using Computer on review copies, completes installation/library/CLI/maintenance guidance and independent specification/standards review, and repeats final applicable checks. The user's actual converted-vault verdict must be recorded before v2 is declared finished.
- Publication of these tickets, passing the convention checker or acceptance of the earlier prototype does not satisfy full migration preservation or the final delivery gate. Keep raw private archives, outputs and native evidence ignored; publish aggregate findings and honest limitations.

## Comments

- 2026-10-04 (/root): The user approved the proposed ticket sizes, deliverables and blocker edges with “Agreed”. Published all 11 individual tickets. Only 01 is initially unblocked. Parent planning records and the accepted specification are preserved; production implementation has not begun.
- 2026-10-04 (/root): Independent documentation validation clarified read-only inspection, the already accepted operational folder layout and first-use Bases configuration in ticket 03. The 11 approved slices and their dependencies are unchanged; story 34 is now explicitly shared by 03 and 04.
- 2026-10-04 (/root): The same validation made materialized source-tag notes explicit in ticket 02's imported metadata/date criteria and synthetic case. The separate Wayfinder handoff was reconciled after publication so it now points at this implementation frontier and its delivery gates.
- 2026-10-04 (/root): The user invoked implement-spec for complete v2 delivery. Created the integration branch, committed validated planning as d71fac3 and claimed the first eligible slice. Implementer worktrees use TDD at the already-confirmed public boundaries; merger agents integrate completed slices before the frontier advances. Parallel execution is now authorized by the invoked skill, with isolated branches and coordinated shared-boundary changes.
