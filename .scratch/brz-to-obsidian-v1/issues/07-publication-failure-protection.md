# 07: Protect publication against source and I/O failures

Status: claimed

Assignee: /root/implement_07

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Make interrupted, changing-source, and destination-race conversions fail honestly without exposing partial vaults or modifying caller-owned files.

**Blocked by:** [01: Convert a minimal Brain into a fresh vault](01-minimal-brain-vault.md)

**Specification stories:** 8, 9, 10, 11, 67, 71, 72.

**Boundary and dependency rationale:** The minimal slice already copies an original-note payload through a source session and owned staging, so these failure cases can be completed independently of graph/tag/resource feature work.

**Acceptance criteria:**

- [ ] Plans, rendered artifacts, and payload access bind to both source fingerprint and normalized snapshot digest. A different session/source cannot supply bytes merely because asset IDs match.
- [ ] Detect source mutation/truncation and verify every streamed length/hash plus source consistency before commit. Partial stream, read, write, integrity, or validation failure prevents publication.
- [ ] Validate complete artifact manifests, path uniqueness/containment, conservative final path limits, and absence of unexpected files. Recheck destination state at commit; late caller content must remain unchanged.
- [ ] Cleanup resolves and checks only converter-owned targets before recursive operations on Windows. If cleanup fails, report the exact owned leftover and retain the original material failure diagnostics.
- [ ] Workflow manages session/payload context lifetimes and returns durable values after closure. Access after closure fails explicitly; success/failure paths do not leave required resources open.
- [ ] Return truthful outcomes and actual receipts: none before verified commit; if an error occurs after commit, retain the verified receipt and clearly state publication occurred. Failure results preserve available issues/counts and JSON isolation.
- [ ] Use real temporary files/directories plus controlled faults through public interfaces for early/late failure, destination appearance, wrong binding, changed source, truncated/mismatched streams, staged validation, cleanup failure, and session teardown.
- [ ] Installed CLI and direct workflow calls exhibit the same relevant outcome and diagnostics; assertions inspect actual destination/staging bytes and caller-owned sentinels.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.

