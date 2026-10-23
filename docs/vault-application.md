# Reviewed existing-vault application

`Operations.observe_reviewed_source`, `apply_reviewed_update`,
`inspect_update_status` and `read_update_details` form the shared headless
application boundary. [Checkpoint history](vault-checkpoints.md) retains exact
source, before and proposed bytes; [vault admission](vault-admission.md) supplies
the current Git, policy and authored-file observation. The existing
fresh-destination publisher has a separate path.

## Review and admission

Application takes one canonical, fully resolved, current-generation S1
`ReviewPlan`. Core projects its selected exact files and explicit displaced
rename paths. The outer operation checks the complete converted-source
inventory against the `ReviewedSourceBinding` observed for that proposal and
generation. This binding covers path, mode, size and SHA-256 for every payload
file, as well as the source root. It remains separate from S1's per-choice
assumptions so review refresh can retain unaffected decisions. A changed binding
requires fresh source observation and review before application.

Immediately before starting, application rediscovers owned history and scoped
admission, checks the review's actual current and incoming facts, and requires
every storage or tracking consent in the current policy query. An unresolved,
stale or unsupported choice refuses the whole update. The user's index, HEAD,
other refs, staged modes and unrelated authored files are preserved. Selected
ignored files enter the snapshot only through accepted tracking consent.
During an active vault-changing operation, the user, Obsidian, sync tools and
other programs must leave the target vault unchanged.

## Durable order and supported profile

The executor currently admits ordinary files on a qualified local fixed NTFS
volume on Windows. It refuses an unsupported volume before publication. It
checks current file bytes and metadata, stages the complete proposed inventory
on the same volume, copies required file and directory security from the
destination context, and refuses unsupported metadata such as alternate data
streams. New parent directories are staged with their intended inherited
security before the first authored namespace move.

The operation retains a prepared checkpoint with source, preimage and proposed
objects. Its converter-owned Git intent records the operation ID, kind,
generation, `finish` direction, exact before/result inventories, affected and
protected paths, metadata and created parents. Git object and reference writes
use command-scoped [Git `core.fsync` and `core.fsyncMethod`](https://git-scm.com/docs/git-config)
settings. Only after the intent ref is verified does
the executor publish a file or parent. Staged files are flushed after their
final metadata changes, closed, then moved with same-volume `MoveFileExW`
`MOVEFILE_WRITE_THROUGH`; replacing an existing file also uses
`MOVEFILE_REPLACE_EXISTING`. Each visible transition is checked against its
prepared bytes and metadata. Explicit reviewed rename removals move the old
authored path into owned staging. Application verifies the full accepted
inventory, retains an actual-result checkpoint, then retains a terminal
receipt before reporting `applied`. The relevant Windows contracts are
[file-buffer flushing](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers)
and [the move flags](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw).
The executor uses same-volume moves and does not request the cross-volume
copy-and-delete option.

An application-authored result manifest records the exact retained intent
commit and includes that link in its semantic fingerprint. History discovery
requires the matching validated operation root, including after a later local
checkpoint. A direct checkpoint-storage result has no application link and
remains valid storage without claiming an apply or terminal receipt.

An earlier [disposable ordinary Windows mechanism probe](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/273#issuecomment-6363943793)
observed the Git-intent, flush, move and readback primitives on the current
local NTFS host. The [#273 production-executor qualification](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/273#issuecomment-6367761700)
then checked its own ordinary publication sequence and retained result on
that host. These observations do not establish survival of a hardware power
cut, continuous multi-file visibility, or support for arbitrary security
metadata, encrypted files or remote volumes. The executor refuses capabilities
it cannot retain. The accepted ordinary resource envelope and S2 aggregate
qualification belong to issue #278.

## Recovery truth and results

Converter ownership uses an exact `.git/brz2obsidian` marker. A foreign marker
or retained incomplete intent sends admission to recovery first; the operation
does not delete foreign ownership. The intent ref remains discoverable when a
locator is absent or unreadable, but recovery cannot proceed without validated
checkpoint association and history. Matching-history repair belongs to issue
#276. `inspect_update_status` validates the real
intent, prepared checkpoint, result and receipt graph before interpreting
current files. It compares each affected path with exact before/result bytes
and metadata and checks created directories. Unknown third-version bytes remain
unknown for recovery; an acknowledged file count alone proves no publication
state. A later valid local checkpoint can follow a completed apply without
erasing its terminal history.

`Operations.prepare_recovery`, `refresh_recovery`, `resolve_recovery` and
`execute_recovery` use the same retained graph and current admission. The first
stopped operation offers `finish` or `restore`; a recovery intent saves the
selected direction, its review generation and its exact predecessor. A second
stop follows that saved direction. Recovery reviews later edits to affected
files and associated links, and requires an explicit choice before replacing or
removing changed bytes. A completed `restore` reports `restored`; finishing an
interrupted Undo reports `undone`. The result concerns the reviewed file
inventory. Empty parent directories created during an earlier operation may
remain, and later content in them is preserved. Source lineage remains the
retained generated source, separate from authored preimage bytes.

A recovery preparation retained before its new intent is still an unpublished
checkpoint: the preceding operation ref remains authoritative. Fresh inspection
validates its origin, predecessor, direction, review and current inventory;
retry can reuse that exact preparation when its meaning is unchanged. It does
not turn the preparation into a completed operation or choose a direction on
the caller's behalf.

`VaultApplyResult` reports a bounded phase, elapsed time, operation identity,
kind and generation, planned/published counts, publication and history state,
recovery need and safe diagnostics. A selected no-op returns
`no_content_change` with terminal history. Cooperative cancellation before
intent retains preparation without publishing working files; after intent it
persists a stop at a recoverable boundary. A process lost after a real move can
be classified by a separate fresh-process inspection. Complete bytes with a
missing terminal receipt or failed cleanup report `content_complete` and
recovery need; failed discovery after a possible move reports unknown
publication.

`Operations.inspect_history` exposes current admitted actions. Large
before/result comparisons use `read_update_details(offset=..., limit=...)`:
the validated intent supplies pages of at most 100 paths with sizes and
SHA-256 digests, without payload bytes. Unavailable or malformed operation
authority yields an unavailable page.
