# 06: Extend the independent raw-source audit to the new conversion policy

Status: resolved
Assignee: /root/independent_audit_implementer
Approved: 2026-10-06
Specification: [Accepted conversion specification](../spec.md)

**What to build:** Independently verify the new converter output against raw original records and payloads, detecting plausible but incomplete or misleading vaults. The acceptance driver can run all four required originals with repeat and reorder proof.

**Blocked by:** [03 — Keep category dashboards usable through missing type notes and icons](03-type-source-gaps.md); [04 — Preserve ordinary-to-category hierarchy in both directions](04-category-hierarchy.md). This reusable audit can proceed alongside the combined publication-safety proof.

## Acceptance criteria

- [x] Extend the existing standard-library-only independent oracle and preserve its import-boundary checks. Derive included identities, references, safe evidence, selections/paths, graph/assignments, supplied-body expected adaptations, absent-declaration predicates, image eligibility/associations/order and provider effects directly from raw original source facts. Production filtered snapshots/counts/dispositions/manifests are observed output, never expected preservation truth.
- [x] Audit exact safe originals and all required payload hashes/lengths, every supplied-body edit, authored-reference accounting, explicit generated presentation obligations, resolving diagnostic links, raw state/path/length/outcome, complete category membership/hierarchy/native support and excluded-content absence. Do not infer recovery, emptiness or original-note bytes for absent bodies.
- [x] Positive public synthetic controls exercise all behavior slices and earlier supported cases independently. Corruption controls falsify included-body text, unsafe/safe evidence, excluded identities/owned bytes/labels, missing/duplicate/misowned/generated-order embeds, gap predicates, fabricated originals/reference credit, neutral/provider/override effects, graph/membership/navigation and diagnostics.
- [x] Corruption tests recompute counts and file receipts consistently before rejection, proving semantic preservation rather than only manifest mismatch. A structurally valid forged receipt or clean production convention checker cannot mask each corruption. Retain meaningful existing controls and no private archive in public tests.
- [x] Extend the three-input driver to a fourth mandatory original argument while retaining previous arguments/fingerprint pins. Help, documentation and an executed synthetic example identify all four originals and a fresh short ignored output location; verify selected code import/current version. Do not hard-code 0.2.0 or treat a comparison/recovery backup as the fourth source.
- [x] Driver supports exact/repeat/ZIP-and-root-record reorder for each input: 12 complete outputs. Independently prove root-record multisets and physical payload equality, and reject changed/omitted/duplicated reordered records/payloads. Hash originals before/after operations and at completion; fail if final fingerprint drifts.
- [x] Keep source-required oracle behavior distinct from source-free check_vault, mutable UI conventions and production accounting. Real raw records/assets/audit outputs remain local and ignored; public records summarize aggregate gates and honest failures only.
- [x] Existing public oracle/driver tests stay green. Record reproducible tool usage and bounded synthetic/corruption proof; completing tooling does not claim the four private archives have passed.

## Verification boundary

Existing independent raw-source oracle/driver public callables and CLI with synthetic archives and real files. Standard-library/local independent support only; do not import production interpretation helpers to compute expectations.

## Specification coverage

User Stories 16–20, 32–39, 41–49, 54–65, 68–70; Implementation Decisions 1–25 as independently audited obligations; Testing Decisions 5–10, 12–17, 20.

## Comments

