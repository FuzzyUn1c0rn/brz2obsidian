# 05: Prove the combined conversion and publication guarantees

Status: resolved
Assignee: /root/workflow_safety_implementer
Approved: 2026-10-06
Specification: [Accepted conversion specification](../spec.md)

**What to build:** Inspect and convert one complete synthetic archive combining the new features and delivered v2 resources into a verified fresh vault. Repeats are deterministic; real publication failures preserve caller files and report durable output honestly.

**Blocked by:** [03 — Keep category dashboards usable through missing type notes and icons](03-type-source-gaps.md); [04 — Preserve ordinary-to-category hierarchy in both directions](04-category-hierarchy.md). Earlier behavior blockers are transitive.

This strengthens already-green behavior with combined interactions and real
publication faults. Earlier slices must already refuse their known invalid cases
and preserve caller files; this gate does not permit deferring known failures.

## Acceptance criteria

- [x] A complete mixed synthetic conversion combines forgotten exclusion, exact supplied Markdown, multi-image absent ordinary notes, missing type body/icon with included/overridden members, multiple-parent category hierarchy, Home/tags/dates/collision naming, PDFs/ZIP/generic files/external URLs and reviewed video timing. Independently expected output facts, bytes, graph and scoped counts agree.
- [x] Public library/default wiring/dependency injection, console/module text/JSON and strict schema/profile versions agree. Reject incompatible combinations and inconsistent owner/asset/finding joins. Inspection remains read-only with measured source facts/planned obligations and no publication counts/receipt; conversion retains clean/warnings/refused/failed and exits 0/2/1/1.
- [x] Conversion prepares afresh and verifies the complete new artifact plan before safe fresh-destination publication. Source fingerprints/scoped digest/policy bind analysis, plan, generated presentations, manifests and durable receipt. Missing bytes and generated images cannot inflate original-byte or authored-reference conservation credit.
- [x] Extend existing real stream/write/copy and staging-deletion/truncation/same-length-corruption tests to new artifacts. Exercise source mutation, unsafe paths/Windows junctions, rename/rmdir races and teardown/post-commit failures at highest practical existing boundaries. Caller before/after inventories/hashes and owned cleanup prove no caller deletion or partial accepted output.
- [x] After actual verified publication, preserve/report durable receipt even if a later stage fails; do not claim no publication. Report only available measurements and null unknown counts on refusal/failure, without exclusion leakage or invented success facts.
- [x] Exact/repeat/root-record and ZIP-order permutations keep selections, paths, body edits, image ordering, findings/affected-member order and logical output deterministic. Differences are restricted to documented input/snapshot provenance, raw evidence ordering and explicit clock/run/bookmark metadata.
- [x] The independent source-free checker accepts actual generated embeds/neutral properties, detects missing images/real convention defects, retains schema 1 unless shape changes, and preserves caller inventory/bytes on success/failure. It neither trusts a historical receipt to prove current content nor becomes a source-gap/preservation oracle.
- [x] Current non-UUID alternate source and inward import barriers prove source-neutral reuse. No BRZ numeric role/ForgottenDateTime parsing enters generic planning. Existing v1/v2 cumulative public behavior stays green.
- [x] Update library/CLI/schema/coverage/checker/publication documentation and run relevant package/documented-example smoke against 0.3.0. The delivered distribution contains runtime material only; do not publish private fixtures, vaults or screenshots. Record integration proof and remaining full-input/native/user gates.

## Verification boundary

Actual synthetic archives/filesystems at public workflow, thin wrappers and separate checker. Existing public publisher/stream interfaces for real failures when workflow cannot reliably expose them. No mock-only conservation or private testing API.

## Specification coverage

User Stories 12–20, 31–39, 40–62, 64, 69–70; Implementation Decisions 1–25 except the full-input/native delivery gate; Testing Decisions 1–11, 16–17, 20.

## Comments

