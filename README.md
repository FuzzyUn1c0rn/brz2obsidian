# brz2obsidian

A Python library and thin CLI for migrating verified TheBrain BRZ exports into
a fresh standard Obsidian vault. The accepted specification and implementation
tickets are ready; the production converter has not been implemented yet.

- [Accepted first-version specification](.scratch/brz-to-obsidian-v1/spec.md)
- [Implementation tickets and dependencies](.scratch/brz-to-obsidian-v1/README.md)
- [Initial module and folder layout](.scratch/brz-to-obsidian-v1/architecture-layout.md)
- [Completed Wayfinder map and research](.scratch/brz-to-obsidian/map.md)
- [Domain glossary](GLOSSARY.md)

Start implementation with [01: Convert a minimal Brain into a fresh vault](.scratch/brz-to-obsidian-v1/issues/01-minimal-brain-vault.md), following the [ticket claim and completion process](docs/agents/issue-tracker.md#implementation-operations).

## Development environment

Use the project virtual environment for all runtime, build, and development
packages. The initial target is native Windows with Python 3.14. Create the
environment from the available base Python if it is missing:

```powershell
python -m venv .venv
```

Commands can use its interpreter directly, without activating the environment:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip list
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The initial environment contains only the bundled packaging bootstrap. The
requirements manifest is intentionally empty. Introduce packages gradually when
the implementation needs them, verify native compatibility, and record the
resolved versions. When package metadata is introduced, it will declare the
library's dependencies; the requirements manifest will record the tested
development environment. Keep those roles consistent.

The virtual environment is local and must be recreated on a fresh checkout.

Optional activation in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Direct interpreter commands work even when local policy prevents activation.
The first implementation ticket owns installation, dependency checks, and the
first complete inspect/convert behavior.

## Private data and generated output

Keep real BRZ inputs, generated review vaults, and UI evidence in the ignored
`brz` directory. Use synthetic data for checked-in fixtures and aggregate
results in shareable research reports. The virtual environment, Python caches,
test caches, coverage output, and package build output are also ignored.

Private acceptance inputs and disposable prototype artifacts are not included
in a checkout. Ordinary automated tests will use synthetic inputs; full-source
and native acceptance use the explicitly selected local archives and fresh
test vaults described in the specification.

The completed Wayfinder decisions remain separate from implementation tickets.
Older specification links redirect to the accepted first-version specification.
