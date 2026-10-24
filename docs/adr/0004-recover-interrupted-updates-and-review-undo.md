---
status: accepted
---

# Recover interrupted updates and review undo

An interrupted update must be detected on restart and recovered before another
update begins. Retain enough Git history and operation metadata to finish applying
or restore affected files. If those files have subsequently changed, preserve the
new edits and require review instead of resetting the whole vault. This accepts
explicit recovery work because ordinary file publication cannot be treated as a
completed update merely because its history was recorded.

The first release offers Undo for the most recent applied import or update,
presenting the reversal for review and protecting edits made afterwards. Users
therefore have a recovery path without needing Git knowledge. Reversing older
operations is deferred.
