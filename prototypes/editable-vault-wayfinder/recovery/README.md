# Recovery direction and interrupted latest Undo — #249

This bounded follow-up asks whether a persisted operation can distinguish applying,
latest Undo, finishing recovery and restoring recovery after a real process stops.
It extends the engineering evidence for the accepted GIT-B01–B03 behavior, without
implementing an application feature or replacing the human verdict.

From the project root in PowerShell:

```powershell
.venv/Scripts/python.exe prototypes/editable-vault-wayfinder/recovery/experiment.py --help
.venv/Scripts/python.exe prototypes/editable-vault-wayfinder/recovery/experiment.py
```

The focused stale-review repair has its own bounded command:

```powershell
.venv/Scripts/python.exe prototypes/editable-vault-wayfinder/recovery/refresh_evidence.py --help
.venv/Scripts/python.exe prototypes/editable-vault-wayfinder/recovery/refresh_evidence.py
```

The second command generates fresh repositories only below
`tmp/merge-wayfinding/followups/recovery/<run>/`. It prints the report path, elapsed
time and experiment source hash. `results.json` retains the executed fresh-process
commands and all observations. `expected-before-run.json` is written before any
repository is initialized and contains literal expected bytes, transitions and
next actions. Nothing is deleted except one explicitly identified converter-only
loose blob in the disposable missing-preimage fixture.

Prior assessed run before the stale-review repair on 2026-10-21:
`tmp/merge-wayfinding/followups/recovery/20261021-121901-712f3a00/`.
All 47 explicitly stated observations passed in **159.091 seconds** on Git
`2.55.0.windows.5` and Python `3.14.8` through the project `.venv` interpreter.
The experiment SHA-256 is
`e71a56f3f92d27bd7e18495ad183b54c24bf11446113f0eca4953b810f965ea7`.
The report maps all five #249 acceptance criteria to evidence; independent review
and coordinator integration remain required. An earlier run stopped during
missing-object fixture setup because Windows marked the loose object read-only;
the final source clears only that one owned fixture object's bit before removal.

The original prototype stays unchanged. This script loads its plumbing read-only
with `git show` from local commit
`273233fb4020ceb156ed6b3ab33785adcedfdda9`, path
`prototypes/editable-vault-wayfinder/git/experiment.py`, and verifies SHA-256
`fddfe131e1d0ad791abdcaeb2939a2c51311a95143fe80f81f0c0771664be6df` before use.
It reuses only the controlled Git environment, generated fixture repository,
owned-path guard, raw-blob/isolated-index snapshots, inventory/user-state helpers
and bounded preflight. Its output boundary and ref namespace are replaced in the
in-memory imported module. The original prototype's worker/state machine does
not run. No project-checkout Git mutation, retained vault/archive, network access,
production test or broad regression suite is involved.

## Executed scenario design

| Scenario | Real stop and independently expected recovery |
| --- | --- |
| Partial latest Undo | First complete a reviewed apply. Add author writing to B, then explicitly review keeping the whole B note while reversing A/C. Stop a child after A is reversed, add later writing to A, and restart in a fresh process. Finish reverses eligible C, preserves A/B and requires review of later A. Explicit keep-later review completes as `undone`. B retains both its imported source change and author writing. |
| Partial finish recovery | Stop apply after A. Add later A writing, then select finish and stop a second child after B is published. Add later B writing. Restart offers only continuation of saved finish, refuses an opposite-direction request and a stale generation, completes eligible C, and requires review for A/B. Reviewed completion reports `applied`. |
| Partial restore recovery | Stop apply after A/B. Select restore and stop a second child after A is actually reversed. Add later B writing. Restart offers only continuation of saved restore and refuses finish/stale-generation requests. C remains its preimage; B is preserved for review. Reviewed completion reports `restored`, never `applied`. |
| Unavailable indispensable preimage | After partial apply, remove A's unique converter-only preimage blob from the fresh repository. Fresh inspection and both recovery choices report `recovery-required` with the missing object. Import/onboarding remain blocked; no operation files, refs, metadata, normal index/HEAD/branches/tags/config or objects are changed by those attempts. |
| Changed effective storage policy | After partial apply, bind an encryption-filter attribute through a controlled external attributes file and configure a controlled sentinel filter. Fresh workers refuse C06 before any history/file mutation or sentinel execution. The incomplete manifest is retained; import/onboarding cannot bypass it. |

Every normal stage records full file inventories (SHA-256 and byte count), literal
affected-file bytes as hex, the persisted manifest, converter refs, required-object
reachability and normal Git state. Normal Git evidence includes HEAD bytes and OID,
exact index hash, staged blob/mode/path entries, branch/tag refs and config hash.
An ignored authored note/cache remain outside converter snapshots. Both changed
policy and missing-preimage injections are fixture setup; comparisons around the
subsequent refusals establish that those operations make no further changes.

## Candidate state contract

