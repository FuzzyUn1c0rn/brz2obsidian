# 01: Exclude forgotten thoughts throughout inspection and conversion

Status: resolved
Assignee: /root/forgotten_reference_implementer
Approved: 2026-10-06
Specification: [Accepted conversion specification](../spec.md)

**What to build:** Inspect and convert a supported archive with forgotten thoughts into a fresh vault that contains only included thoughts and safe evidence. The source archive stays unchanged; excluded thoughts leave no destination artifacts or identifying audit traces.

**Blocked by:** None (can start immediately).

## Acceptance criteria

- [x] Default exclusion applies to every BRZ archive from a valid populated ForgottenDateTime, independently of attachment state. There is no include-forgotten option. Establish trustworthy identities/ownership before scoping; malformed scope markers and unsafe source identities/paths still refuse.
- [x] Excluded subjects contribute no assigned/reserved target, note, owned local/external asset, original copy, icon/provider effect, classification/tag membership, relationship, stub, warning subject, individual exclusion identity/list/count, associated raw record or unsafe history. Included counts describe included scope. Omitted subjects cannot affect collision names, greedy selection or ordering.
- [x] Remove an entire authored linked phrase/embed resolving to an excluded subject, including label/target, without a plain-text reminder or deletion marker. Preserve other text, code literals, Unicode and newline spelling. Unknown nonexcluded targets retain refusal. No title/pixel matching removes unrelated included content.
- [x] Preserve byte-exact safe originals and provably included raw evidence with original values and omission/null distinctions. Omit unsafe exact originals rather than editing and calling them exact; omit unsafe fields/records/whole unscopable history collections. Raw spans, embedded state-map keys and guide-linked evidence cannot reintroduce exclusions.
- [x] Excluded providers remove membership/appearance effects, letting included members proceed under ordinary included selection; do not create category placeholders. An excluded designated Home retains required-entry refusal, with no replacement Home. Parse/refusal/failure output must not echo excluded identities, titles or content.
- [x] Public inspect/convert workflow and text/JSON wrappers expose the scoped behavior and honest source measurements. Source-neutral contracts and policy, source module/profile, renderer and serialized result/record schemas advance to 3, package to 0.3.0; format stays 5. Establish the accepted common optional source-gap/generated-presentation contract and serialized shape with empty facts now, so later slices populate rather than silently redefine the closed version-3 shape. Preserve signatures/outcomes/exits, reject incompatible versions, and keep the separate checker at schema 1 unless its public shape changes. New absence features remain refused until their behavior slices land.
- [x] A complete handwritten synthetic conversion proves owned content removal, incoming references, exact-copy conflicts, raw evidence/history, collisions, relationships, assignments, excluded provider/Home, malformed scope markers and unknown targets. Same-title/same-pixel included controls survive. Inspect, output inventories/bytes, manifests, records, reports and failures are checked from raw fixture facts.
- [x] Retain inward import barriers, injected interfaces and a non-UUID alternate source on current source-neutral contracts with empty new optional facts. Update affected existing acceptance-oracle/version expectations so existing public checks remain green, without deferring known failures to a later ticket.
- [x] Document the default scope, safe-copy tradeoff and changed public versions alongside the behavior. Use the project environment; existing applicable regressions pass. Record bounded proof and limits without claiming full original-archive conversion.

## Verification boundary

Actual synthetic ZIPs through public inspect/convert, thin text/JSON commands and output/source inventories. Use existing public source/core/renderer boundaries only for higher-level-impractical contract failures. No private-helper or new runtime test seam.

## Specification coverage

User Stories 15–16, 32–39, 49–50, 56–57, 60–62, 69–70; Implementation Decisions 1–8, 20–21, 23, 25; Testing Decisions 1–3, 5, 7, 10, 16–17, 20. Read the accepted specification; these references identify emphasis, not permission to ignore cumulative requirements.

## Comments

