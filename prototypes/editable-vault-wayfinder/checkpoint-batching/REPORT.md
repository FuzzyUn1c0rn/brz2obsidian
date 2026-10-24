# Exact-byte batching at the representative checkpoint envelope

Author `/root/checkpoint_scale`, 2026-10-21. This answers [Measure exact-byte checkpoint batching at the representative envelope](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/253). Feature root `codex/editable-vault-wayfinder`; accepted integrated baseline `823c21445646f09059ac8e9bf8dc15cdbbbaca86`.

**Bounded author result: PASS. Independent review remains pending.** One raw-byte batch per capture produced exactly the accepted baseline histories and working bytes, with fewer processes and lower observed capture times in this run. This establishes a viable engineering candidate for the measured fixture; it accepts no user wait/size limit, native responsiveness claim or production implementation. Four separate capture timings are not an end-to-end import measurement.

## Candidate and expected outcome

The candidate materializes each immutable synthetic capture into fresh run-owned files outside the vault, then calls `git hash-object -w --no-filters --stdin-paths` once. Its isolated index, tree/commit construction, fixed author/committer identity/date, parent order and converter CAS refs retain the frozen mechanism. Expected Git launches per capture are seven: empty-index setup, one raw blob batch, index entries, tree, prior-ref lookup, commit and CAS ref update. Operation metadata is persisted with the original frozen mechanism after the four captures.

Before execution, `expected-before-run.json` bound all four exact inventories and baseline commit OIDs, 1,753 blobs /22 trees /six commits, 1,780 ref-reachable objects plus one index-only staged draft, unchanged user state/approved bytes, seven launches per capture and the resource boundary. These expectations were not changed after observation. The fixture is extracted from the accepted integration and independently checked against baseline inventory hashes before capture.

| Envelope | Files | Bytes |
| --- | ---: | ---: |
| Initial / changed converted source | 1,405 each | 358,487,359 each |
| Initial / changed whole authored vault | 1,750 each | 380,117,374 each |

The synthetic vault retains 318 unrelated authored notes, 20 unrelated 1-MiB binaries and seven configuration paths, alongside the incoming notes and binaries. The changed input alters one note and one 17,329,582-byte attachment. Provenance, coarse attachment distribution and approximation limits remain those of the [accepted representative checkpoint measurement](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/252); this experiment reads no retained private inputs.

## Measured comparison

| Separate capture | Historical per-file baseline seconds | Materialization seconds | Batched Git capture seconds | Inclusive candidate seconds | Baseline / candidate Git calls |
| --- | ---: | ---: | ---: | ---: | ---: |
| source_initial | 108.365468 | 2.331466 | 24.792530 | 27.123998 | 1,411 / 7 |
| vault_initial | 117.361847 | 2.961910 | 7.351706 | 10.313617 | 1,756 / 7 |
| source_changed | 86.929661 | 4.548069 | 5.356201 | 9.904268 | 1,411 / 7 |
| vault_changed | 112.045514 | 2.877208 | 5.770896 | 8.648104 | 1,756 / 7 |

The four inclusive candidate captures sum to **55.989986 seconds**, including **12.718653 seconds materialization**. They launch **28 Git processes**, compared with the historical baseline's 6,334. Total measured script interval is **102.719829 seconds**, including generation/setup, storage accounting, state/object/raw-byte validation. No expensive baseline capture was repeated.

The historical baseline was measured earlier on the same Windows host with the same project Python 3.14.8 and Git 2.55.0.windows.5, fixture and fixed history identity. Its raw source/result and independent review identities are retained below. The candidate adds filesystem materialization/read work rather than sending immutable bytes directly to each Git process; inclusive time counts that work. Host load, antivirus, cache warmth and run ordering were not controlled or randomized. These are a single candidate run compared with accepted historical observations, not a paired statistical benchmark or universal speedup prediction. The direct observations establish launch-count reduction and lower inclusive times at this envelope.

## Bytes, topology, deduplication and preservation

