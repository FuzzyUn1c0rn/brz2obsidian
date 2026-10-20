# Synthetic category and link prototype

Question: does explicit category reuse and distinct incoming naming produce an
understandable, link-preserving result in a populated vault?

Owner: Wayfinder [#246](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/246),
under [#239](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/239).
Constraints come from the [accepted interview](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/240#issuecomment-6297581685)
and [Obsidian research](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/242#issuecomment-6297641004).
These disposable sources are retained by explicit user request. All content is
synthetic. Production renderer, checker and publication code are untouched.

## Run

From the repository root in PowerShell:

```powershell
.venv\Scripts\python.exe prototypes\editable-vault-wayfinder\categories\generate.py
```

The generator prints its fresh output path under
`tmp/merge-wayfinding/categories/<UTC>-<random>/`. It refuses an existing output
path and any destination outside that scratch root. Optional `--output` must name
a fresh child of that root. It neither opens an app nor contacts a service.

Double-click `demo.html` for the standalone in-memory category walkthrough.
It has three scenario tabs, guided action buttons and free choices. It writes
nothing, loads no external resources and does not read generated vaults. The
HTML explains consequences; the generator supplies exact file artifacts.

## What the generator produces

Each case has:

- `before-vault/` and `proposal-vault/`: exact synthetic snapshots. Every proposal
  awaits review; case 3 is blocked and cannot be treated as an applied update.
- `before-inventory.json` and `proposal-inventory.json`: every path, size and
  SHA-256, including synthetic `.obsidian` settings and attachments.
- `native-before/` and `native-proposal/`: fresh review copies. Native review uses
  explicit synthetic paths through the installed app UI; preserve snapshots.
- `independent-expectations.json`: explicit expected membership lists, tags,
  overview targets, absent targets and source-reference content from the
  separately authored `scenarios.json`, rather than inferring success from
  generated output.
- `static-observations.json`: comparison of actual fixture text to those
  expectations, with each observed/expected value and evidence kind.
- `prior-mappings.json`, `proposed-mappings.json`, `review.json`: illustrative
  source identity and category/tag choices, plus a pending conflict where needed.
  These JSON shapes are planning examples, not an approved persistence contract.

The generator writes hand-authored before/proposal states. It does not implement
an existing-vault importer, merge algorithm, general YAML parser, arbitrary-link
resolver or Obsidian emulator. Its narrow fixture inspection establishes file
bytes, explicit targets and declared memberships. Actual rendered memberships,
resolved links and presentation require the native observations below.

## Three cases

| Case | Controlled difference | Independently expected outcome |
| --- | --- | --- |
| 01 Separate and shared | Share incoming Projects with existing Projects; keep incoming Topics separate from existing Topics. Reuse `reviewed`, keep `atlas/research` distinct from existing `research`. | Shared Projects has Local project and both Atlas notes; existing Topics has only the existing Topic; separate Topics has only incoming Topic. Source Projects prose/attachment remain in a reference note linked to shared Projects. Import overview lists exactly its two used categories. |
| 02 Incompatible dashboard | Existing People has a custom Dataview tag query; incoming membership uses linked `categories`. | Existing People bytes remain unchanged. Existing Ada and incoming Ada are linked members. A separate compatible-view note/Base is proposed with an explicit category target and pending independent review; arbitrary custom-query adaptation is not demonstrated. |
| 03 Rename and remap | Source Projects is renamed Initiatives with the same source identity. Topic was moved and its memberships/prose edited; propose mapping to existing Work. | Identity points to the moved note without duplicating it. Compatible FutureIdea membership/reference/overview links propose Work. The moved note stays byte-identical, with manual favorites and prose. Its membership conflict has `verdict: null`, `apply_allowed: false`; no whole update has been applied. |

The case-3 preimage explicitly models a move and rewritten incoming relationship.
It is not evidence that Obsidian performed an automatic rename or rewrote links.
The prior mapping is keyed by the original source identity; the proposed mapping
keeps that key despite the changed source title.

All cases retain an existing ordinary `Existing/Topic.md`, shortened and qualified
wikilinks, Markdown link, alias display, heading and block link. Incoming ordinary
filenames are `Topic — Atlas.md`, `FutureIdea — Atlas.md` and `Ada — Atlas.md`.
Neither `FutureIdea.md` nor `Plans/FutureIdea.md` is introduced; their existing
links remain intentionally uncreated. Existing category prose, attachments,
overview, templates and settings are preserved byte-for-byte.

This only establishes safety properties of these chosen synthetic filenames.
It does not settle the general naming algorithm, case/Unicode collisions,
arbitrary shortened links, filesystem limitations or plugin behavior.

## Bounded native evidence

Independent reviewer `/root/prototype_review` observed three fresh proposal copies
in installed **Obsidian 1.14.4**, default dark theme, during a **10m19s** batch on
2026-10-20. The coordinator authorized standard **Open folder as vault** with
explicit synthetic paths; a separate app profile was not required. The app
briefly restored a retained vault; only chrome/vault-manager navigation was used
to leave it, with no retained note or settings edits. No retained-vault captures,
community-plugin installation or Sync activation occurred. The earlier proposed
profile-isolation prerequisite and blanket access limit are superseded.

Canonical published evidence is the [independent native report summary](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/246#issuecomment-6299475058).
The full local report and exact source/pre/post inventories are under
`tmp/merge-wayfinding/prototype-review/native-1603b9fd/`. Source reference:
local commit `fc98f9b90afcdc45da916ee48b6966cf7ed9f6fd`; native input copies came
from generator run `tmp/merge-wayfinding/categories/20261020T190242Z-4dc4a41f/`.
The report's `source-inventory.json` and `pre-inventories.json` bind actual inputs;
subsequent documentation edits do not change that observed candidate.

Observed results:

- Shared Projects rendered exactly three expected rows; separate imported Topics
  rendered one. The shortened Topic and relative Markdown heading links reached
  the existing Topic content. Intentional targets stayed visibly unresolved and
  were not created.
- The source-reference note visibly preserved source prose/identity, the shared
  category link and imported attachment link. The import overview displayed
  Projects (shared), Topics (separate) and original-content navigation; its
  separate-category link reached the expected category.
- The proposed compatible People Base rendered exactly the two expected rows.
  Existing People prose and its unexecuted Dataview fence were visible.
- Pending remap rows matched Work/Projects expectations. The moved note retained
  source identity, manual memberships/prose and visible `atlas/research`/`reviewed`
  tag chips; the incoming relationship reached it. This was a hand-authored
  snapshot, with no automatic move, merge or Apply demonstrated.
- All non-`.obsidian` bytes and paths across all six copies stayed identical to
  pre-inventories. Only the three opened proposal copies changed expected
  `.obsidian` serialization/defaults/workspace state. Before copies were unopened
  and fully unchanged.

Unverified observations remain precise: attachment-viewer navigation, native
existing-root-overview presentation, Tag pane interaction, qualified/alias/
explicit-heading/block link clicks, existing Topics native view and native
before-copy comparison. Static bytes, visible links and tag chips establish
different facts. Automatic rename/link rewriting on/off, duplicate-basename
ambiguity, template insertion, arbitrary plugins, Sync/Git recovery and production
import correctness were not established. A further native sample needs a concrete
decision gap; no broad rerun or separate-profile gate is implied.

## Accepted presentation and remaining scope

On **2026-10-20**, after viewing actual source-reference and overview captures,
the user accepted: “an import-specific category overview labels categories as
shared or separate, and incoming category prose/attachments are preserved in a
clearly named source-reference note linked to the shared category”.

Approval covers organization and shown links only. It does not settle exact
typography, duplicate title display, metadata visibility or final naming details.
The HTML remains an explanatory model, and this verdict does not approve all
of #246. The coordinator owns publishing the canonical accepted-presentation
record; the native evidence comment above precedes this narrow verdict.

| ID | Status and requirement | Reference and planned check |
| --- | --- | --- |
| CAT-P2 | **Accepted organization/links:** preserve incoming category prose/attachments in a clearly named source-reference note linked to the shared category. Exact final name, typography and metadata visibility remain open. | Actual `01-source-reference.png` under the native evidence directory; static source prose/attachment bytes and explicit links; future output checks independently assert separate content and links, plus native organization/navigation comparison. Attachment viewer remains unverified. |
| CAT-P3 | **Accepted organization/labels:** the import-specific categories overview labels categories as shared or separate. Exact styling remains open. Import scope and preserving the existing overview are earlier product constraints. | Actual `01-scoped-overview.png`; static exact category link set and preserved existing overview; future output checks assert labels/targets and native navigation. Existing overview native appearance remains unverified. |
| CAT-P1 | **Proposed presentation, reconcile with final GUI:** show each incoming category and its explicit separate/shared destination choice. | Browser/static explanation and native output observed; final mapping UI presentation is not accepted by CAT-P2/P3. |
| CAT-P4 | **Proposed presentation, reconcile route:** explain incompatibility and offer the separately reviewed compatible view. | Native People Base exact rows observed; where the preserved category exposes the additional view remains a material presentation decision. Arbitrary custom-query adaptation stays outside the accepted boundary. |
| CAT-P5 | **Proposed presentation, reconcile with final review UI:** show identity/mapping consequences and block unresolved manual membership conflicts. | Browser block-state and native pending snapshot observed. The illustrative conflict needs no user data-resolution verdict; actual future conflicts require their own review. |
| CAT-P6 | **Proposed presentation, reconcile with final mapping UI:** explain namespace/reuse and remembered tag choices. | Static mappings and native tag chips observed; explanation/discovery UI is not accepted by CAT-P2/P3. |

The remaining material category presentation decision is how users reach and
review a compatible view from an incompatible preserved dashboard; mapping/tag
explanation and conflict presentation should be reconciled with the owning GUI
design, rather than requiring a choice of fictional memberships. The case-3
`verdict: null` models a future user's conflict and is not a pending real-data
approval request. General filename reservation, identity persistence and support
contracts remain specification questions. Initial linked-membership support and
the accepted organization do not need to be reopened.
