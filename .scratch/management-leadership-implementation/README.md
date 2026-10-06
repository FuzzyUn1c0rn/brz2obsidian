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

Tickets **01–08** are resolved and integrated. Complete original-input
preservation passed the fresh m5 twelve-output matrix and separate independent
raw-source verification at frozen runtime `e2c5fc3f05d2daa0d0547d2bbaa2b12557a248b5`.
The prior m3/m4 failures remain retained history; verified source/oracle TXT and
diagnostic-link repairs precede m5. Actual-output native review passed strategic
samples in observed Obsidian 1.14.4, with independent source/CSV/ledger/checker
evidence and retained complete automated preservation. **09: Deliver the reviewed
release after actual-vault user acceptance** remains claimed by
`/root/release_documenter`. Only the public-guidance criterion remains checked.
Spec review at `5f971b96500a33d58ec09f4d9bd6c2d08f9a8cde` reported zero actionable
findings. Standards initially reported zero documented-rule breaches and an
optional P3 duplication observation; later clarification confirmed a material P2
compact-reference validation bypass. Its isolated repair at
`fc1685aaea691bff47fa47408d37c78b7188f94c` passed separate bounded verification
before integration. The pre-repair full-suite/package and m5/native results remain
historical evidence. Fresh complete public/package gates, the four-original
matrix/re-audit and comparison of native-facing bytes are pending; equivalent
strategic native observations can be reused only after that comparison. Final
review closure, the actual-vault user verdict, preserved-input guards and
aggregate delivery also remain pending.
Neither automated nor agent native review supplies user acceptance or arbitrary
representation coverage; no delivery or publication is declared.

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

- 2026-10-06 (/root/native_vault_reviewer, separate merger): Integrated the
  independently verified P2 repair candidate
  `fc1685aaea691bff47fa47408d37c78b7188f94c` with
  `git merge --ff-only fc1685aaea691bff47fa47408d37c78b7188f94c` from clean root
  `5f971b96500a33d58ec09f4d9bd6c2d08f9a8cde`. Exact worker HEAD/clean status,
  root HEAD/clean status and ancestry exit 0 were confirmed; candidate diff check
  passed. Five candidate files cover the source-local compact-reference validation
  repair, public workflow regressions and truthful release/ticket metadata.
  Separate ignored root `tmp/ml-implementation/09/repair-independent/report.md`
  and `independent-proof.json` record PASS for 13 synthetic controls and 35 public
  inspect/convert operations, private malformed-reference refusal, unchanged
  sources/caller inventories and valid compact/literal controls. Spec's zero
  finding review remains separate from the confirmed Standards P2 and its repair.
  Ticket 09 stays claimed, with only guidance checked and invalidated final
  technical proofs reopened. No suite, matrix, package, UI, environment or
  additional runtime/source change was performed by this merger. Fresh gates,
  affected native comparison/refresh, user verdict and delivery remain pending.

- 2026-10-06 (/root/integration_merger): Integrated **partial ticket 09** candidate
  `7a18c6bfb02af35c51662376e41308aa167339ea` using
  `git merge --ff-only 7a18c6bfb02af35c51662376e41308aa167339ea` from clean
  root `d057533b1025d2d68ef90ec989dfb52cd3abeb68`, with clean exact worker and
  ancestry exit 0. Seven public guidance/evidence files only; baseline diff check
  and `git diff --exit-code d057533b1025d2d68ef90ec989dfb52cd3abeb68 7a18c6bfb02af35c51662376e41308aa167339ea -- src tests pyproject.toml requirements.txt`
  pass, confirming runtime/tests/dependency/build inputs unchanged.

  Reviewed public diff/UTF-8 evidence against ignored root 09
  `partial-candidate-independent.json` bounded PASS. Initial `685746b` punctuation
  corruption and unqualified byte-preservation wording were repaired; candidate
  preserves actual UTF-8 and limits dependency proof to 1,741 non-bytecode files.
  Independent receipt corroboration covers 57 exact wheel runtime modules plus
  RECORD/metadata, 18 actual operations, three source and three truly wheel-bound
  literal conversions, physical 36-file/two-embed receipts and 136 unchanged
  regression inputs. Attributed full gate is 1,508 tests in 293.16s, Ruff on 133
  files and pip PASS; first snapshot was captured during execution. Root editable
  metadata refresh to 0.3.0 retained its separate binding/dependency/runtime proof.
  No suite/matrix/package/checker/native/environment rerun was needed for this
  docs-only integration. Ticket 09 remains **claimed**, only three proven criteria
  checked; independent final review, user verdict, final source guards and delivery
  remain open. Source/native evidence remains valid because code is unchanged.