All **four commit OIDs**, all **1,781 object OIDs** and all converter refs exactly match the accepted baseline. That includes source-history parentage, distinct whole-vault preimage, accepted-result parent and the operation commit parents retaining required source/preimage/result history. The four actual tree path/blob inventories match separately computed raw Git blob identities from the deterministic expected bytes. Every retained loose object was decompressed and its header length and SHA-1 identity verified. Final working files match the complete approved literal byte mapping.

Exactly **1,780 objects are ref-reachable**; the remaining object is the independent staged user draft held by the preserved index. All required converter commits/payloads are ref-reachable. There are **1,753 blobs, 22 trees and six commits**. Repeated configuration payloads and cross-source/vault sharing retain the established deduplication. The incoming source trees exclude unrelated authored context, while both whole-vault trees include it.

The real index bytes and staged entries, HEAD bytes/OID, independent branch/tag refs and repository config hash remain exactly equal to their fresh pre-capture state. The staged-then-unstaged note keeps the reviewed current authored bytes. Unrelated untracked files remain intact. Synthetic publication changes only the two reviewed paths. No normal-index rewrite, user branch update, network command, checkout, reset or stash was used.

| Cumulative phase | Loose objects | Logical loose bytes | Allocated file-stream bytes |
| --- | ---: | ---: | ---: |
| source_initial | 1,416 | 357,228,304 | 359,628,976 |
| vault_initial | 1,767 | 378,278,343 | 380,758,320 |
| source_changed | 1,774 | 395,648,088 | 398,134,016 |
| vault_changed | 1,778 | 395,666,583 | 398,154,880 |
| Final operation retained | 1,781 | 395,667,100 | 398,155,408 |

Final `.git` regular files occupy **395,668,440 logical /398,156,808 allocated bytes**, exactly matching the accepted baseline. `count-objects -v` reports zero packs/garbage. No packing/GC occurred; no packed-size result is claimed. File-stream allocation uses the accepted Windows `FileStandardInfo.AllocationSize` method and excludes directory/MFT overhead and volume-free-space accounting.

## Resources and exact evidence

Before running, the declared boundary was **300 seconds overall**, with **30-second Git subprocess timeouts**, estimated retained disk below **3 GiB** and estimated peak Python working set below **2 GiB**. The run completed within the bound without timeout. Recorded run regular files occupy **2,253,273,204 logical /2,276,748,752 allocated bytes** before final commands/results JSON writes; this includes four retained materializations totaling **1,477,209,466 input bytes**. Directory/MFT overhead and final report/log growth are excluded. Actual peak Python working set was **823,222,272 bytes**, queried through Windows process memory counters; Git child processes are excluded. No memory-pressure or disk-full test was performed.

This retained staging footprint is an experimental cost, not a proposed production storage contract. The overall budget is checked at Git-call, materialization and raw-object validation boundaries; it does not preempt every OS/Python operation. No application cancellation or progress behavior was tested. The largest measured batch command completed inside its existing 30-second subprocess bound; this does not define a supported universal batch size.

Run: `tmp/merge-wayfinding/followups/batching/20261021-125837-f28726e1/`. `results.json`, `commands.json`, `expected-before-run.json`, exact as-run helper, frozen dependency sources, baseline reference and actual synthetic repositories/input files are retained there.

```powershell
.venv/Scripts/python.exe prototypes/editable-vault-wayfinder/checkpoint-batching/measure.py
```

