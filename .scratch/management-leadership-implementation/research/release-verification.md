# Release verification candidate

Date: 2026-10-06
Status: technical gates passed — actual-vault user verdict and delivery pending.

## Current repair boundary

The full-implementation independent Spec review at frozen integration
`5f971b96500a33d58ec09f4d9bd6c2d08f9a8cde` reported no actionable findings.
Standards retained its original optional P3 observation and subsequently confirmed
one material P2: excluded-reference removal accepted padded compact authorities
before the normal reference binder could reject their unsupported syntax.
These are separate review conclusions; Spec's zero does not erase the P2.

The isolated repair validates the reviewed compact-reference boundary before
identity-based removal, sharing the existing binder validation rather than
permissively decoding another copy. Five public inspect/convert regressions cover
one/two padding and padded query, missing-path and fragment variants. Each requires
private refusal, no receipt/destination and unchanged synthetic source. RED was
five failures (unexpected clean); GREEN five passes. The affected source/workflow/
architecture selection passed 171 tests; alternate-source controls passed 37;
selected Ruff check/format passed. Original reproduction and RED/GREEN command,
import and file-hash evidence are retained in root
`tmp/ml-implementation/09/worker-evidence-b4a3743/reference-repair/` (`repro.json`, `red.log`, `green.log`, `affected.log`,
`alternate.log`, `repair-proof.json`).

## Repaired-runtime public/package gates

Independent repair verification passed at
`fc1685aaea691bff47fa47408d37c78b7188f94c`: 13 independent synthetic controls
and 35 public inspect/convert operations. The repair was integrated into frozen
root `b4a3743ff98656934b6e7075ceaae4caf824405a`; both review axes and their
separate conclusions/limits are recorded in [final review](final-review.md).

At that root tip, the fresh complete command
`.venv/Scripts/python.exe -m pytest -q --basetemp=tmp/r10` passed
**1,513 tests in 295.57 seconds**, exit 0. Ruff check passed, format check
reported **133 files already formatted**, and pip check passed. Root proof is
`tmp/ml-implementation/09/repaired-regression-command.json`,
`repaired-regression.log`, `repaired-regression-exit.txt`,
`repaired-style-env.json`, `repaired-{ruff-check,ruff-format,pip-check}.log`.

The new `repaired-runtime-before.json` was captured **before launch**;
`repaired-runtime-after.json` was captured after suite completion. All **136
tracked runtime/test/build inputs** match each other and the isolated package
checkout. The isolated verifier retained its initial before-only comparison and
added `tmp/10/post-suite-input-proof.json` rather than overwriting that history.
The selected interpreter remains root `.venv/Scripts/python.exe`, CPython 3.14.8;
worktree imports use explicit `PYTHONPATH=<worktree>/src;<worktree>`.

The fresh build at clean `b4a3743` used
`-m pip wheel --no-deps --no-build-isolation --wheel-dir tmp/10/wheels .`.
Its 0.3.0 wheel SHA-256 is
`7959117dd8c76803f6c4fa3e9a53f79d690f9558e274246bae95012b9e499089`.
All **57 runtime modules** equal source bytes; all **62 RECORD rows** match
wheel inventory/digests/lengths. Remaining entries are distribution metadata;
private, test, development and prototype files are absent.

The actual README library example, both architecture examples and checker
snippet passed against fresh combined synthetic v3 input. Each conversion
published a verified 36-file receipt with complete physical byte inventory.
The same three literal conversions ran in processes explicitly importing the
wheel. **18 actual console/module/wheel text/JSON inspect/convert/check-vault
operations** passed: warning exits 2/2 and pristine checker exit 0, correct
versioned JSON, no inspection receipt/actual-generated counts, three gaps,
one presentation and two actual generated embeds. Checker/source guards passed.
Package/converter stays 0.3.0; contracts/profile/renderer/result/record 3,
BRZ 5, checker 1. Declared target metadata remains 1.13.7, separate from observed
native 1.14.4. No environment install or retargeting was performed.