- 2026-10-06 (/root/forgotten_reference_implementer): Bounded reopened repair
  implemented at runtime commit `cb256bdbb89f77ac8265c5d28713a19f0ac05b41`,
  based on confirmed clean integration `fbab5d89de04f0672dd661c59c7f0580fde0e1b7`
  in the assigned managed checkout. The accepted real-ZIP Workflow and thin CLI
  seams remained unchanged. TDD vertical cycles reproduced (1) an excluded
  compact URI surviving inline code, (2) a Unicode-escaped serialized identity
  surviving a comment, (3) uppercase/mixed canonical UUID and percent-encoded
  URI literals surviving, and (4) uppercase canonical ownership in nested,
  serialized and Unicode-escaped settings retaining private sibling content and
  transitive record identities. Each failing public control passed after its
  respective bounded repair; logs are `tmp/ml-residual-scope/red1.txt` through
  `red4.txt` and `green1.txt` through `green4.txt`.

  The outer source adapter still removes only the approved active reference
  spans. It then refuses privately with static `invalid_reference` when a proven
  omitted identity/association remains. No accepted output or partial destination
  is published. Shared original/evidence/body inspection recognizes known
  canonical UUID case variants, case-exact compact identities and associated
  record IDs, plus one percent layer followed by one serialized Unicode-escape
  layer. Canonical UUID casing participates in existing ownership closure, so an
  associated record is removed as a whole with its dependents. This does not
  infer arbitrary encodings, title/pixel matches or unreviewed reference spans;
  no raw BRZ/evidence parsing, new test seam or contract version enters the core.

  Forty-one added public cases cover pure inactive leakage, all four literal
  contexts (inline/fenced code, HTML comments, plain text), canonical/compact,
  canonical case variants, URL/Unicode escaped spellings, active removal plus
  residual literals, closure-derived associated IDs, private text/JSON inspect
  and convert, unchanged source/caller bytes, safe exact original bodies,
  unrelated compact case spellings, same-title included content, whole-record
  ownership and safe serialized numeric precision/null/omission controls.
  Existing owned content, same-pixel, active removal and unknown-target controls
  remain green. The three reopened criteria are checked against this bounded
  proof together with retained earlier evidence, not arbitrary representation
  detection or full-original/native/user acceptance.

  All Python commands used only
  `C:/Users/stefa/projects/brz2obsidian/.venv/Scripts/python.exe`, with explicit
  `PYTHONPATH` pointing to this checkout's `src` and root. Focused command:
  `-m pytest -q tests/application/test_forgotten_workflow.py tests/sources/test_reader.py tests/sources/test_note_spans.py tests/application/test_alternate_source.py tests/application/test_alternate_v2_source.py tests/test_architecture.py --basetemp=tmp/ml-residual-scope/pytest-affected -o cache_dir=tmp/ml-residual-scope/cache`
  passed **135 tests in 14.79s**. Final complete command:
  `-m pytest -q --basetemp=tmp/ml-residual-scope/p -o cache_dir=tmp/ml-residual-scope/cache`
  passed **1,116 tests in 160.72s**. Ruff `check --no-cache`, Ruff
  `format --check` (126 files), `pip check` and `git diff --check` passed.
  Logs are `affected.txt`, `final-full.txt`, `lint.txt`, `format.txt` and `pip.txt`
  under the same ignored effort directory. The first full run's single maximal
  category-name failure came from the longer proof path crossing the unchanged
  240-unit limit; its unchanged test passed with the shorter contained base
  before the final complete run (`full.txt`, `path-replay.txt`).

  Latest integration `git merge --ff-only codex/management-leadership-v3` was
  already up to date before this evidence-only record. No original archive,
  retained user vault, native app, PR or remote publication was changed. Complete
  original-source, native and actual-user gates remain pending. Independent
  bounded review and integration remain coordinator-owned; the local resolved
  status records implementer proof and does not claim delivery.

- 2026-10-06 (/root): Reopened for a bounded source-side privacy repair after
  read-only exploration at `5d480061`: an excluded thought URI inside inactive
  code/comment/plain text survives in the adapted note even though the exact
  original is omitted. Active linked phrases already follow the approved removal
  path. Complete exclusion and preservation of unrelated literals require safe
  refusal when a proven omitted association remains after those removals;
  arbitrary literal rewriting and title matching are not authorized. Implement
  and verify at the existing public real-ZIP workflow seam on an isolated managed
  branch based on integration `b5c9ef1ab05e7c409d76cb32b6b6017e0c349d08`.
  Earlier evidence remains retained; affected criteria await new proof. The
  independent oracle will reject a forged accepted output with this residual leak.

