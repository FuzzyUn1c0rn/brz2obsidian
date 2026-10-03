# 04: Adapt thought and image links without rewriting notes

Status: ready-for-agent

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Convert actual source-local thought and image links into working vault references while preserving all other authored Markdown, code examples, and newline spelling.

**Blocked by:** [02: Preserve hierarchy and empty thought targets](02-hierarchy-empty-targets.md); [03: Preserve files and resource references](03-files-resource-references.md)

**Specification stories:** 17, 48, 49.

**Acceptance criteria:**

- [ ] The BRZ source module recognizes supported inline local thought/image references, decodes compact thought IDs with the verified byte ordering, protects code/literal examples, and emits typed spans bound to exact document text.
- [ ] Core resolves live created or uncreated thought targets and preserved image assets; embedded references do not invent additional Related edges. Invalid or unsupported local/cross-Brain references receive actionable refusal.
- [ ] Renderer applies only approved nonoverlapping spans with bounds, expected-substring, digest, and binding checks; source text outside those spans remains exact, including CRLF/CR/LF spelling.
- [ ] Existing images remain inline using correctly encoded relative resource paths from both root Home and ordinary note locations. Original note bytes remain independently preserved.
- [ ] Generated note Wikilinks are qualified and use safe readable aliases, preserving original display evidence. Names containing dots and collision suffixes resolve to exactly the assigned target.
- [ ] The early span gate now passes through the complete public source-to-vault workflow, including repeated identical links, nesting, escaped delimiters, lists/quotes, inline/fenced code, and unsupported reference-style/HTML local syntax. Do not rebuild whole source Markdown from parser tokens.
- [ ] Inspect, counts, migration record, adaptations, and terminal/JSON results agree with actual converted references; independent expected references and nonadapted text comparisons verify the output.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.