The manifest stores schema, operation identity and kind (`apply`/`undo`), generation,
phase, explicit direction, reviewed path versions, source/pre/result commit IDs,
protected paths and terminal outcome. Each manifest update increments generation.
Metadata commits have real parent edges to the indispensable snapshot commits and
previous operation manifest. The manifest is retained by an owned Git ref;
object IDs in JSON alone are not treated as reachability.

| State | Supported next action in this bounded mechanism |
| --- | --- |
| `reviewed` | Run the fully reviewed apply or Undo after checking current bytes and generation. |
| `publishing` after a stop | Review a choice to finish the current operation or restore its pre-operation bytes. |
| `recovering` with saved finish/restore | Continue the saved direction. A conflicting direction or stale generation is refused without mutation. |
| `review-later-edits` | Explicitly review keeping the protected current whole files; changed review assumptions must be reviewed again. |
| `review-later-edits` with subsequently changed inputs | `review-keep` refuses stale assumptions without mutation. Fresh inspection offers executable `refresh-review`; that action captures current assumptions/changed paths and advances generation without publishing or approving files. A separate current-generation `review-keep` is required. |
| Missing history or incompatible effective policy | Resolve that prerequisite; recovery remains required and new import/onboarding stay prohibited. |
| Complete | Report `applied`, `undone` or `restored` according to the actual operation/direction, together with reviewed retained files. |

A stopped restore can already have reversed some paths; its direction cannot be
inferred from current bytes. Direction and generation are persisted before the
first replacement in that direction. A restore completed with explicit keep-later
choices is a reviewed restoration result, not a claim that every file equals the
old checkpoint. It can retain imported changes inside a kept whole note, as the
accepted preservation behavior allows.

Missing-preimage refusal deliberately does not try to rewrite a journal whose
history is damaged. The persisted manifest stays incomplete with its original
direction/generation; every new process derives `recovery-required` and the same
missing prerequisite from that durable state. No fresh onboarding fabricates a
pristine baseline or erases the recovery obligation.

Independent review found that the initial candidate correctly refused a keep
after another edit during recovery review, but had no executable way to renew
that stale review. The repair adds `refresh-review` rather than treating the
stale keep as approval. Refresh preserves kind, saved direction, all vault bytes,
normal Git state and required history, and keeps import/onboarding blocked.
Old-generation requests cannot approve the new assumptions. Only a separate
explicit keep completes eligible recovery, after which ordinary preparation can
continue. The focused driver exercises this shared transition for finish,
restore and latest-Undo finish; the earlier 159-second suite is retained under
its original source hash rather than blanket-repeated.

Observed focused repair run on 2026-10-21:
`tmp/merge-wayfinding/followups/recovery/refresh-repair-20261021-123052-197587ef/`.
All **45 focused observations** passed in **129.404 seconds**. The repaired
`experiment.py` SHA-256 is
`14dfb0078fa7f30ab90eca1f2e9f5de66ce7b188a0188fc0d0afa5309eebabc3`;
the `refresh_evidence.py` SHA-256 is
`d55a1805eca9612cea9eee3c5ab4d6ec091ad919cae17c36c43e47ed47f0a282`.
Finish and restore advance generation 4 → 5 on refresh, then 6 on explicit keep;
the interrupted Undo case advances 7 → 8 → 9. In every case the stale keep and
old-generation keep refuse without mutation; refresh changes only owned operation
metadata, leaves vault/user Git state unchanged, and preserves the incomplete gate.
Independent review must assess the repair and reuse of the earlier evidence.

## Recommendations and retained limits

For #247, require a versioned persisted distinction between operation kind,
execution/recovery direction, generation and terminal outcome. Retain indispensable
versions through actual Git graph edges; validate their availability before any
recovery mutation. Tie requested actions to the reviewed generation, persist a
direction before publishing, and return truthful next actions on restart.

Require both import and onboarding entry points to honor the same incomplete-
operation gate. Preserve later bytes and recheck reviewed resolution assumptions.
When those assumptions become stale, expose an executable, publication-free
refresh transition and require a new explicit resolution against its generation.
Policy/history refusals must retain that gate and must not invoke custom programs
or rewrite user Git state. A completed restore must not be reported as an applied
update; expose reviewed retained files so its remaining imported changes are clear.

This is bounded executable evidence on controlled ordinary repositories and one
installed Git executable. It does not establish power-loss/fsync durability,
production I/O-failure handling, locking/concurrent writers or changes racing
after preflight, complete inherited-policy/layout detection, arbitrary history
corruption recovery, history-copy restoration, structured/native link semantics,
large-scale behavior, UI design or a supported Git-version range. Missing history
restoration and other follow-ups have separate owners. No observed contradiction
of the accepted behavior/policy is inferred from those unexecuted areas.

The observations need independent review before the coordinator records issue
completion and source integration. The script supplies no closure verdict.
