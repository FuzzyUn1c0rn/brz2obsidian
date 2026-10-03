# 08: Prove reuse with an alternate source

Status: resolved

Assignee: /root/implement_08

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Run the same generic conversion workflow with a test-only source module from another format, proving that input replacement preserves compatible vault behavior.

**Blocked by:** [06: Report known gaps and enforce verified source coverage](06-verified-coverage-source-gaps.md); [07: Protect publication against source and I/O failures](07-publication-failure-protection.md)

**Specification stories:** 60, 61, 62, 63, 64, 65, 68.

**Acceptance criteria:**

- [x] Use non-UUID opaque identities that actually reach generic core, explicit stable naming seeds, compatible Markdown/reference facts, assets, hierarchy/jumps/tags, entry designation, and faithful original evidence. No BrainId/settings/numeric TheBrain enum is required.
- [x] Run corresponding logical fixtures through real synthetic BRZ and alternate test source by changing only source binding/profile in composition. Do not change generic core, renderer, publisher, or workflow to accommodate the alternate source.
- [x] Compare corresponding created/uncreated selections, assigned paths, note content, relationships/tags, copied bytes, native configuration, counts, and outcomes under controlled run metadata. Source identities/provenance/fingerprints remain honestly different.
- [x] Reject unknown finding rules, incompatible profiles, invalid normalized references/entries, source changes, and alternate-source stream/lifetime failures with the agreed durable result behavior.
- [x] Enforce inward dependency direction and verify generic modules can operate without importing TheBrain/CLI implementations, including via package initializers.
- [x] Call reusable modules and Workflow directly with no stdout, argument parsing, or process exits; another presentation entry interface can consume the same results.
- [x] Keep the alternate source strictly test support, with no speculative dynamic registry or second production source-format compatibility claim.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.

- 2026-10-03 (/root/implement_08): Implemented the alternate source entirely under test support. Folio JSON names entries, connections, explicitly designated entry, document spans and file-backed payloads with non-UUID opaque keys and supplied stable hexadecimal naming seeds. The Folio module imports only inward contracts and standard-library facilities; it requires no BrainId, settings or numeric TheBrain enums. Its original JSON, naive date, omission/null distinctions and original note bytes are retained faithfully.
- Corresponding independent synthetic BRZ and Folio sources pass the same Workflow, renderer and filesystem publisher with only SourceModuleBinding/profile replaced and fixed RunMetadata. Both create three item notes, preserve four local payloads, retain ten item targets, five hierarchy/Related/tag relationships and two adapted local references. Tests compare created/uncreated paths, note bytes, native/hidden tag memberships, graph listings, resource bytes, report and native app/bookmark configuration against matching and independently specified expected results. Source-specific identities, evidence, fingerprints and original local-reference syntax remain different and truthful.
- Alternate-source failure proofs cover unknown finding rule, incompatible module/version/format profiles, absent/nonordinary entries, invalid endpoints/targets/spans, source mutation, opening/partway-reading a real payload failure, stream revocation/closed session, and postpublication teardown failure. Failed prepublication attempts leave neither destination nor staging; teardown after commit keeps the verified receipt and actual counts. A reviewed Folio warning rule uses the allowed stable warning code without borrowing BRZ predicates.
- Public analyze/plan/render/publish and Workflow calls run without stdout, argument parsing or process exit. Another presentation consumes a round-tripped RunResult. A fresh subprocess blocks all source implementation, CLI, module entry point and concrete wiring imports while converting Folio through generic package initializers. An AST dependency gate also includes every generic package initializer and enforces inward imports. No production module, dynamic registry or runtime second-format claim was added.
- Verification (root project interpreter with PYTHONPATH explicitly set to this worktree src): `C:\Users\stefa\projects\brz2obsidian\.venv\Scripts\python.exe -m pytest tests/application/test_alternate_source.py -q` passed 19 tests. Full `-m pytest -q` passed 255 tests; `-m ruff check . --no-cache`, `-m ruff format --check . --no-cache` and `git diff --check` passed. The test-support tracer initially failed for missing paired-source support and then observable cross-source resource ordering; support was completed with stable corresponding opaque asset order. A subsequent real partial-stream slice failed before adding its source-boundary fault support and then passed. All accepted seams were already confirmed by the specification.