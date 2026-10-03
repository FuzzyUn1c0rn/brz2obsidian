# 04: Adapt thought and image links without rewriting notes

Status: resolved

Assignee: /root/implement_04

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Convert actual source-local thought and image links into working vault references while preserving all other authored Markdown, code examples, and newline spelling.

**Blocked by:** [02: Preserve hierarchy and empty thought targets](02-hierarchy-empty-targets.md); [03: Preserve files and resource references](03-files-resource-references.md)

**Specification stories:** 17, 48, 49.

**Acceptance criteria:**

- [x] The BRZ source module recognizes supported inline local thought/image references, decodes compact thought IDs with the verified byte ordering, protects code/literal examples, and emits typed spans bound to exact document text.
- [x] Core resolves live created or uncreated thought targets and preserved image assets; embedded references do not invent additional Related edges. Invalid or unsupported local/cross-Brain references receive actionable refusal.
- [x] Renderer applies only approved nonoverlapping spans with bounds, expected-substring, digest, and binding checks; source text outside those spans remains exact, including CRLF/CR/LF spelling.
- [x] Existing images remain inline using correctly encoded relative resource paths from both root Home and ordinary note locations. Original note bytes remain independently preserved.
- [x] Generated note Wikilinks are qualified and use safe readable aliases, preserving original display evidence. Names containing dots and collision suffixes resolve to exactly the assigned target.
- [x] The early span gate now passes through the complete public source-to-vault workflow, including repeated identical links, nesting, escaped delimiters, lists/quotes, inline/fenced code, and unsupported reference-style/HTML local syntax. Do not rebuild whole source Markdown from parser tokens.
- [x] Inspect, counts, migration record, adaptations, and terminal/JSON results agree with actual converted references; independent expected references and nonadapted text comparisons verify the output.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.

- 2026-10-03 (/root/implement_04): Implemented supported inline thought/image references through the complete public BRZ-source -> core -> Obsidian-renderer -> publication workflow. Compact GUIDs use verified .NET `bytes_le`; inward document spans bind canonical item/asset IDs while retaining exact original syntax, original display evidence, source destinations and document digests. A character provenance map follows CRLF/CR normalization and parser block indentation, including partial tab expansion and ordinary Unicode line separators. Image destination subspans preserve authored alt/title spelling and share the one preserved asset assignment; root Home and Notes use their actual encoded relative paths.
- 2026-10-03: TDD red evidence covered the initial unsupported-reference workflow, Unicode/tab provenance errors, silently missed reference-style/autolink forms, image-alt corruption from naive destination substitution, and a renderer KeyError for an absent assigned target. Public tests now independently expect the final vault bytes, unchanged authored segments/newlines, backup/image bytes, qualified dotted/collision paths, safe aliases, counts, original reference evidence, adaptations/accounting and terminal/JSON output. Core and renderer reject altered bounds/text/digests/targets and overlap; live uncreated targets remain intentional and embedded links add no Related relationships. Typed actionable refusals cover invalid IDs/images, cross-Brain/server-qualified links, unsupported reference-style/HTML/autolink local syntax and overlapping image-wrapped thought links. Code, escaped literals, comments and external links remain unchanged.
- 2026-10-03: Merged integration tip `979993b` (ticket 05 native tags) before final verification, retaining tags/frontmatter/listings alongside reference behavior. All commands used root project `.venv\Scripts\python.exe` with `PYTHONPATH=C:\Users\stefa\projects\brz2obsidian-worktrees\ticket-04\src`, without reinstalling shared editable packages. `-m pytest tests/application/test_links_workflow.py tests/application/test_reference_module_seams.py tests/sources/test_note_spans.py -q`: 37 passed. Final `-m pytest -q`: 150 passed. `-m ruff check .`: passed; `-m ruff format --check .`: 58 files already formatted; `git diff --check`: passed. Full independent real-export preservation and native Obsidian acceptance remain the later tickets 09/10; this ticket records synthetic public-seam evidence only.