Fresh ignored release-worktree proof: `tmp/10/{build.log,package-smoke.log,
final-smoke.log,final-package-proof.json,wheel-integrity-proof.json,
post-suite-input-proof.json,wheels/}` and synthetic outputs `tmp/s10/`.
Root retained exact copies of the current ignored proof under
`tmp/ml-implementation/09/worker-evidence-b4a3743/`: `reference-repair/`
(88 files), `package-proof/` (15 files) and `package-outputs/` (469 files).
Its `retention-receipt.json` verifies every retained byte; these copies survive
release-worktree retirement. Original isolated paths remain execution provenance.
Root independently corroborated wheel/source/RECORD, all 136 inputs, the 18
operations, three physical JSON receipt joins and six documented conversion
executions in `tmp/ml-implementation/09/repaired-package-independent.json`.

Ticket 09's full-public and package criteria are again satisfied for this exact
repaired runtime. Independent final review and the fresh source/native retention
gates described below are also satisfied. The user verdict and aggregate
delivery remain unchecked. The isolated package verifier did not
access private originals, audited outputs or the user review copy.

## Repaired-runtime original-source and native retention gates

The fresh m6 driver completed all **12 exact/repeat/reordered outputs**, and a
separate complete raw-source/result/receipt re-audit passed, exit 0, at frozen
clean root `b4a3743ff98656934b6e7075ceaae4caf824405a`. Reordered-source
record/payload proofs and all repeated/reordered logical output comparisons
passed. Every one of the **7,029 matrix files**, all **four original source
fingerprints** and all **562 retained-vault files** remained unchanged under the
complete before/after guards. Runtime/oracle/driver bindings and frozen input
bytes were verified. D's 359 bodies, 63 image obligations, 47 definitions/330
members and full supplied-content/privacy/ownership/graph obligations passed
independent raw-source joins rather than matching aggregate totals alone.

The independent verifier command, with root project interpreter, explicit
`PYTHONPATH=<root>/src;<root>` and no bytecode, was:

```powershell
.venv\Scripts\python.exe -B tmp/ml-implementation/07/verifier-audit-m6.py --stable-authorized --expected-head b4a3743ff98656934b6e7075ceaae4caf824405a
```

Root ignored proof: `tmp/ml-implementation/07/m6-independent-gate.md`,
`m6-matrix.log`, `m6-matrix-exit.txt`, `verifier-audit-m6.log`,
`verifier-audit-m6-exit.txt`, `verifier-report-m6.json`,
`verifier-matrix-inventory-m6.json`, and actual outputs under `tmp/m6/`.
The original m5 verifier/matrix remain immutable historical evidence.

Independent complete native-facing equivalence passed at the same root pin:
all **2,337 exact-original output files** compared, **2,329 byte exact**, and
only eight records/bookmarks differing by individually checked clock scalars.
The exact mask is `/run_metadata/run_id`, `/run_metadata/run_time`,
`/run_metadata/bookmark_time` in each migration record and `/items/0/ctime` in
each bookmark. No other field, source fingerprint/evidence, body, title, link,
provider/member join, property/date, count or artifact byte was normalized.
All Markdown, assets/originals, Bases, templates, report/guide, CSS/plugin
artifacts and required delivered configuration retain their actual bytes.

The existing n3 native copies also match their immutable final ledgers and m6:
shipped non-config content is exact, the record/bookmark clock mask is unchanged,
app serialization retains equal values, core-plugin values agree and previously
recorded native defaults/additions remain unchanged. Complete m5/m6 inventories,
every n3 file, native ledgers and 136 runtime inputs survived the read-only gate.

```powershell
.venv\Scripts\python.exe -B tmp/ml-implementation/09/native-equivalence/check_equivalence.py --stable-authorized --expected-head b4a3743ff98656934b6e7075ceaae4caf824405a
```

