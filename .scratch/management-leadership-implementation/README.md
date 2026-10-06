# Management & Leadership conversion implementation

Status: claimed
Assignee: /root
Integration branch: `codex/management-leadership-v3`
Production baseline: `9ddba911eb53e589b53d8059141462ee3a274aea`
Final code-review fixed point: `9ddba911eb53e589b53d8059141462ee3a274aea` (user confirmed)
Approved: 2026-10-06

The user approved all nine tickets and their dependencies, then requested a local
branch, a commit of the Wayfinder session's changes and **implement-spec** for
the entire accepted specification. This index tracks implementation toward a
finished, verified 0.3.0 converter; ticket publication is completed planning.

Read the accepted [specification](spec.md), [approved breakdown](ticket-breakdown.md)
and [complete requirement coverage](specification-coverage.md). The completed
[Wayfinder map](../management-leadership-wayfinding/map.md) and its research remain
decision evidence. Follow the [local claim/completion process](../../docs/agents/issue-tracker.md),
root [domain vocabulary](../../GLOSSARY.md), accepted [architecture](../../docs/adr/0001-source-neutral-core.md)
and [workspace housekeeping](../../docs/workspace.md).

## Ticket graph

| Ticket | Direct blockers | Verifiable result |
| --- | --- | --- |
| [01: Exclude forgotten thoughts throughout inspection and conversion](issues/01-forgotten-exclusion.md) | None | Default included-only conversion, safe exact copies/evidence, complete reference/artifact privacy and version-3 public contracts. |
| [02: Display owned images when an ordinary thought note is absent](issues/02-absent-note-images.md) | [01](issues/01-forgotten-exclusion.md) | Visible one/multiple original images, notice A and truthful source-gap diagnostics, with supplied Markdown preserved. |
| [03: Keep category dashboards usable through missing type notes and icons](issues/03-type-source-gaps.md) | [02](issues/02-absent-note-images.md) | Unknown type text/neutral appearance with usable membership, overrides and provider/member diagnostics. |
| [04: Preserve ordinary-to-category hierarchy in both directions](issues/04-category-hierarchy.md) | [01](issues/01-forgotten-exclusion.md) | Reciprocal scoped navigation, category hierarchy before Bases and classification kept separate. |
| [05: Prove the combined conversion and publication guarantees](issues/05-combined-workflow-safety.md) | [03](issues/03-type-source-gaps.md), [04](issues/04-category-hierarchy.md) | Complete mixed public workflow, deterministic output, real publication faults, durable receipts and independent source-free checking. |
| [06: Extend the independent raw-source audit to the new conversion policy](issues/06-independent-audit-tooling.md) | [03](issues/03-type-source-gaps.md), [04](issues/04-category-hierarchy.md) | Raw-source independent oracle/corruption proof and four-input exact/repeat/reorder driver. |
| [07: Audit complete preservation across all four original archives](issues/07-four-archive-preservation.md) | [05](issues/05-combined-workflow-safety.md), [06](issues/06-independent-audit-tooling.md) | Twelve complete audited outputs; all 359 supplied bodies, 63 affected images and 47 definitions/330 members checked by identities/joins/bytes. |
| [08: Verify actual converted vaults in native Obsidian](issues/08-native-obsidian-review.md) | [07](issues/07-four-archive-preservation.md) | Actual-output native rendering, navigation, discovery and maintenance on disposable copies. |
| [09: Deliver the reviewed release after actual-vault user acceptance](issues/09-release-user-acceptance.md) | [08](issues/08-native-obsidian-review.md) | Final independent review, complete tooling/package/examples/guidance and actual user verdict. |

## Working the frontier

Tickets **01: Exclude forgotten thoughts throughout inspection and conversion**,
**02: Display owned images when an ordinary thought note is absent** and
**04: Preserve ordinary-to-category hierarchy in both directions** are resolved
and integrated. The unclaimed frontier is **03: Keep category dashboards usable
through missing type notes and icons**.
Type gaps consume the shared source-gap capability
from ordinary fallback. Combined safety and independent audit tooling can then
progress independently. Complete four-original proof precedes native actual-output
review, final release verification and the actual-vault user verdict.

Claim an eligible ticket before implementation and record its assignee. Use an
isolated managed worktree/branch based on this integration tip for each implementer,
TDD at the user-confirmed public seams, and a merger agent to integrate verified
work. Keep each slice green, including affected existing oracle/version checks.
Resolve only when all criteria have evidence, with exact commits/commands/results
and any limits in Comments. Update this index as the frontier advances.

## Delivery constraints

The original Management & Leadership BRZ alone is mandatory; recovered backups
cannot replace it. All four original archives require complete exact/repeat/reorder
audits. Present Markdown wins, source gaps remain unknown, and generated images
receive no invented original-byte/Document/authored-reference credit. Forgotten
thoughts leave no output artifacts or identifying exclusion ledger.

