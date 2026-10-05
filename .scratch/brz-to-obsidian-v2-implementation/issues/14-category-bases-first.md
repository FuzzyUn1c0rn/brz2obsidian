# 14: Put category Bases first and remove generated introductory images

Status: claimed

Assignee: /root/v2_implement_14

Labels: ready-for-agent

Published: 2026-10-05 from the user's actual converted-vault review feedback.

**Specification:** [Version 2 implementation specification](../spec.md), especially stories 21, 24–33, 46, 49 and 79–82.

**Implementation set:** [Version 2 implementation index](../README.md)

**Blocked by:** [13: Repair final implementation-review findings](13-final-review-repairs.md).

**What to build:** Category notes are navigation dashboards. After their title, show contextual Members and Gallery Bases before retained source labels, authored Markdown, resources and graph navigation. Omit the converter-generated introductory category icon image completely. Keep category icon properties and exact image assets for the overview and inherited/member table/card icons. Ordinary/member notes keep their separately editable body-icon snapshots. Authored images inside source content remain intact below the Bases.

## Acceptance criteria

- [ ] Actual public conversion places Members/Gallery immediately after a category heading, with no generated category body-icon embed. Source labels, authored Markdown/images, resources, dates, identities and graph links remain intact below the Bases; ordinary/member body icons remain unchanged.
- [ ] Migration adaptation evidence accurately describes the resulting presentation, without claiming a category body snapshot that is absent. Neutral icon selections, icon properties, destination eligibility, assets, dynamic inheritance, templates and rename-safe Base behavior remain valid.
- [ ] Update the independent raw-source oracle and meaningful public controls at the already approved workflow/checker boundaries. Prove both new presentation and retained source content, ordinary/member images and icon properties without deriving expectations from production output. Pass cumulative tests, lint/format, dependency/import/version and diff checks through the project virtual environment.
- [ ] Fresh exact/repeat/reordered A/B/C conversions pass independent preservation. Sources and all earlier audited outputs remain pristine; exact differences from the prior accepted presentation are accounted for. Save receipts/proof under new ignored root `brz/v2d/`, without overwriting outputs or edited vaults.
- [ ] Generated/current maintenance guidance and final package examples describe category dashboards consistently. Verify final wheel/examples against the changed implementation, retain proof privately, merge the integration tip and commit a clean isolated branch for merger handoff.
- [ ] Root repeats affected independent review and native checks, safely updates the user's actual reviewed category notes with pre-edit backups and preserved unrelated edits, and records the result. Final ticket 11 separately obtains the user's verdict on this revised actual vault before declaring v2 finished.

## Ownership and testing boundaries

The isolated implementer owns production rendering/planning evidence as needed, affected public tests and independent acceptance expectations, narrow maintenance/testing/source guidance and final package/audit proof, plus this ticket's first five criteria. Root owns spec/index/map, ticket 11, the final criterion, native UI and the actual reviewed vault. The merger owns integration. Do not resolve this ticket before root verifies its final native/review criterion.

Use TDD at the previously user-confirmed public inspect/convert workflow and source-free checker boundaries; focused renderer/source seams remain approved when relevant. Do not ask for seam confirmation again. Keep independent expectations separate from production builders. Read the complete accepted spec/source mapping, glossary/ADR and TDD skill, including tests/mocking guidance. Preserve destination-icon refusal for categories even though their large body image is omitted: their icon remains used by native Bases.

All Python uses root `.venv/Scripts/python.exe` with process-local worktree PYTHONPATH. Do not reinstall/repoint the shared editable installation. No release/schema bump for this unreleased presentation refinement. The implementer is not alone: do not revert others' changes. Root current baseline is `11e0af7e5f722c49b0c7240dd64b29e5da111ed3`; merge the latest integration tip before handoff.

Useful outside context: `C:/Users/stefa/projects/brz2obsidian-agent-notes/v2-ticket-13-outcome.md`, `v2-ticket-13-final-audit.py`, `v2-ticket-13-prepare-audit.py`, `v2-ticket-13-root-checkpoint.md` (historical), `v2-recovery-delivery-ready.md` (delivery history). Latest pristine output is `brz/v2c/`; source paths come from its private operation metadata, not guessed filenames. Final prior packaging proof is `brz/v2-worktree-evidence/ticket-13-final/`; preserve it. Save a complete outside handoff as `v2-ticket-14-outcome.md` with exact scope, red/green evidence, commands/results, audit/package proof and remaining root-owned native acceptance.

## Comments

- 2026-10-05 (/root): The user reviewed the final actual vault and requests removal of introductory images on category notes so the Bases are the primary navigation surface. This direct instruction authorizes the refinement without another design approval. Category metadata/images remain available to Bases; generated category body images are omitted and Bases move before retained source content. Delivery 11 depends on this refinement and renewed actual-vault acceptance; the user has not accepted the revised result yet.
