# 03: Browse categories through rename-safe native dashboards

Status: resolved

Assignee: /root/v2_implement_03

Labels: ready-for-agent

Published: 2026-10-04 after the user approved the 11-slice breakdown and dependencies.

**Specification:** [Version 2 implementation specification](../spec.md)

**Implementation set:** [Version 2 implementation index](../README.md)

**Source-feature comparison:** [Accepted representations and limitations](../source-feature-mapping.md)

**What to build:** Home opens a Categories overview, and category notes embed native Members/Gallery Bases with complete discovery and live icon inheritance.

**Blocked by:** [02: Preserve canonical properties, source dates and editable icon snapshots](02-properties-dates-icon-snapshots.md).

**Specification stories:** 5, 15–20, 23–34, 39, 49–50, 74, 80.

## Acceptance criteria

- [x] Enable/configure the bundled Bases plugin in this slice's generated vault so its dashboards work before template support lands. Include the required native configuration in verified publication and artifact accounting, without requiring a community plugin or copying unrelated reference settings.
- [x] Discover actual memberships through linked category properties and the embedding category identity; a hierarchy/prose/provider link alone is not membership.
- [x] Contextual member queries remain applicable after link-preserving category renames; document that users open member views through the category dashboard rather than a standalone Base without an embedding category.
- [x] Exclude Templates/Attachments support deliberately; keep legitimate Template-named members. The overview uses the category tag and folder role guard and excludes ordinary source tags or same-basename ordinary notes.
- [x] Tables start Icon, Note, Inheritance, categories, created, updated, with deterministic note sorting; the overview starts Icon then Category. Gallery uses native images. The decorative Appearance display is absent.
- [x] Category icon changes update inherited views; member overrides win. Provider reordering/addition does not reselect defaults. Blank opt-out and invalid/dangling/nonmember providers behave as specified, without rewriting body-icon snapshots.
- [x] Every generated Base/embed/overview and its reserved names is included in publication/accounting; original Home content and entry/bookmark behavior remain available.
- [x] Perform an early bounded native check on a converter-produced synthetic vault to confirm contextual query, image and rename behavior. Keep that evidence separate from final full-output acceptance.

## Testing boundaries

Workflow-generated Base/frontmatter/guard fixtures plus the prior prototype's native scenarios repeated on this slice's actual output.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-05 (/root/v2_implement_03): Resolved after [bounded native acceptance](../research/native-category-dashboards.md) on actual converter output in Obsidian 1.13.7. Root's Computer review confirmed contextual member discovery through native rename, table/gallery image behavior, valid overrides, blank/invalid provider controls, deliberate support exclusions, retained Home/identity/body snapshots and unchanged hashes for all 28 baseline files. No production defect or repair was needed. Merged current integration `6cf2014` through `cf7c5fa`, preserving ticket 06's PDF limitation paragraph alongside dashboard guidance; a final merge check was already up to date. Final automatic gate: **445 tests passed in 33.97s**, Ruff check `--no-cache .`, Ruff format `--check .` (86 files), pip check and git diff check passed. The project virtual environment and process worktree/src PYTHONPATH were used, with the imported package path confirmed in this worktree. No root checkout mutation, UI by implementer, editable-install mutation, installation, real-archive acceptance, PR, push or cleanup occurred. Templates/configuration extension, checker, complete archive audits and final user acceptance remain later tickets; root owns the index frontier.

- 2026-10-05 (/root/v2_implement_03): Implemented actual workflow-produced contextual Members/Gallery Bases, guarded Categories overview, preserved Home entry with added overview navigation, native Bases/link-update configuration, support accounting and adaptation records. Public workflow red/green cycles began with missing artifact obligations, then missing icon/provider formulas; expected public output comes from literal accepted contracts and synthetic source facts. The cumulative exact authored-byte/backup/graph/tag checks retain their original preservation assertions, with the explicitly generated Home entry/support files added to expected output. The baseline local acceptance oracle independently accounts for those files and checks native configuration. Initial automated gate: 388 tests passed, Ruff lint and format (75 files), pip check and git diff check passed using the root project virtual environment and process worktree/src PYTHONPATH. Root is reviewing an exact converter-produced synthetic vault with three distinct valid local PNGs on a fresh review copy; the native criterion and final resolution remain pending that evidence and the latest integration merge.

- 2026-10-05 (/root): Claimed after ticket 02 was resolved and merged with independent cumulative checks. The implementer owns generated dashboards and their automatic evidence; root performs the required bounded Computer check on a fresh converter-produced synthetic review copy before resolution.

- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
- 2026-10-04 (/root): Independent documentation validation assigned minimum Bases enablement to this dashboard slice, where the first native Base check requires it. Ticket 04 retains that configuration while adding native Templates. Ticket sizes and blockers are unchanged.
