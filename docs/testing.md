# Testing and acceptance

## Choosing verification

Choose the smallest verification scope that establishes the actual change,
affected consumers and mandatory acceptance criteria. Record the environment,
check IDs, pytest selectors/expressions, required GUI execution and freshness
independently of submitted results. Broaden or repeat checks for new changes,
failures or unresolved concerns. Explicit full-suite, fresh-execution, native and
user acceptance requirements remain mandatory.

Focused or manual-only verification is valid when it establishes the required
scope. Documentation changes need checks of affected facts, commands, links and
workflow rules; unrelated runtime or GUI runs are unnecessary. Required independent
review still applies to manual-only completion.

Public tests use synthetic archives and temporary files, primarily through the
Workflow inspect/convert interfaces and affected public seams. Expected behavior
must come from independently established requirements and source facts. Synthetic
coverage, private source preservation, native observations and user acceptance
each establish different evidence.

## Automated check runner

Run or accept pytest, Ruff lint/format and dependency checks (`pip check`) only
through `tools/check.py`. Use an absolute assessed checkout, its matching runner
and a project `.venv` interpreter. A worktree may reuse another checkout's
interpreter without modifying its installation; serialize package installation
separately. See [README](../README.md) for bootstrap and dependency manifests.

`run` defaults to `pytest`, `lint`, `format` and `dependency`. Repeat `--check`
to select checks and `--test` for repository-relative files/directories or pytest
node IDs. Use `-k` and `-m` for keyword and marker expressions. No pytest selector
or expression means the full configured suite, which discovers `tests/`;
handoff regressions in `.agents/skills/implement-spec-enhanced/tests/` need a
separate focused selection. Invalid, zero-test or entirely skipped selections
do not establish passing pytest coverage.

| Environment | Requirement |
| --- | --- |
| `base` | PySide6 absent; Qt-dependent tests skip |
| `gui` | Pinned `requirements-gui.txt` installed and usable Qt |
| `auto` | Development convenience; records the detected environment |

Completion requirements name `base` or `gui`. The runner supplies offscreen Qt;
`--require-gui` requires actual GUI test execution. A full GUI suite includes
Windows launcher controls; `-m gui` alone is focused coverage.

```powershell
$checkout = (Get-Location).Path
$python = Join-Path $checkout '.venv\Scripts\python.exe'
$runner = Join-Path $checkout 'tools\check.py'
# Focused base pytest plus lint; matches the requirements example below.
& $python $runner run --checkout $checkout --python $python --environment base --check pytest --check lint --test tests/application/test_ui_preferences.py
# Full GUI completion checks, when required.
& $python $runner run --checkout $checkout --python $python --environment gui --require-gui
# Focused Qt adapter checks.
& $python $runner run --checkout $checkout --python $python --environment gui --check pytest -m gui --require-gui
& $python $runner run --help
& $python $runner validate --help
```

Use an interpreter matching each example's environment; establishing both base
and GUI coverage needs separate environments.

Each run creates `tmp/checks/<run>/` with `receipt.json`, logs and isolated caches.
Retain the printed `RECEIPT:` path and outcomes, including failed/interrupted
runs. Keep receipts and logs intact in their original directories; follow
[workspace housekeeping](workspace.md) when retiring temporary evidence.

| Run exit | Meaning |
| --- | --- |
| `0` | All requested checks passed |
| `1` | A tool completed with a failure |
| `2` | Setup/execution error or source changed during execution |
| `3` | Incomplete/interrupted execution |

### Receipt validation

Before accepting automated check claims, validate the receipt against separately
authored requirements. For the focused base example, save this JSON under
`tmp/<effort>/required-checks.json`:

```json
{
  "schema_version": 1,
  "environment": "base",
  "checks": [
    {
      "id": "pytest",
      "scope": "focused",
      "selectors": ["tests/application/test_ui_preferences.py"],
      "keyword": null,
      "marker": null,
      "require_gui": false
    },
    {"id": "lint"}
  ]
}
```

```powershell
& $python $runner validate --receipt 'C:\checkout\tmp\checks\1234abcd\receipt.json' --checkout $checkout --requirements 'C:\checkout\tmp\effort\required-checks.json'
```

Replace the example paths with the actual receipt and requirements paths.
Validation exits `0` for passing evidence meeting the requirements and `2` for
rejection. Text logs or manually written passed values cannot replace validation.
A full receipt covers a focused selector only if its recorded executed tests
prove coverage; keyword/marker requirements need the same executed expression.

Receipts bind execution to the assessed source, runner, environment, selection
and evidence files. Source snapshots include tracked and nonignored new files,
including guidance: an unchanged runtime does not make an earlier receipt bind
to a documentation-only commit. Changes during execution invalidate passing
evidence, including disk changes Git would normalize. A pre-commit receipt may
bind to a clean commit only when the Git-normalized tested contents match.

- `validate --ref FULL_COMMIT` assesses that Git tree instead of current files;
  reference validation requires Git 2.43 or later.
- `--reuse-reason` documents original context and applicability for equivalent
  contents in another checkout. Reuse cannot satisfy fresh-execution requirements;
  independent fresh checks require the verifier's own invocation and receipt.
- `--allow-failed` inspects the integrity of failed evidence for a held verdict;
  it never establishes passing completion.

