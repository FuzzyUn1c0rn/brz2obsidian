# 01: Convert a minimal Brain into a fresh vault

Status: resolved

Assignee: /root/implement_01 (codex/brz-v1-01)

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Install the CLI and reuse its library workflow to inspect and convert a tiny, valid Brain with one plain Markdown Home note into a verified fresh vault.

**Blocked by:** None (can start immediately).

**Specification stories:** 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 35, 36, 37, 38, 39, 40, 60, 61, 63, 64, 65, 69, 71, 72, 73.

**Boundary and dependency rationale:** This is the first complete path through source interpretation, inward contracts, analysis/planning, pure rendering, publication, workflow, CLI, and tests. There is no production code requiring a separate prefactoring ticket.

**Acceptance criteria:**

- [x] Use the project virtual environment on native Windows/Python 3.14 to install the package and exercise both the console and module entry points. Install runtime/build/development dependencies only in that environment as needed, check compatibility, record resolved versions in the requirements manifest, and run behavioral/lint checks through its interpreter.
- [x] A shareable synthetic format-5 archive with the verified root record structure and explicit Home can be inspected without output mutation and converted through the reusable workflow and CLI. Convert repeats preparation instead of trusting a prior inspect result.
- [x] The generated vault has an always-created root Home with original heading/body, migration report, version-1 migration record, exact original-note backup, and tested native startup/bookmark preferences. An empty Home variant also creates a concrete entry.
- [x] Retain every source record/field, omitted/null distinction, raw date, original source identity, and present bytes for this slice. Original evidence is separate from strict normalized facts; actual byte hashes/lengths and source accounting are verified.
- [x] Use the accepted reusable deep-module interfaces and strict frozen Pydantic contracts with immutable nested values. Pure core/rendering has no I/O or outer imports; generic workflow uses injected source/rendering/publication interfaces; CLI alone handles arguments, output, and exit translation.
- [x] Text results are actionable; JSON is one version-1 envelope with honest planned/actual/null counts and a receipt only for verified publication. Invalid Home/source and nonempty destination variants fail with stable diagnostics and no alteration of caller content.
- [x] Write and verify in owned staging before publication. On a basic pre-commit failure, remove only owned staging and report an actual leftover if cleanup fails. Return durable values after closing source resources.
- [x] Before relying on adapted references, establish an early source-span feasibility gate on exact original text, including code protection, repeated references, CRLF, lists/quotes, and escapes. Repair or replace the private parser implementation if needed without changing the agreed seam; production link adaptation is completed by its own slice.
- [x] Exercise the public workflow/source/rendering/publication seams with actual synthetic ZIPs and temporary destinations. Record and explicitly refuse feature classes not yet implemented; do not present this minimal slice as full real-export support.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.
- 2026-10-03: Provisioned the minimal root virtual environment with Python 3.14.8, include-system-site-packages=false, and bundled pip 26.2.1. The initial requirements manifest is empty; no third-party project dependencies are installed. Package installation, compatibility gates, and complete inspect/convert acceptance remain to implement.
- 2026-10-03: /root/implement_01 claimed ticket on codex/brz-v1-01; confirmed integration codex/brz-to-obsidian-v1 was an ancestor before implementation. Used the accepted workflow/source/core/rendering/publication/CLI seams and the tdd skill's actual-I/O guidance.
- 2026-10-03: Implemented the minimal ordinary Markdown profile with read-only inspect, repeated convert preparation, strict frozen inward contracts, durable source session results, exact original-byte backup, independently retained original JSON (including omission/null, raw dates and high-precision numbers), source accounting, generated native Home preferences/bookmark, and owned staged publication verified by full length/hash manifest. Unsupported relationships, tags, resource attachment classes and live local adaptation are refused explicitly; this is not full real-export support.
- 2026-10-03: Red/green evidence: source-span test first failed collection before source package existed, then passed after parser instrumentation/provenance mapping; workflow test first failed collection before application package existed, then passed after the first full conversion path. Active HTML-local reference test failed because no refusal was emitted, then passed after explicit unsupported diagnosis. Exact display-text assertion failed on pending parser text leaking into repeated-link labels, then passed after scoping text to the recognized link tokens. Two manually drafted expected offsets and one hash were corrected against the authored fixture before being retained as literal expectations.
- 2026-10-03: Native dependency gate passed on Windows CPython 3.14.8 using only the existing root project .venv. Resolved pydantic 2.13.5, markdown-it-py 4.2.0, pytest 9.1.1, Ruff 0.16.10 and setuptools 84.0.0; full transitive versions are pinned in requirements.txt. Editable installation currently points at C:\Users\stefa\projects\brz2obsidian-worktrees\ticket-01; integration will reinstall at the root after merge. pip check reported no broken requirements.
- 2026-10-03: Verification commands, through C:\Users\stefa\projects\brz2obsidian\.venv\Scripts\python.exe: `-m pip install --no-build-isolation -e ".[dev]"`; `-m pytest -q` (18 passed); `-m ruff check .` (passed); `-m ruff format --check .` (passed); `-m pip check` (passed). Tests exercise the installed console .exe and module entry, one JSON envelope/round-trip, strict immutable values, empty Home, nonempty destination preservation, invalid Home/source, unsupported feature refusal, fresh preparation, scoped payload closure, public module composition, staged corruption cleanup, and actual cleanup-leftover reporting. Cleanup denial is injected at the filesystem boundary; all staged files/leftovers are real temporary files.
- 2026-10-03: Root independently opened the freshly published synthetic brz/ticket01-native-minimal vault in native Obsidian 1.13.7. Startup selected root Home — Entry thought in Reading view with original heading/body visible; bookmark badge showed Bookmarked, native Bookmarks listed Home, and following it selected the same assigned root Home. Synthetic screenshot is local ignored brz/ticket01-native-home.jpg. Fresh publication had 1 thought note, 1 original backup, 6 length/hash verified files. This satisfies the narrow native preferences criterion; complete real-source and native first-version acceptance remain tickets 09/10.
