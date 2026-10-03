# Disposable vault trial: artifact and native app checks

Date: 2026-10-03. Status: human accepted the representation with a root-level Home addition; native checks and source Home verification complete.
Question: does the [chosen vault model](../issues/03-vault-model.md) preserve usable content and hierarchy in standard Obsidian?
Ticket: [Validate the proposed vault in Obsidian](../issues/04-vault-trial.md).

## Local artifacts

- [Review Vault guide](</C:/Users/stefa/projects/brz2obsidian/brz/prototype-vaults-r1/Review Vault/START HERE.md>): a representative real-data slice from both inspected archives, with a few synthetic cases.
- [UI Checks guide](</C:/Users/stefa/projects/brz2obsidian/brz/prototype-vaults-r1/UI Checks/START HERE.md>): synthetic native-app checks.
- [Prototype documentation](</C:/Users/stefa/.codex/worktrees/vault-prototype/brz2obsidian/.scratch/brz-to-obsidian/prototype/README.md>): build commands, feature coverage, shortcuts, and source comparison.
- [Synthetic inline-image screenshot](</C:/Users/stefa/projects/brz2obsidian/brz/prototype-vaults-r1/ui-evidence/native-inline-image.jpg>): captured in the native Obsidian test vault.
- [Home Checks entry note](</C:/Users/stefa/projects/brz2obsidian/brz/prototype-vaults-r1/Home Checks/Home — Entry thought.md>): separate synthetic vault used to verify the accepted root-level Home behavior.
- [Home graph screenshot](</C:/Users/stefa/projects/brz2obsidian/brz/prototype-vaults-r1/ui-evidence/home-native-graph.jpg>): native graph with the identifiable Home filename and linked uncreated child.

All generated private content remains under the primary repository's ignored `brz/` directory. This report uses aggregate counts and synthetic names. The throwaway code lives in the managed worktree `C:\Users\stefa\.codex\worktrees\vault-prototype\brz2obsidian` on `codex/vault-prototype`; its capture commit is linked from the prototype ticket. No existing user vault was used for testing.

## Artifact comparison

The Review Vault contains 16 real thought notes (A: 9; B: 7), including two parent-note exceptions, plus two synthetic thought notes. Its recorded slice has 69 uncreated real targets. Many are boundaries of this deliberately small slice and have content in the source; their absence is not the proposed behavior of a full conversion. The JSON identifies eligibility and boundary state.

Independent read-only comparison passed for:

| Measure | Result |
| --- | ---: |
| Copied resources byte-identical to archive members | 21 |
| Copied resource bytes | 57,237,601 |
| Resource extensions in source | 13 Markdown, 4 PDF, 3 PNG, 1 WebP |
| Real thought records matching their sources | 85 |
| Retained original source-note texts matching their sources | 13 |
| Unique reserved targets across both source Brains | 133 |
| Embedded thought links adapted | 20 |
| Inline local image references adapted | 2 |
| Selected absent type-15 TXT payload records explicitly retained | 4 |
| System thoughts / relationships retained only in JSON | 1 / 11 |

The selected absent children and tagged absent member have no file. The empty duplicate-title target remains uncreated and distinct from its materialized namesake. Forty-four complete source tag-membership relationship records are retained. Raw original Markdown bytes use `.md.original` under Attachments to avoid introducing duplicate active notes.

The comparison ran with Windows Python 3.14.8. To repeat it locally from the repository root, use the project environment and the retained throwaway worktree:

```powershell
.\.venv\Scripts\python.exe -B 'C:\Users\stefa\.codex\worktrees\vault-prototype\brz2obsidian\.scratch\brz-to-obsidian\prototype\check_trial_inventory.py' --source-root 'C:\Users\stefa\projects\brz2obsidian' --vault 'C:\Users\stefa\projects\brz2obsidian\brz\prototype-vaults-r1\Review Vault'
```

This comparison establishes artifact/source correspondence. It does not establish rendering fidelity or human usability.

## Native Obsidian observations

The user opened the fresh UI Checks vault and authorized continued app checks. Obsidian 1.13.7 was observed in its window title and Settings. These checks used the built-in UI through the Computer Use plugin; no community plugin or custom navigation UI was involved.

| Check | Observed result |
| --- | --- |
| Qualified missing link from a note under Notes | Clicking `[[Notes/Empty qualified]]` created `Notes/Empty qualified.md`, a zero-byte file. An existing `Other/Empty qualified.md` did not capture the link. No nested Notes/Notes directory was created. |
| Alias and location override | With the test vault's default new-note location temporarily set to the vault root, clicking `[[Notes/Aliased empty\|Original absent label]]` created `Notes/Aliased empty.md`, a zero-byte file. The alias displayed the intended label; no root-level target or doubled Notes folder appeared. |
| Native backlinks | The created qualified target showed one backlink. The built-in Backlinks pane identified Path checks and its link context; following that backlink returned to the source note. |
| Empty hierarchy chain | Empty chain B had readable Parents and Children sections linking to A and C. A and C remained uncreated. The single existing middle note carried both relationships. |
| Native graph and uncreated targets | With Existing files only disabled, the global graph displayed uncreated targets. Enabling it hid those targets. The option was restored to disabled; `hideUnresolved` is false. |
| Native tags and search | Clicking the native archive-label tag ran `tag:#archive-label` search and found the tagged Multi-parent child note and Tag memberships listing. Memberships for uncreated targets remain readable in that listing; there is no absent file on which to store native properties. |
| Inline synthetic PNG | Live Preview rendered the synthetic gradient PNG inline. Resources links to the synthetic text file and external fixture URL were visible. |
| Real source PNG and WebP | Guided cases in Review Vault rendered their original PNG and WebP images inline. The WebP case also showed source headings, italic text, and paragraphs beneath its original title. |
| Real source PDF | Following the Resources link opened the archived PDF in Obsidian's native viewer. Its first page rendered, and the viewer reported five pages. The separate absent type-15 TXT record did not prevent access to the complete PDF. |