This used explicit root `PYTHONPATH` and `PYTHONDONTWRITEBYTECODE=1`. Proof:
`tmp/ml-implementation/09/native-equivalence/{report.md,equivalence-proof.json,
equivalence.log,equivalence-exit.txt}`. Under the persisted strategic sampling
policy, the new material visual sample list is empty. This supports reuse of
[existing actual-output native observations](native-v3-acceptance.md), not a
new UI session or blanket per-item visual coverage. Observed Obsidian 1.14.4,
CLI-disabled, sampling and CSV correspondence limits remain explicit.

The coordinator prepared the guarded clean actual user review copy at root
`tmp/u4/Leadership` from fresh m6 D: all **1,552 files** were byte exact before
any app interaction (`tmp/ml-implementation/09/final-user-copy-receipt.json`).
Earlier `tmp/u3/Leadership` remains untouched. The actual user verdict is still
pending. No agent, convention checker, source audit or native-equivalence
PASS supplies that verdict or authorizes publication/delivery.

The following pre-repair sections remain historical. Their earlier 136-input
comparison and old wheel/example proof do not certify the repaired runtime.

## Pre-repair candidate evidence

This record aggregates completed technical evidence for the pre-repair 0.3.0 candidate.
It does not declare delivery, acceptance or publication. Public guidance/package
verification ran from integration ancestor
`d057533b1025d2d68ef90ec989dfb52cd3abeb68` on `codex/ml-v3-09`.
The candidate changes guidance/evidence only: runtime, tests, dependency manifests
and build configuration are unchanged. The final independent review must record
its own fixed candidate tip, findings and any resulting repairs.

## Pre-repair public and environment gate

