# brz2obsidian

A Python library and thin CLI for migrating verified TheBrain BRZ exports into
a fresh standard Obsidian vault. The accepted specification and implementation
tickets describe the full first-version scope. The current production slice
converts a synthetic minimal format-5 Brain with ordinary Markdown Home into
a verified fresh vault. Relationships, tags, resources and local-reference
adaptation are explicitly refused until their implementation slices complete.

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

Install the recorded native-compatible environment, then the package:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation -e ".[dev]"
```

Package metadata declares dependency families; `requirements.txt` records the
resolved Windows/Python 3.14.8 development environment. Install all packages
inside this environment, adding them only as needed.

The virtual environment is local and must be recreated on a fresh checkout.

Optional activation in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Direct interpreter commands work even when local policy prevents activation.
## Usage

```powershell
.\.venv\Scripts\brz2obsidian.exe inspect tests/fixtures/minimal.brz --json
.\.venv\Scripts\python.exe -m brz2obsidian convert tests/fixtures/minimal.brz brz/minimal-vault
```

Inspect is read-only preflight. Convert repeats preparation and accepts only
an absent or empty destination; it stages and verifies the complete manifest
before publishing. Exit codes are 0 for clean success, 2 for approved warnings,
and 1 for refusal/failure. JSON mode emits one version-1 result envelope;
unmeasured counts are null and receipts appear only after verified publication.

The root `Home — Entry thought.md` is the entry note, with native Home bookmark
and startup selection. `MIGRATION REPORT.md` explains the result;
`migration-record.json` retains source evidence, mappings and byte inventory.
Exact original-note bytes reside under Attachments with `.md.original` ending.

Library callers can use default composition or inject their own interfaces:

```python
from brz2obsidian.application.wiring import default_workflow

workflow = default_workflow()
inspection = workflow.inspect("source.brz")
result = workflow.convert("source.brz", "new-vault")
```

See [architecture](docs/architecture.md) and [testing](docs/testing.md).

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
