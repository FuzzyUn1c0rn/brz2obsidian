# Matching converter-history restoration experiment (#250)

This bounded engineering experiment asks whether a **verified, matching complete
history copy** can repair missing/damaged converter refs and objects while newer
current notes, staged selection and independent Git history remain byte-for-byte
preserved. It supplements the frozen #244 mechanism; it is not production update,
backup or transport code. The previously accepted HTML walkthrough remains the
human-facing behavior prototype. This helper supplies the previously missing
real-filesystem/Git evidence rather than adding a second simulated walkthrough.

From the checkout root, with installed Git and the project interpreter:

```powershell
.venv/Scripts/python.exe prototypes/editable-vault-wayfinder/history-restore/experiment.py
```

No package installation, network, pytest, production check or native app is
needed. Each invocation creates fresh synthetic repositories beneath
`tmp/merge-wayfinding/followups/history/<run>/`; each scenario restores/refuses
in a fresh Python process. No repository is deleted. The ownership marker and
absolute containment guard prohibit using retained vaults or this checkout as
experiment targets. No checkout, reset, stash, clean or automatic remote command
is used. The fixture's inert remote is never contacted.

The script imports the frozen Git experiment read-only, checks its SHA-256
`fddfe131e1d0ad791abdcaeb2939a2c51311a95143fe80f81f0c0771664be6df`, and redirects
only its disposable output boundary. Frozen input commit:
`273233fb4020ceb156ed6b3ab33785adcedfdda9`. Source changes during a run invalidate
the result. Only a retained completed run with the final source hash is evidence.

## Proposed association and completeness contracts

The experimental `.brz2obsidian/association.json` is a **current association
anchor**, established independently by this fixture's explicitly reviewed prior
association. It carries a vault identifier, source collection identifier,
lineage identifier and expected generation. It contains no historical note
payloads and is not a parallel history store. Its historical versions are also
captured in Git. This path/schema, identity lifecycle and generation management
are contract recommendations for #247, not an accepted production format.

The supplied backup's own assertion of identity never establishes association.
The supplied Git envelope must agree with the independent current anchor. A
notes-only copy carries this anchor only if the actual copying mechanism includes
that file; Obsidian Sync or an arbitrary selection is not assumed to do so.
Without an independent retained association, the outcome is
`association-review-required`; titles, paths and similar bytes cannot recreate
the missing provenance. Separately reviewed association may be possible using
trusted source/migration information. Preservation-first fresh onboarding is a
different reviewed option when trustworthy history cannot be recovered, subject
to the interrupted-operation gate. No fixture invents pristine original output
from current notes.

The proposed Git-owned `identity` and `history` refs supplement the frozen
`source`, `vault`, `accepted`, and `operation` refs. The history envelope records:

- Schema, association, required owned refs and their exact OIDs.
- Per-snapshot path/mode/blob/byte-count/SHA-256 inventories.
- The operation manifest and its indispensable source/preimage/result links.

Commits, trees, blobs and manifests are all retained in the **same vault Git
object store**. Required commits are actual parents of the owning history and
operation commits; JSON OIDs alone are refused as insufficient retention.
Validation verifies object content-address integrity, ref agreement, snapshot
inventories, association consistency and operation row/preimage/result agreement.
`git fsck --full --strict --no-reflogs` also checks the supplied complete copy.
Independently authored literal expectations for every source/preimage/accepted
snapshot provide a separate oracle from those self-described inventories.

These checks prove consistency and accidental-corruption detection for the
trusted synthetic fixtures. They do not authenticate a hostile forged backup.
Real restore needs independently trusted association/provenance and explicit
review of the chosen generation. An identifier is an association key, not a
secret, signature or proof of ownership. Defining trusted association recovery
when *all* local association is absent remains an explicit #247 contract; the
safe observed outcome is refusal pending association review.

## Restoration and refusal boundaries

All supplied-copy validation and the bounded current-policy preflight finish
before the first target object or ref write. Mismatched, incomplete, corrupt and
unreachable prerequisites return a refusal with a full byte inventory showing
zero target mutation; supplied-copy bytes also remain identical.

After validation, the helper copies only the reachable converter object closure
as content-addressed loose Git objects. It then updates only the six owned refs
in one compare-and-swap `update-ref --stdin` transaction and validates again.
It copies no normal index, HEAD, user branch/tag, configuration or working file.
An intact different target history is not silently replaced by an older copy;
that case requires separate generation reconciliation. Actual concurrent changes
between validation and mutation remain outside this experiment.