- 2026-10-06 (/root): Claimed the initially unblocked slice for an isolated
  implementer based on `codex/management-leadership-v3`, planning commit
  `bb7a5ab6506dce699bb7d8373bf04a25375d5979`. TDD seams are already confirmed in
  the accepted specification; no new user testing approval is needed.

- 2026-10-06 (/root): Published after the user approved all nine tickets and their
  dependencies, then explicitly invoked implement-spec for complete implementation.

- 2026-10-06 (/root/forgotten_implementer): Implemented in isolated managed
  worktree on `codex/ml-v3-01`, based on integration claim `f017b7d`. Public seams
  are the already-confirmed real-ZIP inspect/convert workflow and thin CLI, with
  existing contract/source/core boundaries for incompatible versions. TDD skill
  applied in vertical cycles: (1) forgotten scope red counted 3 items/2 edges
  instead of 2/1; (2) incoming authored reference red refused rather than removing
  its whole phrase; (3) current envelope red reported schema 2; (4) excluded embed
  and date-only Home controls red refused under the wrong predicate; (5) mixed
  fixture red leaked an excluded UUID through an opaque raw field key; (6) scoped
  evidence red rounded `0.123456789012345678901234567890`; (7) malformed excluded
  reference red incorrectly succeeded; (8) associated setting red retained its
  own raw identity/content; (9) image-wrapped excluded reference red refused on
  overlapping spans. Each defect was fixed and the respective public test went
  green before moving on. Failure/ownership/path/unknown-target controls also
  prove private refusals and unchanged caller/source bytes.

  The 15 forgotten workflow cases cover owned Markdown/images/icons/URLs,
  relationships, excluded category/tag providers and Home, exact-copy conflicts,
  raw state keys/fields/associated settings/unscopable history, Unicode and mixed
  newlines, code literals, same-title/same-pixel included controls, exact safe
  numeric values and omission/null distinctions. Unsafe original assets are
  omitted; their included Documents expose `original_asset_id=null` and
  `original_copy_omitted=true`, without identifying excluded subjects. Safe
  originals remain on the existing byte-exact copy path. No exclusion ledger,
  individual count or include-forgotten mode was added.

  Current public versions are package 0.3.0, snapshot/policy 3, source
  module/profile 3, renderer 3, result/record 3; BRZ stays 5 and checker stays 1.
  SourceGap, GeneratedPresentation, SourceGapDiagnostic and
  GeneratedPresentationTarget reserve semantic role/provider/member and ordered
  image obligations with empty initial facts. Snapshot/plan/inspection/record
  share those shapes, with separate gap/generated-embed counts. New state-3
  absences and category hierarchy still refuse pending their approved slices.
  The opaque Folio adapter and existing independent oracle expectations use the
  current contracts. Existing generic graph fixture controls now explicitly
  carry null forgotten markers; dedicated tests verify actual exclusion.

  Verification with the root project `.venv` interpreter and worktree
  `PYTHONPATH`: complete `python -m pytest -q --basetemp=tmp/p01` passed
  **798 tests in 112.50s**; Ruff check `--no-cache` and format check passed;
  `pip check` passed. Built the 0.3.0 wheel with no dependency installation; its
  inventory contains runtime package/distribution files only. Console/module
  JSON and documented library workflows plus source-free checker smoke passed.
  Disposable logs, wheels and smoke outputs are under ignored
  `tmp/ml-implementation/01/` (pytest-owned files under `tmp/p01`). An existing
  maximal-name test uses a short pytest-owned child to preserve the actual
  240-unit publication limit inside longer managed worktree paths.

  Limits: this is synthetic public-seam proof for ticket 01. No original archive
  was converted or mutated, retained user vault changed, native application
  acceptance claimed, or actual user verdict supplied. Complete four-archive,
  absence/hierarchy and publication/native/user gates remain on the approved
  frontier. The implementation index and other ticket/Wayfinder records belong
  to the integration coordinator.

- 2026-10-06 (/root/forgotten_implementer): Reopened after independent behavioral
  and static REWORK at `524822d`: nested associated raw records and Unicode-escaped
  serialized JSON ownership retained private sibling content/record identity;
  malformed compact authority suffixes echoed source URI/title in refusals. Prior
  verification evidence is retained. Repair uses the same confirmed public seams
  and vertical TDD: three nested/serialized/escaped workflow controls first
  leaked associated outer IDs; after recursive ownership/transitive closure they
  pass while safe serialized strings retain exact decimal spelling. A malformed
  authority public inspect/convert control first leaked its compact identifier;
  static reference error messages now omit raw URI/targets. Explicit duplicate
  ownership keys and metadata-record controls ensure all declarations participate.
  Source bytes and existing caller sentinel inventory remain unchanged. Logs are
  `tmp/ml-implementation/01/repair-red1.txt`, `repair-green1.txt`,
  `repair-red2.txt`, `repair-green2.txt`; new full verification is in progress.
  Independent re-verification remains required before integration.

