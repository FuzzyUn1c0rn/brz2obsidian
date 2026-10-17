## Agent skills

### Issue tracker

Track issues, specifications and Wayfinder maps in GitHub Issues for
`FuzzyUn1c0rn/brz2obsidian`.
For issue tracking, specification publication, or implementation from GitHub
issues, follow `docs/agents/issue-tracker.md`.

### Triage labels

Use the five default triage roles.
Use `docs/agents/triage-labels.md` when interpreting or changing triage status.

### Domain docs

Use a single-context layout with root `GLOSSARY.md` and `docs/adr/`.
Consult the glossary when domain terminology or behavior is relevant, and
applicable ADRs when investigating or changing architecture, module boundaries,
or public interfaces. Follow `docs/agents/domain.md` for these conventions.

## Implementation Work

Apply the `tdd` skill to features and behavior-changing fixes. For refactoring
and other changes intended to preserve behavior, select verification for the
changed area and affected consumers; existing checks may suffice. Required
acceptance gates still apply.

Continue within the requested scope through implementation, applicable
verification, and repairs caused by the change. Complete only when acceptance
criteria and required review gates are satisfied; identify any remaining blocker
or required user verdict.

## Python environment

Use the project `.venv` interpreter for Python development and tooling
(`.venv\Scripts\python.exe` on Windows). Create it if missing.
Install runtime, build, and development packages only inside this environment, as they become
needed. See `README.md` for bootstrap commands and dependency manifests.

## Automated checks

Use measured coverage to guide every test addition, removal and change. Measure
production line and branch coverage, test contexts and elapsed time. Investigate
repeated-coverage hotspots and consolidate redundant cases, setup and repeated
Workflow/CLI execution. Use focused measurements or applicable existing evidence;
keep independently checked outcomes and meaningful input differences explicit
when execution paths overlap. The complete ordinary verification bundle must
finish in less than ten minutes; everyday feedback should take seconds.

Select checks from the actual change, affected consumers and mandatory acceptance
criteria. Run or accept pytest, Ruff lint/format and dependency checks only through
`tools/check.py`; before running or accepting them, read
[the runner and receipt contract](docs/testing.md#automated-check-runner).

Focused or manual-only verification is valid when it establishes the required
scope. Broaden or repeat checks for new changes, failures or unresolved concerns.
Use `tools/coverage_suite.py` for the complete ordinary verification bundle:
the maintained selection, all four runner checks, production branch coverage
and receipt validation. Use focused `tools/check.py` checks during development.
Exhaustive discovery of every historical test is an explicit additional scope,
not a routine completion prerequisite. Named exhaustive, fresh-execution and
user/native acceptance gates still apply.

## Temporary artifacts

For development runs, prototypes, screenshots, agent handoffs, or cleanup,
follow [workspace housekeeping](docs/workspace.md). Use Git-ignored
`.scratch/<effort>/` for small disposable planning artifacts and `tmp/<effort>/`
for generated development runs inside the current checkout.

## Native investigation

Before investigating source behavior or retrieving content in a native app,
follow [bounded native investigation](docs/agents/native-investigation.md).

## Visual verification

Default to strategic sampling for native and rendering checks. Before a visual
review, read [the sampling policy](docs/testing.md#visual-sampling-policy).

For all application UI implementation and review, and when capturing, specifying,
implementing or reviewing a user-approved presentation, follow
[the presentation procedure](docs/agents/accepted-presentation.md).
