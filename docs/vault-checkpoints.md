# Existing-vault checkpoint history

`Operations.inspect_history`, `capture_checkpoint` and `read_checkpoint` expose
the stage-2 checkpoint boundary. The application contracts carry typed facts;
`publication.vault_history` owns filesystem and Git I/O. Current admission and
the accepted S1 `ReviewPlan` supply scope and consent. A loaded historical review
always requires current revalidation before it can authorize a new operation.
The [vault admission policy](vault-admission.md) describes supported Git layouts
and the unchanged-target prerequisite during a running vault-changing operation.

## Owned history

The association binds a vault/import pair, source collection/module and physical
vault/Git roots. Its derived `refs/brz2obsidian/imports/<association>/checkpoints`
ref points to a converter-owned commit chain independent of the user's branch.
The small `.brz2obsidian/locator.json` names the current association, generation
and commit for discovery. A locator alone never establishes trustworthy history.
The reader compares it with the owned ref, real commit parents, schema-versioned
association and manifest blobs, complete role trees and verified blob bytes for
every retained generation. Unknown graph nodes, missing roots, mismatched
inventories, duplicate or unknown interpretation fields, and inconsistent
semantic meaning refuse dependent capture. Raw control-object bodies are
released after each validated generation; the Git control-response limit is
per generation rather than a lifetime history-size limit.

Each manifest records ordered path, Git mode, size, SHA-256 and Git object ID
inventories for `source`, `vault`, `preimage` and `proposed`. The `prepared`
boundary keeps the proposed result and original preimage before a later apply
intent. A `result` boundary requires that exact prepared commit and a complete
current vault inventory equal to the proposed inventory, while retaining its
source and preimage roles. A meaningful new boundary may append history;
equivalent input, settings and review meaning return the existing checkpoint.
Volatile review IDs and operation/history proof tokens do not create duplicate
history, but this duplicate check grants no general current apply authority.

Exact S1 `SavedReview` values are kept in a compact reachable transport:
`review.json` names byte values by SHA-256, using existing role blobs where
available. Any additional historical bytes live under the `review-content`
role. The reader requires every marker to resolve to exactly one declared,
reachable blob and rejects unused extra review-content edges. It verifies Git
type, length, SHA-1 and SHA-256 before restoring the strict S1 value through
core `load_review`. Source-version keep/decline, mapping, path decisions and
approved exact bytes remain historical evidence; `LoadedReview.ready` is false.

## Capture and failure outcomes

Capture obtains a fresh admission/history observation before work and compares
it with the caller's supplied admission. It checks required storage and tracking
consents, selected subject scope, current source/review bytes and, for a result,
the prepared policy rules and complete result inventory. A selected absent path
may become present under unchanged rules and reviewed inclusion; full current
inventory still records its actual bytes. Changes to the relevant rules or
consent scope refuse continuation.

Input sizing and available temporary/Git space and memory are checked before
spooling. The converter then copies raw on-disk bytes into owned temporary
spools, verifies their length and digests, and writes Git blobs without filters
or the user's index. The user's index bytes, staged paths and modes, HEAD,
branches, tags, independent refs, configuration and unrelated authored files
are not rewritten by checkpoint capture. Actual object writes are read back
before they are reported as verified. `not_started`, `possible` and `verified`
distinguish an untouched object store, a write whose outcome is uncertain, and
independently verified objects. `objects_written` says an owned object was
independently found; `history_retained` says the owned ref points at the new
commit. A failure after ref publication but before durable locator replacement
can truthfully report retained history while current discovery requires
recovery. Locator writes flush the pending file before replacement.

The measured small binary checkpoint is a development control; the accepted
full resource envelope and complete ordinary check budget are qualified by
stage-2 integration issue #278. Native durability and later apply/recovery/Undo
behavior have their separate stage-2 owners.
