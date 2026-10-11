# GitHub scope snapshots

Read this when a structured handoff uses GitHub Issues for its accepted spec or
ticket. `ticket` and `spec` accept canonical
`https://github.com/<owner>/<repo>/issues/<number>` URLs. Existing local-file
records remain supported. Stage requirements use the identical ticket identity.

Before dispatch, the coordinator retrieves the full accepted issue body and
comments, checks the relevant approvals and scope, and preserves the raw UTF-8
JSON under `tmp/<effort>/sources/`. A read-only retrieval example is:

```powershell
$issueUrl = 'https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/123'
$captured = gh issue view $issueUrl --json url,title,body,comments,updatedAt
if ($LASTEXITCODE -ne 0) { throw 'Issue retrieval failed' }
[System.IO.File]::WriteAllText($snapshotPath, ($captured -join "`n"), [System.Text.UTF8Encoding]::new($false))
```

Supply an actual absolute `$snapshotPath` in the effort's ignored directory.
Confirm retrieval is complete; pagination or truncation that leaves relevant
comments unavailable is an unresolved prerequisite. Capture any additional
referenced acceptance decisions as ordinary evidence. GitHub remains the source
of current status, dependencies and decisions; the snapshot identifies the exact
scope assessed in this attempt.

Copy the accepted snapshots unchanged to `sources/ticket.json` and
`sources/spec.json` inside the coordinator's assigned attempt. These files are
shared evidence, so every assessed checkout can use them without local spec
files or commits containing copied issues. When both references use the same
issue, they can share one snapshot path. Candidate input adds:

```json
{
  "ticket": "https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/123",
  "spec": "https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/120",
  "source_snapshots": {
    "ticket": "sources/ticket.json",
    "spec": "sources/spec.json"
  }
}
```

These fields supplement the other required candidate input. Supply snapshots
for exactly the URL references; mixed local-file and URL sources are supported.
The writer binds each path and SHA-256 digest in `candidate.json`. The validator
checks the bytes, issue identity, title, body, comments and `updatedAt` at every
transition, without network access. It establishes preserved content and
identity, while the independent reviewer judges completeness and acceptance.

Keep snapshots inside the attempt and unchanged after publication. Carry-forward
copies them with the original candidate bytes and digests. Changed accepted
scope needs reassessment and a new candidate/attempt, preserving the old scope
and review history. A changed live issue does not silently rewrite old evidence.
