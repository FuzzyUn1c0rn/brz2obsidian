# Structured reconciliation evidence for #251

Question: which edits to actual generated notes can be proposed together while
preserving meaning, and where must the converter retain exact vault bytes and
require explicit review? This is a bounded design experiment and evidence replay,
not a production reconciler or a general Markdown/YAML parser.

Open `index.html` directly for the single-file in-memory walkthrough. It exposes
all three input versions, observed output, free-play choices and guided steps.
Its reducer only replays the recorded experiment and illustrative stale-review
state; it does not execute Git, save decisions or publish files. Existing accepted
GUI behavior remains in #244/#246; this evidence viewer claims no new GUI approval.

Replay truthfulness repair after independent review: S17 now displays the actual
note/reference proposal plus exact retained/incoming binary facts. S24 displays
the known reviewed/current notes and their digests, explicitly saying that no
incoming-note merge was exercised. S27 displays all actual Git input versions,
the retained vault result and the separate rejected text-merge candidate. Generic
empty-detail labels are scoped to genuine unknown-original, deleted-note and
source-absent dispositions; omitted replay detail no longer implies those facts.
Replay PASS labels now read the recorded per-case PASS values consistently.
The mechanism, expectations and native evidence are unchanged. Focused static
execution of the page's actual rendering code is retained under
`tmp/merge-wayfinding/followups/structured/replay-repair-rendered.json`, with exact
data/file comparisons in `replay-repair-static.json`; no fresh mechanism/native
run was needed for this display-only repair.

Run the manual experiment from the checkout root:

```powershell
.venv/Scripts/python.exe prototypes/editable-vault-wayfinder/structured-reconciliation/experiment.py
```

Each run writes a fresh directory beneath
`tmp/merge-wayfinding/followups/structured/<UTC>/`, with actual generated files,
source contracts, before-execution expectations, input/result bytes for each
merge case, identity fixtures, results, generated inventory and a case report.
The command uses the actual public `analyze → plan → render` path from `src/`.
The source collection, items, documents and attachments are synthetic. No BRZ or
retained vault is read. The experiment changes no project Git configuration,
index, refs or production source. Its single real Git operation is `merge-file`
against disposable files. No tests, coverage claim or ordinary verification
bundle is introduced; this is manual prototype evidence under the prototype skill.

## Exact observed candidate

Mechanism evidence input: Git prototype frozen commit
`273233fb4020ceb156ed6b3ab33785adcedfdda9`. Incorporated root for this worker:
`codex/editable-vault-wayfinder` at
`b2f9bdf4d24384097ad99911c1f9c30f8d06ba3d`.

Observed final mechanism run:
`tmp/merge-wayfinding/followups/structured/20261021T101626Z/`.
All **27** bounded expected observations pass in **0.485 seconds**. The report
and results bind exact generated paths/hashes and independently authored expected
outcomes. Experiment SHA-256:
`ed0c8ecfa42efa7c3b1aff7c4fa27c87f27cb3124ecbce84c910f508e6619ac4`.
Expected-outcome SHA-256:
`ef8b0f4d06db5b45808f58caa84f05ca34635118ea7634bc33210333b8b53ad4`.
The recorded renderer/input-source hashes remain in `results.json`; the replay
is bound visibly to this run, rather than pretending to perform new merges.

Oracle provenance: `expected.json` was authored before running the experiment.
First preparation failed because the synthetic classification lacked the public
contract's required evidence; adding explicit synthetic OriginalEvidence repaired
the fixture. Next preparation exposed intentionally uncreated empty target notes;
explicit synthetic document bodies made the selected positive target controls
present. These are input-preparation corrections, not observed converter failures.
The initial expected S17/S20 resource folder incorrectly used the asset seed;
static planner ownership rules use item seed `00000011`, so those literal paths
were corrected before the successful run. Initial snapshots remain in earlier
run directories. None of the expected merge dispositions, memberships, prose,
identity decisions or relationship targets was copied from the reconciliation
function. The independent reviewer must assess those semantic expectations.

## Observed reconciliation boundary

