# brz2obsidian

A local Python library and thin CLI that migrates reviewed TheBrain BRZ
exchange-format-5 exports into a fresh standard Obsidian vault. It preserves
Markdown, present attachment bytes, original JSON evidence, Home, hierarchy,
Related links and tags. Unsupported source meanings are refused.

The first-version scope is the feature classes verified in two supplied
TheBrain 15 exports and controlled synthetic fixtures. See [source coverage
and warnings](docs/source-coverage.md), the [accepted specification](.scratch/brz-to-obsidian-v1/spec.md)
and [implementation gates](.scratch/brz-to-obsidian-v1/README.md).

## Development environment

Use the project virtual environment for all runtime, build and development
packages. From this checkout, create it if missing and install:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation -e ".[dev]"
.\.venv\Scripts\python.exe -m pip check
```

Direct commands work without activation; optional activation is
`.\.venv\Scripts\Activate.ps1`. Keep every package inside this environment and
recreate it on a fresh checkout. `pyproject.toml` declares dependency families;
`requirements.txt` pins the compatibility-checked runtime/build/development
packages. Tested runtime support is native Windows / CPython 3.14.8. Package
metadata requires Python >=3.14; other platforms and later runtimes have not
been accepted. Native presentation uses Obsidian 1.13.7.

## Inspect and convert

```powershell
.\.venv\Scripts\brz2obsidian.exe inspect 'C:\exports\source.brz'
.\.venv\Scripts\brz2obsidian.exe inspect 'C:\exports\source.brz' --json
.\.venv\Scripts\python.exe -m brz2obsidian convert 'C:\exports\source.brz' 'C:\vaults\new-vault'
.\.venv\Scripts\python.exe -m brz2obsidian convert 'C:\exports\source.brz' 'C:\vaults\another-new-vault' --json
```

For a synthetic trial, use `tests/fixtures/minimal.brz` and a fresh short
output path such as `brz/minimal-vault`. Console and module entry points behave
alike. Inspect is optional read-only preflight: it reports planned targets and
counts, with destination feasibility, payload copy verification and publication
pending. Convert repeats preparation, streams copies into owned staging,
verifies the complete manifest, then publishes.

Only an absent or empty destination is accepted. A nonempty destination is
refused without modifying it. Choose a short path: the conservative final
absolute-path limit is 240 UTF-16 units, including reserved uncreated targets.
This is a one-time migration with no merging, overwrite, synchronization or
Home override. External URLs/directories remain references; conversion does
not fetch or open them.

| Outcome | Exit code | Result |
| --- | ---: | --- |
| `clean` | 0 | Successful inspection or verified publication without warnings |
| `warnings` | 2 | Successful inspection or verified publication with approved warnings |
| `refused` | 1 | Source, feature or destination prevents proceeding |
| `failed` | 1 | Operational failure |

Text mode prints concise counts, issues and guidance. JSON mode writes one
version-2 `brz2obsidian.result` envelope to stdout. Unmeasured counts are `null`,
and `receipt` is `null` until actual verified publication. A later teardown
failure can return `failed` with a retained receipt and `publication_occurred`
issue: inspect that vault before retrying. Argument errors exit 1; help exits 0.

For scripts that capture stdout as UTF-8, set
`$env:PYTHONIOENCODING = 'utf-8'` before running the CLI; otherwise Python uses
the Windows stream encoding. This affects encoding, not the JSON schema.

## Use the vault

Open the generated folder in standard Obsidian. The root `Home — <title>.md`
is the starting note and native Home bookmark; other thought notes are under
`Notes/`; reviewed thought types become notes under `Categories/`. Each typed
ordinary member is materialized, including empty members, and receives linked
`categories` and `appearance_category` properties. Categories retain their own
authored content/resources; members do not inherit that content. Home links to
`Categories.md`, whose native overview discovers category dashboards under
`Categories/` with the `categories` tag. Each dashboard embeds Members and
Gallery Bases from `Templates/Bases/`. Tables start Icon, Note, Inheritance,
categories, created, updated. Gallery uses native image cards. The bundled Bases
plugin and automatic link updates are enabled, alongside native navigation.
Open member views through their category dashboard: a standalone contextual
Base has no embedding category. Native category renames with link updates keep
member discovery working. Membership comes from linked `categories` properties;
Templates/Attachments areas are excluded while legitimate Template-named members
remain visible. Ordinary prose, hierarchy and provider links do not classify notes.

Edit membership directly. `appearance_category` independently chooses a category
in the member's memberships; reordering or adding categories does not choose a
new provider. A valid local `icon` override wins; otherwise the valid provider's
current local image is used. A blank provider opts out, and an invalid provider
shows Invalid provider without borrowing another category's icon. Valid overrides
remain visible with blank or invalid providers. Category icon changes update
inherited dashboard images; note-body images are separately editable migration
snapshots. Declared colours remain metadata. Imported created/updated dates use
source calendar components, with complete original strings retained as evidence.
Bundled Templates is also enabled, with the Templates folder and ISO date format.
Create a new note, switch to Editing view, run **Templates: Insert template**,
and choose the generic New note or the complete template for its category.
Templates use each assigned category stem under `Templates/`, initialize both
dates on insertion, leave overrides blank and omit imported source IDs.
Date variables are quoted literal strings so native link-update YAML rewrites
preserve them; the bundled Templates plugin still inserts the calendar date.
For existing notes, edit `categories` directly: full templates can overwrite
shared scalar properties, including dates and providers. Maintain `updated`
explicitly. In the reviewed Obsidian build, a Properties save normalized CRLF
line endings to LF while preserving authored text. Keep pristine converter
output and original backups for exact pre-edit byte evidence.
`Vault guide.md` documents duplicate lookup, canonical properties,
meaningful entity links, safe editing and the category/member-template/Base
starters for future categories. This follows the actual kepano manual template
pattern with contextual queries and collision-safe links; no registry or
community plugin is required. Additional delivery gates remain tracked in the
[implementation index](.scratch/brz-to-obsidian-v2-implementation/README.md).
Original headings, labels and bodies are retained, with supported
local references adapted to assigned paths. Parents/Children/Related sections
provide navigation; native Backlinks, Graph and tag search provide discovery
without community plugins.

Empty thoughts remain distinct intentional uncreated targets unless they need
files for Home, a definition, typed membership or hierarchy coverage. Click a native link to create one later
under its assigned `Notes/` path. That note does not automatically receive
reciprocal migration sections. Conditional `Uncreated targets.md` and
`Tag memberships.md` preserve otherwise hidden items/connections/memberships;
created-note memberships are available through native tag search.

`Attachments/` groups resources by owner. Thought-note backups end in
`.md.original`; decorative icons remain preserved without Resources clutter.
Inline images stay inline; additional files/external references appear in
Resources. `MIGRATION REPORT.md` explains warnings and simplifications;
`migration-record.json` retains source evidence, identities, target assignments,
relationships, edits and byte inventory. Original JSON preserves numeric
values, raw dates and omitted-versus-null distinctions.

Two exact warning rules cover one absent-TXT pattern and intact icons with
length discrepancies. See [conditions and issue codes](docs/source-coverage.md#approved-warnings).
Other missing required content and unverified meanings stop conversion.

## Check an editable vault

```powershell
.\.venv\Scripts\brz2obsidian.exe check-vault 'C:\vaults\editable-vault'
.\.venv\Scripts\python.exe -m brz2obsidian check-vault 'C:\vaults\editable-vault' --json
```

The public `brz2obsidian.vault_check.check_vault(vault)` operation checks current
properties, category/provider references, required Bases/images and imported
identity pairs without a source archive or migration record. It preserves file
bytes and inventory. Its distinct strict version-1 `brz2obsidian.vault-check`
result reports `clean`/`issues`/`failed`, with command exits 0/2/1 and null
unavailable measurements. Custom properties, template date variables and
intentional uncreated ordinary targets are allowed. See [checker usage,
schema, diagnostic codes and structural limits](docs/vault-checker.md).

## Library usage

```python
from brz2obsidian.application.wiring import default_workflow

workflow = default_workflow()
inspection = workflow.inspect("source.brz")
result = workflow.convert("source.brz", "new-vault")
if result.receipt is not None:
    print(result.receipt.destination)
print(result.model_dump_json(by_alias=True))
```

The workflow returns durable `RunResult` values and does not print, parse
arguments or exit the process. Callers can inject a source/profile, renderer,
publisher and metadata factory, or invoke modules directly. See [architecture
and runnable composition examples](docs/architecture.md).

## Verification and private data

See [test commands and native-review procedure](docs/testing.md), [complete
real-export preservation](.scratch/brz-to-obsidian-v1/research/real-export-acceptance.md)
and [native review](.scratch/brz-to-obsidian-v1/research/native-acceptance.md).
Keep private archives, generated vaults and UI evidence under ignored `brz/`.
Ordinary tests use synthetic inputs and need neither private archives nor GUI
access. Public reports contain aggregate evidence only. The virtual environment,
tool caches and build output are ignored.

The [glossary](GLOSSARY.md) and [architecture decision](docs/adr/0001-source-neutral-core.md)
record terminology and design. Completed Wayfinder research remains decision
evidence; actual implementation acceptance is tracked separately.
