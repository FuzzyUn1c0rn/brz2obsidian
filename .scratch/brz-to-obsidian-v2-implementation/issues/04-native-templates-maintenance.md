# 04: Create and extend objects with native templates and a maintenance guide

Status: claimed

Assignee: /root/v2_implement_04

Labels: ready-for-agent

Published: 2026-10-04 after the user approved the 11-slice breakdown and dependencies.

**Specification:** [Version 2 implementation specification](../spec.md)

**Implementation set:** [Version 2 implementation index](../README.md)

**Source-feature comparison:** [Accepted representations and limitations](../source-feature-mapping.md)

**What to build:** A user opens the generated vault, selects a full template for a new note, sees it discovered in the dashboard and can add a future category using documented starters.

**Blocked by:** [03: Browse categories through rename-safe native dashboards](03-native-category-dashboards.md).

**Specification stories:** 14, 19–20, 28, 32, 34–50, 74, 79–80.

## Acceptance criteria

- [x] Retain and verify the bundled Bases configuration established by ticket 03; enable/configure bundled Templates, native property types, required Home/link preferences and template-folder/date insertion settings. Account for configuration without copying unrelated reference toggles or requiring community plugins.
- [x] Deliver a generic template and complete templates for the actual categories with linked membership/provider, blank overrides, insertion-date variables and no imported source IDs or invented domain-specific schema.
- [ ] Deliver category-note, member-template and contextual Base starter examples that discover a manually classified future note using the same native mechanisms.
- [x] Document template selection, lookup before creation, meaningful entity links, canonical vocabulary, source versus new identity, existing-note membership editing and explicitly maintained update dates.
- [x] Existing memberships are edited directly; do not ship additive category-only templates or promise native protection against arbitrary full-template scalar overwrites.
- [ ] Native insertion on a new note initializes membership/dates, whereas a membership edit on an existing note preserves its established dates, content, provider and identity. User/agent extension does not depend on folders as the type system or registry fields.
- [x] Document deliberate reference adaptations, dashboard entry points and editable snapshots; prove all support/configuration artifacts are manifested and collision-safe.

## Testing boundaries

Workflow actual template/configuration/starter bytes and a bounded Computer check of native insertion, existing-note property edits and future-category discovery.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-05 (/root/v2_implement_04): Date-token repair cumulative gate passes: 495 tests in 45.60 seconds, Ruff lint/format on 91 files, pip check and git diff --check. The new pristine repaired output has quoted native date variables across every full/generic/category/member starter, current guide warnings and all 29 manifest obligations; original native fixture remains exact. The outside checker supplement now describes the safe quoted final form and treats bounded unquoted reference handling as a separate compatibility decision. Native correction evidence remains pending.

- 2026-10-05 (/root/v2_implement_04): Root's native Books rename updated nine links across five files and preserved discovery, but exposed unquoted date variables becoming nested YAML mappings inside the full template. Added a red-before-green public workflow regression that safely parses every actual generated Markdown template, rewrites membership/provider data and reserializes YAML, then proves literal date tokens survive and still substitute to insertion dates. All full/generic/category/member-starter date tokens now use quoted strings through the existing JSON scalar serializer. This is a deliberate native compatibility adaptation, with the same bundled Templates/manual workflow; body title variables are unchanged. PyYAML is declared as a development dependency and pinned at the already installed 6.0.3 for this regression; ticket 08 may move it to runtime for its actual parser. A new ignored repaired fixture folder was published with 29 verified files without touching the original pristine source/output. Root's additional rename-then-insertion correction gate is pending, so Status remains claimed.

- 2026-10-05 (/root/v2_implement_04): Merged integration 31b0d84. Root reports partial native success for Books/generic template insertion with 2026-10-05 dates, correct picker choices and direct Properties edits retaining the established old dates, paired IDs and provider. The native save normalized three CRLF sequences to LF (179 to 176 body bytes; exact equality after only that replacement); authored text and body image remain unchanged in meaning, while all 29 pristine file hashes/backups remain exact. Guide/usage/native aggregate now document this honest editor behavior. Converter byte-preservation and accepted scope are unchanged. Status remains claimed; root's full native verdict is pending.

- 2026-10-05 (/root/v2_implement_04): Merged current integration 7bef5bc, preserving ticket 07's neutral video facts/presentation/report. Final automatic cumulative gate: 494 tests pass, Ruff lint and format on 91 files pass, pip check and git diff --check pass; imported package location is this worktree's src. Prepared an ignored pristine converter-produced native fixture: two distinct image-bearing categories, three typed members, one with nonempty 2010/2011 source dates and authored CRLF content, six imported notes/five payloads/eighteen support files/29 verified files. Its private manifest records source digest, all file hashes and established-member provider/dates/IDs/body hash. Root's outside checklist covers native full/generic insertion, direct membership add/reorder/nonmember provider control, future handwritten member and adapted full-template/Base extension, plus native rename. Native criteria remain unchecked until root returns evidence.

- 2026-10-05 (/root/v2_implement_04): Automatic template/configuration/support work completed through four public workflow tracers, with red-before-green for full templates, starter/guide behavior and configuration record accounting. The pinned actual kepano core-plugin/templates/types/app configuration and Book/People/Author template → linked note → category → Base/embed chains were inspected at 473697347a0eaac790a6596229c741b3915f3b77. Full category templates reuse assigned safe category stems; generic and member starter keep membership/provider blank, native date variables initialize insertion day, and all new-object templates omit imported IDs. All static/dynamic support is planned, manifested, counted and configuration dictionaries retained explicitly in the migration record. Collision/repeat/reordered output checks cover reserved titles, duplicate/NFC names and long stems. The existing baseline independent auditor was extended for the additional static support/configuration and native view references while preserving corruption controls. Initial cumulative gate: 449 tests, Ruff lint/format (89 files), pip check and git diff --check pass using the root project virtual environment with this worktree's src on PYTHONPATH. Native insertion/existing-note edit/future-category criteria remain pending root's bounded Computer evidence; Status stays claimed. See [template slice evidence](../research/ticket04-templates-maintenance.md).

- 2026-10-05 (/root): Claimed after ticket 03 resolved and integrated at c5881d2, with 445 cumulative tests and its bounded native dashboard/rename check passed. The implementer owns native templates, property/configuration support and maintenance guide. Root owns the bounded native insertion/edit/extension check before resolution.

- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
- 2026-10-04 (/root): Independent documentation validation moved first Bases enablement to ticket 03 so dashboards are independently usable; this slice preserves/verifies it and adds Templates and maintenance configuration. The approved dependencies are unchanged.
