# Bounded raw-byte checkpoint batching experiment

This disposable experiment answers [the checkpoint batching question](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/253): can one batch of raw Git blob writes per capture reduce observed time/process cost while preserving the accepted representative-envelope bytes and history? It is engineering evidence for planning, with no application optimizer or accepted performance limit.

Run from the checkout root:

```powershell
.venv/Scripts/python.exe prototypes/editable-vault-wayfinder/checkpoint-batching/measure.py
```

The helper uses project `.venv`, standard-library Python and installed Git. Every run creates a fresh owned output under `tmp/merge-wayfinding/followups/batching/`; nothing is deleted. No retained user input, native application or project Git state is mutated. New retained sources use LF, and the exact executed source is copied/hash-bound before the experiment.

One candidate replaces the frozen mechanism's one `hash-object --no-filters --stdin` launch per payload with one `hash-object -w --no-filters --stdin-paths` launch per capture. It materializes the same immutable bytes into fresh per-capture input files outside the synthetic vault. Materialization time is reported separately and included in capture elapsed time. The remaining isolated-index/tree/commit/CAS-ref operations preserve the frozen sequence, parents, identity/date and commit message. Seven Git calls are expected per capture. There is no packing or GC.

The immutable fixture and correct allocation method are extracted read-only from accepted integration commit `823c21445646f09059ac8e9bf8dc15cdbbbaca86`; the original Git mechanisms come from `273233fb4020ceb156ed6b3ab33785adcedfdda9`. Source and whole-vault scopes remain distinct. Expected inventories, four exact commit identities, counts and refs are recorded before capture, then independently compared with generated path/blob identities and actual user Git/working-file state. Every retained loose object is decompressed and its raw header/length/identity checked.

The accepted historical baseline is retained in `baseline-reference.json`, including exact original raw helper/result provenance, LF retained-copy identity, environment, capture timings and accepted object IDs. Historical timings belong to the raw executed helper `e479371a651c98206eacb760cceb6d21e76fd9a36774059e68407e7b2aa49bfe`; the LF Git copy was not separately timed. Original expectation mistakes and allocation reconciliation remain explicit. No expensive baseline capture is automatically repeated.

Before execution, this run was bounded to 300 seconds overall, with 30-second frozen Git subprocess timeouts, estimated retained disk below 3 GiB and estimated peak Python working set below 2 GiB. The overall guard runs at Git-call and file-materialization boundaries; it does not promise application cancellation or preempt every Python/OS operation. Failure or timeout remains an observed incomplete result, never a silently increased boundary. File-stream allocation excludes directory/MFT overhead and volume free-space accounting; peak Python working set excludes Git child processes.

The synthetic repository uses empty controlled host/template policy and the accepted exact-byte storage assumption. This is no authorization to bypass custom hooks, filters, encryption, LFS or unknown repository policy. There is no new policy detector or support matrix. Live-vault scanning, concurrent edits, cancellation/progress, disk-full, power-loss durability, native responsiveness, packed storage and a maintained Git version range remain unverified.

See `REPORT.md` for actual measurements, source hashes, criterion reconciliation and recommendations. Four capture times are separate operations, not an end-to-end import time or a universal throughput prediction.
