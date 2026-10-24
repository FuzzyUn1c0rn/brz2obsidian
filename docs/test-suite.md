# Maintained test suite

[Issue #227](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/227) defines the
coverage-guided reset. The executable selection is
[tools/test-suite.json](../tools/test-suite.json). Run it with:

```powershell
.\.venv\Scripts\python.exe tools/coverage_suite.py
```

This is the complete ordinary bundle: selected pytest cases, Ruff lint and
format checks, dependency checks, coverage reports and receipt validation. It
requires the GUI development environment, actual GUI test execution, at least
80% **branch coverage of all production Python**, and total elapsed time below
600 seconds. Line coverage is reported separately. The generated summary,
coverage JSON and HTML identify the actual coverage and remaining gaps; the
issue records the qualified candidate and measured baseline.

`coverage.json` retains exact contexts once per file, declared by
`meta.context_scope="file"`. Function/class regions retain their ordinary summaries,
executed/missing lines and branch arcs without repeating the full-file context map.
All production files, including unexecuted modules, remain in the denominator.
Raw coverage data and HTML contexts remain available. Reporting uses the same
global deadline and validates the check receipt before and after reports.

The maintained command uses two pytest-xdist workers, grouping module functions
and class methods together with `loadscope`. It disables scope reordering and
worker restarts. Manifest order is preserved within each worker; global serial
order is not guaranteed. The existing 600-second deadline includes the worker
processes and combined production coverage. Focused measurements and direct
runner checks remain serial by default; `--workers 2` explicitly selects parallel
execution, and `--workers 1` can select serial maintained-suite execution.

For everyday development, run the smallest affected selection through
`tools/check.py`. Use `tools/coverage_suite.py --test <file-or-node>` when a new
coverage measurement helps the decision. Focused measurements are partial suite
evidence; neither command requires running the default bundle after every edit.
See [the runner and measurement contract](testing.md#automated-check-runner).

Ruff excludes the retained experiment sources under
`prototypes/editable-vault-wayfinder/` from routine lint and format checks.
Those files preserve historical experiments and their as-run evidence;
production code, tests and tools remain within both checks.

The historical exhaustive suite is retired by the user's 2026-10-17 decision.
Older full-suite or fresh full BASE/GUI ticket requirements are withdrawn.
Never recreate those executions by accumulating focused batches. The reduced
selection and affected focused checks are the automated verification strategy.

Plain table controls retain source rows/cells, code and breaks, literal protection,
exact current/prior capture binding, references and one real BRZ publication.
The complete actual-source table inventory and native Obsidian review remain
separate acceptance evidence for #237.

## Responsibilities and additional checks

The manifest retains existing public-contract tests and representative real
integrations. It also retains a compact independent preservation audit and
checks of the measurement/runner infrastructure. These protect distinct
assertions even when they add no production branches.

The default runner controls check the selected checkout and duration output,
failed pytest with a later dependency result, and exact parameter evidence.
Source mutation, large output on both streams, interruption and inherited
pytest-option controls remain focused checks when their runner protocol changes.
Their test definitions and independent assertions remain available; omitting them
from the default does not establish those outcomes afresh for every application edit.

Three selected existing controls address the function-level review's first
priorities: distinct resource filenames and original bytes after naming
collisions, preservation of caller-owned replacement capture directories,
and rejection of same-size payload corruption after repeated verification.
The corruption control selects profile 3; it does not restore the older-profile
matrix. These checks protect observable migration and filesystem safety outcomes.

| Family | Default responsibility | Trigger for additional focused checks |
| --- | --- | --- |
| Editable-vault reconciliation | Exact-byte proposals, owner/facet identity, formats/onboarding, structures/memberships, absence/memory, binary/link safety, review/consent, selective refresh and saved-review resume at their public in-memory boundaries | Changed normalized fact, interpretation, decision dependency, history, codec or readiness: select its owning `tests/reconciliation` family plus actual affected consumers. Opaque and malformed inputs, partial evidence and unaffected retained decisions remain independent outcomes. |
| Converter-owned vault history | Selected real admission and repository-layout controls, selected output/reversal effects, binary recovery with a terminal-receipt fault, and persisted selective review refresh | Changed capture, retained graph, publication journal, Undo, matching-history repair or ownership: select the owning application controls and affected consumers, including a real process or native check where required. The complete functional leaf assessments retain their explicit source applicability; the default does not repeat each leaf lifecycle. |
| Core and rendering | Source-neutral planning, names, references, resources, tags, categories, strict facts and exact output examples | A changed planning rule, renderer, classification or resource obligation: select its owning public-module cases and affected output examples. |
| BRZ source | Admission/read failures, exact reference spans, Markdown inserts, exclusion, and representative real conversion | Changed source predicates or formats: select their source-admission vectors. Add downstream checks for a distinct diagnostic, publication or output consequence. |
| Local API source | Capture integrity, transport failures, payload roles, SVG/ICO/JPEG examples, external references, relationship discovery/reversal and qualified missing-TXT behavior | Changed HTTP, profile, codec, join or capture rule: select its positive, near-miss and tamper families at the source/session boundary. Codec-specific variant controls remain important even when their branches overlap. |
| Application and CLI | State/revision handling, warning consent, worker protocol, recovery, truthful receipts, real entry points, JSON/text and safe diagnostics | Changed command, serializer, warning or recovery contract: select the affected result/state vectors and a real process example. Source variations need not all repeat through every entry point. |
| Qt and platform | Actual worker conversion, API controls, responsiveness, diagnostics, recovery, completion actions, preferences and startup coordination | Changed controls, asynchronous callbacks, layout or Windows integration: select their adapter cases. Approved presentation changes also require the existing visual sampling procedure. |
| Publication | Real filesystem staging, ownership, failure cleanup, retry and verified publication facts | Changed filesystem operation or artifact family: select the corresponding fault timing and affected nested-manifest examples. |
| Production vault checker | Source-free conventions, findings, read-only behavior and application integration | Changed convention or checker command: select its direct checker/CLI cases and affected consumer projection. This checker does not prove migration preservation. |
| Independent preservation audit | Original payloads/metadata, pinned-source drift, real-file evidence and rehashed image/span/count forgeries | Changed oracle, source/output meaning or shared audit support: select the affected audit family and its positive/adversarial controls. Do not restore the historical 3,000-plus-case oracle suite. Actual migration acceptance has a separate scope. |
| Runner, coverage and architecture | Source-bound receipts, failures/interruption, Unicode pipes, parameter evidence, isolation, honest metrics, import direction and Windows launchers | Changed runner/coverage contract: run affected public-command controls. Changed packaging/assets/entry points: verify the affected build, install and runnable examples. Skill evals run when their skills change. |

[Issue #229](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/229) physically
retires the unselected historical definitions and parameter variants. The
retirement baseline retained 397 test definitions and 1,149 cases. Helper-only
modules, fixtures and assets remain available to retained tests and independent
acceptance tools. Retired assertions provide no current automated assurance.
Later changes add controls to that baseline; the runner receipt records the
actual selected case count for each candidate.

Issues #231 and #232 add leading-BOM note interpretation/capture compatibility
and readable error controls at public source, application, CLI and Qt boundaries.
These preserve independently checked input distinctions and safe presentation
outcomes even where parser or workflow execution overlaps existing coverage.
Native application appearance remains independently reviewed.

For a future change, select surviving cases that establish its actual scope and
author focused checks where the changed behavior needs coverage. Do not assume
that an older family or matrix remains executable. Broaden for a failure, a new
affected consumer, an unresolved concern or a named acceptance requirement.
Budget additional ordinary checks together with the default bundle when both
are required.

## How the selection changes

1. Inspect missing branches and meaningful outcomes for the changed behavior.
   Measure relevant surviving cases before adding focused checks for gaps.
2. Compare additional branch coverage and elapsed time. Inspect assertions and
   input distinctions wherever contexts show repeated execution. Function
   contexts combine parameter instances, so they cannot prove an individual
   parameter is redundant.
3. Retain independent expected answers, significant input distinctions and
   necessary integrations. A covered branch only proves execution. A low-cost
   regression can remain valuable with zero unique branches.
4. Consolidate equivalent setup or repeated outer-layer variation at its owning
   public interface. Search imports before deleting a test module: several
   existing test files also provide helpers to other families.
5. Update the manifest and this ownership guidance when responsibilities change.
   Qualify the resulting selection with the normal command. Record any proposed
   departure from 80% or the time limit as a measured scope decision; do not
   silently weaken the threshold or exclude production code.

The reset removes 86 exact duplicate executions: 156 declaration cases become
104 distinct UTF-8 inputs, and 57 HTML cases become 23. All distinct bytes,
retained node IDs and existing assertions remain. The HTTP fixture uses a
0.01-second shutdown poll; one same-selection comparison of eight HTTP controls
passed in 7.28 seconds before and 3.17 seconds afterward. This is focused
evidence, not an extrapolated whole-suite speedup.

The default deliberately leaves gaps, notably less common capture/acquisition
failures, source ownership/attachment combinations and some platform/UI errors.
Use the generated missing-branch lists and the table above when those behaviors
change. The 80% checkpoint does not establish every edge case, native appearance
or a separately assigned source/user acceptance verdict.


The maintained manifest includes the ten owning public reconciliation files:
proposals, identity, formats, structure, memberships, absence, attachments,
resolution, refresh and resume. Each is selected once. Their shared value setup
and replay contexts overlap, while their independently expected byte/meaning,
provenance and refusal outcomes remain distinct. They exercise bounded pure and
in-memory outer/core compositions, without repeating the historical Workflow/CLI
matrices. Focused measurements guide additions and actual consolidation.

The final assembled S1 check uses this maintained default once at its frozen
head, including all four checks, actual GUI, all-production branch coverage and
the total 600-second budget. A separately assigned fresh refresh/resume check may
use the matching runner directly; the default supplies line/branch/context/time
measurement. Exact-snapshot receipt reuse across assigned candidate/integration
or aggregate assessments requires explicit requirements and rationale, and never
substitutes for required independent fresh execution or full manual scope. An
unchanged head does not need duplicate broad execution for record bookkeeping.


The maintained selection uses explicit cases from `test_vault_admission.py`:
dirty/staged/Unicode user state, scoped storage choices, configured hooks,
typed attributes, unavailable resource/access observations, denied parents and
metadata aliases, plus representative LFS, foreign-lock, index-flag and external
storage refusals. `test_vault_admission_layouts.py` remains selected once for
actual linked worktrees, bare repositories, unmerged stages, SHA-256 and reftable
qualification refusals. Their independent bytes/index/refs/config oracles remain
explicit. The broader attribute, policy, index-version, access and process
families remain focused checks when those contracts change. The focused #271
assessment also owns the inward-import boundary and minimal Operations consumer;
its original source/evidence binding remains explicit.

Three pure modules, `test_selected_effects.py`, `test_reversal_absence.py` and
`test_reversal_outputs.py`, add independently expected selected-byte, absence,
ownership and link effects. The actual binary recovery control retains its
result after a terminal-receipt failure. The persisted-review control captures
real Git records, reloads them unready, reobserves current facts and retains
choices across repeated memo saves. Editing one note invalidates only that
choice; advancing the actual source/vault baseline invalidates the remaining
stale choice. These controls compose storage with the existing canonical review.
Full crash/restart, latest/interrupted Undo, repair and resource observations
retain their separately qualified evidence and freshness limits; they are not
replayed as a broad matrix in every default run.

Measured focused fixture changes retain their independent outcomes: native Git
CMD delegation reduced the old-format control from 3.56 to 0.87 seconds, the
typed-matcher failure from 14.03 to 3.04 seconds and the actual file writer from
15.14–15.82 to 5.71 seconds. The writer still changes the actual owned file once,
retains its literal new bytes and compares other files/index/refs. These are
focused observations, not a projected whole-S2 bundle qualification.