The runner requirements schema requires a nonempty `checks` array. Manual-only
structured handoffs use a different schema that allows an empty array; their
stage requirements and publication procedures belong in the existing
[handoff contract](../.agents/skills/implement-spec-enhanced/references/handoffs.md).

Direct covered-tool execution is allowed only for runner bootstrap or a concrete
runner failure preventing necessary evidence. Record the reason, exact command,
interpreter, checkout and outcome as diagnostic evidence. After repair, obtain
qualifying completion evidence through the runner and validate it. Package
installation/builds, private acceptance drivers and native observations use
their own routes.

CI in `.github/workflows/checks.yml` runs full Windows base and GUI checks and
retains runner receipts/logs. Both job results and receipts validated against
independent requirements establish hosted acceptance. Offscreen GUI success
leaves actual Windows appearance, native dialogs and pointer usability unverified;
private preservation and user acceptance retain their separate gates.

## Stable-candidate checkpoint

For candidate completion, finish affected focused checks, resolve known findings
and synchronize integration before committing stable source in a clean checkout.
Record the full commit ID, run the required completion checks and validate their
receipts against that candidate. Keep source unchanged through publication.
Focused success cannot replace required full coverage.

A repair produces a new stable candidate. Reassess evidence against the new
source and requirements, rerun affected checks and every check requiring fresh
execution, and obtain required independent verification. Preserve earlier
receipts with their original source and outcomes; explicitly justify permitted
reuse. A later passing run does not erase an earlier failure.

## Preservation and package checks

When full-export acceptance is required, use `tests.local_acceptance.run`. Its
CLI requires five exact fingerprinted originals (A–E), creates fifteen complete
exact/repeat/reordered outputs, refuses an existing output directory and checks
source fingerprints throughout. Pins are maintained in
`tests/local_acceptance/run.py`; recovery or re-export substitutes do not qualify.
Use a fresh short ignored destination:

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = (Join-Path $checkout 'src') + ';' + $checkout
& $python -X utf8 -m tests.local_acceptance.run --source-a 'C:\exports\A.brz' --source-b 'C:\exports\B.brz' --source-c 'C:\exports\C.brz' --source-d 'C:\exports\D.brz' --source-e 'C:\exports\E.brz' --output (Join-Path $checkout 'tmp/audit-01')
```

Use the checkout/interpreter variables above and substitute the exact original
paths. The independent audit derives preservation expectations from raw records
and archived bytes. Its image checks require Windows WIC and usable codecs,
including WebP; missing decoding capability yields `AuditUnavailable` and leaves
image eligibility unverified. Synthetic driver runs do not establish private
archive acceptance.

The source-free `check_vault` convention checker does not establish migration
preservation; its findings and a source-bound preservation verdict remain
separate. Native handling of preserved file-image URLs is still unverified;
the affected E sample remains held until an explicit automatic-load guard exists.

For affected packaging or executable-example changes, verify wheel contents,
metadata/entry points and execution of the documented examples. Use synthetic
inputs and independently expected outputs. These checks leave native rendering
and user acceptance to their applicable gates.

## Visual sampling policy

Use strategic sampling of actual output for visual/native review. Application UI
and approved generated presentations follow the
[presentation procedure](agents/accepted-presentation.md); source diagnosis or
content retrieval follows [bounded native investigation](agents/native-investigation.md).

1. Before using the app, identify each distinct behavior, control type, styling
   context and relevant state, including hidden/overflow controls. Select
   representative cases, combining equivalent behaviors where practical. Record
   references, independently derived sample paths and planned observations.
2. Compare actual appearance and exercise interactions, revealing hidden controls.
   Include relevant enabled/disabled, focus, hover and expanded states. Observe
   scrollbar track/thumb contrast and drag the actual thumb; exercise wheel and
   keyboard access where applicable. Offscreen drawing or scroll reachability
   alone does not establish native appearance or pointer usability.
3. Record satisfied/failed/unverified status, evidence, covered requirements and
   limits. Reuse observations only while output/context remain applicable. Expand
   around defects, uncertainty or meaningful differences; repair and recheck
   affected failures. Complete only when every required group and selected
   behavior has applicable observations.

Use fresh copies of actual generated vaults, preserve pre-interaction inventories
and hashes, and record the observed app version. Verify each imported sample's
included identity, assigned target and file existence before opening it. Inspect
intentionally uncreated targets through links/listings; creating a missing note
is a separate deliberate test. Compare sampled Base results with independently
expected membership. Verify preserved external destinations without fetching or
opening them. For editing/read-only controls, compare applicable before/after
inventories and bytes; keep originals, baselines and normal user vaults intact.

The current local Windows UI review uses 100% scaling only; leave the normal
system setting unchanged. Sample narrow windows, long paths/findings, stacking,
scrolling, keyboard access and a usable footer. Observe the actual task-sheet and
diagnostic scrollbars independently at that scale.

Actual local-build acceptance also samples two launches, window restoration or
attention, unchanged active inputs, a fresh launch restoring only the output
parent folder, one corrupt preference case and an idle test-owned crash/stale
relaunch. Preserve existing preference bytes and record source/environment and
observations. Never terminate
an active conversion or user-owned process for these controls.

Sampling leaves required complete source/body/image/inventory/preservation audits
at their full scope. Report observed coverage separately from extrapolated
confidence. Keep any required user's actual-vault or running-app verdict as its
separate completion gate.
