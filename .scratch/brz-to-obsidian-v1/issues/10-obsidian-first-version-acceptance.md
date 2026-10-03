# 10: Accept the first version in Obsidian and document usage

Status: ready-for-agent

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Review the actual complete converter outputs in standard Obsidian and finish installation, library, CLI, architecture, and testing guidance for first-version use.

**Blocked by:** [08: Prove reuse with an alternate source](08-alternate-source-reuse.md); [09: Verify complete preservation on both real exports](09-real-export-preservation.md)

**Specification stories:** 3, 23, 29, 30, 38, 59, 69.

**Acceptance criteria:**

- [ ] Open fresh test copies of both actual generated real vaults, preserving pre-click output for comparisons. Never test in the user's normal vault; record the native Obsidian version used.
- [ ] Verify root Home, startup selection/native bookmark, representative Parents/Children/Related navigation, uncreated-target click-to-create, and native backlinks/Graph/tag discovery without community plugins or replacement features.
- [ ] Check selected actual inline PNG/WebP, PDF, generic file, and external-reference links from root and ordinary notes. This representative native review complements full preservation checks and does not claim every page/note was reviewed.
- [ ] Fix converter output defects through the responsible public seam, rerun affected automatic/independent checks, and repeat affected native observations before claiming acceptance.
- [ ] Verify installation, console/module commands, direct reusable workflow examples, inspect/convert text/JSON and exit behavior, fresh-vault restrictions, known warnings, intentional uncreated targets, and source coverage are documented accurately.
- [ ] Document reusable module interfaces, inward dependency rules, source/profile composition, private/public test commands, native-review procedure, resolved dependency/runtime versions, and conservative platform/app-version claims.
- [ ] Record that all approved slice criteria, applicable automated tests, alternate-source reuse, complete real-source preservation, and native-review gates passed before declaring the first version accepted. The earlier prototype and completed Wayfinder map cannot substitute for these results.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.