Use the project virtual environment for all Python tooling. Keep private inputs,
vaults, identities, screenshots and detailed audit receipts ignored. Existing
source-neutral architecture, public workflow/CLI and separate read-only checker
remain the testing boundaries confirmed by the user. Independent raw-source
preservation proof, native actual-output observations and the user's actual-vault
verdict are separate required gates. Source originals and retained user vaults
are never destructive test targets.

Final specification/standards review covers the complete implementation from a
fixed recorded baseline. Repair findings through an isolated implementer, repeat
invalidated proof and archive managed worktrees after their work is safely
integrated. The user requested a pull request when everything is complete; create
it after implementation and required acceptance, then attach it to this chat.

## Comments

- 2026-10-06 (/root/integration_merger): Integrated ticket 02 with
  `git merge --ff-only a6f62b9e37bb193d231cf688e630722fa4f6d06b` from clean
  root `e50a638d16b0137b111bffe1fc7f8f9f0875c0c9`. Independent bounded static
  review, 21 handwritten actual-ZIP control groups and 213 focused tests PASS
  at that exact head. Root merged absent-note image/category/hierarchy/integrated
  v2 and both alternate-source checks pass: **197 tests in 22.54s**; diff check
  is clean. Ticket 02 records exact commands and attributed worker complete
  regression evidence. Ticket 03 is eligible and remains unclaimed; complete
  four-original/native/user/review/release gates remain pending.

- 2026-10-06 (/root/integration_merger): Integrated ticket 04 by
  `git merge --ff-only f42a900563be235aae85da8a047b7ae9a384948e` from clean
  root `a29e8a088d7d288e663dd633a2bd0ca939864a87`. Independent bounded static
  review, ten handwritten actual-ZIP control groups and 63 focused tests PASS
  at that exact head. Root merged category hierarchy/category/dashboard/graph
  and both opaque alternate-source checks pass: **113 tests in 13.34s**;
  diff check is clean. Exact commands and attributed worker 828-test evidence
  are recorded in ticket 04. Ticket 02 remains in progress, with 03 blocked;
  full-source/native/user/release gates remain pending.

- 2026-10-06 (/root): Claimed the two eligible slices after verified ticket 01:
  ordinary absent-note images and reciprocal category hierarchy. Each uses its
  own managed worktree/branch based on this integration tip. Type-gap work remains
  blocked by the image slice; complete-source/native/user gates remain pending.

- 2026-10-06 (/root/integration_merger): Integrated ticket 01 by
  `git merge --ff-only 5fbb5ccf3d4c3cfb02779c25c876ddfa3bb179c3` from clean
  integration baseline `929f2a8735e99b66ee25f45d159b8b3f1d9c0916`.
  Independent bounded behavioral and static repair verification both PASS at
  that exact head; prior failures and replay evidence remain retained under
  ignored `tmp/ml-implementation/01/`. Merged focused forgotten workflow,
  both alternate-source workflows and architecture tests pass: **63 tests in
  10.67s** through the root project environment, with clean diff check.
  See ticket 01 for exact commands and attributed full-suite/package evidence.
  Tickets 02 and 04 are now eligible but remain unclaimed. No full-original,
  native, actual-user acceptance, final review or release gate is completed.

- 2026-10-06 (/root): Before production edits, the integration baseline passes
  all 781 public tests in 125.04 seconds, Ruff check/format on 115 files and pip
  check through the project environment. The first managed worktree is based
  on the integration claim commit; its implementation branch is `codex/ml-v3-01`.
  Public seam approval already recorded in the accepted specification applies
  to TDD. Full-input/native/user acceptance remains pending.

- 2026-10-06 (/root): The user explicitly selected completed v2 `9ddba91` as
  the final code-review fixed point, covering session planning/housekeeping and
  the complete implementation. Record the actual reviewed integration tip at
  that gate; implementation proceeds without further testing-seam approval.

- 2026-10-06 (/root): Committed the complete approved session records and
  workspace conventions as `bb7a5ab6506dce699bb7d8373bf04a25375d5979` on the
  integration branch. Privacy checks found no original record identities in
  published session files across all four inputs. Claimed forgotten exclusion
  for isolated TDD implementation; baseline lint/format/dependencies pass and
  the complete public baseline is running.

- 2026-10-06 (/root): Published the approved nine-ticket graph and coverage after
  the actual user approval. Full implementation is explicitly authorized by the
  subsequent branch/commit/implement-spec request. Initial frontier is forgotten
  exclusion; no migration or release gate is yet claimed complete.
- 2026-10-06 (/root): The user additionally requested a PR when everything is
  done. PR creation follows completed implementation and required acceptance.
