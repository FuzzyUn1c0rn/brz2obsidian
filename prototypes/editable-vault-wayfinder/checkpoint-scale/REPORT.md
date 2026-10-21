# Whole-authored-vault checkpoint envelope — issue #252

Author: `/root/checkpoint_scale`, 2026-10-21. Feature root `codex/editable-vault-wayfinder`; dispatched integration base `b2f9bdf4d24384097ad99911c1f9c30f8d06ba3d`. Frozen mechanism input `273233fb4020ceb156ed6b3ab33785adcedfdda9`.

**Bounded measurement completed; separate read-only reconciliation PASS. Independent review remains pending.** Four unchanged-mechanism captures completed inside the declared 720-second experiment boundary. These are separate source/vault initial/changed capture timings, **not an end-to-end import measurement**. No accepted wait-time, universal size limit, responsiveness or cancellation promise follows from them. The original timed run retains FAIL for incorrect hand expectations; it has not been relabelled or overwritten.

## Provenance and selected envelope

Aggregate discovery read only filesystem sizes and ZIP central-directory entries in the approved private `brz/` root. It did not open private member/file content or mutate originals. `inventory-aggregates.json` retains anonymized aggregate observations; the ignored private ordinal map remains unpublished. Text-like member counts may include several representations of a note, while nontext/nonmetadata members are a size proxy rather than semantic attachment records.

| Aggregate input | Count and bytes | Size observations |
| --- | --- | --- |
| Largest observed archive (input-04) | 1,037 members; 363,153,294 uncompressed bytes | 665 nontext/nonmetadata members; 356,971,839 bytes; p50 344,428; p95 584,660; max 17,329,582 bytes |
| Another observed archive (input-03) | 63 members; 164,001,091 uncompressed bytes | Nontext/nonmetadata maximum 42,592,266 bytes; outside chosen envelope |
| Retained authored vault (input-06) | 318 Markdown / 254,566 bytes; 237 other / 73,112,634 bytes; seven config / 7,230 bytes | Other-file maximum 29,677,232 bytes; counts are stat-only |

The synthetic envelope combines these observations rather than reproducing a private vault. It contains 740 incoming 2-KiB notes (the documented 740-source-item baseline, including generated/empty-item note paths as an assumption), 318 unrelated authored 2-KiB notes, 665 incoming binaries, 20 unrelated 1-MiB binaries and seven relevant configuration files. Incoming binary counts, coarse buckets and total bytes match the largest observed archive proxy; the source median is matched, while p95/compression/revision similarity are not reproduced. Configuration paths intentionally share three repeated payloads. All data is synthetic and deterministic.

| Input | Files | Bytes |
| --- | ---: | ---: |
| source_initial | 1,405 | 358,487,359 |
| vault_initial | 1,750 | 380,117,374 |
| source_changed | 1,405 | 358,487,359 |
| vault_changed | 1,750 | 380,117,374 |

The changed source and approved vault result alter one note and one **17,329,582-byte binary**. That binary matches the largest member in the selected archive and its >=16-MiB bucket, rather than the old 256-KiB calibration. Completely different SHAKE-256 revisions avoid artificial padding compressibility and provide a conservative full-revision loose-storage case. Larger observed maxima remain unmeasured.

## Timings and storage

| Separate capture | Seconds | Git subprocesses |
| --- | ---: | ---: |
| source_changed | 86.929661 | 1,411 |
| source_initial | 108.365468 | 1,411 |
| vault_changed | 112.045514 | 1,756 |
| vault_initial | 117.361847 | 1,756 |

Four capture times sum to 424.702490 seconds. Total original measurement script time was 459.241260 seconds, including fixture/setup/storage/raw-byte validation. It was bounded at 720 seconds before execution; each frozen Git command retains its 30-second timeout. There was no timeout or interruption. These bounds do not establish supported application cancellation.