- 2026-10-06 (/root/integration_merger): Integrated independently verified native
  evidence candidate `7cb3ed2510d272a3fa269963caa3f30c389557f5` using
  `git merge --ff-only 7cb3ed2510d272a3fa269963caa3f30c389557f5` from clean
  root `6cb5f75daa0ec048d4c95e82f8d4499ad918a1fe`; clean exact worker and
  ancestry exit 0 confirmed. Four public evidence/guidance files only;
  `git diff --exit-code 6cb5f75daa0ec048d4c95e82f8d4499ad918a1fe 7cb3ed2510d272a3fa269963caa3f30c389557f5 -- src tests pyproject.toml requirements.txt`
  returned 0, and baseline diff check passed. No runtime regression, matrix,
  checker, package, environment or UI rerun was needed for this docs-only merge.

  Reviewed aggregate report/ticket/guidance against root ignored
  `tmp/ml-implementation/08/native-evidence-7cb3ed25/verify/final-candidate-independent.json`
  bounded PASS. Independent retained-inventory/maintenance joins support native
  review observations, source-bound handoff, actual C145 CSV and D47/330 ledger,
  template/provider/rename cases and 45 read-only checker operations. Strategic
  rendering samples extrapolate equivalent cases; full source/body/image audits
  remain ticket 07 evidence. Observed app 1.14.4 differs from declared/stored
  1.13.7; the optional Obsidian CLI stayed disabled. Sole UI reviewer observations
  support pixel/rendering claims; helper verification did not repeat them.
  Four originals, 562 retained files, audited outputs and clean user-copy guard
  remain preserved. Ticket 08 is resolved; 09 eligible/unclaimed with actual user
  verdict, cumulative review and release gates pending. No delivery declaration.

- 2026-10-06 (/root): The user requested strategic native/visual sampling during
  ticket 08 and made this the future repository default. Recorded the policy in
  AGENTS/testing guidance and reconciled accepted testing decision 18, ticket 08
  and its planning pointers. Explicitly observe distinct behaviors and special
  cases, reuse completed evidence and record sampling limits. Full source audits
  and the actual user verdict remain required. All 47 D category contexts and 330
  memberships had already been observed; remaining native cases use sampling.

- 2026-10-06 (/root/integration_merger): Integrated complete ticket 07 metadata
  by `git merge --ff-only c95f23e749f5cbf2bf0aebf1372817a8e3c47e26` from
  clean root `e2c5fc3f05d2daa0d0547d2bbaa2b12557a248b5`, clean worker/exact
  candidate and ancestry exit 0 confirmed. Exact delta contains only ticket 07,
  aggregate preservation research and the narrow private-original testing section.
  `git diff --exit-code e2c5fc3f05d2daa0d0547d2bbaa2b12557a248b5 c95f23e749f5cbf2bf0aebf1372817a8e3c47e26 -- src tests pyproject.toml requirements.txt`
  returned 0: runtime/tests/config remain identical to the verified matrix code.
  Baseline diff check passes. No redundant regression/package/environment/native
  work was run for this evidence-only integration.

  Reviewed aggregate/document bindings against ignored root 07
  `m5-gate-summary.json`, `verifier-report-m5.json`,
  `verifier-m5-handoff-report.json`, `m5-supplementary-checks.json` and
  `m5-public-privacy-scan.json`. Driver exit 0 and separate independent PASS bind
  all twelve outputs, four raw reorder multiset/payload proofs and eight vault
  comparisons to frozen runtime. Twenty-four supplementary library/CLI operations
  are clean/read-only. All 7,029 matrix files, four originals and 562 retained
  files remain unchanged. Original D verifies 359 bodies/63 embeds/47 definitions/
  330 members/1,017 payloads/1,552 files/93 warnings by full source joins, not
  totals alone. Independent native-handoff joins also PASS without GUI inference.
  Public three-document canonical source-identity scan PASS with zero matches;
  aggregate-only manual review and an additional UUID search of ticket/research
  found no private subjects/assets. m3/m4 FAIL histories remain retained.
  Ticket 07 is resolved; 08 is eligible and unclaimed, 09 remains blocked.

