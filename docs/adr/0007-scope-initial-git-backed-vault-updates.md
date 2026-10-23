---
status: accepted
---

# Scope initial Git-backed vault updates

The initial support target is a complete, self-contained local repository rooted
at the vault, including staged, unstaged and newly created authored content.
Preserve the user's index, HEAD, branches and independent history. Initially
refuse advanced/shared/incomplete repository layouts and applicable custom
storage or execution rules rather than silently bypassing them. This accepted
scope remains conditional on engineering evidence.

During conversion, from start until finish or stop, the user, Obsidian, sync tools
and other programs must leave target authored content and relevant settings
unchanged. This also applies during vault-changing recovery, Undo, repair and
cleanup. Concurrent editing is unsupported; existing operation guidance explains
the prerequisite without an additional acknowledgement dialog or checkbox. The
[2026-10-23 user amendment](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/254#issuecomment-6360422317)
removes external-writer protection and its mandatory race workloads. Pre-existing
and between-operation edits, fresh review before starting/resuming, selective
invalidation, ordinary byte/history integrity, converter ownership, atomic-write
and flush requirements, interruption recovery and later-edit Undo remain required.

Converter-owned history retains exact on-disk bytes. Built-in line-ending,
encoding and keyword transformations require a specific reviewed storage-policy
choice before snapshots are written; this never grants permission to bypass
encryption, LFS, hooks or unknown repository rules. Existing exclusions retain
their separate disclosure and inclusion-consent requirements. These limits
accept narrower repository compatibility to preserve recoverable bytes without
silently changing the user's storage policy.

If notes arrive without history, offer verified matching history restoration or
separately reviewed preservation-first onboarding, explain unavailable older
recovery/Undo, and resolve interrupted operations first. Do not infer pristine
historical content from current notes or the migration record. The
[accepted compatibility and history-recovery decision](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/248)
records the complete conditional matrix and human answers from 2026-10-20;
prototype discrepancies return there for explicit human revision before affected
implementation specifications become ready.