| Identity | SHA-256 |
| --- | --- |
| Executed LF candidate measure.py | `f63b46ae792b3264703db3d9c15ef9e24c9399db359d8f050bad69941d86a392` |
| baseline-reference.json | `656db3ad6dea52a5ef022169f3c480bc6205e5c705d87f4e009e36f4bd002bdf` |
| Frozen Git experiment.py from 273233f | `fddfe131e1d0ad791abdcaeb2939a2c51311a95143fe80f81f0c0771664be6df` |
| Retained LF fixture/allocation helper from 823c214 | `abefbea9bec6e277f979fa4f9d1dff7875f24932e0b6554a06b3ca7cf0861c9b` |
| Historical original raw timed helper | `e479371a651c98206eacb760cceb6d21e76fd9a36774059e68407e7b2aa49bfe` |
| Historical LF retained timed-helper copy | `5dfe87701c04e706d79316c0fdfec5dbcca26ad5d412843235f72220e465bdbf` |
| Historical immutable results.json | `e96f44492bfd371d60179e9b7928c8025fc1a291be0ea16ed05b1b2b2477eb64` |
| Historical independent review | `9933f1e7e167eb70a63f694c60e147393579bd8808bb3609bffca03b9a8dde5f` |

The historical raw timed helper is distinct from its CRLF-to-LF-normalized Git copy; those normalized bytes were not the historical timed bytes. The fixture/allocation helper was separately reconciled and is used here only as an explicitly hash-bound dependency. Original baseline raw FAIL expectations remain preserved; author and independent correction established the accepted counts/allocation. This candidate has its own unchanged expectations and author PASS, and no reporting repair/re-execution was needed. New retained candidate sources use LF.

Environment: Windows-11-10.0.26100-SP0; `3.14.8 (tags/v3.14.8:8e6e75d, Sep 30 2026, 18:19:33) [MSC v.1944 64 bit (AMD64)]`; `git version 2.55.0.windows.5`; project interpreter `C:\Users\stefa\projects\brz2obsidian\.venv\Scripts\python.exe`. Empty controlled Git system/global/template policy, fixed synthetic history identity/date and no native application were used. The same deterministic immutable fixtures permit exact OID comparison despite different normal-index file timestamps; preservation is checked against this run's own initial user index, not the earlier fixture's timestamped index bytes.

## Recommendations and remaining gates

Raw-byte batching is a demonstrated candidate for reducing process cost while retaining this history/byte model. Carry the exact observations into final specifications; production code may select a suitable mechanism only with its own applicable checks. Keep whole-authored-vault preservation, separate source/vault histories, actual-index isolation, parent retention and storage/execution-policy preflight as requirements. This controlled experiment supplies no generic permission to bypass hooks, filters, encryption, LFS or inherited custom policy.

No universal time/size threshold or scope downgrade is justified. End-to-end import time, active-vault scan consistency, user-facing progress/cancellation, publication/recovery race handling, storage exhaustion, power-loss/fsync durability, cleanup/packing, larger envelopes and the maintained Git capability/version range remain explicit specification/implementation gates. Materialization here captures fixed in-memory byte mappings; it does not prove an atomic or race-safe live-vault scan. The existing GIT-B01–B03 behavior verdict and selected GUI direction remain their own accepted decisions.

## Criterion reconciliation

| Accepted criterion | Author result / evidence |
| --- | --- |
| Accepted baseline, one candidate and literal expectations before execution | PASS: frozen baseline/dependency hashes, one raw batch mechanism, immutable expected-before-run.json |
| Identical representative source/vault envelope, unrelated content and changed binary | PASS: all four input inventories and commit/OID equality; retained synthetic materializations only |
| Runtime/disk/memory bounds, historical timing provenance and no broad checks | PASS:102.720s within300s;2.277GB file-stream allocation,823MB Python peak within estimates; no repeated original captures |
| Actual four-capture cost, process/storage/dedup and topology/reachability | PASS: comparison table;28vs6,334 launches; identical1,781objects/refs and allocated/history storage |
| User Git/working bytes and exact-byte storage-policy scope | PASS:11/11 author checks; original index/HEAD/refs/config preserved; no custom-policy support/bypass claim |
| Truthful findings, limitations and no performance promise | PASS: historical comparison and remaining contracts explicit; no accepted wait/size limit |
| Complete evidence, recommendations and independent exact-candidate review before closure | AUTHOR READY; INDEPENDENT REVIEW PENDING: root owns review, integration, durable publication and closure |
