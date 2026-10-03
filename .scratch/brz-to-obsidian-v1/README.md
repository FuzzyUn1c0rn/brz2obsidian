# First-version implementation tickets

Status: resolved

Assignee: /root

Integration branch: `codex/brz-to-obsidian-v1`

The accepted [migration specification](spec.md) and [initial folder layout](architecture-layout.md) now live in this implementation area. The [completed Wayfinder map](../brz-to-obsidian/map.md), its resolved decision tickets, and research remain in their original planning area; these implementation slices are not children of that map.

The user approved this breakdown on 2026-10-03. Each linked implementation ticket was published with Status: ready-for-agent, scope, acceptance checkboxes, specification-story coverage, and test seams. All ten slices and the [final review repair](issues/11-final-review-repairs.md) are now resolved; no implementation frontier remains. Follow the [claim and completion process](../../docs/agents/issue-tracker.md#implementation-operations), [domain vocabulary](../../GLOSSARY.md), and [accepted architecture decision](../../docs/adr/0001-source-neutral-core.md).

No standalone prefactoring was needed: implementation started without a production converter. The first slice established a narrow working path through the reusable modules, library workflow, CLI, and actual vault publication. Later feature slices extended that usable path; the final gates verified the complete first version.

| Slice | Blocked by | Demonstrable result |
| --- | --- | --- |
| [01: Convert a minimal Brain into a fresh vault](issues/01-minimal-brain-vault.md) | None | Install the CLI and reuse its library workflow to inspect and convert a tiny, valid Brain with one plain Markdown Home note into a verified fresh vault. |
| [02: Preserve hierarchy and empty thought targets](issues/02-hierarchy-empty-targets.md) | 01 | Convert a graph Brain into simple linked notes while leaving unnecessary empty thoughts uncreated and materializing only the Home and hierarchy parents that need files. |
| [03: Preserve files and resource references](issues/03-files-resource-references.md) | 01 | Migrate supported archived files, images, decorative icons, note originals, URLs, and external directory references into useful resource links with byte-preserved local assets. |
| [04: Adapt thought and image links without rewriting notes](issues/04-source-note-links.md) | 02, 03 | Convert actual source-local thought and image links into working vault references while preserving all other authored Markdown, code examples, and newline spelling. |
| [05: Preserve tags using native Obsidian features](issues/05-native-tags.md) | 02 | Convert source tag assignments into native vault tags and preserve tag-authored content and otherwise hidden memberships without duplicating Obsidian search. |
| [06: Report known gaps and enforce verified source coverage](issues/06-verified-coverage-source-gaps.md) | 04, 05 | Complete the reviewed source profile so verified Brains convert with precise known-gap warnings and unsupported or unreliable input is refused explicitly. |
| [07: Protect publication against source and I/O failures](issues/07-publication-failure-protection.md) | 01 | Make interrupted, changing-source, and destination-race conversions fail honestly without exposing partial vaults or modifying caller-owned files. |
| [08: Prove reuse with an alternate source](issues/08-alternate-source-reuse.md) | 06, 07 | Run the same generic conversion workflow with a test-only source module from another format, proving that input replacement preserves compatible vault behavior. |
| [09: Verify complete preservation on both real exports](issues/09-real-export-preservation.md) | 06, 07 | Convert the exact two real archives and independently prove complete content, file, graph, identity, and metadata preservation for the agreed first-version coverage. |
| [10: Accept the first version in Obsidian and document usage](issues/10-obsidian-first-version-acceptance.md) | 08, 09 | Review the actual complete converter outputs in standard Obsidian and finish installation, library, CLI, architecture, and testing guidance for first-version use. |

## Working the frontier

Start with the minimal Brain conversion. After that, hierarchy/empty targets, resource preservation, and publication-failure protection can progress independently. Link adaptation joins hierarchy with resource preservation; native tags extend hierarchy. Completing the verified profile joins link and tag behaviors. Alternate-source proof and full real-source preservation can then run independently, after verified coverage and failure protection. Native first-version acceptance waits for both.

Every prerequisite number is local to this new implementation set. Transitive blockers are omitted. No implementation ticket depends on a Wayfinder decision ticket; those decisions are already resolved.

## Coverage and standing constraints

All 73 specification user stories are covered by one or more implementation slices. The original 72 stories retain their numbering; the added virtual-environment requirement is story 73 and belongs to the first ticket. Native dependency compatibility and exact source-span feasibility are early gates, not deferred discoveries at the final review.

Retain strict inward Pydantic contracts, reusable deep modules, the highest practical workflow testing seam, and focused tests at public module interfaces. Use only fresh test vaults, native Obsidian discovery, synthetic checked-in fixtures, and ignored private acceptance inputs/outputs. New formats and unverified meanings remain outside the initial release.

## Environment and bootstrap

The user requires a minimal project Python virtual environment before implementation. Install every runtime, build, and development package only inside it, adding packages gradually when needed. See the [development setup](../../README.md#development-environment) for commands and manifest roles. The first ticket uses that setup to complete package installation and native compatibility gates; environment provisioning alone does not complete its conversion criteria.

## Comments

- 2026-10-04 (/root): The full accepted specification is implemented on `codex/brz-to-obsidian-v1`. All ten implementation tickets and the final review repair are resolved. Final gates: 295 public tests, Ruff lint/format, pip check, complete independent preservation across six exact/repeat/reordered A/B conversions, alternate-source reuse, documented library/CLI examples, and representative native Obsidian 1.13.7 acceptance. Both independent review axes have zero outstanding findings. See [preservation acceptance](research/real-export-acceptance.md), [native acceptance](research/native-acceptance.md), [final review](research/final-review.md), and [usage](../../README.md).
