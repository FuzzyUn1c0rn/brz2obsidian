---
status: accepted
---

# Preserve vault edits when applying later source exports

Users continue authoring in Obsidian after importing a Brain, so later source
exports must be reconciled with vault changes. Design for both updates to prior
imports and first imports into existing vaults, delivering updates to
converter-created vaults first. This puts preservation of user edits at the
centre of the first release.

Matching titles from unrelated collections do not establish shared identity:
create separate notes by default, and require an explicit user choice before
combining an imported item with an existing note. The first release supporting
arbitrary vaults defers ordinary-note combination but supports a choice to reuse
existing vault categories, as recorded in
[the import placement decision](0005-keep-imported-collections-distinct.md).

Present proposed changes for review before applying them. Changes established
to be compatible can be proposed automatically; conflicting source and vault
edits require a user decision, with neither side silently winning. Keep a vault
note and flag the disappearance when its source item is absent from a later
archive. Respect a note deleted in the vault rather than automatically
recreating it.

Protect user edits throughout imported notes, including generated relationships,
categories, tags and attachment links. Missing or duplicated source identifiers
require user resolution before updating the affected item; candidate matches may
be suggested. Preserve each note's current vault filename and folder by default,
offering source-driven renames separately for review.

For the first release, finish reviewing the whole update before applying it.
Resolve conflicts by keeping the vault version, accepting the source version or
editing the result; applying compatible changes while deferring unresolved
conflicts is outside that release. If the source of a locally deleted note later
changes, offer explicit restoration while keeping the note deleted by default.
Do not repeatedly offer restoration for an unchanged source item.

Support vaults created before update tracking through explicit onboarding review.
Use trustworthy original generated output when available; otherwise preserve the
current vault and require review of uncertain differences when establishing its
first update baseline. Do not infer an unchanged original from the current vault
or from the migration record alone.

Accept a user-selected archive from the same Brain even when it is older or has
different scope. Present it as the incoming source version, without assuming
chronological order. Missing source items remain subject to the preservation
rule above. Include generated dashboards, templates and guides in the reviewed
proposal with protection for local edits; Obsidian configuration changes require
a distinct choice because they affect the whole vault.

Use the Windows app as the primary conflict-review interface. The CLI supports
inspecting a proposal and applying a fully resolved plan under the same rules,
and reports unresolved conflicts. Allow vault editing during review, then recheck
affected files before application and invalidate stale approvals. Require a brief
pause in editing while applying changes.

For conflicting attachments, offer the vault version, the incoming version or
both. Keeping both preserves the current file at its existing path and assigns
the incoming version a distinct path; review the associated link changes.

Remember a decision to keep the vault version for the reviewed source version,
without repeatedly asking about the same unchanged source content. A later change
to that content is reviewed again. Repeating an archive with the same settings
must not duplicate content, overwrite local edits or manufacture changes from
fresh run identifiers and timestamps. Capture meaningful local changes at the
checkpoint boundary without creating meaningless history entries.

Retain attachments that disappear from the source by default and report their
disappearance. Review changes to imported references separately; removing retained
files requires an explicit cleanup action.

Report unrelated existing vault problems without blocking the operation. Block
new harmful inconsistencies introduced by the proposal and existing problems
that make affected changes unsafe. Distinguish intentionally uncreated targets
and acknowledged source gaps from errors.

Persist proposals and review decisions so review can continue after closing the
application. Tie decisions to the source and vault state reviewed; on reopening,
recheck those inputs and invalidate decisions whose assumptions changed. Applying
still requires the whole update to be resolved.

Allow bulk approval of compatible changes after a summary, with access to
individual comparisons. Conflicts, category/tag mappings and configuration
choices require explicit resolution. Whole-update review does not require
individual approval of every compatible file change.

These choices favour preservation and explicit review over automatic replacement
or mirroring source deletions. They extend the existing one-time migration
scope. Technical validation must establish identity recovery and conflict
detection mechanics within these product constraints.
[Converter-managed update history](0003-converter-managed-update-history.md)
records the direction for managing history, and
[recoverable updates](0004-recover-interrupted-updates-and-review-undo.md)
records interruption and undo behavior. These records establish design constraints,
not an implemented update capability.

The [completed interview](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/240#issuecomment-6297581685)
preserves the full agreed product requirements. The separate
[editable-vault import and update Wayfinder map](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/239)
owns the remaining research, GUI and logic prototypes, specification decisions and
planning handoff.