- 2026-10-06 (/root/integration_merger): Integrated verified exact clean branch
  head `12cdd084a6ddf13d90ac14d421cafa2c135ac9e7` from `codex/ml-v3-05`
  with `git merge --ff-only 12cdd084a6ddf13d90ac14d421cafa2c135ac9e7` on
  clean root `5d4800613cb5c2aced4b7f84f9ccbf87bcbdd85e`; ancestry check exit 0.
  Independent `tmp/ml-implementation/05/verification.md` records bounded PASS:
  **18 handwritten actual-ZIP/fault groups**, **47 focused tests in 26.10s**,
  and read-only exact wheel/source-byte verification of **57 runtime modules**.
  It checks combined present/absent/category/hierarchy/accounting behavior,
  reached real partial-write/read/staging faults, actual postcommit durable
  receipts, source/caller inventories and separate checker behavior.

  Merged root command:
  `.venv/Scripts/python.exe -m pytest -q tests/application/test_integrated_v3_workflow.py tests/publication/test_v3_failure_protection.py tests/application/test_failure_protection.py tests/publication/test_failure_protection.py tests/application/test_alternate_source.py tests/application/test_alternate_v2_source.py tests/vault_check/test_check_vault.py --basetemp=tmp/ml-implementation/merger/pytest-05-12cdd084 -o cache_dir=tmp/ml-implementation/merger/pytest-cache-05-12cdd084`
  passed **181 tests in 44.37s**, exit 0. Runtime import resolves to root src.
  `git diff --check 5d4800613cb5c2aced4b7f84f9ccbf87bcbdd85e..12cdd084a6ddf13d90ac14d421cafa2c135ac9e7`
  passed, exit 0. Worker complete **1075-test** suite, Ruff on 126 files, pip
  and documented wheel-example smoke remain attributed worker evidence; no
  redundant complete suite was run on identical fast-forwarded code. Copied
  ignored proof destination is `tmp/ml-implementation/05/worker-evidence-12cdd084/`;
  worktree archival remains coordinator-owned.

  Known limit: excluded identities can still survive in inactive Markdown
  code/comment/bare URI content after unsafe-original omission. This bounded
  PASS proves active authored phrase removal and does not close that separate
  ticket 01 privacy defect. Coordinator will reopen/repair 01 independently.
  Ticket 06 remains claimed; ticket 07 is not eligible. Full-original scoped
  oracle/preservation, native/user acceptance and release remain pending.
  No other ticket claim, source/retained-vault change, PR or push was performed.

- 2026-10-06 (/root/workflow_safety_implementer): Final fixed-code-head complete
  suite at `4f8f5cb4523c1d079f0ffd49fa5d7a16065ce424`, command
  `-m pytest -q --basetemp=tmp/ml-workflow-safety/final`, passed
  **1,075 tests in 156.86s**; `tmp/ml-workflow-safety/final-suite.log` retains
  output. All nine ticket criteria are satisfied through this slice's synthetic
  public proof plus cumulative existing version/source-neutral/safety controls.
  Remaining commit changes this ticket evidence only. Independent root replay
  and integration are subsequent operations, not claimed by this resolution.

- 2026-10-06 (/root/workflow_safety_implementer): Implemented only this claimed
  slice in managed worktree `ml-v3-workflow`, branch `codex/ml-v3-05`, after
  confirming clean HEAD and integration merge-base both
  `5d4800613cb5c2aced4b7f84f9ccbf87bcbdd85e`. Public testing authorization is
  accepted Testing Decision 20. Read the tracker/domain/workspace instructions,
  glossary, ADR 0001, accepted specification/index and TDD skill/references.
  Code/test/documentation commit is
  `4f8f5cb4523c1d079f0ffd49fa5d7a16065ce424`. Merging the latest integration
  branch returned `Already up to date`; there are no runtime production edits.
  This ticket adds bounded proof of the already integrated policies, without
  changing the independent raw-source oracle, driver or its architecture barriers.

- 2026-10-06 (/root/workflow_safety_implementer): The initial tracer failed
  through `default_workflow().inspect` on the inherited actual v2 ZIP (12 source
  items rather than the independently required 11 included items). Completed
  the synthetic source fixture with the forgotten subject/owned payload,
  incident edge, two ordinary parents of the category, stable naming collision,
  supplied blank member, ordinary absent body/two valid PNGs, simultaneous
  type body/icon gaps and an opaque ZIP resource. The tracer then passed.
  Subsequent combined/fault controls exercised existing behavior directly;
  no failing production behavior was invented to justify a runtime change.
  Two independent expected support/file totals were corrected to 18/36: all
  included nonempty hierarchy components are covered, so the conditional
  Uncreated targets listing is unnecessary. CLI subprocess capture uses the
  documented UTF-8 environment setting. These fixture/test corrections do not
  change accepted product policy.

