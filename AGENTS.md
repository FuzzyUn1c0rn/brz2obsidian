## Agent skills

### Issue tracker

Track issues, specifications and Wayfinder maps in GitHub Issues for
`FuzzyUn1c0rn/brz2obsidian`.
See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five default triage roles.
See `docs/agents/triage-labels.md`.

### Domain docs

Use a single-context layout with root `GLOSSARY.md` and `docs/adr/`.
See `docs/agents/domain.md`.

## Implementation Work

For any implementation work, applying the `tdd` skill is mandatory.

## Python environment

Use the project `.venv` interpreter for Python development and tooling
(`.venv\Scripts\python.exe` on Windows). Create it if missing.
Install runtime, build, and development packages only inside this environment, as they become
needed. See `README.md` for bootstrap commands and dependency manifests.

## Automated checks

Select checks from the actual change, affected consumers and mandatory acceptance
criteria. Run or accept pytest, Ruff lint/format and dependency checks only through
`tools/check.py`; before running or accepting them, read
[the runner and receipt contract](docs/testing.md#automated-check-runner).

Focused or manual-only verification is valid when it establishes the required
scope. Broaden or repeat checks for new changes, failures or unresolved concerns.
Required full-suite, fresh-execution and user/native acceptance gates still apply.

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
