# Representative checkpoint measurement for #252

This disposable measurement asks whether the frozen Git checkpoint mechanism can
capture a whole authored vault with unrelated content and representative binary
revisions. It measures synthetic data selected from aggregate observations; it is
not an exact reproduction of a private vault, an application implementation, or
a performance/support policy.

Run from the checkout root:

```powershell
.venv/Scripts/python.exe prototypes/editable-vault-wayfinder/checkpoint-scale/measure.py
```

Every run creates a fresh owned repository under
`tmp/merge-wayfinding/followups/scale/<timestamp>-<id>/`; it never deletes anything.
Only standard-library Python and installed Git are used. The script extracts the
exact `experiment.py` from commit `273233fb4020ceb156ed6b3ab33785adcedfdda9`, records
its hash, imports it, and changes only its generated-output root. Every capture
uses its unchanged `snapshot`: one `hash-object --no-filters` subprocess per file,
an isolated index, `write-tree`, `commit-tree` and converter-owned CAS ref updates.
A command log and partial results survive an incomplete run. The wall boundary is
720 seconds, checked at each Git-call entry, with each frozen Git subprocess also
bounded to 30 seconds. This prototype boundary is separate from the ordinary
production verification bundle. No production regression bundle is needed here.

`expected-before-run.json` records literal expected inventories/counts before the
first capture. The initial and changed source histories remain distinct from the
whole-vault preimage and accepted-result histories; the operation metadata commit
retains source/preimage/result through parent links. An independent user branch,
tag, inert remote, staged-then-unstaged note and untracked authored content are
present. No network command, packing, GC, checkout, reset or stash is used.

Aggregate discovery used only ZIP central-directory member sizes and filesystem
regular-file sizes beneath the approved private `brz/` root. No archive member or
retained-vault file content was read or copied. The ignored aggregate report uses
input ordinals, and its private path map must remain ignored and unpublished.
The inventory classification is approximate: Markdown counts are destination
notes, text-like archive members may include `.md`/HTML/TXT duplicates, and
nontext/nonmetadata archive members are a payload-size proxy rather than a
semantic attachment inventory.

The envelope combines the known 740-source-item baseline with 318 unrelated
synthetic authored notes (the observed retained-vault Markdown count), 665
incoming binaries matched to the largest archive's nontext/nonmetadata count,
coarse size buckets and total bytes, 20 unrelated 1 MiB binaries and seven
configuration files totaling 7,230 bytes. The 740 synthetic incoming notes are a
planning envelope for items including empty/generated notes, not a claim that
740 authored source bodies were observed. All 1,058 notes are 2 KiB, with unique
identities and mixed line endings. Binary bytes are deterministic SHAKE-256
output, avoiding unrealistically compressible padding. This approximates already
compressed attachments conservatively; it does not reproduce actual compression
ratios or revision similarity.

The 665 incoming binary sizes are 40×32,768, 611×344,428, ten×8,388,608,
one×9,340,785 and three×17,329,582 bytes: exactly 356,971,839 bytes. A changed
17,329,582-byte binary uses entirely different synthetic bytes, alongside one
changed note. This lies in the observed largest archive's >=16 MiB bucket and
matches its largest member; a separate observed archive has a 42,592,266-byte
maximum, which remains outside this chosen envelope. Whole-vault byte counts,
first/changed capture timings, loose-object logical size, file-stream disk
allocation and object reachability are reported separately. No packed-size or
universal size/throughput limit is inferred.

Read the run report and criterion matrix for observed results, exact identities,
limitations and the correction to the original ref-reachability expectation for
the independently staged user blob. Runtime depends on storage, caches, host load,
Git process launch, compression and file count. Neither interactive progress nor
cancellation, disk-full, power-loss durability, concurrency, arbitrary repository
policy, or a maintained Git version range is established by this measurement.

The measured original source is retained as `measure-as-run.py`; it contains two
incorrect hand-count/reachability expectations and an allocation method later
found to report logical size. Its raw results remain immutable and explicitly
retain FAIL for those expectations. The corrected `measure.py` is a distinct
source revision; original timings are attributed only to `measure-as-run.py` and
the unchanged frozen Git mechanism. Reconcile the retained timed run without
repeating captures:

```powershell
.venv/Scripts/python.exe prototypes/editable-vault-wayfinder/checkpoint-scale/measure.py --verify tmp/merge-wayfinding/followups/scale/20261021-122855-899d5c0a
```

This read-only step checks all four exact path/blob inventories, working bytes,
normal user Git state and reachability. It measures allocation through Windows
`FileStandardInfo.AllocationSize`, reconstructing each phase's exact cumulative
loose-object set from retained commits and the preserved user index. It writes
only the separate reconciliation evidence file. Seven synthetic configuration
paths deliberately contain three repeated payloads; the staged user blob is
index-reachable and lies outside ref reachability. The timestamped expectation
correction was written from deterministic fixture arithmetic before timed
capture completion, without reading observed Git object sets.

`inventory.py` preserves the aggregate-only discovery command. Running it reads
approved `brz/` sizes and writes the ignored aggregate and private ordinal map
under the scale output root. Publish only `inventory-aggregates.json`, never the
private map. Archive suffix-based classifications are proxies and do not count
thoughts or semantic attachment records.
