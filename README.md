# brz2obsidian

Convert a TheBrain `.brz` export into an Obsidian vault on your computer.
The converter creates Markdown notes, copies attachments, and turns supported
relationships, tags and thought types into Obsidian links, tags and categories.
No community plugins are required.

The library, CLI and local Windows app also support a bounded local API source
with qualified graph, classification, authored Markdown and owned resources,
including explicit and inherited icons.
See [local API import](#local-api-import) for Brain UUID selection, external
credentials, search options and the current content-stage limits. Acquisition
spans requests and is not an atomic snapshot. Editing or syncing during
acquisition can produce a mixture of source states. Conversion verifies the
captured copy's integrity; this does not prove that the live Brain stayed
unchanged or that every captured object existed at the same moment. Inspection
releases its capture, so conversion acquires again and pays that cost again.

This is a **one-time conversion into a new vault**. It does not merge into an
existing vault or keep TheBrain and Obsidian synchronized. Your source archive
is read without being modified.

## Optional local Windows app

The local app currently supports read-only source inspection, preliminary
destination validation, reviewed clean/warning conversion, independent vault checking
and explicit safe diagnostic copy/save, recovery and optional published-vault actions.
Final native acceptance is being delivered through
the [Windows UI implementation](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/93).
The existing command-line converter remains available below.

From the checkout root, install the optional GUI dependencies and build its
checkout-bound launcher:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-gui.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e '.[dev,gui]'
.\.venv\Scripts\python.exe tools\build_ui.py
```

Double-click **build/ui/Start brz2obsidian.cmd**, choose a BRZ archive, then
select **Inspect archive**. Inspection shows planned counts, unavailable actual
counts, source limitations and pending checks. Diagnostic details are collapsed
initially and remain available after the worker exits. The source is read-only. Standalone **Inspect** offers **Convert this archive**
after a usable clean/warning inspection. This carries the source and reviewed
findings into **Convert**, with destination validation still required. Switching
tabs does not inspect or acknowledge warnings.
During inspection, conversion or vault checking the window stays responsive; Close waits for
completion.

Expand **Diagnostic details** for selectable, bounded report pages. **Copy details**
copies the complete current safe report; **Save diagnostic report** explicitly saves
it as local UTF-8 text. Canceling or failing an export keeps the operation result.
Reports remain in memory only for the current result and expire when it is replaced
or the app closes. The app creates no diagnostic history or automatic report files.

Use **Check vault** to choose an existing vault folder and check its current
structure and conventions without changing files. Clean, issues and failed
checks have distinct outcomes; checker issues are not conversion warnings or
failures. The check does not repair files or prove preservation of source content.

In **Convert**, choose an existing output parent folder and edit the suggested
archive-stem vault name. The backend shows the complete destination and adjacent
errors. Validation is read-only and accepts only an absent or empty target;
it does not reserve the folder or guarantee writes. Generated paths, collisions,
manifest feasibility and the final 240 UTF-16-unit path limit remain pending
until conversion. Editing coalesces checks and discards obsolete results while
retaining the inspection findings. After a clean inspection and valid destination,
select **Convert** explicitly. For source warnings, review the findings and use
**Convert with warnings** explicitly; no checkbox or extra dialog is required.
This authorization applies only to that current attempt. A changed source or
review requires fresh inspection and authorization. Conversion rechecks the source review and all final
publication safeguards. A verified result shows actual counts and its published
path in place of the destination form. Refusal, failure and uncertain worker
termination have distinct messages; never treat a visible folder as success.
A verified warning publication is **Vault created with warnings**.
The CLI below still creates missing output parents.

After verified publication, explicitly choose **Open folder**, **Open migration
report**, **Open in Obsidian** or **Check vault** in the result area. These actions
also remain available when publication succeeded before a later error. Checking
automatically selects that published folder and remains read-only; no open or
check starts automatically. An open failure keeps the result and shows a copyable
path. **Open in Obsidian** requests Obsidian's vault manager. There, choose
**Open folder as vault** and select the exact published vault folder shown in
the app. The request does not confirm that the vault opened; you complete folder
selection in Obsidian. **Open migration report** remains a separate action.

Launching the app again restores or draws attention to its existing window;
it does not start another operation. If Windows prevents foreground activation,
the taskbar/caption flashes and the existing window shows a brief message.
Independent command-line commands remain available while the app is open.

Only the last output parent folder is remembered in
`%LOCALAPPDATA%\brz2obsidian\preferences.json`. A new launch has no selected
archive, reviewed inspection, result/check history, diagnostic log or saved window
geometry. An unreadable preference leaves an empty usable form with a nonfatal
message; choose the output folder again. A failed preference save preserves the
current operation result and does not prevent further work.

This launcher uses this checkout's `.venv` and is not a standalone distribution.
Moving the checkout or environment requires rebuilding. A missing environment
shows setup guidance; launching never installs or downloads packages. Headless
installation does not require `requirements-gui.txt`. The tested GUI runtime is
64-bit CPython 3.14.8, PySide6/Qt 6.12.0 on Windows. In an isolated worktree, the
helper accepts `--python C:\absolute\project\.venv\Scripts\python.exe` while
continuing to resolve code from that worktree.

## Before you start

This guide uses **Windows PowerShell**. You will need:

- **Python 3.14 or later**, available as `python`. The tested runtime is
  CPython 3.14.8 on Windows; other platforms and later runtimes have not been
  accepted.
- **Git**, available as `git`, to download this project.
- **Obsidian**, installed so you can open the converted vault.
- A **TheBrain BRZ export**. The converter supports reviewed features of
  TheBrain 15's BRZ exchange format 5. An archive with unsupported features may
  be refused; [inspect the archive](#4-inspect-the-archive) for diagnostics before
  conversion.

Export your Brain as a `.brz` archive in TheBrain and keep the original as a
backup. Make sure the Brain has a Home thought before exporting. Use the `.brz`
file directly; you do not need to unzip it.

Reviewed Markdown inserts use native Obsidian presentation: static linked ToCs,
editable responsive tables and all 13 native callout types. Authored emoji icons
remain visible in callout titles. Formatting-loss warnings identify table layout
changes, icon fallbacks and unsupported declarations; review the Migration report
and linked notes after conversion. ToCs need manual updates after heading edits.
No extra callout plugin, CSS snippet or custom icon assets are required.

**Forgotten thoughts are excluded automatically**, along with their owned
content and connections. Links and embeds pointing to excluded thoughts are
removed from imported note text. There is no option to include forgotten
thoughts. A forgotten Home prevents conversion.

## Step by step: convert your archive

Run the following commands in the same PowerShell window, in order.

### 1. Download the converter

Check that Python and Git are available:

```powershell
python --version
git --version
```

Confirm that Python reports version 3.14 or later, then download the project:

```powershell
git clone https://github.com/FuzzyUn1c0rn/brz2obsidian.git
cd brz2obsidian
```

If you already have a checkout, open PowerShell in its `brz2obsidian` folder
and skip the clone command. Run all remaining commands from that folder.

### 2. Install the converter

Create a local Python environment and install the pinned dependencies and
converter:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pip check
```

Wait for each command to finish successfully before continuing. The final
command should report `No broken requirements found.`

You only need this setup once per checkout. The commands below use this
local environment directly, so you do not need to activate it or change
PowerShell's execution policy.

### 3. Choose your archive and output folder

Replace these example paths with your own:

```powershell
$source = 'C:\exports\My Brain.brz'
$vault = 'C:\vaults\My Brain'
```

`$source` must point to an existing `.brz` file. `$vault` is the folder the
converter will create. It may also be an existing **empty** folder. Do not
choose an existing vault with notes in it.

Keep the output path short to leave room for imported filenames. The converter
limits complete output paths to 240 UTF-16 units (most ordinary characters
count as one). Quotes allow paths containing spaces.

### 4. Inspect the archive

```powershell
.\.venv\Scripts\python.exe -m brz2obsidian inspect $source
```

Inspection is an optional, read-only preview. It reports planned note and
attachment counts and any warnings or reasons conversion cannot proceed.
It does not create a vault or confirm that your chosen output folder is usable.
The `Pending:` line is expected: copying, verification and publication happen
during conversion.

- **`inspect: clean`** — proceed to conversion.
- **`inspect: warnings`** — read the warnings, then proceed if the described
  missing content or adaptations are acceptable to you.
- **`inspect: refused` or `inspect: failed`** — follow the printed guidance
  before continuing.

### 5. Convert to a new vault

```powershell
.\.venv\Scripts\python.exe -m brz2obsidian convert $source $vault
```

The converter prepares the import again, copies files into a staging folder,
verifies them, and publishes the completed vault. On success, look for:

```text
convert: clean
...
Verified vault published: C:\vaults\My Brain
```

A result of **`convert: warnings`** with **`Verified vault published:`** also
means the vault was created successfully. Open `MIGRATION REPORT.md` in the
vault to understand the warnings before relying on the imported content.

Do not run conversion again into the same populated folder. For a fresh attempt,
choose another destination, such as `C:\vaults\My Brain retry`.

### 6. Open the vault in Obsidian

1. Open Obsidian's vault switcher and choose **Open folder as vault**.
2. Select the output folder, such as `C:\vaults\My Brain`.
3. Open the root note named `Home — <title>.md`, or use the Home bookmark.
4. Read `MIGRATION REPORT.md` and `Vault guide.md`.

The generated vault uses Obsidian's bundled features, including Bases,
Templates, Backlinks and Graph. Category dashboards show their members in
native tables and galleries. The renderer targets Obsidian 1.13.7; current
native output review used Obsidian 1.14.4.

### 7. Check the vault (optional)

```powershell
.\.venv\Scripts\python.exe -m brz2obsidian check-vault $vault
```

A result of `check-vault: clean` means the checked structural conventions have
no reported issues. This read-only command checks properties, category links,
required images and Bases, and imported identities. It does not repair files
or prove that missing source content was recovered. You can run it again after
editing memberships, renaming categories or changing templates.

See [checker diagnostics](#checker-diagnostics) for common findings.

## More command examples

### Convert without PowerShell variables

After installation, you can supply the paths directly:

```powershell
.\.venv\Scripts\python.exe -m brz2obsidian convert 'C:\exports\Work.brz' 'C:\vaults\Work'
```

The installed console command works the same way:

```powershell
.\.venv\Scripts\brz2obsidian.exe inspect 'C:\exports\Work.brz'
```

### Try a small sample first

The repository includes a synthetic archive with no private data. From the
project folder, convert it and check the result:

```powershell
.\.venv\Scripts\python.exe -m brz2obsidian inspect '.\tests\fixtures\minimal.brz'
.\.venv\Scripts\python.exe -m brz2obsidian convert '.\tests\fixtures\minimal.brz' '.\tmp\readme-demo\vault'
.\.venv\Scripts\python.exe -m brz2obsidian check-vault '.\tmp\readme-demo\vault'
```

Open `tmp\readme-demo\vault` as a vault in Obsidian to explore the result.
Use a different output folder if you have already run this example.

### Get JSON output for scripts

Add `--json` to any command. For example, to save an inspection result:

```powershell
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -m brz2obsidian inspect 'C:\exports\Work.brz' --json | Out-File -Encoding utf8 '.\inspection.json'
```

Migration results use schema `brz2obsidian.result`, version 7. The checker has
its own schema, `brz2obsidian.vault-check`, version 1. Inspection has no
publication receipt; a conversion receipt records the verified published vault.
Errors retain their existing codes and may include a diagnostic reason and safe
item name. An absent name leaves the old JSON shape unchanged; a populated
optional `subject` requires older strict readers to accept this extension.
`Issue.rule_id` can carry a diagnostic reason identifier. Human explanations can
change; scripts should use structured codes and fields. Unexpected conversion
errors can leave publication status unknown, so check the destination before
retrying. An unexpected checker error exits 1 and may provide only a safe
explanation on stderr, without a JSON result.

## Local API import

Enable the local API in the running TheBrain desktop app and use the current
address shown in its settings. The default is `http://127.0.0.1:11522/api`.
Provide its key through the `THE_BRAIN_LOCAL_API_KEY` environment variable before
launching the converter. Keep the key out of command arguments and saved reports.
Requests are read-only and restricted to a local HTTP(S) origin; the converter
does not scan ports or open a Brain for you.

In the Windows app, choose **TheBrain local API**, enter the address, select
**Refresh Brains**, then choose the Brain by name and full ID. Duplicate names
remain separate choices. The app reads the key from its launch environment and
has no key field. **Advanced search limits** exposes the options below.

For the CLI, replace this example with the Brain's exact lowercase, hyphenated,
nonzero UUID:

```powershell
$brain = '11111111-1111-4111-8111-111111111111'
.\.venv\Scripts\python.exe -m brz2obsidian inspect $brain --source-kind local-api --api-url http://127.0.0.1:11522/api
.\.venv\Scripts\python.exe -m brz2obsidian convert $brain 'C:\vaults\My Brain' --source-kind local-api --api-url http://127.0.0.1:11522/api
```

Omitting `--source-kind` selects BRZ input. `--json` and the normal exit codes
apply to both sources. Use `inspect --help` or `convert --help` for option bounds.

| Option | Default | Purpose |
| --- | --- | --- |
| `--api-search-initial-results` | 5000 | Initial raw wildcard hit limit, before deduplication |
| `--api-search-timeout` | 300 | Total wildcard search budget in seconds |
| `--api-search-max-response-bytes` | 128000000 | Maximum decompressed bytes per wildcard reply |
| `--api-search-max-results` | disabled | Optional positive result ceiling; saturation refuses import |

The supported scope includes public, non-forgotten ordinary thoughts, types and
tags, a valid ordinary Home, supported relationships, authored raw Markdown,
qualified images, files and explicit/inherited icons. Private, custom,
conflicting or unsupported included content refuses import. Rendered notes are
never a substitute for raw authored Markdown, and external destinations remain
references. Formatting adaptations can produce warnings. One reviewed case of a
missing TXT attachment can warn when a separately preserved PDF from the same
owner qualifies; this does not claim that the PDF replaces the missing text.
Other unavailable required content refuses import. No partial vault is published.

Inspection fully acquires content and releases its capture. Conversion acquires
again; allow for that cost. In the app, changed settings or source invalidate the
review, and warning publication requires **Convert with warnings**. Direct CLI
conversion can publish with warnings and exit 2. Multi-request acquisition is
not an atomic snapshot: avoid editing or syncing while it runs. Captured-copy
integrity and reconciled counters do not prove universal discovery completeness
or that the live Brain remained unchanged.

## What you will find in the vault

| File or folder | What it contains |
| --- | --- |
| `Home — <title>.md` | Your starting note, based on the Brain's Home thought |
| `Notes/` | Imported thought notes with supported Parents, Children and Related navigation |
| `Categories.md` and `Categories/` | Thought types as linked categories with member dashboards |
| `Attachments/` | Copied files and images, grouped by their source owner, plus safe original note backups |
| `Templates/` | Templates for new notes and the Bases used by category dashboards |
| `Vault guide.md` | Instructions for browsing, editing and extending the vault |
| `MIGRATION REPORT.md` | Conversion warnings, adaptations and source-gap explanations |
| `migration-record.json` | Detailed migration evidence and file inventory |

Included Markdown is retained with supported local links adapted to their new
paths. Safe original note bodies are also kept as `.md.original` backups;
originals containing excluded references are omitted explicitly. Present
attachment bytes are preserved. External URLs and directory links remain
references; the converter does not download their contents.

Some empty thoughts deliberately remain links to notes that have not yet been
created. Clicking one in Obsidian lets you create its note later. Conditional
`Uncreated targets.md` and `Tag memberships.md` files record otherwise hidden
items or memberships.

For certain reviewed missing-note cases, available source images are displayed
with a notice. **Missing prose, captions and layout are not recovered.** Missing
category text or icons are also explained in the migration report. Other missing
required content or unsupported features can prevent conversion.

For daily use, start with the generated `Vault guide.md`, whose template links
use the vault's actual sanitized or disambiguated names.

## Maintain the converted vault

Search existing names and aliases before creating a note. To create one, switch
to Editing view, run **Templates: Insert template**, and choose `New note` or
the full template named for its category. Templates initialize properties;
choosing a category does not apply a template. Use full templates for new notes,
since inserting one into an existing note can overwrite dates and providers.
Maintain `updated` yourself after insertion.

| Property | How to maintain it |
| --- | --- |
| `categories` | A list of links to category notes; empty is valid |
| `appearance_category` | One optional category link also present in `categories`; blank opts out of inherited icons |
| `icon` | One optional link to a local image; a valid override takes precedence over the category icon |
| `created`, `updated` | Optional ISO dates; keep template variables quoted, such as `"{{date:YYYY-MM-DD}}"` |
| `tags`, `aliases` | Native string lists; source tags remain distinct from categories |
| `source_collection_id`, `source_item_id` | Preserve the paired imported identities through edits and renames; omit both on new notes |

Edit membership directly in Properties or frontmatter. Removing the provider's
category requires updating `appearance_category`; reordering memberships does not
select another provider. Invalid providers are reported even if an explicit
icon works. Body-icon references are separate migration-time snapshots: edit
them separately if changing category or provider metadata. Replacing a shared
image's bytes can affect every reference to it.

Open Members/Gallery through category dashboards so their contextual queries
have a category. Hierarchy, prose links and source tags do not create membership.
Use Obsidian's native rename with automatic internal-link updates enabled;
prefer qualified links when names collide. Migration records describe the
original conversion and do not track later edits. Keep pristine output and safe
`.md.original` backups if you need exact pre-edit bytes: Obsidian can normalize
frontmatter and line endings when saving.

To add a category:

1. Create `Categories/Experiments.md` using `Category starter` in Editing view.
   Keep its native `categories` tag and contextual dashboard embeds.
2. Add `"[[Categories/Experiments]]"` to a member's `categories` list and, if
   wanted, its `appearance_category` property.
3. Copy `Templates/Member template starter.md` to `Templates/Experiments.md`.
   Set those membership/provider links, keep quoted date variables, and omit
   imported identities. Select this template manually for future members.
4. Reuse Members/Gallery or customize a copy of `Templates/Bases/Starter.base`,
   preserving contextual membership and exclusions for Templates/Attachments.

Run `check-vault` after membership, template or rename changes. Ordinary links
can intentionally point to uncreated notes; a clean check does not establish
source preservation, image rendering, Base query behavior or automatic date
maintenance.

### Checker diagnostics

The checker reads current vault files without the source archive and never
repairs or rewrites them. Custom properties are allowed. Fix reported problems
in Obsidian or your editor, then run it again.

| Finding | What to check |
| --- | --- |
| `invalid_frontmatter` / `invalid_property` | YAML structure, duplicate keys and known property types, dates or paired identities |
| `invalid_category` / `invalid_provider` | Category targets exist, carry the category role, and the provider is a member |
| `missing_base` / `missing_image` / `invalid_base` | Required files exist; images are nonempty and Base YAML is valid data |
| `ambiguous_reference` | Use a qualified vault path to distinguish colliding names |
| `duplicate_source_identity` | Multiple notes carry the same imported identity pair |
| `unsafe_reference` | A required reference or filesystem entry cannot be read safely inside the vault |
| `read_failure` | Access permissions, text encoding or file/directory availability |

Use `check-vault --json` for structured findings with artifact, property,
reference, guidance and candidate paths. A clean result covers structural
conventions, not all ordinary note links or native presentation.

## Results and troubleshooting

For `inspect` and `convert`:

| Result | Exit code | Meaning |
| --- | ---: | --- |
| `clean` | 0 | Inspection or conversion succeeded without warnings |
| `warnings` | 2 | Inspection or conversion succeeded with warnings to review |
| `refused` | 1 | The source, a feature or the destination prevents proceeding |
| `failed` | 1 | An operational error occurred; read the printed guidance |

For `check-vault`, exits are **0** for `clean`, **2** for `issues`, and **1** for
`failed`. Exit code 2 therefore means different things for conversion and
checking. In PowerShell, run `$LASTEXITCODE` immediately after a command to see
its exit code.

| Problem | What to do |
| --- | --- |
| `python` or `git` is not recognized | Install the missing prerequisite, reopen PowerShell and repeat the version check. |
| Python is older than 3.14 | Install a supported Python version, then create the environment with that interpreter. |
| `.venv\Scripts\python.exe` cannot be found | Return to the project folder and complete installation in step 2. |
| The destination is not empty | Choose a new output folder. Conversion does not overwrite or merge existing files. |
| An output path is too long | Choose a shorter destination, such as `C:\v\Brain`. |
| Home is missing or forgotten | Set an included Home thought in TheBrain, export again and inspect the new archive. |
| Source content or features are refused | Follow the [inspection guidance](#4-inspect-the-archive) and the printed diagnostic. Follow the stated action: converter limitations need a report; source or access problems have their own guidance. |
| Conversion succeeds with warnings | Review `MIGRATION REPORT.md`, including any optional source-repair steps. |
| The checker reports issues | Follow its diagnostics and [checker guidance](#checker-diagnostics). It does not modify the vault. |

If a failure still prints `Verified vault published:` or reports
`publication_occurred`, the vault was published before a later cleanup failure.
Inspect that output before retrying, and use a fresh destination for any retry.

## Project status and developer resources

The checkout is version **0.3.0**. Version 2 was delivered and accepted. Version 3
adds forgotten-thought exclusion, reviewed missing-note image display, category
source-gap handling and category hierarchy. Complete four-archive preservation
and native output review passed; actual-user acceptance and independent final
review remain pending. See the [current frontier](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/8)
and [release verification record](https://github.com/FuzzyUn1c0rn/brz2obsidian/blob/05b36923cd330261973bd35e19e6fa20ada88290/docs/history/management-leadership-implementation/research/release-verification.md).

For contributors and library users:

- [Python library examples](#python-library)
- [Test commands and verification procedures](docs/testing.md)
- [Workspace housekeeping and private-data locations](docs/workspace.md)
- [Glossary](GLOSSARY.md) and [architecture decision](docs/adr/0001-source-neutral-core.md)

The installation above uses the pinned runtime, build and development packages
in `requirements.txt`. Contributors can explicitly install the development extra
and build a wheel using the same environment:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-build-isolation -e ".[dev]"
.\.venv\Scripts\python.exe -m pip wheel --no-deps --no-build-isolation --wheel-dir tmp/build/wheels .
```

### Python library

Use the default factory to inspect or convert a BRZ archive:

```python
from brz2obsidian.application.wiring import default_workflow

workflow = default_workflow()
inspection = workflow.inspect("source.brz")
result = workflow.convert("source.brz", "new-vault")
```

For the local API, the factory pairs the supported source profile and policy.
It reads credentials from the environment by default; callers can supply a
zero-argument `credentials` provider returning the key.

```python
from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.sources.thebrain.local_api import LocalApiConfig, LocalApiSourceRef

workflow = local_api_workflow(LocalApiConfig())
reference = LocalApiSourceRef("11111111-1111-4111-8111-111111111111")
inspection = workflow.inspect(reference)
result = workflow.convert(reference, "new-api-vault")
```

The standalone checker needs only the current vault:

```python
from brz2obsidian.vault_check import check_vault

result = check_vault("new-vault")
for issue in result.issues:
    print(issue.code, issue.artifact, issue.guidance)
```

Implementation contracts live in [source code](src/brz2obsidian/);
[AGENTS.md](AGENTS.md#documentation) defines where project documentation belongs.
