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
it creates no authored blobs, index or target history. The view freezes the
actual pre-initialization scalar attribute/ignore configuration so its temporary
name cannot activate unrelated `includeIf` rules. Physical temp containment and
native access are established before allocation, without `gettempdir()` access
probe files. Cleanup removes only this owned external view.

After reviewed target initialization, #272 must rediscover actual Git policy
before the first authored capture. Actual `includeIf gitdir`/`onbranch` policy
can now differ; changed policy requires re-review and new scoped consent before
capture. A retained empty initialized repository is an actual preparatory change
and must be disclosed truthfully by that operation's result.

## Policy and recovery coverage

Storage requirements disclose that converter snapshots retain exact on-disk
bytes despite applicable built-in newline, encoding or keyword transformations.
Tracking requirements separately identify selected ignored authored subjects.
Both bind the vault/repository, effective policy and subjects. Tracked ignore
matches remain tracked. Unrelated ignored authored paths remain untouched and
appear as recovery gaps. Known cache/temp directories are explicitly disclosed
in `exclusions` and remain outside the authored inventory.

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
| A2: effective policy/nonexecution | system/global/repository/info rules, qualified canaries, active/inactive hooks, trace sinks |
| A3: actual advanced/incomplete layouts | real linked/bare/unmerged/format controls and storage-layout matrix |
| A4: authored inventory/path/access | exact unborn/dirty inventory, actual Windows ACL/junction/hardlink/read-only controls, caches and concurrent file race |
| A5: scoped storage/tracking choices | builtin/inclusion requirements, tracked ignores, changed policy, conditional post-init rediscovery |
| A6: typed facts/coverage/fingerprints | strict record rejection, independent authority/observation fingerprints, current-user-state and unavailable controls |

| Policy row | Owning control / execution limit |
| --- | --- |
| C01 | no-repository/missing-Git, future conditional policy, temp containment and cleanup; #272 performs reviewed initialization/capture |
| C02 | unborn root, committed dirty root and detached HEAD with exact unchanged state |
| C03 | same-file partial staging, literal staged blob and raw index preservation |
| C04 | ordinary refs/remotes, unused definitions and cache exclusions |
| C05 | built-in exact-byte storage requirement and changed-policy binding |
| C06 | actual custom/missing filter canaries, effective global/info bindings |
| C07 | LFS attribute/pointer refusal without payload execution |
| C08 | custom merge/diff/textconv/monitor canaries, active reference hook, inactive samples/empty hook location |
| C09 | Git markers/foreign locks/converter metadata and actual unmerged stages; no abort/delete |
| C10 | repository/global/info ignores, tracked matches, distinct selected inclusion and unrelated gaps |
| C11 | actual main+linked worktrees and redirected metadata |
| C12 | parent/root-within-parent and nested repositories; actual bare root |
| C13 | actual sparse configuration, skip-worktree and assume-unchanged flags |
| C14 | actual shallow/promisor/alternate/grafted ancestry, missing/corrupt objects and SHA-256/reftable refusals |
| C15 | actual junction/hardlink/read-only/ACL denial and concurrent bytes; synthetic low-space fact at the filesystem seam |
| C16 | exact 18 MB binary inventory remains supported; #273 owns binary apply and #278 measured resource qualification |
| C17 | installed Git/capabilities, actual missing executable and old-style unsupported-option wrapper |

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