- 2026-10-06 (/root/workflow_safety_implementer): Added 47 controls in
  `tests/application/test_integrated_v3_workflow.py` and
  `tests/publication/test_v3_failure_protection.py`, with reusable synthetic
  source support in `tests/support/v3_collection.py`. Independently authored
  literals require 11 included subjects, 11 relationships, seven imported notes,
  11 exact copied payloads, 18 support files, three gaps, two generated embeds
  and two authored references. Every output path and copied byte is checked;
  canonical provider/membership/hierarchy joins and ordered gaps/member images
  agree. No missing-body/icon originals, excluded identities/content, or fake
  generated-reference credit enter output. Real copy/open/read/short-stream and
  partial writes, staging delete/truncate/same-length corruption and source
  mutation reach the new notes/images/report/record. A real owner-directory
  Windows junction and real rename/rmdir races retain caller files; unsafe
  owned staging is explicitly reported before controlled removal. Teardown and
  post-commit failures retain complete verified receipt/counts. Fresh conversion
  after changed inspection binds the newly supplied body. Repeat/reorder checks
  retain every raw root-record multiset/payload and retained safe evidence;
  all content and ordered new obligations agree. Only documented fingerprint,
  scoped digest, raw evidence pointers/order and clock/run/bookmark provenance
  vary. Checker schema 1 accepts the actual generated/neutral output and detects
  a deleted generated image despite a historical verified record, read-only.

- 2026-10-06 (/root/workflow_safety_implementer): All Python commands used
  `C:/Users/stefa/projects/brz2obsidian/.venv/Scripts/python.exe` with explicit
  `PYTHONPATH=<this checkout>/src;<this checkout>`; the shared editable install
  was not retargeted and no environment packages were installed. Focused command
  `-m pytest -q tests/application/test_integrated_v3_workflow.py
  tests/publication/test_v3_failure_protection.py
  --basetemp=tmp/ml-workflow-safety/verified-new` passed **47 tests in 27.84s**.
  The additional retained-evidence order assertion passed separately in **2.29s**.
  Complete cumulative command `-m pytest -q
  --basetemp=tmp/ml-workflow-safety/full` passed **1,075 tests in 160.23s**,
  including strict schemas/incompatible profile and owner/asset/finding joins,
  clean/warnings/refused/failed exit behavior, non-UUID Folio substitution,
  inward import checks and existing v1/v2 safety/convention controls. Final
  lint `-m ruff check --no-cache .` passes; `-m ruff format --check .` passes
  on **126 files**; `-m pip check` reports no broken requirements;
  `git diff --check` passes. Local receipts/logs are ignored under
  `tmp/ml-workflow-safety/` (`focused.log`, `full.log`, `lint.log`, `format.log`,
  `pip.log`, retained test outputs).

- 2026-10-06 (/root/workflow_safety_implementer): Package command
  `-m pip wheel --no-deps --no-build-isolation --wheel-dir
  tmp/ml-workflow-safety/wheels .` builds `brz2obsidian-0.3.0-py3-none-any.whl`,
  SHA-256 `3a35b51f52e1d137c11e236092eebf6a7f80a92ef2899982a8e96bd027167883`.
  The executed ignored `tmp/ml-workflow-safety/package_smoke.py` checks all
  57 package-module bytes against current sources, runtime-only wheel contents,
  version/dependencies/console entry point and actual README default-workflow,
  architecture explicit-workflow/direct-module and checker Python examples
  (only caller paths substituted). Three complete 36-file vaults and a separate
  direct-wheel import/module inspect/convert/check-vault pass, exits **2/2/0**,
  source unchanged, schema 3/profile 3/checker 1 and two generated embeds.
  `wheel.log` and `package-smoke.log` retain evidence. README/runtime dependency
  guidance now includes Pillow; schema, publication, mixed coverage, checker
  and package documentation describe current behavior and bounded proof.
  Historical v2 delivery remains distinct from pending v3 acceptance.

- 2026-10-06 (/root/workflow_safety_implementer): Limits: entirely synthetic
  actual ZIP/filesystem evidence on this Windows/Python environment, using
  controlled failures at existing public publisher/source-stream and OS
  boundaries. This is not independent complete raw-source preservation proof,
  a private original-archive run, a native Obsidian observation, actual-user
  acceptance or release delivery. Source originals and retained user vaults
  were not accessed. Those later gates remain pending; root independent
  verifier/merger must verify the exact final head before integration.

- 2026-10-06 (/root): Claimed after independently verified tickets 03 and 04
  were integrated. Implement in an isolated managed worktree based on integration
  `4d515a62b2ba6552e8e7ca513615cf1b7ffa839c`, using the accepted public testing seams.
  Full original-source, native and actual-user gates remain pending.

- 2026-10-06 (/root): Published after the user approved all nine tickets and their
  dependencies, then explicitly invoked implement-spec for complete implementation.
