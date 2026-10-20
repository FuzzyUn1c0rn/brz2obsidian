# Executable Git/history experiment for #244

This throwaway experiment asks whether converter-owned Git history can retain
source/vault versions and recover a partly published update while preserving an
author's staged work, HEAD and branches. It accompanies the entirely synthetic
[`index.html`](index.html) walkthrough. Neither artifact implements an application
update feature, establishes a supported Git range, or supplies the human verdict.

Run from the checkout root in PowerShell:

```powershell
.venv/Scripts/python.exe prototypes/editable-vault-wayfinder/git/experiment.py
```

The command prints a new run directory and its `REPORT.md` and `results.json`.
Every run creates fresh synthetic repositories beneath
`tmp/merge-wayfinding/git/experiments/<run>/`. Nothing is deleted. The runner never
uses this checkout or a supplied vault as an experimental Git repository. Worker
commands require an existing run ownership marker and a repository under that
absolute output boundary. No packages are needed beyond the standard library and
the installed Git executable.

Observed final-source run after the independent-review repair on 2026-10-20:
`tmp/merge-wayfinding/git/experiments/20261020-212847-d8cfe087/`.
Its recorded synthetic outcomes passed in **81.107 seconds**. The source SHA-256 is
`fddfe131e1d0ad791abdcaeb2939a2c51311a95143fe80f81f0c0771664be6df`.
The 120-note/two-256-KiB-revision measurement took 8.649 seconds for the first
snapshot and 7.543 seconds for the changed snapshot; loose objects occupied
537,484 bytes. These are observations from one bounded run, with the limits below.

## What the experiment actually executes

1. Create independent user history, a second branch, a tag and an inert remote.
   Stage one version of A, then edit A again without staging. Add untracked authored
   content, ignored authored content and an ignored cache. Record the exact normal
   index hash, staged entries, HEAD bytes/OID, branch/tag refs and config hash.
2. Store exact blobs with `hash-object --no-filters`, write snapshot trees through
   `GIT_INDEX_FILE`, and use `commit-tree` plus compare-and-swap `update-ref` under
   `refs/brz2obsidian/prototype/`. Source and vault chains are distinct. Versioned
   review/operation metadata lives in Git. Its commit parents retain the required
   source/preimage/result commits; textual object IDs alone are not retention.
3. Persist `review-saved`, then start a subprocess which persists `applying`,
   physically replaces A (finish case) or A/B (restore case), and exits immediately
   with code 73 **before any per-file progress journal**. The parent edits A after
   the exit. Another fresh Python process reopens the Git manifest and classifies
   affected file bytes as before/result/diverged. New preparation is blocked.
4. A further fresh process finishes or restores eligible B/C files, while retaining
   A's later bytes and persisting `recovery-review`. In the restore case B really
   contained published result bytes and is reversed to its preimage. A stays
   unresolved. A synthetic explicit keep-later-edits review then completes the
   finish case and records the actual accepted vault result.
5. Edit B after completion. Prepare latest-operation Undo: it writes its review
   metadata and changes no vault files. A synthetic explicit whole-Undo decision
   retains later B edits and reverses eligible A/C. No reset, checkout, stash,
   user-branch update or normal-index rewrite occurs.
6. Exercise controlled text merging with real `git merge-file`; raw round trips
   for mixed endings, UTF-16/BOM, ident and binary bytes; explicit tiny binary
   keep-both/link changes; Git-persisted review assumptions; real meaningful
   checkpoint suppression; simple identity/keep-vault/format decisions; controlled
   exclusion and storage-policy refusal probes; and a bounded binary measurement.

The report's “PASS” means that the explicitly recorded synthetic observations
matched their independently stated outcomes. It is **not** a production acceptance
verdict or a statement that every accepted compatibility row is implemented.

The exact inventories, commands/exit codes, manifests, converter refs and user
Git states are retained in `results.json`. “before” and “after” inventories contain
SHA-256 and byte counts, not just Git status summaries. The disposable repositories
retain the actual blobs and index for inspection. The `reconciliation.cases`
records distinguish real Git merging from small Python policy/identity decisions.
The legacy-baseline decision is logic-only: no history restore or native Sync
operation was attempted.

## Evidence and boundaries

