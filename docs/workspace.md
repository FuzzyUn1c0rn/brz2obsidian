# Workspace housekeeping

Store small disposable planning artifacts under `.scratch/<effort>/` and
generated development artifacts under `tmp/<effort>/` in the current checkout.
Both directories are Git-ignored. Keep the original exports,
retained user vaults, backups, reusable tests and durable decisions in the
locations below so a finished temporary effort can be deleted safely.

## Where files belong

| Location | Purpose | Lifetime |
| --- | --- | --- |
| `brz/` | Original private TheBrain exports and retained user vaults | Keep; not temporary |
| `backups/` | Private preimages and restore evidence for changes to user files | Keep until the backup is explicitly retired; Git-ignored |
| `tmp/<effort>/` | Generated test vaults, audit runs, screenshots, reference snapshots, one-off scripts and agent handoffs | Disposable after the effort finishes; Git-ignored |
| `.scratch/<effort>/` | Draft issue bodies, exploratory notes and other small temporary artifacts | Disposable; Git-ignored |
| `tests/` | Synthetic fixtures, reusable test helpers and the independent acceptance driver | Versioned development support |
| GitHub Issues | Specifications, Wayfinder maps, tickets, accepted decisions and durable discussion; see `docs/agents/issue-tracker.md` | Durable project records |
| `docs/`, `GLOSSARY.md`, `AGENTS.md` | Current development guidance and domain decisions | Versioned project records |

The existing `brz/Software Engineering v2` vault keeps its established path.
Future retained user vaults should have an explicit destination selected for
that migration. Never use them for destructive tests or temporary experiments.
Private data remains ignored even when it needs to be retained.

Python's `.venv`, `__pycache__`, and packaging tools' `build/`, `dist/` and
`*.egg-info` are tool-managed, ignored locations. Keep the working environment;
caches and build products can be recreated.

## During development

1. Choose a short effort name such as `tmp/v3-types/`. Put that effort's runs,
   notes, screenshots and one-off scripts inside it. Agent handoffs stay inside
   the current checkout rather than in sibling folders.
2. Use fresh destinations for conversions and private acceptance runs. Short
   paths preserve room for imported filenames under the converter's path limit.
3. Promote reusable helpers into `src/`, `tests/` or a maintained tool directory.
   Publish specifications, Wayfinder maps, tickets and accepted decisions in
   GitHub. Keep current architecture decisions in `docs/adr/` and maintained
   development guidance in `docs/`. Record aggregate acceptance results before
   retiring their temporary evidence.
4. Keep original inputs and the only copy of user-created or edited content
   outside `tmp/` and `.scratch/`. Retain required restore copies under `backups/`.
5. Delete a finished effort's temporary directory when its reusable support and
   required records have been retained. Keep active efforts until their work is
   complete. Tests and maintained tooling must not depend on historical runs,
   temporary handoffs or sibling folders.

The [automated check runner](testing.md#automated-check-runner) allocates exclusive
`tmp/checks/<run>/` directories with independent pytest basetemps and pytest/Ruff
caches. Logs and receipts stay outside pytest-owned paths. Legacy configured
`tmp/pytest`, `tmp/pytest-cache` and `tmp/ruff-cache` locations remain relevant
only for the documented bootstrap or runner-failure investigation exceptions.

Managed Git worktrees use the Codex app's worktree lifecycle and their assigned
paths. Archive them through that lifecycle, preserving needed ignored files
first, rather than moving their checkouts into `tmp/`.