- 2026-10-06 (/root/forgotten_implementer): Final repair verification binds to
  the repaired runtime including the required-metadata privacy guard: complete
  public suite **808 passed in 111.45s**; affected forgotten/source-reader suite
  **43 passed in 4.09s**; Ruff lint/format and pip check pass. Nested ownership
  now removes entire associated records and transitive dependent identities;
  source JSON strings are inspected recursively with every duplicate ownership
  key visible, while retained strings and precise raw numbers remain unchanged.
  Unscopable required collection metadata refuses privately instead of escaping
  through an indexing error; excessive recursion follows the same safe source
  refusal boundary. All source-reference refusals omit interpolated raw targets.

  Direct replays of the independent nested-setting, escaped-serialized and
  malformed-authority source ZIPs pass against fresh outputs with unchanged
  source bytes. Prior independent reports, vaults and first-slice wheel/logs were
  retained. Final repair 0.3.0 wheel is under ignored
  `tmp/ml-implementation/01/repair-wheels/`, SHA-256
  `507fc7a8bf8e072fb8251d4af2a3a758812ca02ef764292648eeda05f4ec9e46`.
  Direct wheel imports prove runtime-only inventory, console private refusal,
  module escaped-ownership conversion, library inspection and source-free checker
  smoke. Logs: `repair-final-regression.txt`, `repair-final-affected.txt`,
  `repair-replay.txt`, `repair-packaged-smoke.txt`. No new source semantics,
  original-archive/native/user acceptance or other-ticket completion is claimed.
  Independent re-verification and integration remain coordinator-owned.

- 2026-10-06 (/root/integration_merger): Resolved integration gate after
  coordinator authorization bound to exact repaired commit
  `5fbb5ccf3d4c3cfb02779c25c876ddfa3bb179c3` on `codex/ml-v3-01`.
  Both independent bounded verdicts PASS: behavioral report
  `tmp/ml-implementation/01/behavioral-verification-repair.md` records all six
  replay/control groups, unchanged source/caller inventories and 43 focused
  tests in 5.92s; static report
  `tmp/ml-implementation/01/static-verification-repair.md` clears R1-R3 and
  confirms the required-metadata private refusal boundary. The unavailable
  role-specific custom guard protocol is not claimed as executed; the invoked
  implement-spec workflow is supported by these concrete exact-head checks.

  From the clean root integration checkout at
  `929f2a8735e99b66ee25f45d159b8b3f1d9c0916`, executed
  `git merge --ff-only 5fbb5ccf3d4c3cfb02779c25c876ddfa3bb179c3` successfully.
  Merged verification command:
  `.venv/Scripts/python.exe -m pytest -q tests/application/test_forgotten_workflow.py tests/application/test_alternate_source.py tests/application/test_alternate_v2_source.py tests/test_architecture.py --basetemp=tmp/ml-implementation/merger/pytest-01-5fbb5cc -o cache_dir=tmp/ml-implementation/merger/pytest-cache-01-5fbb5cc`
  passed **63 tests in 10.67s**, exit 0. Runtime imports resolve to the root
  checkout. `git diff --check 929f2a8735e99b66ee25f45d159b8b3f1d9c0916..5fbb5ccf3d4c3cfb02779c25c876ddfa3bb179c3`
  is clean. The 808-test complete suite (111.45s), Ruff/pip and repaired wheel
  evidence above remain attributed to the implementer; the identical
  fast-forwarded code does not require redundant full-suite execution here.
  Copied worker evidence is retained under
  `tmp/ml-implementation/01/worker-evidence-5fbb5cc/` before later archival.

  Scope remains this synthetic, versioned public-workflow slice. Future absence,
  hierarchy, publication/full-original preservation, native/user acceptance,
  final cumulative review and release gates remain pending. Ticket 02 and 04
  are eligible; their claims remain coordinator-owned.
