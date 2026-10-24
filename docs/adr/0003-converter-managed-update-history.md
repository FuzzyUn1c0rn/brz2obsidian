---
status: accepted
---

# Keep update history under converter control

Use Git for version storage and change history, managed locally by the converter
and requiring neither Git knowledge nor a GitHub account. Retain distinct
converted-source versions and vault versions in Git so that source changes can
be reconciled with user edits. Do not maintain an additional history folder or
parallel version store. Converter metadata, such as source identities and import
associations, describes how content is interpreted; it is not a separate history
system and its historical versions also belong in Git. The converter remains
responsible for preservation rules, validation and review.

Capture all authored notes and attachments, including user-created content, plus
relevant configuration; exclude temporary files and caches. Create checkpoints
at import/update boundaries, preserving the current vault before application and
recording the accepted result afterwards. Continuous edit tracking is outside
the converter's scope; users may maintain more frequent commits independently.
This accepts the storage cost of unrelated authored content and large attachments
to preserve context and support recovery across the operation.

Respect existing Git exclusions rather than silently force-adding excluded
authored content. Disclose the resulting recovery limits. If an operation needs
to modify an excluded file, require an explicit decision to include it in
tracking before proceeding.

Reuse an existing vault Git repository with clearly identified converter history,
preserving the user's branches and staged work. If an existing merge or another
repository operation prevents safe integration, require it to be finished before
proceeding. This avoids making users manage commits, branches or Git conflicts
for converter updates while supporting their independent Git workflow.
Keep converter checkpoints until the user explicitly chooses cleanup, showing
storage cost and the recovery that would be lost. Cleanup must preserve the
baseline needed for subsequent updates and respect independently maintained
user Git history.

The first release requires an installed, supported Git version. Check availability
and compatibility before preparing an update and provide setup instructions when
needed. Users operate the converter without needing Git commands; bundling Git
is deferred to standalone distribution work. Repository integration mechanics
and Git's suitability for the required merge cases still require technical
validation.

The first release requires review of the whole update before applying it, as
recorded in [the preservation decision](0002-preserve-vault-edits-during-import-updates.md).
