# Triage Labels

Use these GitHub labels for the five canonical triage roles.

| Role | GitHub label | Meaning |
| --- | --- | --- |
| needs-triage | needs-triage | Maintainer evaluation needed |
| needs-info | needs-info | Waiting for more information |
| ready-for-agent | ready-for-agent | Fully specified for an agent |
| ready-for-human | ready-for-human | Requires human implementation |
| wontfix | wontfix | Will not be actioned |

Assignment represents a claim; closing an issue as completed represents
resolution. Internal subtasks resolve after accepted integration on their recorded
feature root; parent specifications require actual delivery and their remaining
gates. PR readiness is separate from triage readiness. Follow
[PR delivery and issue completion](issue-tracker.md#pr-delivery-and-issue-completion).
Migrated issue bodies retain historical `Status:` fields, including `claimed`
and `resolved`.