- 2026-10-06 (/root/integration_merger): Integrated diagnostic-link repair by
  `git merge --ff-only 30beacbdcdd6ee4c8d827db954b273f1d8958cef` from clean
  root `43bd85ae5716b738622503969506fdace632643e`; exact clean worker/ancestry
  confirmed. Final delta from independent CODE `a433040a87e50584447bbb62c013b9b6139cd746`
  is only ticket 02 metadata. Bounded independent PASS covers 21 unique handwritten
  and 291 maintained controls; root affected gap/image/type/architecture tests
  pass **254 in 31.18s**, diff check clean. Ticket 02 is resolved; ticket 07
  remains eligible/claimed with all criteria unchecked. Historical matrix FAIL
  evidence is retained. Full matrix/native/user/final release gates remain open.

- 2026-10-06 (/root/integration_merger): Integrated repaired reopened 06 with
  `git merge --ff-only 40669c807372c5463de279a3842d55a12f497f0e` from clean
  root `098fe473cd5ad44dc3ea1d6564fde958a9665ef6`. Clean exact worker/ancestry
  confirmed. Final candidate differs from independently verified code
  `fc7d4ad9cf3ec8d3a6373f1af12d73b85f778bbe` only in ticket 06 metadata.
  Bounded independent PASS: 116 handwritten controls in 10.59s, 372 maintained
  in 124.95s and eight VideoHtml scoped-policy probes. Historical `2803f92`
  FAIL remains retained. Root duplicate-TXT/driver/import/architecture checks
  pass: **141 tests in 40.07s**; diff check clean. Ticket 06 is resolved;
  ticket 07 remains claimed by `/root/txt_declaration_implementer` and is eligible
  for a fresh complete matrix. No original matrix/native/user/release completion
  is inferred from this tooling merge.

- 2026-10-06 (/root/integration_merger): Integrated reopened ticket 01 TXT repair
  with `git merge --ff-only 88dd6dcb24e818339edd84fc9fe3346c38d4b426` from
  clean root `45a3bf0abd613838177aa353ad365d8831b39d69`. Independent runtime
  `3a4b1db80fef07c1dfaf857dd114ea84beaa5c64` PASS covers 127 handwritten
  and 264 maintained controls; the final delta is only ticket 01 metadata,
  preserving verified runtime/test bytes. Root TXT/scope/workflow/source-reader/
  architecture tests pass: **220 in 15.52s**; diff check is clean. Ticket 01
  is resolved cumulatively. Ticket 06 remains claimed and 07 blocked pending
  its independent oracle repair and fresh complete matrix. No original-source,
  native/user or release completion is inferred.

- 2026-10-06 (/root/integration_merger): Integrated **partial evidence only**
  using `git merge --ff-only aadb55521c252708e09fc9d66f5d00a77627e020` from
  clean root `30ed23205d5569b1884376ffd559b5d0068f8456`, after clean candidate
  and ancestry checks. Reviewed the three-file aggregate/ticket/testing delta
  against ignored matrix log, D refusal JSON, partial counts and duplicate scan.
  Nine A/B/C independent audits passed; D refused with null receipt/counts.
  Five included absent TXT member groups retain ten separate declarations;
  production and independent scope guards both reject their duplicate spelling.
  Eighteen supplementary source-free checks were read-only; preservation guards
  retain four originals and 562 retained-vault files. Public evidence contains
  aggregate facts without original subject/attachment identities or assets.
  Corrected two Markdown trailing-space errors found by diff check; no runtime
  tests were needed for this evidence-only integration. Ticket 07 remains claimed
  and unchecked, blocked on coordinator-owned 01/06 compatibility repairs and a
  fresh complete matrix. No full-preservation/native/user/release gate passed.

- 2026-10-06 (/root/integration_merger): Integrated repaired ticket 06 with
  `git merge --ff-only e2d95ebc07187d53d5767879cff028f916032b13` from clean
  root `f23a8bee142457cf64a3bba1fd5ce84293bd9dca`; clean exact worker head
  and ancestry confirmed. Independent bounded PASS covers 24 handwritten
  replays, five bracket-label groups and 243 maintained tests in 112.70s.
  Historical `f70b023` FAIL evidence remains retained. Root driver/import-boundary
  and architecture checks pass: **13 tests in 30.77s**; diff check is clean.
  Ticket 06 records exact commands and attributed worker full-suite evidence.
  Ticket 07 is eligible and unclaimed; no private-original matrix, native/user
  observation or final release gate is completed by tooling integration.