Some converter blobs are also reachable from independent user branches/tags.
Content-addressed objects represent the same bytes regardless of the referring
ref. Healthy matching existing objects are left untouched; replacing a corrupt
same-OID converter object restores the independently hash-verified original
content. Each positive record lists the complete shared-object intersection and
the actually written intersection. This is shared immutable storage, not a user
history rewrite. The normal staged selection is separately preserved byte for
byte even though newer working files differ from it.

A development run discovered that Git's loose objects are read-only on Windows:
unconditionally replacing healthy objects failed with `WinError 5`. The repaired
helper leaves matching healthy objects untouched. It makes only a validated
damaged same-OID converter object writable before replacement. The failed run
and later development run remain disposable, nonqualifying evidence; the final
source run is named in the handoff report. This is not a durability guarantee
for interrupted object repair.

Known/suspected interrupted operations take priority over association/onboarding.
The gate reads available Git operation status independently of a current marker;
an `applying`, `recovery-review` or `undo-applying` operation blocks restoration
from an older baseline even if the marker is absent. Unreadable operation state
also retains the recovery gate. A code-inspection repair added this check after
finding that a marker-only gate could otherwise replace newer applying intent.
The experimental current recovery marker contains only an operation/suspicion
signal, not preimages. Missing indispensable history returns `recovery-required`
and `onboarding: blocked`, preserving current content. Such a marker may survive
a copy only when that copy actually includes it. Absence of the marker is not
proof that an operation never existed. Complete recovery-direction/intent
contracts are owned by #249; this helper does not finish/reverse an interrupted
file publication or declare recovery complete. Restoring history alone never
replays old approvals: current files and assumptions still need fresh review.

The incomplete fixture physically persists `applying` in Git, removes the exact
indispensable A preimage blob, and verifies that `cat-file -e` fails. Its first
restart has no current marker and must recognize the Git operation. Its second
restart also lacks the association anchor and retains a suspicion marker;
recovery still wins over onboarding/association. The chosen supplied copy is the
older applied baseline, not a copy of the indispensable interrupted generation.
Restoration from a complete matching copy of an interrupted generation and its
subsequent file recovery remain #249/#247 integration work.

## Evidence and acceptance matrix

`results.json` contains fixture identities, interpreter/Git version/executable,
source hashes, literal independent expectations, exact commands and per-scenario
outcomes. Scenario JSON files retain exact file/index/HEAD/config bytes as hex,
SHA-256 inventories, staged entries, user refs and all before/after comparisons.
`REPORT.md` lists observed outcomes. Run timing measures this bounded fixture
only; it is not the representative-scale evidence from #252.

| #250 criterion | Evidence seam |
| --- | --- |
| Independently expected association/completeness/integrity | Explicit current fixture anchor, required refs/parents, raw object hashes, snapshot inventories, independently authored literal history bytes |
| Intact, missing/damaged target and matching complete-copy restoration | Four positive fresh-process cases, actual restored refs/objects followed by validation and literal snapshot reads |
| Exact newer files/index/HEAD/refs/config preserved | Exact inventories and staged entries before/after every case; rewritten independent user ancestry remains valid |
| Mismatch/incomplete/corrupt rejected without mutation | Missing owned ref, missing/corrupt object, different identity and JSON-only unreachable operation dependency; corrupt target with invalid copy and distinct intact target generation; exact target and supplied-copy comparison |
| Incomplete operation cannot bypass onboarding | Known incomplete-operation fixture with indispensable history unavailable returns recovery-required and blocks onboarding |
| Reproducibility and contract recommendations | One project-venv command, source binding and retained scenario JSON; this README's explicitly proposed contracts and limits |
| Independent review | Required separately; author PASS supplies no review or closure verdict |

This proves a **quiescent complete directory copy** containing the actual
self-contained Git objects, owned refs, relevant configuration and current
association. It does not prove that a normal clone, arbitrary folder-copy tool,
selective note copy, Obsidian Sync, remote or another device transports these
requirements. No automated transport, additional history directory or backup
product is introduced.

Remaining implementation gates include complete effective-policy/containment and
layout detection, trusted association repair, persisted format/version lifecycle,
concurrent editors/Git writers, durable locking, power loss/fsync, object/ref
publication failures, disk-full/access failures, Unicode/case/reparse path
handling, packed-object variants, advanced layouts, a supported Git version
range and real user acceptance. The controlled fixture uses ordinary local
SHA-1 repositories and the installed Git only. Accepted #248 support/history
policy remains authoritative; no observed result justifies silently narrowing it.