Actual input is version-7 imported ordinary-note output: canonical source IDs,
linked `categories`, `appearance_category`, icon/dates/tags/aliases, two prose
paragraphs, Resources, Parents and Related sections. The fixture also generates
real category dashboards, Base definitions, guides/templates/configuration and
all positive link targets. Ordinary-note automatic compatibility is demonstrated
only for the subset below. This does not support combining unrelated ordinary
notes or category-note bodies, arbitrary classification dashboards, format
upgrades or changing category mappings without explicit review.

| Cases | Independently expected meaning | Observed boundary |
|---|---|---|
| S01–S05 | Keep local alias/prose; accept independent source paragraph/property; same-slot divergent edits unresolved | Independent scalar fields and fixed-position plain paragraphs combine; same-slot edits retain exact local bytes and a reason |
| S06–S07 | Projects + local Manual + incoming Topics; overlapping membership removal unresolved | Additive membership proposals retain local order and add incoming links; any removal overlapping a local change requires resolution |
| S08–S09 | Incoming Parent/Other parent and local Peer/Local peer survive; same-section deletion conflicts | Separate generated sections combine; concurrent divergent changes within one section are conservatively unresolved |
| S10, S26 | Independent resource change and local prose combine; divergent resource-target edits conflict | Resources is an atomic reviewed section in this bounded model |
| S11–S12, S19 | Unknown YAML, ambiguous heading ownership and non-UTF-8 changed content stay unresolved | No YAML anchors/merge keys, duplicate keys, arbitrary nested values, fences, source heading collisions or encoding conversion is claimed |
| S13–S16 | Unique moved identity keeps Reading path; absent/duplicate identity needs resolution; unknown original needs onboarding | Actual identity fixture bytes and inventories drive unique-path selection; titles never establish identity |
| S17 | Exact local binary at its current path, exact incoming binary at a distinct path; explicit reviewed reference change | Actual binary files and note link bytes are written/read; no automatic binary merge or invented original bytes |
| S18, S20–S24 | Preserve unsupported local edits if source unchanged; retain source-absent note; keep local deletion; changed-source restoration review; no-op; stale review | Pure disposition/byte-digest observations, not persisted application/restart evidence |
| S25 | Source relationship resolves to uniquely moved Peer path and retains display label | Only the known generated relationship slot is retargeted; local prose links are not globally rewritten |
| S27 | Clean text merge must not publish duplicate YAML keys | Actual `git merge-file -p vault.md base.md incoming.md` exits **0**, creates two `priority` keys; canonical parser rejects it as unresolved |

The S27 counterexample is substantive: Git's syntactic success does not prove
valid frontmatter or preservation of note meaning. Its actual three files and
merged result are retained under `git-clean-duplicate-key/`.

Every unresolved parse/merge fixture retains the exact current vault bytes;
the original and incoming bytes remain separate comparison inputs. Membership
checks use literal expected sets; relationship/resource checks independently
extract exact target paths; prose expectations are literal independently chosen
phrases. This checks meaning beyond a successful merge exit code. It does not
establish arbitrary Markdown interpretation: position-based paragraphs with
stable counts are a deliberately narrow proof, and ambiguous segmentation must
return unresolved. A production candidate must establish stronger edit alignment
before broadening that subset.

## Recommendations for #247 contracts

1. Reconciliation input identifies source collection/item, known source-output
   baseline bytes and output-format/profile version, current note bytes/path,
   incoming bytes, stable item/resource assignments, and already reviewed mapping
   choices. A baseline digest without validated reachable original bytes is unknown.
   Configuration/format upgrades and new category mappings remain distinct reviews.
2. Identity association precedes affected changes. Return uniquely associated
   current path, identity-resolution with candidates, or missing/deleted disposition.
   Missing/duplicate identifiers cannot authorize guessed replacement. The inventory
   must distinguish malformed/duplicated identity properties and preserve unknown
   facts; the tiny canonical regex inventory is not that complete production parser.
