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

## Python environment

Use the project `.venv` interpreter for Python development and tooling
(`.venv\Scripts\python.exe` on Windows). Create it with the available base
Python using `python -m venv .venv` if missing. Install runtime, build,
and development packages only inside this environment, as they become
needed. See `README.md` for bootstrap commands and dependency manifests.

## Automated checks

Every repository agent must run pytest, Ruff lint/format checks and dependency
checks through `tools/check.py`; before running or accepting them, read
[the runner and receipt contract](docs/testing.md#automated-check-runner).
This requirement takes effect when the runner and adoption changes integrate together.

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

When capturing, specifying, implementing or reviewing a user-approved presentation,
follow [the presentation handoff procedure](docs/agents/accepted-presentation.md).
