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
- `native-before/` and `native-proposal/`: fresh review copies. Open these copies
  only after the safe native environment is established. Preserve snapshots.
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

## Bounded native observation plan

Decision: whether these explicit choices present shared membership and preserved
source content clearly, and whether these fixture links retain their targets.
Known evidence: exact identities, inventories, bytes and expected members above;
official research leaves ambiguous resolution and actual Base rendering open.

Batch: these three cases only, at most 15 minutes after the isolated workspace is
ready. Each case already includes present-content controls (existing Topic,
Local project, existing Ada and existing Work note). Stop once listed targets
and Base members are observed, or at the first isolation/version/plugin limit.
Do not expand to extra vaults or install plugins. No paid Sync activity.

Native access discovery on 2026-10-20 established that the Computer Use package
`@oai/sky` imports and `sky.list_apps()` works. It returned no Obsidian window.
The pre-existing executable exists at
`C:/Users/stefa/AppData/Local/Obsidian/Obsidian.exe`; its version metadata did not
yield a usable product/file version. No app was launched or activated. The
documented `sky.launch_app` accepts an identifier/path, with no isolated-profile
arguments/environment. Official [URI documentation](https://obsidian.md/help/uri)
and [CLI documentation](https://obsidian.md/help/cli) did not establish an isolated
profile contract. An ordinary launch might restore retained vaults or change
global recent-vault state. Safe isolation was therefore not established; every
native observation remains **unverified**. This is an access/isolation limit,
not a claim that Obsidian is absent or that the native helper failed.

When the coordinator resumes native review:

1. Establish an approved disposable Obsidian profile/environment before launching.
   Do not guess an Electron switch, change retained user preferences, open a
   retained vault or add plugins. If isolation remains unavailable, leave the
   native gate open and use a user-controlled review environment.
2. Within that environment choose **Open folder as vault**, selecting exactly
   the printed case's `native-before/` or `native-proposal/` absolute path.
   Confirm the visible vault path/name before following any note link. Record
   actual Obsidian version, theme, core plugins and automatic-link-update setting.
3. Case 1: open `Existing/Link probes.md` in both copies; observe the shortened
   Topic link and qualified/alias/heading/block/Markdown controls reach the
   existing content. Inspect uncreated links/listings without clicking them.
   Open shared Projects and separate Topics dashboards and compare actual row
   sets to `independent-expectations.json`. Open the source reference and its
   attachment, then the import and existing overviews.
4. Case 2: inspect the existing custom People dashboard, then the proposed
   compatible view. Observe two expected linked members; record unsupported
   custom-query rendering separately. Do not install Dataview or imply that a
   fenced code example proves any plugin behavior.
5. Case 3: inspect the moved note/source identity, unchanged manual membership
   and prose, incoming relationship to the moved note, proposed Work view and
   review JSON. The UI/file snapshot cannot approve the pending conflict. Do not
   simulate Apply or describe its proposal as a completed update.
6. Preserve a native post-interaction inventory/hashes, separating expected
   `.obsidian` workspace/cache writes from note/content differences. Compare to
   the original manifests. Record case/requirement status and exact observations;
   screenshots alone do not prove file preservation or link targets.

Rename/move behavior under automatic-link-update on/off, ambiguous duplicate
basenames, template insertion and full-copy/Sync history are outside this first
batch. They remain unverified; a later batch needs a concrete decision gap.

## Proposed presentation details — awaiting human verdict

These stable IDs are candidates for recording an accepted presentation. None has
been approved, and the HTML is an explanatory model rather than the final app UI.
Native vault appearance needs its own actual Obsidian reference/version/theme.

| Candidate ID | Proposed detail | Evidence/check needed |
| --- | --- | --- |
| CAT-P1 | Show each incoming category's title, separate/shared choice and exact selected vault category. A same-name match does not select sharing automatically. | Demo actions; final UI behavior and user verdict. |
| CAT-P2 | Keep shared category prose unchanged; preserve source category content in a separately named reference note with links to shared category and source attachments. | Case-1/2 static bytes; native reference/attachment presentation; user verdict. |
| CAT-P3 | Import overview lists only categories used by that import and labels shared/separate choices; existing vault overview stays authored. | Static exact link set; native overview navigation and user verdict. |
| CAT-P4 | Explain the incompatible existing dashboard and offer a separate compatible view for its own review. | Case-2 preserved bytes and explicit-target Base; actual rows/native appearance and user verdict. |
| CAT-P5 | Show stable source identity, old/new category target and affected memberships/links; visibly block a whole proposal while a manual membership conflict needs a verdict. | Case-3 JSON/static evidence; final review interactions and user verdict. |
| CAT-P6 | Explain readable source tag namespace versus explicit existing-tag reuse and remember the mapping. | Static tags/mapping examples; native tag view and user verdict. |

Remaining user decisions include whether reference-note names/location and scoped
overview wording are understandable; how a separately reviewed compatible view
should be reached from an incompatible shared category; and the case-3 manual
membership conflict verdict. Those do not reopen the accepted initial
linked-membership boundary. General filename reservation and persistence/support
contracts need specification work after native evidence; this prototype makes no
new product-policy decision.
