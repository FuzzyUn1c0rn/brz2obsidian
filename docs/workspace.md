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
| `docs/history/` | Supporting research and verification reports from completed work, plus the GitHub migration index | Versioned historical evidence |
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

Pytest reserves `tmp/pytest` for generated test files and clears it on each run.
Use it only for pytest-owned files. Concurrent runs in the same checkout need
distinct `--basetemp=tmp/pytest-<run>` paths. Pytest's cache is
`tmp/pytest-cache`; Ruff's cache is `tmp/ruff-cache`.

Managed Git worktrees use the Codex app's worktree lifecycle and their assigned
paths. Archive them through that lifecycle, preserving needed ignored files
first, rather than moving their checkouts into `tmp/`.

## Planning records migrated on 2026-10-07

Specifications, Wayfinder maps, implementation indexes and tickets moved from
`.scratch/` to GitHub Issues. Completed work remains closed; the writer-helper
specification remains open as issue #3. Approved layouts and breakdowns are
comments on their feature issues. Supporting research and verification reports
remain under `docs/history/`; its [migration index](history/README.md) maps the
former paths to their destinations. Current documentation links use those
destinations.

`.scratch/` is now empty and Git-ignored, ready for disposable artifacts.
Byte-preserved migration preimages are retained under
`backups/scratch-migration-2026-10-07/`; the migration receipt in `docs/history/`
records source hashes and verified relationships. These backups are restore
evidence, separate from the GitHub tracking records.

## Existing artifacts moved on 2026-10-05

Completed development artifacts have these replacement locations:

| Former location | Replacement |
| --- | --- |
| Historical generated directories and evidence files under `brz/` | `tmp/legacy/brz/<original-name>` |
| Sibling `../brz2obsidian-agent-notes/` | `tmp/legacy/agent-notes/` |
| Sibling `../brz2obsidian-worktrees/` containing four research notes | `tmp/legacy/worktree-notes/` |
| Root `.pytest_cache/` and `.ruff_cache/` | `tmp/legacy/caches/pytest/` and `tmp/legacy/caches/ruff/` |
| `brz/v2-native/ticket-14-reviewed-update/` | `backups/software-engineering-v2/category-update-2026-10-05/` |

The `brz/` directory retains the four original exports, including Management &
Leadership, and the reviewed Software Engineering vault. The small controlled
research exports are temporary evidence under `tmp/legacy/brz/`; the checked-in
synthetic fixtures remain under `tests/fixtures/`.

Historical reports and archived one-off scripts record paths used at the time
of their original verification. Use the mapping above to find relocated
evidence; archived scripts need their paths reviewed before reuse. Current
development commands use `tmp/`.

Links to private temporary evidence are available locally while it is retained;
the versioned reports keep the conclusions after that evidence is deleted.

The local relocation inventory and verification receipt live under
`tmp/housekeeping/2026-10-05/`. They are temporary bookkeeping, not test inputs.
No tests, original exports, user-vault files or versioned decision records are
retired by this move.