The four captures launched 6,334 Git processes in total. Every capture launches one `hash-object --no-filters` process per file plus six control calls. The changed vault still takes 112 seconds even though its changed payloads already exist from the preceding changed-source capture. The measured commands establish repeated process launch and full rehash work; no batching optimization or causal speedup was measured. Cache warmth, compression, storage and concurrent host activity remain confounders.

| Cumulative phase | Loose objects | Loose logical bytes | File-stream allocated bytes |
| --- | ---: | ---: | ---: |
| final | 1,781 | 395,667,100 | 398,155,408 |
| initial | 6 | 366 | 392 |
| source_changed | 1,774 | 395,648,088 | 398,134,016 |
| source_initial | 1,416 | 357,228,304 | 359,628,976 |
| vault_changed | 1,778 | 395,666,583 | 398,154,880 |
| vault_initial | 1,767 | 378,278,343 | 380,758,320 |

Final `.git` regular files total **395,668,440 logical bytes** and **398,156,808 allocated bytes**. `git count-objects -v` reports 1,781 loose objects, `size: 386393` KiB, zero packs and zero garbage. Git's reported size is retained separately from logical lengths and Windows allocation. No packing, repacking or GC was run; no packed-storage claim is made.

Allocation is Windows `FileStandardInfo.AllocationSize` summed over file streams, including resident-file values; directory/MFT metadata and a volume-free-space delta are excluded. The original `GetCompressedFileSizeW` fields returned logical lengths and are rejected as allocation evidence. The read-only reconciliation reconstructs each cumulative object set from retained commit closures plus the preserved user index and measures the corresponding still-loose object files. All original observed logical sizes agree with that reconstruction.

Changed-source capture grows loose logical storage by **17,369,745 bytes** and stream allocation by **17,375,696 bytes**. The subsequent changed-vault capture grows them by **18,495 / 20,864 bytes**, because both changed payloads are reused; it adds three trees and one commit. The final operation record adds one metadata blob, tree and commit. This is observed deduplication across source/vault histories, not a prediction about future cleanup or packing.

## Preservation, topology and exact-byte checks

All four snapshot path/blob inventories match independently calculated raw Git blob identities from deterministic expected fixture bytes. All 1,750 final payloads were also read back through `cat-file --batch` and compared byte-for-byte, and approved working files match exactly. No decoding or newline normalization occurs. The incoming source histories exclude all unrelated authored notes/binaries/configuration. Vault preimage and approved result retain the full 1,750-file context.

Source history has its own parent chain; accepted result retains its vault preimage; operation metadata parents retain required source/preimage/result commits. There are **1,753 blobs, 22 trees and six commits = 1,781 objects**. All **1,780 ref-reachable** objects include every converter-required commit/payload. The single remaining blob is the intentionally independent staged user draft, retained through the unchanged real index. It is not missing history. Across all four payload inventories there are 1,750 unique payload blobs; three configuration duplicates explain the difference from the original hand count.

The real index bytes/staged entries, HEAD bytes/OID, independent branch and tag refs, and repository config hash remain exactly equal to the initial snapshot. An inert remote was never contacted. The note staged then edited in the worktree keeps its unstaged authored bytes; unrelated untracked files remain present and receive checkpoint coverage. Publication changes only the two synthetically reviewed paths. No normal-index rewrite, user branch update, checkout, reset or stash was used.

## Corrections and exact evidence binding

The original `expected-before-run.json` incorrectly counted repeated configuration bytes as unique and expected the staged draft to be ref-reachable. A timestamped `expectation-correction-before-completion.json` calculated the corrected counts solely from deterministic fixture arithmetic before capture completion, without inspecting observed Git objects. Original `results.json` truthfully retains FAIL for those two assertions; all raw-byte, approved-file, user-state, required-commit and source-scope checks passed. The separately executed reconciliation returns PASS for corrected expectations, exact four-tree inventories, retained state and allocation. Original timings belong to the original helper and frozen mechanism; the corrected capture path has not been timed.

