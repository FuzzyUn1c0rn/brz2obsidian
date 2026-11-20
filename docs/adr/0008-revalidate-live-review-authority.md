# Revalidate live authority when reusing review proofs

A saved review can reuse immutable backing bytes, replay results, and safely
qualified parses. The current traversal still proves the complete registration
and role closure, exact retained bytes, physical history links, and current
policy before granting authority. A match between two immutable backings can
share storage while their registrations retain distinct provenance. Keeping
reuse below the admission boundary avoids repeated reconstruction while
preserving the guarantees of fresh review and converter-owned history.

A terminal Source Result may supply its physical history anchor to the first
Local review memo, whose own policy must be freshly proved. A format memo may
likewise use its actual onboarding Local as a storage parent without changing
the onboarding replay meaning. Neither history relationship transfers a grant
or a readiness verdict. Reobserve current policy and inventory under the
publication lease even when the same public call already qualified the complete
graph.

See [ADR 0002](0002-preserve-vault-edits-during-import-updates.md),
[ADR 0007](0007-scope-initial-git-backed-vault-updates.md), and
[the bounded Apply and review work](https://github.com/FuzzyUn1c0rn/brz2obsidian/pull/375).