The complete public suite ran in the root project environment at
`91706941877ad71fb9087debee791f5a6bbc9ec4`: **1,508 passed in 293.16 seconds**, exit 0.
The actual commands were:

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=tmp/r9
.venv\Scripts\python.exe -m ruff check --no-cache .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pip check
```

Ruff check passed, format check reported **133 files already formatted**, and
pip check reported no broken requirements. Native Windows CPython **3.14.8**
used the root `.venv/Scripts/python.exe`.

The isolated package verifier compared all **136 tracked runtime, test,
pyproject and requirements files**, their lengths and SHA-256 hashes, with both
root regression snapshots (the first captured during the running suite, the
second after completion). Every candidate input matches both snapshots.
Accordingly the completed full gate remains applicable; no broader rerun was
needed for guidance edits. Any subsequent runtime/test/config repair requires
affected verification and reconsideration of this exact-input reuse.
Root ignored proof: `tmp/ml-implementation/09/regression-runtime-{before,after}.json`,
`regression.log`, `regression-exit.txt`, `regression-execution-head.txt`,
`ruff-check.log`, `ruff-format.log`, `pip-check.log`.

The coordinator refreshed the existing root editable distribution from stale
0.2.0 metadata to **0.3.0**, using
`.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .`.
Its root binding, all third-party non-bytecode package files and versions, and all 57 runtime module
bytes stayed unchanged. `editable-refresh-proof.json` and `editable-refresh.log`
retain that separate environment proof. A fresh post-refresh pip check also
passed, exit 0 (`pip-check-refresh.json`). The isolated verifier did not install,
retarget or mutate this environment; it selected its worktree using explicit
`PYTHONPATH=<worktree>/src;<worktree>`.

## Pre-repair wheel and documented examples

Build: root project interpreter, from the isolated checkout,
`-m pip wheel --no-deps --no-build-isolation --wheel-dir tmp/09/wheels .`.
The resulting `brz2obsidian-0.3.0-py3-none-any.whl` SHA-256 is
`e336365b2f77d7c474264eb61eb29619ca860ba581e03e88ae0c1ef70b93a4ce`.
All **57 runtime Python modules** match the selected source bytes exactly;
all remaining wheel entries are 0.3.0 distribution metadata. No private,
development, test or prototype artifact is distributed. Package metadata and
console entry point agree with documented installation guidance; the wheel
was exercised directly without installing it or creating another environment.

The actual README library example, both architecture examples and the checker
library snippet passed against a fresh combined synthetic v3 archive.
Each of the three conversion examples produced **36 files** with a verified,
published receipt whose relative inventory, lengths and hashes equal physical
output. Each current vault checker result was clean. The same three literal
conversion examples also ran in separate processes whose selected import path
was explicitly inside the wheel.

**18 actual CLI operations** passed: installed console, Python module and
direct-wheel module, each in text and JSON, for inspect, convert and check-vault.
Inspect/convert truthfully returned warnings/exit **2**; pristine checking returned
clean/exit **0**. JSON inspection had no receipt and unknown actual generated
counts; it exposed three source gaps and one generated presentation. Conversion
verified 36 actual files and two generated embeds. Checker operations preserved
full output inventory/bytes. Synthetic source bytes stayed unchanged.

Observed versions agree: package/converter **0.3.0**; snapshot/policy contract,
source module/profile, renderer, result and record **3**; BRZ format **5**;
source-free checker **1**. The renderer still declares **1.13.7** target metadata;
this is distinct from the actual native application's observed **1.14.4**.

Private proof in the isolated release worktree is ignored under `tmp/09/`:
`package_smoke.py`, `package-smoke.log`, `final_smoke.py`, `final-smoke.log`,
`final-package-proof.json` and `wheels/`. Synthetic outputs are in `tmp/s9/`.
The JSON captures interpreter/import bindings, distribution versions, actual
commands/outcomes and regression-input comparison. Those disposable scripts are
verification records, not new production or reusable test interfaces.

## Source and native observations retained

The [complete independent four-original matrix](four-archive-preservation.md)
passed at frozen runtime `e2c5fc3f05d2daa0d0547d2bbaa2b12557a248b5`:
12 raw-source/result/receipt audits, four reordered-source proofs and eight
logical output comparisons, with all **7,029 files** preserved. Original D
retained 359 supplied bodies, 63 fallback images, 47 definitions/330 members,
1,017 present payloads, 1,552 actual files and 93 warnings. Four original archives
and 562 retained-vault files remained unchanged. No private subject identifiers,
assets or screenshots are published here.

[Actual-output native review](native-v3-acceptance.md) passed using strategic
behavior sampling in observed Obsidian **1.14.4**, with CLI disabled. It includes
all 47 D category contexts/330 memberships, the native C 145-member CSV proof,
image cards/chart/layout-A notices, hierarchy, earlier-source controls,
maintenance/template/rename/provider/date/identity/body observations and 45
read-only checker operations. Native coverage limits remain explicit there.
Root-retained ignored native evidence is under
`tmp/ml-implementation/08/native-evidence-7cb3ed25/`; source proof remains under
`tmp/m5/` and `tmp/ml-implementation/07/`.

Guidance now points to current v3 proof, distinguishes historic v2 totals,
includes implemented inspection/record collections and counters, and qualifies
safe exact originals. Default exclusion, present-body precedence, unknown absent
prose/captions/layout, neutral type icons, independent hierarchy/membership,
optional source investigation and checker/preservation limits remain explicit.
The untouched clean actual user review copy awaits the user's verdict; this
package work neither opens nor mutates it or any private original/retained vault.

## Remaining delivery gate

The technical candidate has complete independent review/repair verification,
fresh public/package/source proof and native retention against runtime
`b4a3743ff98656934b6e7075ceaae4caf824405a`. The user's actual verdict on the
exact clean actual output and the final aggregate delivery record remain pending.
No agent/native/source/checker PASS substitutes for that verdict. Any later
material output repair must refresh affected proof and invalidated user review.
Recovered or re-exported archives remain separately fingerprinted inputs.