- 2026-10-06 (/root/integration_merger): Integrated verified label repair by
  `git merge --ff-only 4332f61eee8e9bb4b0386bf969d38189b2194c65` from clean
  root `dd286452c6304c37f12357c4b5acd5a1e0b978ca`, ancestry and clean worker
  confirmed. Independent bounded PASS covers 14 handwritten public groups and
  142 focused tests in 16.74s, retaining the integrated residual guard. Root
  linked spans/forgotten/both alternate-source/architecture checks pass:
  **142 tests in 17.40s**; diff check is clean. Reopened ticket 01 is resolved
  cumulatively and its third criterion checked. Ticket 06 remains claimed and
  07 blocked; full four-original/native/user/review/release gates remain pending.

- 2026-10-06 (/root/integration_merger): Partially integrated residual ticket 01
  guard by `git merge --ff-only 9d69a6509b20c0e85e966149cc5cb0bc22667593`
  from clean root `fbab5d89de04f0672dd661c59c7f0580fde0e1b7`.
  Independent exact-head bounded PASS covers 18 body/encoded and 2 metadata
  groups, 103 focused tests and seven-file static review. Root forgotten/source
  spans/both alternate-source/architecture tests pass: **117 in 14.31s**;
  diff check is clean. Parent 01 stays claimed by the label implementer, with
  its third criterion unchecked for included entity/escaped punctuation loss.
  Ticket 06 remains in progress and 07 is ineligible. Full-original/native/user/
  final-review/release gates remain pending; no other ticket was claimed here.

- 2026-10-06 (/root): Reopened and claimed ticket 01's proven inactive-reference
  privacy gap after verified ticket 05 integration at `b5c9ef1`. Preserve unrelated
  literal text and refuse safely when a known omitted association cannot be
  removed through the approved active-reference path. Ticket 06 also adds
  independent forged-output corruption proof for this case. Full-source/native/
  actual-user gates remain pending.

- 2026-10-06 (/root/integration_merger): Integrated ticket 05 with
  `git merge --ff-only 12cdd084a6ddf13d90ac14d421cafa2c135ac9e7` from clean
  root `5d4800613cb5c2aced4b7f84f9ccbf87bcbdd85e`, ancestry confirmed.
  Independent bounded PASS covers 18 handwritten actual-ZIP/fault groups,
  47 focused tests and exact wheel/source bytes for 57 runtime modules.
  Root merged v3 workflow/failure, existing publication/failure, both alternate
  sources and read-only checker tests pass: **181 tests in 44.37s**; diff check
  is clean. See ticket 05 for exact commands and attributed worker evidence.
  Ticket 06 remains in progress. Coordinator will separately reopen/repair
  ticket 01 for the known inactive-reference privacy issue; ticket 05's active
  phrase controls do not close that gap. No full-original/native/user/release
  completion or ticket 07 eligibility is claimed.

- 2026-10-06 (/root): Claimed tickets 05 and 06 after verified type-gap
  integration at `4d515a62b2ba6552e8e7ca513615cf1b7ffa839c`. Combined workflow
  safety and independent raw-source tooling proceed in separate managed
  worktrees. All four original BRZ files and 562 retained-vault files pass the
  read-only preservation guard. Full-source/native/user/release gates remain pending.

- 2026-10-06 (/root/integration_merger): Integrated ticket 03 with
  `git merge --ff-only 68982810ea2a60ee5eec4d9f14537916815a7c7a` from clean
  root `296b3af67a2dc9590f0a97080200723b7adf50b8` after confirmed ancestry.
  Independent bounded static review, 19 handwritten raw-ZIP control groups
  and 192 focused tests PASS at that exact head. Root merged type-gap/image/
  category/property/hierarchy and both alternate-source checks pass:
  **325 tests in 30.05s**; diff check is clean. Ticket 03 records exact commands
  and attributed worker full regression evidence. Tickets 05 and 06 are eligible
  and unclaimed; complete four-original/native/user/review/release gates remain
  pending.

- 2026-10-06 (/root): Claimed type-note/icon gaps after ticket 02's verified
  integration. Tickets 01/02/04 are resolved; combined workflow safety and
  independent audit tooling remain blocked by this slice.

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
