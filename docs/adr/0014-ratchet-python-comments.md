# Ratchet existing Python comments down to zero

Run the Python comment ban as part of the maintained lint check. Allow only
the existing multiset of comment text fingerprints for each repository path.
Line numbers shift with normal edits, and a repository-wide count would let
deletions conceal new comments elsewhere. Match Python comment tokens so a
hash inside authored sample text or a string stays part of the program.

Require the baseline to shrink when comments are removed. The prune command
refuses new fingerprints, and review baseline edits as deletion-only. Preserve
the effect of tool directives while they are grandfathered or replace them
with an explicit supported configuration before retiring them. Keep durable
rationale with its decision and file implementation debt against its owning
code.
