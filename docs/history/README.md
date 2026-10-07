# Historical evidence and GitHub migration

Specifications, Wayfinder maps, implementation indexes and tickets moved to
[GitHub Issues](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues) on 2026-10-07. Completed work is closed and
labelled `historical`. The writer-helper specification reuses open issue #3.
This directory retains supporting research, verification reports and archived
inspection scripts. New planning and tracking records belong in GitHub.

The [migration receipt](github-migration.json) records source SHA-256 hashes,
issue URLs, dependencies and supporting-file locations. Migrated issue bodies
retain original comments and status lines as history; current GitHub state
and native issue relationships govern tracking.

Architecture layouts, approved ticket breakdowns, requirement coverage and
source-feature mappings are retained as comments on their feature issues.

GitHub issue links to unchanged supporting files use immutable published
commit `34c8f0b3f5399fea04daaf4490944b475a6f4da4`. The changed aggregate inventory is retained in a
comment on its Wayfinder map. Supporting files also remain available here.

Archived reports retain historical command paths, commit pins and observations.
Their private `tmp/` and `brz/` evidence links are usable only where that data
is retained. Inspection scripts have their repository-root and helper paths
adjusted for this archive; their substantive research behavior is unchanged.
Review historical commands before rerunning them. `.scratch/` is now ignored
and reserved for disposable artifacts.

## Migrated records