| Source | SHA-256 |
| --- | --- |
| Frozen experiment.py at 273233f | `fddfe131e1d0ad791abdcaeb2939a2c51311a95143fe80f81f0c0771664be6df` |
| measure-as-run.py (immutable original timed helper) | `e479371a651c98206eacb760cceb6d21e76fd9a36774059e68407e7b2aa49bfe` |
| measure.py (executed read-only reconciliation) | `8552562ac9818d1932c5cec47ae5d9fe3cc854254267a119cc6414591fff5ebf` |

Commands, executed from the checkout root:

```powershell
.venv/Scripts/python.exe tmp/merge-wayfinding/followups/scale/discover.py
.venv/Scripts/python.exe prototypes/editable-vault-wayfinder/checkpoint-scale/measure.py
.venv/Scripts/python.exe prototypes/editable-vault-wayfinder/checkpoint-scale/measure.py --verify tmp/merge-wayfinding/followups/scale/20261021-122855-899d5c0a
```

The second command ran the original helper bytes now retained as `measure-as-run.py`; the third ran the distinct corrected helper hash. `commands.json` retains original Git command arguments, counts and elapsed times. Raw results, original source, frozen source, pre-run expectations and separate reconciliation live under the named run. Current `inventory.py` preserves discovery source; only its output provenance is published.

Environment: Windows-11-10.0.26100-SP0; 3.14.8 (tags/v3.14.8:8e6e75d, Sep 30 2026, 18:19:33) [MSC v.1944 64 bit (AMD64)]; `git version 2.55.0.windows.5` at `C:\Program Files\Git\cmd\git.EXE`; project `.venv` interpreter; 12 logical CPUs. Controlled empty Git system/global/template policy, fixed synthetic commit identity/date, no network and no native app were used. Observed free space during capture was 443,630,735,360 bytes; no disk-full pressure was tested.

## Contract recommendations and remaining gates

Carry observed time/storage into #247 without inventing an accepted user wait or size limit. The mechanism completes this combined envelope but its approximately two-minute whole-vault captures make a responsiveness claim unproved. Keep whole-authored-vault preservation and C16 support conditional on measured implementation evidence. No observed failure requires a compatibility-scope downgrade. Larger archives, more notes, incompressible multiple revisions, packed storage, retention/cleanup, encoding/editability and a maintained supported Git range remain separate gates.

A bounded batching experiment should compare the same fixture, exact histories and preserved user state against a candidate with fewer Git launches. Require actual time/process/storage results and deterministic exact-byte/tree/ref/reachability equivalence; do not infer an optimization from plausibility. Cancellation, progress, concurrent editing/stale capture, storage exhaustion, races, power-loss/fsync durability and native application behavior need explicit production contracts/acceptance. This fixture is captured from in-memory immutable mappings and does not prove a concurrent live-vault scan is atomic.

## Issue acceptance matrix

| Criterion | Authored result | Evidence / remaining boundary |
| --- | --- | --- |
| Aggregate provenance, counts/sizes and envelope assumptions | PASS | Anonymized aggregate JSON and provenance/selection above; no private content/names published |
| Unrelated authored content, representative changed attachment, frozen exact-byte topology | PASS | 318 unrelated notes +20 binaries +7 configs; changed17,329,582-byte binary; unchanged frozen snapshot mechanism |
| Generated counts, first/changed time, retained objects/disk, dedup/reachability, environment | PASS after explicit reconciliation | Four capture table, corrected allocation table,1,781-object inventory, commands and exact source bindings |
| User Git/file preservation and honest resource/cancellation limits | PASS within bounded scope | Exact index/HEAD/refs/config and working bytes;459.241260s total; cancellation/concurrency unverified |
| Recommendations and remaining production/compatibility gates | PASS | No universal threshold/scope change; bounded batching question plus explicit remaining gates |
| Reproducible evidence and independent review before closure | AUTHOR EVIDENCE READY; REVIEW PENDING | Root owns exact-candidate independent review, source integration, publication and closure |
