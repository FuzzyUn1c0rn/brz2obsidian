# Read-only vault admission

`Operations.inspect_vault(vault, subjects=...)` is the public preparation seam
for an existing authored vault. `VaultSubject(path, subject_id)` associates a
reviewed source facet with an intended vault-relative file path. Caller values
select observations; they supply neither trusted storage facts nor consent.

The lazy outer implementation lives in `publication/vault_admission.py`.
`application/vault_contracts.py` contains immutable, closed application values
with a version-1 `brz2obsidian.vault-admission` envelope. It reuses S1's
`ReviewPreflight` and `ReviewConsentRequirement`. Core reconciliation and the
fresh-destination `FilesystemPublisher` retain their established roles.
The existing worker operation literals and protocol version 3 are unchanged.

## Unchanged-vault operation prerequisite

From conversion start until it finishes or stops, the user, Obsidian, sync tools
and other programs must leave target authored content and relevant settings
unchanged. The same prerequisite applies during vault-changing recovery, Undo,
repair and cleanup. Concurrent target-vault editing is unsupported. Existing
operation guidance must explain this limitation without an additional
acknowledgement dialog or checkbox. The
[2026-10-23 user amendment](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/254#issuecomment-6360422317)
supersedes earlier active-writer protection requirements and mandatory race gates.

Pre-existing edits, review-time edits outside an active operation and edits
between stopped or completed operations remain supported. Before starting or
resuming, validate current review and affected assumptions, refuse detected stale
facts and selectively invalidate affected decisions while retaining unaffected
ones. Converter ownership, containment, exact byte/history integrity, ordinary
atomic-write/flush, interruption recovery and later-edit Undo remain required.
An observation may detect a change and refuse; it does not reserve the vault or
guarantee preservation against an edit arriving while the operation runs.
Existing cache/temp exclusions retain their scope.

## Interpreting an observation

A supported result admits review of history, or review of initialization when
there is no repository. It grants no capture/publication authority or reservation.
The full observation fingerprint covers current inventory, native identities,
index/staged facts, HEAD/refs, effective policy and qualified Git capabilities.
The preflight state fingerprint describes unresolved history/operation authority
separately, so unrelated authored edits do not invent a new history identity or
invalidate every S1 choice through its history dependency.

History/operation authority stays unknown until the owning history/recovery
implementation validates current reachable records. Existing converter metadata
requires recovery discovery first. Incomplete or unreadable inventory stays
incomplete; it never means a local deletion. Refused or unknown observations
admit no dependent preparation. Recovery-first results admit resolving the
existing operation, preserving its files, refs and foreign locks.

`policy_scope="before_initialization"` explicitly marks provisional discovery.
Git requires a repository for its attribute/ignore interpreters. Admission uses
an app-owned empty temporary Git directory with the actual vault as its worktree;
it creates no authored blobs, target index or target history. The view freezes the
actual pre-initialization scalar attribute/ignore configuration so its temporary
name cannot activate unrelated `includeIf` rules. Physical temp containment and
native access are established before allocation, without `gettempdir()` access
probe files. Cleanup removes only this owned external view. A separate typed-query helper
may build ephemeral ordinary indexes in another owned empty Git directory; these
hold control names and already observed mode/OID/path rows, without authored
payload or object writes. Both namespaces are owned for the observation and
close on success or failure.

After reviewed target initialization, #272 must rediscover actual Git policy
before the first authored capture. Actual `includeIf gitdir`/`onbranch` policy
can now differ; changed policy requires re-review and new scoped consent before
capture. A retained empty initialized repository is an actual preparatory change
and must be disclosed truthfully by that operation's result.

## Policy and recovery coverage

Git's printed attribute states can share spellings with assigned strings. The
adapter uses `check-attr --all` and the documented typed attribute pathspec
matcher to retain their identities. An isolated probe checks literal strings
against genuine true/false/reset markers before the real policy query. Its
configuration, global/system attributes and probe index are independent of
actual authored rules. The later ordinary index preserves original indexed
attribute OIDs and adds only missing observed/selected names; actual Git context resolves
current global/info/nested rules and index fallback. Internal exact-path queries
neutralize inherited pathspec interpretation switches. Raw/typed attribute and
batched ignore observations reject incompatible policy. Repeated observations
can detect changes but do not establish external-writer exclusion. Policy
fingerprints include the decoded identities, rather than their printed words.
See [Git's typed matcher](https://github.com/git-for-windows/git/blob/v2.55.0.windows.5/pathspec.c#L720-L748).

Storage requirements disclose that converter snapshots retain exact on-disk
bytes despite applicable built-in newline, encoding or keyword transformations.
Tracking requirements separately identify selected ignored authored subjects.
Both bind the vault/repository, effective policy and subjects. Tracked ignore
matches remain tracked. Unrelated ignored authored paths remain untouched and
appear as recovery gaps. Known cache/temp directories are explicitly disclosed
in `exclusions` and remain outside the authored inventory.

Built-in transformation applicability follows modern text/legacy crlf precedence,
explicit negative text, encoding and ident semantics. Merge selection retains
case-sensitive driver subsections, configured defaults and overrides of built-in
names, while genuine boolean merge states retain their built-in behavior. See
[conversion precedence](https://github.com/git-for-windows/git/blob/v2.55.0.windows.5/convert.c#L1246-L1285)
and [merge-driver selection](https://github.com/git-for-windows/git/blob/v2.55.0.windows.5/merge-ll.c#L341-L369).

Applicable custom filters/encryption/LFS, active recognized hooks (including
reference-transaction), custom merge/diff/textconv programs and unsupported
layouts refuse. Empty hook locations, inactive samples, unused definitions,
ordinary user refs/remotes, dirty files and partial staging remain admissible
under the other conditions. No command contacts remotes, refreshes the real
index, modifies settings/safe.directory, clears flags or repairs user history.
Inherited Git trace/Windows redirection sinks are removed from child processes;
storage/attribute-source/graft redirections yield explicit refusal before Git is run.

## Engineering qualification and resource limits

The observed baseline is Git 2.55.0.windows.5 with Python 3.14.8 on the current
Windows host, ordinary local SHA-1 objects and file refs. The version is recorded
rather than used as a version floor. Admission checks actual layout/format
responses, raw empty-blob SHA-1, NUL policy/index reads, local object batching and
required plumbing options. Command names alone do not establish capability. On the qualified Git-for-Windows
layout, cached option proof binds the freshly reported version, both the selected
launcher and underlying Git binary hashes, and execution paths. Other layouts or
explicit executables repeat option proof.
Unqualified object/ref formats refuse pending focused compatibility evidence.
Before any Git index consumer, a bounded native-handle read validates the index
checksum, entry extents and actual extensions. Split/sparse indexes refuse;
orphan shared-index files alone do not. Actual ordinary index versions 2/3/4,
including intent-to-add and compressed paths, have public controls. A SHA-256
index remains explicitly unqualified rather than being treated as extension-free.

File hashes stream in 1 MiB chunks. Ignore/attribute inputs are batched. Git
control input plus combined stdout/stderr has a 16 MiB budget; directory/control
observations have a bounded resource budget too. Overflow, malformed results,
I/O errors or the 30-second process deadline yield safe unavailable observations.
The control-output budget does not limit authored binary payload size; #272
owns streamed capture and #273 owns publication/resource rechecks.

Windows observations use OPEN_EXISTING with OPEN_REPARSE_POINT, verified final
handle paths, native owner/security descriptors and same-handle hashing.
Directory listing and affected-path creation/write access are checked separately
from reading unrelated authored files. No owner-equality rule is imposed;
Windows decides access for the actual token, and Git's trust result is retained
without overrides. Directory identities/names, current file identities and Git
metadata are rechecked. Native observations remain current observations and
require another check under later operation ownership.

The read-process adapter uses the Python 3.14 Windows pipe setup and native
suspended creation, attaches the owned Job Object before resuming its primary
thread, then terminates owned descendants and closes pipes on every exit. Its
private-runtime integration and Windows mechanism are qualified by the stated
baseline; other runtimes/platforms need their own actual qualification. This
claim covers owned Git work, not a sandbox for arbitrary launchers.

## Acceptance ownership and public controls

The accepted source is issue #271, under #257/#254 and ADRs 0001/0003/0007.
The checklist's six bullets map to A1–A6 in that order. Tests use independent
literal bytes/paths/modes and compare actual files, index/staged blobs, HEAD,
refs and configuration. The two owning files are selected once in the maintained
manifest. Real supported fixtures require a uniquely marked system-temp case
container because the checkout itself lies in a parent repository (C12). Fixture
manifests, timings and receipts remain in checkout `tmp/issue-271*`; old evidence
and fixtures are preserved.

| Criterion | Owning public evidence |
| --- | --- |
| A1: complete C admission observations | Both `test_vault_admission.py` and `test_vault_admission_layouts.py`; C mapping below |
| A2: effective policy/nonexecution | system/global/repository/info rules, literal driver identities, default/override/case selection, qualified canaries, active/inactive hooks and trace sinks; external-policy writer remains historical evidence |
| A3: actual advanced/incomplete layouts | real linked/bare/unmerged/format controls and storage-layout matrix |
| A4: authored inventory/path/access | exact unborn/dirty inventory, actual Windows ACL/junction/hardlink/read-only controls and caches; concurrent file race remains historical evidence |
| A5: scoped storage/tracking choices | builtin/inclusion requirements, tracked ignores, changed policy, conditional post-init rediscovery |
| A6: typed facts/coverage/fingerprints | strict record rejection, independent authority/observation fingerprints, current-user-state and unavailable controls |

| Policy row | Owning control / execution limit |
| --- | --- |
| C01 | no-repository/missing-Git, future conditional policy, temp containment and cleanup; #272 performs reviewed initialization/capture |
| C02 | unborn root, committed dirty root and detached HEAD with exact unchanged state |
| C03 | same-file partial staging, literal staged blob and raw index preservation |
| C04 | ordinary refs/remotes, unused definitions and cache exclusions |
| C05 | built-in/legacy exact-byte storage, modern-text precedence, literal encoding/ident distinctions and typed-policy binding |
| C06 | actual custom/missing/reserved-name filter canaries, genuine negative/reset contrast and global/info/index-fallback bindings |
| C07 | LFS attribute/pointer refusal without payload execution |
| C08 | merge-default/built-in override/mixed-case driver canaries, genuine boolean contrast, active uppercase Windows reference hook and inactive locations |
| C09 | Git markers/foreign locks/converter metadata even without local Git, actual unmerged stages; no abort/delete |
| C10 | repository/global/info ignores, tracked matches, distinct selected inclusion and unrelated gaps |
| C11 | actual main+linked worktrees and redirected metadata |
| C12 | parent/root-within-parent and nested repositories; actual bare root |
| C13 | actual sparse configuration, split-index early gate/orphan contrast, skip-worktree and assume-unchanged flags |
| C14 | actual shallow/promisor/alternate/grafted ancestry, missing/corrupt objects and SHA-256/reftable refusals |
| C15 | actual junction/hardlink/read-only/ACL denial; concurrent bytes remains historical evidence; synthetic low-space fact at the filesystem seam |
| C16 | exact 18 MB binary inventory remains supported; #273 owns binary apply and #278 measured resource qualification |
| C17 | installed Git/capabilities, missing executable and actual unsupported format/typed-matcher wrappers with setup findings |

Recorded external-policy writer, concurrent file race and concurrent bytes
observations retain their original results and evidence references for the
recorded candidates, including successful observations. They are historical
evidence, not a current concurrent-edit guarantee or mandatory active-writer
gate. Preserve their original fixture manifests, timings, receipts and source
references; the amendment changes current acceptance, not past observations.

R27 maps to the C10 scoped inclusion requirements and disclosed recovery gaps;
#272/#273 own the approved or declined execution. R30 maps to C17 capability
and setup findings. R43 retains the accepted C/H boundary: this admission seam
supplies current facts, and history, recovery and aggregate owners establish
H-policy authority before dependent operations.

Decline/no-byte-publication is enforced by the S1 consent gate and the later
capture/apply owners. This read-only seam never accepts approval flags and
cannot write history on either choice. Actual history validation, publication,
restart recovery, durability and full S2 integration remain with #272–#278;
source/native/user acceptance remains separate from regression coverage.