| Former local path | GitHub issue |
| --- | --- |
| `.scratch/brz-to-obsidian/issues/01-brz-preservation-evidence.md` | [#51: [brz-to-obsidian] Determine what the BRZ export can preserve](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/51) |
| `.scratch/brz-to-obsidian/issues/02-obsidian-representation-evidence.md` | [#52: [brz-to-obsidian] Establish what standard Obsidian can represent](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/52) |
| `.scratch/brz-to-obsidian/issues/03-vault-model.md` | [#53: [brz-to-obsidian] Choose note identity, relationships, and vault layout](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/53) |
| `.scratch/brz-to-obsidian/issues/04-vault-trial.md` | [#54: [brz-to-obsidian] Validate the proposed vault in Obsidian](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/54) |
| `.scratch/brz-to-obsidian/issues/05-conversion-contract.md` | [#55: [brz-to-obsidian] Choose the conversion and failure contract](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/55) |
| `.scratch/brz-to-obsidian/issues/06-implementation-specification.md` | [#56: [brz-to-obsidian] Agree acceptance checks and the implementation specification](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/56) |
| `.scratch/brz-to-obsidian/issues/07-relationship-fixture.md` | [#57: [brz-to-obsidian] Verify hierarchy and default direction with a controlled export](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/57) |
| `.scratch/brz-to-obsidian/issues/08-reverse-and-one-way-evidence.md` | [#58: [brz-to-obsidian] Verify reverse arrows and one-way relationship behavior](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/58) |
| `.scratch/brz-to-obsidian/issues/09-uncreated-target-evidence.md` | [#59: [brz-to-obsidian] Verify uncreated targets and empty-thought hierarchy coverage](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/59) |
| `.scratch/brz-to-obsidian/issues/10-parent-materialization-evidence.md` | [#60: [brz-to-obsidian] Quantify creating parents for uncovered hierarchy relationships](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/60) |
| `.scratch/brz-to-obsidian/issues/11-home-thought-evidence.md` | [#61: [brz-to-obsidian] Verify how BRZ identifies the home thought](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/61) |
| `.scratch/brz-to-obsidian/map.md` | [#7: [brz-to-obsidian] Find the route from a BRZ archive to an Obsidian vault](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/7) |
| `.scratch/brz-to-obsidian/spec.md` | [#12: [brz-to-obsidian] Implementation specification moved](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/12) |
| `.scratch/brz-to-obsidian-v1/issues/01-minimal-brain-vault.md` | [#14: [brz-to-obsidian-v1] 01: Convert a minimal Brain into a fresh vault](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/14) |
| `.scratch/brz-to-obsidian-v1/issues/02-hierarchy-empty-targets.md` | [#15: [brz-to-obsidian-v1] 02: Preserve hierarchy and empty thought targets](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/15) |
| `.scratch/brz-to-obsidian-v1/issues/03-files-resource-references.md` | [#16: [brz-to-obsidian-v1] 03: Preserve files and resource references](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/16) |
| `.scratch/brz-to-obsidian-v1/issues/04-source-note-links.md` | [#17: [brz-to-obsidian-v1] 04: Adapt thought and image links without rewriting notes](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/17) |
| `.scratch/brz-to-obsidian-v1/issues/05-native-tags.md` | [#18: [brz-to-obsidian-v1] 05: Preserve tags using native Obsidian features](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/18) |
| `.scratch/brz-to-obsidian-v1/issues/06-verified-coverage-source-gaps.md` | [#19: [brz-to-obsidian-v1] 06: Report known gaps and enforce verified source coverage](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/19) |
| `.scratch/brz-to-obsidian-v1/issues/07-publication-failure-protection.md` | [#20: [brz-to-obsidian-v1] 07: Protect publication against source and I/O failures](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/20) |
| `.scratch/brz-to-obsidian-v1/issues/08-alternate-source-reuse.md` | [#21: [brz-to-obsidian-v1] 08: Prove reuse with an alternate source](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/21) |
| `.scratch/brz-to-obsidian-v1/issues/09-real-export-preservation.md` | [#22: [brz-to-obsidian-v1] 09: Verify complete preservation on both real exports](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/22) |
| `.scratch/brz-to-obsidian-v1/issues/10-obsidian-first-version-acceptance.md` | [#23: [brz-to-obsidian-v1] 10: Accept the first version in Obsidian and document usage](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/23) |
| `.scratch/brz-to-obsidian-v1/issues/11-final-review-repairs.md` | [#24: [brz-to-obsidian-v1] 11: Resolve final Standards and Spec review findings](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/24) |
| `.scratch/brz-to-obsidian-v1/README.md` | [#4: [brz-to-obsidian-v1] First-version implementation tickets](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/4) |
| `.scratch/brz-to-obsidian-v1/spec.md` | [#10: [brz-to-obsidian-v1] Convert a TheBrain BRZ archive into a new Obsidian vault](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/10) |
| `.scratch/brz-to-obsidian-v2/issues/01-new-archive-evidence.md` | [#39: [brz-to-obsidian-v2] Determine everything the new Brain adds to version 1 coverage](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/39) |
| `.scratch/brz-to-obsidian-v2/issues/02-obsidian-type-options.md` | [#40: [brz-to-obsidian-v2] Establish Obsidian options for types and inherited appearance](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/40) |
| `.scratch/brz-to-obsidian-v2/issues/03-thought-type-representation.md` | [#41: [brz-to-obsidian-v2] Choose how thought types and inherited appearance translate into the vault](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/41) |
| `.scratch/brz-to-obsidian-v2/issues/04-version-two-coverage.md` | [#42: [brz-to-obsidian-v2] Choose version 2 coverage for the other archive differences](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/42) |
| `.scratch/brz-to-obsidian-v2/issues/05-version-two-vault-trial.md` | [#43: [brz-to-obsidian-v2] Test the proposed version 2 representation in a disposable vault](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/43) |
| `.scratch/brz-to-obsidian-v2/issues/06-version-two-specification.md` | [#44: [brz-to-obsidian-v2] Agree the version 2 specification and conversion acceptance checks](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/44) |
| `.scratch/brz-to-obsidian-v2/issues/07-version-two-implementation-tickets.md` | [#45: [brz-to-obsidian-v2] Create the approved version 2 implementation tickets with to-tickets](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/45) |
| `.scratch/brz-to-obsidian-v2/issues/08-native-source-behavior.md` | [#46: [brz-to-obsidian-v2] Verify the new source behaviors in native TheBrain](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/46) |
| `.scratch/brz-to-obsidian-v2/issues/09-attachment-text-meaning.md` | [#47: [brz-to-obsidian-v2] Verify the purpose and state of attachment text records](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/47) |
| `.scratch/brz-to-obsidian-v2/issues/10-kepano-reference-patterns.md` | [#48: [brz-to-obsidian-v2] Evaluate the kepano reference vault against the migration requirements](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/48) |
| `.scratch/brz-to-obsidian-v2/issues/11-vault-templates-and-maintenance.md` | [#49: [brz-to-obsidian-v2] Choose templates and maintenance conventions for the generated vault](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/49) |
| `.scratch/brz-to-obsidian-v2/issues/12-native-maintenance-adaptations.md` | [#50: [brz-to-obsidian-v2] Choose maintenance adaptations exposed by the native vault trial](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/50) |
| `.scratch/brz-to-obsidian-v2/map.md` | [#6: [brz-to-obsidian-v2] Find the route to version 2 for the Software Engineering Brain](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/6) |
| `.scratch/brz-to-obsidian-v2-implementation/issues/01-typed-category-conversion.md` | [#25: [brz-to-obsidian-v2-implementation] 01: Convert thought types and all their members into linked category notes](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/25) |
| `.scratch/brz-to-obsidian-v2-implementation/issues/02-properties-dates-icon-snapshots.md` | [#26: [brz-to-obsidian-v2-implementation] 02: Preserve canonical properties, source dates and editable icon snapshots](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/26) |
| `.scratch/brz-to-obsidian-v2-implementation/issues/03-native-category-dashboards.md` | [#27: [brz-to-obsidian-v2-implementation] 03: Browse categories through rename-safe native dashboards](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/27) |
| `.scratch/brz-to-obsidian-v2-implementation/issues/04-native-templates-maintenance.md` | [#28: [brz-to-obsidian-v2-implementation] 04: Create and extend objects with native templates and a maintenance guide](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/28) |
| `.scratch/brz-to-obsidian-v2-implementation/issues/05-exceptional-markdown-note.md` | [#29: [brz-to-obsidian-v2-implementation] 05: Convert the evidenced differently marked thought note safely](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/29) |
| `.scratch/brz-to-obsidian-v2-implementation/issues/06-zero-length-txt-pdf-gaps.md` | [#30: [brz-to-obsidian-v2-implementation] 06: Report the zero-length absent TXT pattern while preserving PDFs](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/30) |
| `.scratch/brz-to-obsidian-v2-implementation/issues/07-native-video-resources.md` | [#31: [brz-to-obsidian-v2-implementation] 07: Present reviewed video resources without changing their source URLs](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/31) |
| `.scratch/brz-to-obsidian-v2-implementation/issues/08-read-only-vault-checker.md` | [#32: [brz-to-obsidian-v2-implementation] 08: Check editable vault conventions through a read-only library and command](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/32) |
| `.scratch/brz-to-obsidian-v2-implementation/issues/09-integrated-v2-publication-reuse.md` | [#33: [brz-to-obsidian-v2-implementation] 09: Prove the combined v2 workflow, publication safety and source neutrality](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/33) |
| `.scratch/brz-to-obsidian-v2-implementation/issues/10-three-archive-preservation.md` | [#34: [brz-to-obsidian-v2-implementation] 10: Independently verify complete preservation across all three real archives](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/34) |
| `.scratch/brz-to-obsidian-v2-implementation/issues/11-native-v2-acceptance-delivery.md` | [#35: [brz-to-obsidian-v2-implementation] 11: Accept actual v2 vaults in Obsidian and finish delivery guidance](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/35) |
| `.scratch/brz-to-obsidian-v2-implementation/issues/12-remove-unused-colour-properties.md` | [#36: [brz-to-obsidian-v2-implementation] 12: Remove unused colour properties from vault presentation](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/36) |
| `.scratch/brz-to-obsidian-v2-implementation/issues/13-final-review-repairs.md` | [#37: [brz-to-obsidian-v2-implementation] 13: Repair final implementation-review findings](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/37) |
| `.scratch/brz-to-obsidian-v2-implementation/issues/14-category-bases-first.md` | [#38: [brz-to-obsidian-v2-implementation] 14: Put category Bases first and remove generated introductory images](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/38) |
| `.scratch/brz-to-obsidian-v2-implementation/README.md` | [#5: [brz-to-obsidian-v2-implementation] Version 2 implementation tickets](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/5) |
| `.scratch/brz-to-obsidian-v2-implementation/spec.md` | [#11: [brz-to-obsidian-v2-implementation] BRZ to Obsidian — version 2 implementation specification](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/11) |
| `.scratch/implement-spec-enhanced/spec.md` | [#3: [implement-spec-enhanced] Writer helper for structured skill handoffs](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/3) |
| `.scratch/management-leadership-implementation/issues/01-forgotten-exclusion.md` | [#62: [management-leadership-implementation] 01: Exclude forgotten thoughts throughout inspection and conversion](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/62) |
| `.scratch/management-leadership-implementation/issues/02-absent-note-images.md` | [#63: [management-leadership-implementation] 02: Display owned images when an ordinary thought note is absent](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/63) |
| `.scratch/management-leadership-implementation/issues/03-type-source-gaps.md` | [#64: [management-leadership-implementation] 03: Keep category dashboards usable through missing type notes and icons](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/64) |
| `.scratch/management-leadership-implementation/issues/04-category-hierarchy.md` | [#65: [management-leadership-implementation] 04: Preserve ordinary-to-category hierarchy in both directions](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/65) |
| `.scratch/management-leadership-implementation/issues/05-combined-workflow-safety.md` | [#66: [management-leadership-implementation] 05: Prove the combined conversion and publication guarantees](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/66) |
| `.scratch/management-leadership-implementation/issues/06-independent-audit-tooling.md` | [#67: [management-leadership-implementation] 06: Extend the independent raw-source audit to the new conversion policy](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/67) |
| `.scratch/management-leadership-implementation/issues/07-four-archive-preservation.md` | [#68: [management-leadership-implementation] 07: Audit complete preservation across all four original archives](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/68) |
| `.scratch/management-leadership-implementation/issues/08-native-obsidian-review.md` | [#69: [management-leadership-implementation] 08: Verify actual converted vaults in native Obsidian](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/69) |
| `.scratch/management-leadership-implementation/issues/09-release-user-acceptance.md` | [#70: [management-leadership-implementation] 09: Deliver the reviewed release after actual-vault user acceptance](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/70) |
| `.scratch/management-leadership-implementation/README.md` | [#8: [management-leadership-implementation] Management & Leadership conversion implementation](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/8) |
| `.scratch/management-leadership-implementation/spec.md` | [#13: [management-leadership-implementation] Archive-only conversion with visible images and included-scope preservation](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/13) |
| `.scratch/management-leadership-wayfinding/issues/01-complete-archive-comparison.md` | [#71: [management-leadership-wayfinding] Complete the four-archive feature comparison](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/71) |
| `.scratch/management-leadership-wayfinding/issues/02-state-three-evidence.md` | [#72: [management-leadership-wayfinding] Establish state-3 evidence and recovery routes](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/72) |
| `.scratch/management-leadership-wayfinding/issues/03-native-source-observation.md` | [#73: [management-leadership-wayfinding] Verify absent content and type hierarchy in native TheBrain](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/73) |
| `.scratch/management-leadership-wayfinding/issues/04-conversion-policy.md` | [#74: [management-leadership-wayfinding] Agree missing-content policy and category hierarchy behavior](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/74) |
| `.scratch/management-leadership-wayfinding/issues/05-vault-prototype.md` | [#75: [management-leadership-wayfinding] Review the agreed behavior in a representative vault prototype](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/75) |
| `.scratch/management-leadership-wayfinding/issues/06-implementation-specification.md` | [#76: [management-leadership-wayfinding] Agree acceptance checks and publish the implementation specification with to-spec](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/76) |
| `.scratch/management-leadership-wayfinding/issues/07-implementation-tickets.md` | [#77: [management-leadership-wayfinding] Publish the approved implementation breakdown with to-tickets](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/77) |
| `.scratch/management-leadership-wayfinding/map.md` | [#9: [management-leadership-wayfinding] Find the implementation route for the Management & Leadership archive](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/9) |

## Additional migrated records

| Former local path | GitHub comment |
| --- | --- |
| `.scratch/brz-to-obsidian/architecture-layout.md` | [Retained record](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/7#issuecomment-6040209219) |
| `.scratch/brz-to-obsidian-v1/architecture-layout.md` | [Retained record](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/4#issuecomment-6040209746) |
| `.scratch/brz-to-obsidian-v2-implementation/source-feature-mapping.md` | [Retained record](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/5#issuecomment-6040210387) |
| `.scratch/brz-to-obsidian-v2-implementation/ticket-breakdown.md` | [Retained record](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/5#issuecomment-6040211104) |
| `.scratch/management-leadership-implementation/specification-coverage.md` | [Retained record](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/8#issuecomment-6040211805) |
| `.scratch/management-leadership-implementation/ticket-breakdown.md` | [Retained record](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/8#issuecomment-6040212366) |
| `.scratch/brz-to-obsidian/research/archive-inventory.json` | [Retained record](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/7#issuecomment-6040213212) |