The installed executable observed here is Git `2.55.0.windows.5`; the generated
report records its executable path and the Python interpreter. Each repository
starts with an empty controlled template and empty host-global/system Git policy.
Only synthetic fixture configuration is changed, inside the newly generated
repositories. This makes the experiment bounded; it does not exercise the user's
actual inherited configuration. A controlled external attributes file and external
ignore file exercise effective-rule discovery through Git. Filter/LFS/custom-driver
and active-reference-hook fixtures are refused before converter blobs or refs are
written; their controlled sentinel programs are never run. There is no generic
filter/hook bypass choice.

Independent review found that sharing the built-in merge-driver names with diff
attributes incorrectly allowed named `diff=union` plus a configured textconv
command. The repaired candidate treats merge and diff attributes separately.
Controlled `diff=union`, `diff=text` and `diff=binary` textconv fixtures require
C08 refusal. This does not establish a complete production policy detector.

Every mutating worker also repeats the bounded preflight before writing history
or files. Fresh-process fixtures introduce an active reference hook or named diff
textconv **after** saving review, then attempt all six mutating worker actions.
They must refuse without changing files, user Git state, owned refs, objects or
saved status, and without executing the sentinel. This closes that observed
saved-review gap; changes racing after worker-entry preflight remain unverified.

Built-in transformations require the separate exact-byte policy agreement. The
experiment demonstrates a refusal without that choice and raw round trips with
the choice. It does not claim every encoding can be edited or automatically
merged. A changed controlled policy fingerprint invalidates its saved agreement.
Repository/global exclusions are respected; changing an excluded authored file
requires a specific named inclusion choice. That choice adds it only to the
converter snapshot, preserving the user's staged selection. Unrelated excluded
files remain a disclosed recovery gap.

The generated `support_evidence` table maps **every C01–C17 and H01–H09 row** from
the [accepted policy](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/248) to
observed, refused, logic-only or unverified evidence. This is an evidence table,
not a replacement support policy. There is no observed contradiction requiring a
policy revision. Unverified engineering questions remain open with #244/#247;
their affected implementation specifications must not claim readiness from this
prototype.

In particular, there is no evidence for power loss/fsync durability, concurrent
edit races or complete locking, real attachment/link resolution in Obsidian,
structured frontmatter reconciliation, missing/damaged history restoration,
copy/clone/Sync portability, cleanup/GC, advanced/shared/sparse/partial layouts,
arbitrary host hook/filter policy, filesystem collisions/reparse races, disk-full,
large exports, cancellation, or a maintained supported-version range. The small
worker supports the observed applying/recovery seam; an interruption during Undo
is **unverified**, and this candidate must not be treated as a complete recovery
implementation.

The measurement uses 120 synthetic notes and two distinct 256 KiB binary revisions,
records elapsed snapshot time and actual loose-object storage, and performs no GC.
It establishes a measured tiny envelope only. Warm caches and subprocess overhead
may affect it. Larger-file/real-export behavior remains unverified.

## Candidate public outcomes for specification discussion

These are recommendations for #247, subject to the human behavior verdict and
further engineering evidence:

- Preparing an operation returns either a complete review, a meaningful no-op,
  a concrete compatibility/storage-policy refusal, or `recovery-required`. Existing
  incomplete operation state takes precedence over a new update/onboarding.
- Saved review records source collection/item identity, source bytes and profile/
  format, affected current paths/bytes, history generation and effective storage
  policy assumptions. Reopening/applying rechecks them. Changed assumptions return
  a stale-review result before publication; clean textual merge alone does not
  establish valid structured content or links.
- Applying requires a fully resolved review. Persist reachable preimage/result
  history and operation intent before physical publication. Expose incomplete
  publication as a durable state, even if the Git result commit already exists.
- Restart recovery compares current bytes against retained preimages/results,
  finishes/restores only eligible paths, and reports diverged paths for review.
  Preserve later edits and keep normal update blocked until recovery is resolved.
- Latest Undo is a new whole-operation review against the current vault. Retain
  later edits unless an explicit reviewed resolution says otherwise; recheck its
  assumptions before any reversal. Never implement it as a repository reset.
- Unknown original output remains unknown. Missing identity/history needs reviewed
  association/onboarding or validated history restoration, with unavailable older
  recovery/Undo explained. Source updates and format changes remain separate.

These outcomes need versioned production contracts, capability/containment/history
validation, complete failure-state handling and independent acceptance evidence.
This script deliberately supplies none of those as a finished implementation.
