# Verify absent content and type hierarchy in native TheBrain

Status: resolved
Assignee: /root
Type: task
Mode: HITL when native access or source export requires the user; otherwise AFK
Labels: wayfinder:task
Parent: [Find the implementation route for the Management & Leadership archive](../map.md)
Blocked by: 01, 02

## Question

What does the identified source Brain actually display for the absent notes/icons
and ordinary-to-type hierarchy, and what do controlled export/restore comparisons
establish that the archive and documentation alone cannot?

Use the completed research checklists and the private assessment source-review
list. Read the computer-use skill if native automation is available. Record the
app build, Brain identity and any live/archive differences before interpreting
observations. Inspect representative ordinary missing-note owners, both type
missing-note owners and all eight type icons. Observe multiple-parent type links
and distinguish ordinary hierarchy from type assignment/subtype behavior.

Use disposable controls and a fresh ignored output for any experimental export
or restore. Keep original archive/source and retained vaults intact. Capture
actual bytes/identities/paths/hashes where available; an image preview alone does
not authenticate a missing Notes.md original. If a complete new export changes
the input fingerprint, preserve the original and compare both explicitly.

Publish aggregate observations and limitations at `../research/native-source-behavior.md`;
screenshots, exports and private source-level details belong under
`tmp/ml-wayfinding/native-source/`. If only the human can provide an observation,
request the precise bounded action and record the answer; do not simulate it.

## Completion criteria

- The material missing-content hypotheses and hierarchy meanings are tested by
  recorded observations, or their remaining external limitation is explicit.
- Exact bytes recovered/re-exported, if any, are distinguished from display
  evidence, synthesized content and irrecoverable/unavailable bytes.
- The result provides enough facts for the user to choose a conversion policy;
  this task does not decide that policy or implement it.

## Comments

- 2026-10-05: During the later policy session, the user asked what the remaining
  60 notes actually were and whether they were gone. Follow-up native retrieval
  recovered every one and produced a fully compared fresh backup with all 73
  in-scope cohort files. See [Complete recovery of the active missing-note
  cohort](../research/native-source-recovery.md). The answer below remains the
  historical bounded-probe result, not the latest availability claim.
- 2026-10-05: The user confirmed Desktop Backup to BRZ as the original export
  route and required excluding forgotten thoughts. Native observation and
  disposable exports completed; aggregate evidence is linked in the answer.
- 2026-10-05: Claimed for native source verification. The user explicitly authorized computer use; original Brain, archive and retained vaults remain protected by the observation/control scope.
- 2026-10-05: Created during charting. Research blockers guide the control design;
  no native source observation is claimed by the diagnostic subset trial.

## Answer

Completed the native controls in TheBrain 15.0.624.0 against the same Brain
identity. See [Native source verification and controlled exports](../research/native-source-behavior.md)
for the representative observations, fingerprints, comparisons and limitations.

Recovered exact current source bytes for all eight missing type icons, three
ordinary notes and both short type notes. Two fresh desktop backups include
respectively nine and 13 of the original 74 absent files; the final backup's
13 files match the captured local bytes and SHA-256 values. All original 1,024
payloads are unchanged and both backups pass full ZIP CRC checks. Record
identity sets and content/relationship fields remain unchanged apart from
sync bookkeeping and native activation timestamps.

Blank native display did not establish empty content: an initially blank
image-only note rendered after retrieval. The recovered 5/7-byte type notes
contain BOM/line endings, established from actual bytes. Normal sync and native
Markdown export did not fetch the remaining files. Sixty-one ordinary notes
remain absent; one is forgotten and excluded by the user, leaving 60 in scope.
They are not proven irrecoverable. No replacement bytes were synthesized.

Native hierarchy matches ordinary parents of thought types independently of
type assignment. The multiple-parent control has six direct ordinary parents;
the additional ancestor in the Plex is display context. All 54 ordinary-to-type
hierarchy links and 332 assignment links are unchanged.

The original archive contains 16 forgotten ordinary thoughts, 11 owned
attachment declarations and 23 incident relationships. Their exclusion is a
firm user constraint, distinct from attachment state. The policy ticket now
has the facts needed to settle dependent filtering and reporting.

The remaining external limits are explicit: no verified isolated restore
environment, no complete active-note recovery, no authoritative state-3 enum
definition and no verified original producer build/settings. The ticket's
bounded observation criteria are satisfied with these limits; successful
complete conversion has not been claimed or approved.

Verification: read-only full-archive comparison and CRC/hash checks via
`compare_backup.py`; 13 exact local/export byte comparisons and aggregate
hierarchy/forgotten/Markdown checks via `verify_receipt.py`, using `.venv`.
Private evidence and controls stay under `tmp/ml-wayfinding/native-source/`.
