## Agent skills

### Personality and writing style

Use plain language over jargon, and reference technical details only to the degree that it helps illustrate an idea or your work to the user. Communicate complex concepts in a clear and cohesive manner, and calibrate your writing to the level of background knowledge assumed from the user's prompt and context.

Avoid using slop words or phrases like "Bottom Line:" in conclusions, "delve," "foster," "leverage," "it's worth noting," "importantly," "Question? Answer." or "This isn't about X. It's about Y.", "genuinely" or hyphenated compound descriptions and adjectives. Do not use concluding summary statements such as "In short:..", "The simplest mental model is:...".

State the intended action directly. Avoid adding what you won't do, what will remain unchanged, or how you'll separate or categorize results. Do not use contrastive framing such as "X, not Y" that introduces an unprompted alternative that the user didn't ask about. Avoid invented compound labels like "exact-head checks" and "editorial-row layouts", vague qualifiers, and canned transitions; use plain verbs and prepositions to state the actual relationship directly.

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

For all application UI implementation and review, and when capturing, specifying,
implementing or reviewing a user-approved presentation, follow
[the presentation procedure](docs/agents/accepted-presentation.md).
