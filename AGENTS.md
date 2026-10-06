## Agent skills

### Issue tracker

Track issues as local Markdown files under `.scratch/<feature>/`.
See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five default triage roles.
See `docs/agents/triage-labels.md`.

### Domain docs

Use a single-context layout with root `GLOSSARY.md` and `docs/adr/`.
See `docs/agents/domain.md`.

## First-version implementation

Before implementing, read the accepted scope and ticket frontier in
[the implementation index](.scratch/brz-to-obsidian-v1/README.md).

## Python environment

Use the project `.venv` interpreter for Python development and tooling
(`.venv\Scripts\python.exe` on Windows). Create it with the available base
Python using `python -m venv .venv` if missing. Install runtime, build,
and development packages only inside this environment, as they become
needed. See `README.md` for bootstrap commands and dependency manifests.

## Temporary artifacts

For development runs, prototypes, screenshots, agent handoffs, or cleanup,
follow [workspace housekeeping](docs/workspace.md). Put disposable artifacts
under Git-ignored `tmp/<effort>/` inside the current checkout.

## Visual verification

Default to strategic sampling for native and rendering checks. Before a visual
review, read [the sampling policy](docs/testing.md#visual-sampling-policy).
