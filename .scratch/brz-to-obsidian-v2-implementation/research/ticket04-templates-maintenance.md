# Ticket 04 — native templates and maintenance support

Automatic subset evidence, 2026-10-05. The bounded native check is pending;
this report does not certify complete-source or finished-v2 acceptance.

## Implemented behavior

The converter now generates one full template per imported category using its
already collision-safe assigned stem under Templates, a generic New note,
category/member-template starters, a contextual Base starter and Vault guide.
Full templates initialize the canonical core with linked membership/provider,
blank explicit overrides and native insertion-day ISO date variables. New
objects omit both imported IDs. Generic/member starters have blank membership
and provider until deliberately adapted, so fresh output has no dangling
example links in active frontmatter.

Bundled Bases remains enabled; bundled Templates is enabled with Templates
folder/date configuration. Native property types and original Home/bookmark/link
preferences are retained. Every support/configuration file is planned, manifested
and counted separately from imported notes. Migration-record schema 2 preserves
the existing application configuration plus explicit core-plugin/template/type
configuration dictionaries. No unrelated plugin toggles or community plugins
are copied.

The guide documents manual new-note template selection, existing-note direct
membership editing, duplicate lookup, canonical/custom vocabulary, meaningful
entity links, stable imported versus new identity, explicit updated-date
maintenance, provider/order independence, editable body-icon snapshots and
contextual dashboard entry points. The extension recipe uses native Properties,
full templates and contextual embeds without registry fields or additive templates.

## Reference inspection

The actual local kepano repository at
473697347a0eaac790a6596229c741b3915f3b77 was inspected: core-plugins.json,
templates.json, types.json, app.json, Book/People/Author Templates, Out of Control,
Books category and Books.base. It confirms manual selection, linked properties,
independent category queries and dashboard embeds; its domain fields, unrelated
toggles, filename-substring exclusion and literal category predicate are not
copied. V2 deliberately uses faithful source names, canonical properties,
explicit icon providers, folder exclusions and rename-safe contextual queries.

## Automatic verification

Four workflow tests use real synthetic ZIPs and fresh temporary vaults. They
verify exact new-note template bytes, full canonical native configuration, working
starter/query structure and guide instructions, complete inspection/record/
manifest support accounting, safe qualified links, source immutability and
reproducibility through repeated/reordered inputs. Naming controls include
reserved support titles, duplicate category titles, NFC collisions and bounded
long stems. Existing cumulative preservation, receipt/publication, alternate
source and independent-auditor corruption controls remain intact.

Initial gate before merging video integration: 449 tests passed; Ruff lint and
format on 89 files, pip check and git diff --check passed. Python/tooling used
the root .venv interpreter with this isolated worktree's src on PYTHONPATH,
verified by imported package location. The final cumulative gate will be recorded
after merging latest integration and completing native evidence.

After merging integration 7bef5bc (including ticket 07): 494 tests passed in 41.82s;
Ruff lint, format on 91 files, pip check and git diff --check passed. The merge
preserved video source facts/presentation/adaptations and its report limitation.
The private native fixture is verified clean with six imported notes, two
categories, three typed members, five payloads, eighteen support files and 29
manifested files. It records a nonempty 2010/2011 source-date member with exact
authored CRLF content, provider, paired IDs and body hash for direct-edit checks.

## Native gate

Root will open a fresh review copy of a pristine synthetic converter output.
Two imported categories have distinct valid image defaults; an established
typed member has old nonempty source creation/overall-modification dates,
preserved authored text, provider and paired source IDs. The checklist covers
full/generic template insertion in Editing view, direct membership edits,
future-category/manual discovery, adapted full template insertion and native
link-preserving rename. Pristine source/output and all screenshots remain ignored.

Root's partial native observations confirmed Books/generic insertion with
2026-10-05 dates and the correct Markdown-template picker without Base files.
Direct Properties edits on the established imported member retained its old
dates, paired source IDs and Books provider while adding People membership.
The native save normalized its three CRLF sequences to LF: the body changed
from 179 to 176 bytes, and the edited body exactly equals the pristine body
with CRLF replaced by LF. Authored text and its body-image snapshot were retained.
All 29 pristine output hashes and original backups remain exact. The generated
guide and usage document this observed editor limitation without changing the
converter's byte-preservation requirement. Remaining native scenarios and the
full native verdict are pending; this is not final ticket acceptance.

The native category rename subsequently exposed a concrete defect: Obsidian's
link-update YAML rewrite converted unquoted template date tokens to nested
mappings. The converter now quotes all full/generic/starter date variables as
literal strings. A red-before-green public workflow test reads actual published
template frontmatter, safely parses and reserializes a membership/provider
change, then proves both date tokens remain strings and substitute to calendar
dates. PyYAML 6.0.3 is declared/pinned as a development dependency for this
regression; production template serialization continues to use JSON quoting.
This deliberately adapts the reference's unquoted syntax to the observed native
rename behavior without changing the manual bundled Templates mechanism.

A new ignored pristine repaired conversion retains the original synthetic
feature counts and all 29 file obligations. The original native baseline and
its manifest remain unchanged. Root will verify another native category rename
followed by insertion from the corrected full template before final resolution.

After the date repair, all 495 public tests passed in 45.60 seconds; Ruff lint
and format on 91 files, pip check and git diff --check passed. No package install
or editable-install repointing was needed because the pinned PyYAML version was
already present in the project virtual environment. Native correction remains
the pending gate.