The UI Checks generation record describes its initial state (13 synthetic thought files, 10 uncreated targets). Native clicks subsequently created the two zero-byte files above, leaving eight of those targets absent. This is intentional trial history; the generation record was not rewritten after clicks.

The test vault's default new-note location was restored through Settings to the specified `Notes` folder, confirmed in the UI and `.obsidian/app.json`. Graph arrows remain off. Review Vault settings were not changed. No external URL or directory reference was opened during these checks.

## Native features and generated meaning

The user's instruction to rely on Obsidian's existing UI is a design constraint. Native Backlinks, Graph, tag search, ordinary search, and navigation provide discovery. Do not generate a custom backlinks index, graph browser, or tag-search replacement.

Parents and Children sections carry source hierarchy meaning that an ordinary untyped backlink cannot identify. Related remains the accepted simple connection section. The small tag/fallback listings hold source memberships, isolated empty targets, or relationships with no endpoint note in which to store them; they are not general navigation indexes. Raw directional fields remain in JSON without extra arrow navigation in everyday notes.

## Human verdict and limits

The user reviewed the prototype and said it looks quite good. The remaining concern was a clearly identifiable source Home thought. They accepted always materializing that thought, naming its file `Home — <original thought name>.md`, and supplying a native Home bookmark and startup selection. During the native trial they explicitly requested that file at the vault root alongside START HERE, rather than under Notes. These decisions are recorded in the prototype ticket.

Qualified links, click-to-create, backlinks, graph visibility, native tag search, synthetic and real inline images, and a real PDF Resources link have direct app evidence. The real-resource checks establish rendering for the selected PNG/WebP and PDF first page, not every source note or every PDF page. The user's positive review and byte preservation do not establish untested visual fidelity.

The builder is deliberately bound to the two inspected fingerprints and observed inline syntax. Naming details, deterministic full-graph parent selection, complete Markdown adaptation, output failure behavior, and any generated vault settings remain conversion-contract decisions. This is not a production converter or a complete migration.

## Native Home checks

The separate synthetic Home Checks vault tested the accepted presentation in Obsidian 1.13.7. The Home source thought has empty content; its designated entry role forces a concrete note. Its empty child remains an uncreated target.

| Check | Observed result |
| --- | --- |
| Root location | `Home — Entry thought.md` is beside START HERE. Its original heading is Entry thought, with ordinary Children links. Moving it through Obsidian updated the two incoming links and the native bookmark. |
| Native bookmark | The Home bookmark opens the root-level file from Elsewhere. `.obsidian/bookmarks.json` records a file item with that path and title Home. |
| Native startup | Files and links → Default file to open was set to the specific Home file. With Elsewhere last active, closing only this test-vault window and reopening the vault opened Home. `.obsidian/app.json` records `openBehavior: "file:Home — Entry thought.md"`. |
| Native graph | The graph visibly labels the node Home — Entry thought and displays its links, including the uncreated child. No new hierarchy edge or custom navigation feature is introduced. |

`build_home_trial.py` reproduces the observed native settings in a fresh synthetic vault. A separate Home Reproduction directory captures that configuration without resetting the UI-tested Home Checks vault. The settings are evidence for the observed Obsidian version, not a claim about a documented cross-version configuration API.

Source identity is a separate prerequisite. In the synthetic CONTROLLED_EXPORT Brain, the initial Home action returned to PARENT after navigating to CHILD. The user then set CHILD as Home. The root activated PEER, verified it active, and exported a new Brain Archive through TheBrain 15's native UI to the project `brz` folder. The generated dated export was renamed to `brz/controlled-home-child.brz`; its 6,976 bytes have SHA-256 `aa29d7aa0afb687f8b4ffdd490220c3c2e198c729681083fe5065b3bb55dfbf0`. The original fixture's fingerprint remains unchanged.

After exporting, clicking Home selected CHILD; the Home tooltip read CHILD, with PARENT still visibly above it. [Synthetic TheBrain screenshot](</C:/Users/stefa/projects/brz2obsidian/brz/prototype-vaults-r1/ui-evidence/thebrain-changed-home.jpg>) captures this observation. The [research comparison](home-thought.md) passed: only numeric setting 20 changed Value, from PARENT's UUID to CHILD's, and PEER was uniquely latest activated in the export. This verifies Home designation independently of activation and parentlessness for the inspected format. Neither a particular title nor graph topology is used to guess source Home identity.