3. Return `no-op`, `preserve-vault`, `proposed-compatible`, or explicit unresolved
   alternatives with the exact retained bytes and provenance for each changed
   property, prose span, relationship/resource slot and target identity. Return
   onboarding/restoration/source-absence dispositions separately. Proposal is never
   application permission. A whole-update unresolved choice blocks all publication.
4. Establish structural ownership from validated baseline/source metadata and a
   supported format interpretation. A heading alone cannot identify generated
   content. Reject uncertain structure conservatively; keep both inputs available
   for a user-edited result. Identical source bytes permit byte-preserving local
   content without parsing/normalizing it. This fallback is preservation, not refusal
   of the entire vault or an assertion that all Markdown must be auto-mergeable.
5. Merge membership only within the accepted linked convention and already reviewed
   mapping. Additions may be compatible; local removals/remaps overlapping source
   changes need explicit resolution. Preserve unrelated manual memberships and
   `appearance_category` independently. Reusing a category combines membership,
   retaining its source prose/attachments in a separate imported reference note.
6. Validate the full proposed target assignment and resource bytes. Existing link
   meanings, intentional uncreated targets and known source gaps are separate facts.
   A retarget changes meaning and must be reported explicitly with old/new identity,
   path and display text; do not globally replace matching prose. Keep-both preserves
   the current file path and allocates a collision-checked distinct incoming path;
   include each associated reference change in the review.
7. Independently verify the proposed structure and meaning after merge, including
   unique properties/identities, exact membership and target assignment, fragment
   ownership where present and unchanged unrelated content. Unsupported/ambiguous
   results stay unresolved regardless of text-merge status. Source-neutral decisions
   belong in the pure core; Obsidian interpretation, Git and filesystem operations
   remain outer responsibilities under ADR 0001 and accepted #243 testing decisions.
8. Bind review choices to actual source content, profile/format, current affected
   bytes/path, mapping/link dependencies and history generation. Recheck before
   publication. Remember keep-vault for that source version only; a later changed
   source needs review. Reuse #244's actual Git/filesystem preservation/restart
   evidence where applicable; this prototype adds no durable review, apply, recovery
   or Undo implementation. Older/scoped incoming archives do not authorize deletion.

No observed result contradicts accepted #240/#243/#248 policy. Conservative
unresolved output for unknown structure preserves the accepted user-edit path;
it is not a proposal to remove automatic compatible-change support. The automatic
subset above is demonstrated, while a broader parser/alignment policy remains
an implementation specification and acceptance responsibility.

## P01–P14 traceability and limits

| Requirement | Evidence here | What this does not establish |
|---|---|---|
| P01 source-only changes / unrelated authored preservation | S01/S04/S10 independent incoming changes; original input retained; native content inventory unchanged | Whole-vault publication/checkpoint preservation belongs to #244 mechanism and representative-scale work |
| P02 vault-only edits throughout generated sections | S02/S08/S18 local prose/property/relationship preservation | Arbitrary authored YAML/Markdown merge beyond unchanged-source byte preservation |
| P03 compatible proposals / explicit conflicts | S01–S12/S26/S27 dispositions and exact preserved bytes | User resolution UI acceptance or whole-update publication enforcement |
| P04 moved/missing/duplicate identity | S13–S15 actual canonical identity fixtures; S25 generated target retarget; selected native moved Topic/Peer | Production containment/collision/race checks; full identity recovery algorithm |
| P05 source absence / retained attachments | S20 pure preserve disposition; S17 retained exact binary path | Complete source inventory reconciliation/publication; absent resources remain separate reference review |
| P06 local deletion / changed-source restoration | S21–S22 pure dispositions | Persisted restoration suppression/history and actual restored file application |
| P07 repeat-input no-op | S23 pure byte equality no-op | All volatile generated support files/timestamps/settings, or meaningful Git checkpoint suppression; use #244 evidence and future format contract |
| P08 remember keep-vault / new-source review | Recommendation 8 only; original #244 evidence remains applicable | No persisted decision-memory implementation here |
| P09 binary vault/incoming/both + reviewed links | S17 exact files/paths/reference diff; S26 resource conflict; native href and app dispatch observed | Binary content viewer observation; scale/cost; all attachment formats; actual update transaction |
| P10 stale review | S24 actual affected-byte digest difference; illustrative replay | Fresh-process/persisted stale protection and publication race prevention |
| P11 saved review/whole update | Recommendation 3/8; replay explicitly remains review-required | Save/resume/application are in #244; not implemented here |
| P12 unknown original never inferred | S16 returns onboarding-review, exact local bytes kept | History restore/onboarding persistence (separate follow-up owner) |
| P13 harmful inconsistency versus known absence | S27 structural duplicate blocked; selected links resolve to literal expected identities | Complete vault-wide harmful-change checks, heading/block/alias/Markdown link resolution and existing problem classification |
| P14 incoming older/scoped versions | S20 retains content; no date/chronology comparison in decision; recommendation 8 | No actual older BRZ or complete scope comparison run |

