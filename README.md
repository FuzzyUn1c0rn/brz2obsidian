# brz2obsidian

A local Python library and thin CLI that migrates reviewed TheBrain BRZ
exchange-format-5 exports into a fresh standard Obsidian vault. It preserves
included Markdown, present attachment bytes, safe original JSON evidence, Home, hierarchy,
Related links and tags. Unsupported source meanings are refused.

Version 2 (`0.2.0`) adds thought types as linked categories, native dashboards
and templates, source dates, editable icon inheritance, the reviewed unusual
Markdown note, zero-length absent-TXT findings, YouTube presentation and a
read-only vault checker. All three supplied exports use the same TheBrain
version and exercise different features. Nine complete exact/repeat/reordered
conversions passed [independent preservation after the final presentation refinement](.scratch/brz-to-obsidian-v2-implementation/research/category-bases-first-refinement.md).
See [source coverage and warnings](docs/source-coverage.md), the
[accepted v2 specification](.scratch/brz-to-obsidian-v2-implementation/spec.md)
and [delivery gates](.scratch/brz-to-obsidian-v2-implementation/README.md).
Native review of actual outputs, independent final review and the user's
2026-10-05 actual-vault approval complete those delivery gates. Version 2 is
delivered and accepted.

Version 3 (`0.3.0`) development applies default forgotten-thought exclusion to
every archive. Valid populated ForgottenDateTime markers exclude the subject,
owned content, memberships, relationships and associated evidence before naming.
Authored links/embeds to excluded subjects disappear as whole phrases; unrelated
text and code literals remain unchanged. Exact originals containing excluded
references are omitted, with explicit Document original-copy metadata. Safe
originals remain byte exact. Unscopable history is omitted. Counts describe
included scope; there is no include-forgotten option or individual exclusion
ledger. A forgotten Home refuses. The package, snapshot/policy, module/profile,
renderer and migration result/record contracts now use version 3; BRZ stays 5
and the read-only checker stays schema 1. A narrowly reviewed state-3 absent ordinary Notes.md can now display all usable
same-owner note images in stable asset-identity order. The notice states that
unknown prose, captions and layout were not recovered; the Migration report
provides evidence and optional repair steps. Physically present recognized
Markdown always keeps its normal exact preservation path, including blank notes.
Source-gap and generated-presentation collections record the obligations;
generated embeds are counted separately from authored references. Reviewed
type-owned state-3 Notes.md absence remains unknown category text; missing
type icons give categories and inheriting members neutral appearance while
preserving membership and appearance_category links. Valid member icon overrides
still win. The report distinguishes missing providers from affected included
members. Follow the [current frontier](.scratch/management-leadership-implementation/README.md).

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

See [workspace housekeeping](docs/workspace.md) for source exports, retained
vaults, backups and disposable development files. Use ignored `tmp/<effort>/`
for new runs, prototypes, screenshots and handoffs.

Build a local wheel with the same environment when needed:

```powershell
.\.venv\Scripts\python.exe -m pip wheel --no-deps --no-build-isolation --wheel-dir tmp/build/wheels .
```

Runtime dependencies are Pydantic, markdown-it-py, PyYAML and Pillow. PyYAML serves the
read-only checker; Pillow validates pixels for generated image presentations;
setuptools builds the package. The checked wheel contains
package modules and distribution metadata, with no archives, vaults or tests.

## Inspect and convert

```powershell
.\.venv\Scripts\brz2obsidian.exe inspect 'C:\exports\source.brz'
.\.venv\Scripts\brz2obsidian.exe inspect 'C:\exports\source.brz' --json
.\.venv\Scripts\python.exe -m brz2obsidian convert 'C:\exports\source.brz' 'C:\vaults\new-vault'
.\.venv\Scripts\python.exe -m brz2obsidian convert 'C:\exports\source.brz' 'C:\vaults\another-new-vault' --json
```

For a synthetic trial, use `tests/fixtures/minimal.brz` and a fresh short
output path such as `tmp/minimal-vault`. Console and module entry points behave
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
version-3 `brz2obsidian.result` envelope to stdout. Unmeasured counts are `null`,
and `receipt` is `null` until actual verified publication. A later teardown
failure can return `failed` with a retained receipt and `publication_occurred`
issue: inspect that vault before retrying. Argument errors exit 1; help exits 0.