- 2026-10-06 (/root/independent_audit_implementer): Completed the owned
  compatibility repair after claim commit `484c3d4`. Integration
  `f23a8bee142457cf64a3bba1fd5ce84293bd9dca` was already merged; merge replay
  reported up to date. Four new public labels verify an escaped opening bracket,
  escaped closing bracket, paired escaped brackets and balanced bracket text.
  Before repair, three failed at the overly broad nested-phrase assertion and
  the closing-only escape already passed. The scanner now shares balanced active
  phrase boundaries between the complete source and included labels, recognizing
  bracket text without accepting nested active links/images. Display text retains
  literal brackets in the migration record; existing wiki alias sanitation remains
  independently verified. A consistently rehashed false record replacing that
  richer display text with its sanitized alias is rejected. Separate nested-link,
  nested-image and incomplete-destination controls remain closed. Complete
  forgotten-phrase removal and all six earlier formatting controls stay green.

  Using the root project interpreter and explicit checkout `PYTHONPATH`,
  `python -m pytest tests/local_acceptance/test_checker_v3.py -k 'bracket or authored_reference_labels or independently_removes' -q --basetemp=tmp/ml-independent-audit/db --tb=short`
  passed **17 affected checks in 3.93 seconds**. The final complete command
  `python -m pytest -q --basetemp=tmp/ml-independent-audit/r --tb=short`
  passed **1249 checks in 231.49 seconds**, including all **243** maintained
  oracle/driver checks (115 earlier, 116 v3 and twelve driver controls).
  Ruff lint and format passed with **130 files formatted**, pip reported no broken
  requirements and diff checks passed. Only the owned scanner, public controls,
  oracle proof paragraph and this ticket's evidence changed; runtime/source
  matrices/native/UI/PR/push remain outside this repair.

  Historical `f70b023` remains an overall independent-verification **FAIL** despite
  its 24 handwritten groups and 235 maintained passes. The two bounded bracket
  probe failures are preserved at root under ignored `tmp/ml-implementation/06/`.
  This repair requires an independent exact-clean-head replay before integration;
  its implementation checks do not claim that replay or private source acceptance.
  Implementer command logs exist only in tool output and this versioned ticket;
  no separate decoder receipt was saved by the implementer. Selected ignored
  synthetic proof files to preserve before archiving are
  `tmp/audit-synth-02/out/aggregate.json` and `operations.json`, optionally one
  actual CLI manifest (`A-result.json`) and raw public `A.brz` if not already
  copied at root. Root's independent decoder receipt supplies full pixel/source
  hashes. Bulk pytest trees and generated synthetic vaults need not be copied.

- 2026-10-06 (/root/independent_audit_implementer): Reopened and claimed after
  independent verification of clean `f70b0237647eff6894dd1224cd5ed79abc98806f`
  reported overall **FAIL**. Its 24 handwritten replay groups and 235 maintained
  checks passed, but two additional valid included labels (escaped brackets and
  balanced bracket text) were rejected by the oracle as nested active syntax.
  Repair only the independent scanner/tests and this ticket's evidence, preserving
  recorded display text, established wiki alias sanitation, malformed/nested
  active-link rejection and complete forgotten-phrase removal. Root integration
  remains verified `f23a8bee142457cf64a3bba1fd5ce84293bd9dca`; no original/native
  acceptance is claimed by the historical candidate or this repair.