## Native observation, 2026-10-21

Question: do selected real generated output links identify the moved note/peer and
explicit incoming resource target? Plan sent to coordinator before launch; native
ownership was serialized to this worker. One fresh synthetic copy, four navigation
operations (moved Topic, moved Peer, back, resource), no expansion. Setup/inspection
completed within the ten-minute bound; input ended before 10:21:32 UTC.

Selected copy:
`tmp/merge-wayfinding/followups/structured/20261021T101626Z/native-copy/`.
`native-pre-inventory.json` records every path/hash before opening, and the post
inventory/comparison records every later change. Actual installed Obsidian
**1.14.4**, normal Windows scaling unchanged, default dark rendering, no theme or
snippet installed. Standard native Open folder as vault was used. On launch the
app briefly reopened the retained vault; only command-palette/vault-manager chrome
was used to leave it. No retained content editing/settings interaction or retained
vault screenshot was saved. A state read incidentally exposed its active content;
that content is not copied into these artifacts.

Observed on actual rendered output:

- START's `Reading/Topic moved.md` link opened the moved file, with source pair
  `structured-synthetic/topic`, the literal Incoming first paragraph and Local
  alias visible. `native-moved.png` records these facts.
- The generated Related link's actual target was `Reading/Peer moved.md`.
  Following it opened that path and displayed source pair
  `structured-synthetic/peer`. `native-links.png` / `native-peer.png` record the
  generated link context and reached identity. This observes a reviewed synthetic
  proposal; it does not demonstrate native automatic renaming or auto-rewriting.
- Resources displayed `report.txt` with actual target
  `Attachments/a1/report-incoming.txt`, while the distinct retained control stayed
  at `Attachments/00000011/report.txt`. Following it dispatched the Windows .txt
  app chooser. It was dismissed without choosing an app or changing associations.
  Native target href/dispatch is observed; the attachment viewer and its content
  remain **unverified**. `native-resource-app-choice.png` records this limit.
- All non-`.obsidian` bytes/paths remained identical. Only app/appearance/core-plugin
  serialization and new workspace state changed. Core plugins were normalized by
  Obsidian to its defaults, including a `sync` core-plugin flag; no account/Sync
  activation, configuration UI change or community-plugin installation occurred.

Existing category evidence
`tmp/merge-wayfinding/prototype-review/native-1603b9fd/native-review.md` establishes
equivalent linked-membership behavior and moved-note navigation in Obsidian
1.14.4. The human accepted CAT-P2/P3 on #246. It is reusable for those exact
conventions/accepted source-reference and overview decisions. This run did not
open its new Projects Base or verify its exact row set natively; those are not
claimed passed from older fixtures. No new category-body integration or dashboard
ownership policy is inferred.

Precise remaining native gate: production acceptance must independently check its
actual generated/reconciled selected target assignment and membership views in the
supported Obsidian context; this sample proves only the moved ordinary/relationship
targets and resource href/dispatch. Opening a selected attachment in its viewer
and observing new Base rows remain unverified if required by the owning scope.
Heading/block/alias/Markdown-link retargeting, arbitrary encodings, plugin/Sync
behavior and native automatic moves remain outside this experiment. The separate
independent-review gate for #251 remains open until the coordinator assigns a
different actor to these exact sources, expectations and conclusions.
