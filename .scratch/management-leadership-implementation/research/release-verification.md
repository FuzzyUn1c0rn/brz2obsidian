# Release verification candidate

Date: 2026-10-06
Status: partial — independent final review, actual-vault user verdict and delivery pending.

This record aggregates completed technical evidence for the 0.3.0 candidate.
It does not declare delivery, acceptance or publication. Public guidance/package
verification ran from integration ancestor
`d057533b1025d2d68ef90ec989dfb52cd3abeb68` on `codex/ml-v3-09`.
The candidate changes guidance/evidence only: runtime, tests, dependency manifests
and build configuration are unchanged. The final independent review must record
its own fixed candidate tip, findings and any resulting repairs.

## Public and environment gate

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

## Final wheel and documented examples

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

## Source and native gates retained

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

Independent Standards/Spec review of the full implementation, resolution of any
material findings, the user's actual verdict on the exact clean actual output,
and the final delivery record remain pending. No agent/native/source/checker
PASS substitutes for the user verdict. Repairs that change content, paths or
contracts must refresh affected source/native/package/public proof and any
invalidated user review before delivery can be marked complete. Recovered or
re-exported archives remain separately fingerprinted acceptance inputs.