The v3 combined synthetic gate checks forgotten exclusion, supplied Markdown,
ordered image fallback, neutral category appearance, reciprocal category hierarchy
and existing resources together. It also injects real filesystem/stream failures
at the new artifact paths and verifies complete durable receipts after later
failures. This bounded public proof and the local `0.3.0` wheel/example smoke
supplement the historical v2 delivery evidence; full four-original audits,
native actual-output review and the user's actual-vault verdict remain pending.

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
Gallery Bases from `Templates/Bases/` after its heading and any Parents/Children
navigation, without a generated introductory category image. Retained source
content/resources follow
the Bases; category icon properties/assets still supply dashboard images.
Tables start Icon, Note, Inheritance,
categories, created, updated. Gallery uses native image cards. The bundled Bases
plugin and automatic link updates are enabled, alongside native navigation.
Open member views through their category dashboard: a standalone contextual
Base has no embedding category. Native category renames with link updates keep
member discovery working. Membership comes from linked `categories` properties;
Templates/Attachments areas are excluded while legitimate Template-named members
remain visible. Ordinary prose, hierarchy and provider links do not classify notes.
Reviewed ordinary-parent/type-child edges show every direct included parent on
the category and reciprocal category children on created ordinary notes. An
otherwise empty ordinary parent can remain an intentional uncreated target;
hierarchy does not add it to the category's Members.

Edit membership directly. `appearance_category` independently chooses a category
in the member's memberships; reordering or adding categories does not choose a
new provider. A valid local `icon` override wins; otherwise the valid provider's
current local image is used. A blank provider opts out, and an invalid provider
shows Invalid provider without borrowing another category's icon. Valid overrides
remain visible with blank or invalid providers. Category icon changes update
inherited dashboard images; ordinary/member note-body images are separately editable migration
snapshots. Source colours remain in migration evidence; note properties,
templates and Bases omit foreground/background colour fields. Imported created/updated dates use
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
community plugin is required. See [maintenance and reference adaptations](docs/vault-maintenance.md)
for the full human/agent workflow.
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

Exact warning rules cover reviewed absent ordinary notes with usable owned
images, absent type notes/icons, positive-length absent TXT, the reviewed
zero-length absent-TXT/PDF association, and intact icons with length discrepancies.
See [conditions and issue codes](docs/source-coverage.md#approved-warnings).
Other missing required content and unverified meanings stop conversion.
PDF files open natively, but vault Search does not search their body text.
Reviewed videos keep their exact original URL beside a derived native embed;
network/service availability and offline playback remain destination limits.

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
current v2 preservation](.scratch/brz-to-obsidian-v2-implementation/research/category-bases-first-refinement.md)
and the [completed actual-vault acceptance](.scratch/brz-to-obsidian-v2-implementation/issues/11-native-v2-acceptance-delivery.md).
The [final native review](.scratch/brz-to-obsidian-v2-implementation/research/native-v2-acceptance.md)
records complete technical checks, independent review and the user's final approval.
The [initial v2 preservation report](.scratch/brz-to-obsidian-v2-implementation/research/three-archive-preservation.md)
retains the complete audit before the colour-property refinement.
The [v1 preservation](.scratch/brz-to-obsidian-v1/research/real-export-acceptance.md)
and [v1 native report](.scratch/brz-to-obsidian-v1/research/native-acceptance.md)
remain historical evidence.
Keep original private archives and retained user vaults under ignored `brz/`.
Put disposable conversion outputs and UI evidence under ignored `tmp/<effort>/`.
Ordinary tests use synthetic inputs and need neither private archives nor GUI
access. Public reports contain aggregate evidence only. The virtual environment,
tool caches and build output are ignored.

The [glossary](GLOSSARY.md) and [architecture decision](docs/adr/0001-source-neutral-core.md)
record terminology and design. Completed Wayfinder research remains decision
evidence; actual implementation acceptance is tracked separately.