- 2026-10-06 (/root/independent_audit_implementer): Implemented the approved
  public oracle/Workflow and four-input driver seams through red/green slices in
  isolated `codex/ml-v3-06`, initially clean at
  `5d4800613cb5c2aced4b7f84f9ccbf87bcbdd85e`. Merged verified integration
  `f23a8bee142457cf64a3bba1fd5ce84293bd9dca` before final validation, preserving
  the separately owned workflow docs and runtime repairs. No production files,
  spec/index/other ticket records, originals or retained vaults were edited.

  The expected-fact modules remain stdlib/local only, with a closed six-module
  AST import barrier. `check_vault(source, vault)` derives scope, raw ownership,
  safe evidence/precision, names/selections, complete body/reference edits,
  graph/memberships, gap/image/provider facts, all payload bytes and diagnostic
  obligations independently. Physical original record ordinals remain private;
  public accounting pointers address retained safe tables. Excluded-first and
  interleaved records prove that distinction. Equal included/excluded titles and
  image bytes do not determine ownership.

  Red cases established scope/evidence removal, whole active-phrase removal,
  absent-body and type-gap interpretation, repeat/reorder comparison, missing
  fourth-input/help behavior, invalid compressed images, native capability
  failures, encoded residual identities and serialized association values before
  their green implementations. Six independently authored emphasis/code/entity/
  escaped-label controls retained their expected characters while the responsible
  runtime owner repaired dropped `text_special` tokens. No expected preservation
  facts were weakened to match that output.

  Using `C:/Users/stefa/projects/brz2obsidian/.venv/Scripts/python.exe` and
  `PYTHONPATH=<this checkout>/src;<this checkout>`, the final command
  `python -m pytest tests/local_acceptance -q --basetemp=tmp/ml-independent-audit/pytest-final-local --tb=short`
  passed **235** checks in **114.74 seconds**: 115 earlier oracle controls,
  108 v3 controls and twelve driver controls. Semantic corruptions consistently
  rehash actual receipts and update corresponding counts. Changed body text,
  generated order and diagnostic facts can still produce a clean source-free
  checker result; all three are rejected by the raw-source oracle.

  The first full-project command used the unnecessarily long temporary base
  `tmp/ml-independent-audit/pytest-final-project`: **1240 passed, one failed**
  in **238.94 seconds**. The unchanged maximal-name template fixture exceeded
  the existing 240-unit absolute publication guard at that path. Replaying that
  exact test under `tmp/ml-independent-audit/q` passed in **1.31 seconds**.
  No code or expectation was changed for this environment failure.

  The final unchanged full-project command
  `python -m pytest -q --basetemp=tmp/ml-independent-audit/f --tb=short`
  passed **1241** checks in **232.27 seconds**. `python -m ruff check .` passed;
  `python -m ruff format --check .` reports **130 files already formatted**;
  `python -m pip check` reports no broken requirements; `git diff --check` passed.
  All commands used the root project interpreter with this checkout's explicit
  source selection. The worktree contained only intended ticket-06 changes before
  committing this evidence.

  Executed `python -m tests.local_acceptance.run --help` and the documented
  synthetic four-input example in fresh ignored `tmp/audit-synth-02`. All twelve
  exact/repeat/reordered outputs passed with unchanged synthetic fingerprints;
  each has 29 files, five created notes, six exact copies, three gaps, two generated
  embeds and two completely decoded PNG/WebP frames. CLI pins preserve A/B/C and
  require exact original D (320594486 bytes, SHA-256
  `2b24c1d21b4090f3b0ed3ec0227f269b8c7a4e5b6832ada0e244a1dcfc941ced`).
  `run_acceptance(source_paths, output, pins=None)` permits explicit independent
  synthetic pins; the CLI always uses the original pins and verifies selected
  code/current `0.3.0`. Reorder controls reject changed/omitted/duplicated roots
  and physical payloads; a final-drift control rejects after all twelve outputs.

  `decode_image(data, name)` forces BGRA pixels for every accepted frame and
  returns source hash, format/dimensions, codec CLSID/name/version and per-frame
  pixel hashes/decoded lengths. Existing Windows WIC is an explicit native
  dependency. Public PNG and Microsoft Webp codecs report version `1.0.0.0`;
  no codec installation was performed. Strict PNG chunks/CRCs/zlib/scanlines/
  filters/palette/Adam7 accompany native pixels. A two-frame GIF control forces
  both frames. Header-valid compressed WebP and repaired invalid PNG controls
  fail; missing libraries/codecs, allocation/resource limits and unsupported
  required native operations are `AuditUnavailable`, never accepted or mislabeled
  invalid content. APNG strict frame-stream auditing remains unavailable. Native
  pixel production does not claim exhaustive codec conformance or Obsidian render.

  This tooling proof does not claim the four original archives passed, does not
  substitute a recovery export for D and does not complete source/native/user
  acceptance. Those remain tickets 07–09. A public synthetic VP8L sample for
  independent replay is available in `tmp/audit-synth-02/A.brz`, member
  `00000000-0000-0000-0000-000000000005/.data/md-images/z-first.webp`;
  no private sample is needed or exposed.

- 2026-10-06 (/root): Claimed after independently verified tickets 03 and 04
  were integrated. Implement the independent raw-source oracle and four-input
  driver in an isolated managed worktree based on integration
  `4d515a62b2ba6552e8e7ca513615cf1b7ffa839c`. Existing independent decoder research
  and bounded host probe inform the implementation; they do not complete the
  full-source gate, which remains ticket 07.

- 2026-10-06 (/root): Published after the user approved all nine tickets and their
  dependencies, then explicitly invoked implement-spec for complete implementation.
