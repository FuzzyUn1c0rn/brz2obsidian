# 08: Prove reuse with an alternate source

Status: ready-for-agent

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Run the same generic conversion workflow with a test-only source module from another format, proving that input replacement preserves compatible vault behavior.

**Blocked by:** [06: Report known gaps and enforce verified source coverage](06-verified-coverage-source-gaps.md); [07: Protect publication against source and I/O failures](07-publication-failure-protection.md)

**Specification stories:** 60, 61, 62, 63, 64, 65, 68.

**Acceptance criteria:**

- [ ] Use non-UUID opaque identities that actually reach generic core, explicit stable naming seeds, compatible Markdown/reference facts, assets, hierarchy/jumps/tags, entry designation, and faithful original evidence. No BrainId/settings/numeric TheBrain enum is required.
- [ ] Run corresponding logical fixtures through real synthetic BRZ and alternate test source by changing only source binding/profile in composition. Do not change generic core, renderer, publisher, or workflow to accommodate the alternate source.
- [ ] Compare corresponding created/uncreated selections, assigned paths, note content, relationships/tags, copied bytes, native configuration, counts, and outcomes under controlled run metadata. Source identities/provenance/fingerprints remain honestly different.
- [ ] Reject unknown finding rules, incompatible profiles, invalid normalized references/entries, source changes, and alternate-source stream/lifetime failures with the agreed durable result behavior.
- [ ] Enforce inward dependency direction and verify generic modules can operate without importing TheBrain/CLI implementations, including via package initializers.
- [ ] Call reusable modules and Workflow directly with no stdout, argument parsing, or process exits; another presentation entry interface can consume the same results.
- [ ] Keep the alternate source strictly test support, with no speculative dynamic registry or second production source-format compatibility claim.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.
