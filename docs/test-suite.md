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

For everyday development, run the smallest affected selection through
`tools/check.py`. Use `tools/coverage_suite.py --test <file-or-node>` when a new
coverage measurement helps the decision. Focused measurements are partial suite
evidence; neither command requires running the default bundle after every edit.
See [the runner and measurement contract](testing.md#automated-check-runner).

The historical exhaustive suite is retired by the user's 2026-10-17 decision.
Older full-suite or fresh full BASE/GUI ticket requirements are withdrawn.
Never recreate those executions by accumulating focused batches. The reduced
selection and affected focused checks are the automated verification strategy.

## Responsibilities and additional checks

The manifest retains existing public-contract tests and representative real
integrations. It also retains a compact independent preservation audit and
checks of the measurement/runner infrastructure. These protect distinct
assertions even when they add no production branches.

Three selected existing controls address the function-level review's first
priorities: distinct resource filenames and original bytes after naming
collisions, preservation of caller-owned replacement capture directories,
and rejection of same-size payload corruption after repeated verification.
The corruption control selects profile 3; it does not restore the older-profile
matrix. These checks protect observable migration and filesystem safety outcomes.

| Family | Default responsibility | Trigger for additional focused checks |
| --- | --- | --- |
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
retained suite contains 397 test definitions and exactly 1,149 cases. Helper-only
modules, fixtures and assets remain available to retained tests and independent
acceptance tools. Retired assertions provide no current automated assurance.

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
