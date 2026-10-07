# Ticket 04 — native templates and maintenance support

Completed ticket-scope evidence, 2026-10-05. The bounded native check passed,
including the date-variable correction gate. This report does not certify
complete-source or finished-v2 acceptance.

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
verified by imported package location. The later cumulative and native gates
are recorded below.

After merging integration 7bef5bc (including ticket 07): 494 tests passed in 41.82s;
Ruff lint, format on 91 files, pip check and git diff --check passed. The merge
preserved video source facts/presentation/adaptations and its report limitation.
The private native fixture is verified clean with six imported notes, two
categories, three typed members, five payloads, eighteen support files and 29
manifested files. It records a nonempty 2010/2011 source-date member with exact
authored CRLF content, provider, paired IDs and body hash for direct-edit checks.

## Native verdict and correction

Root's complete bounded check passed in standard Obsidian 1.13.7 with bundled
Templates and Bases, on a disposable copy of actual synthetic converter output.
The native picker showed full/generic/starter Markdown templates and the
subsequently adapted future template, with nested Base files excluded. Full and
generic insertions resolved titles and initialized insertion-day dates without
imported source IDs. Direct generic membership/provider edits produced dynamic
discovery.

Existing-note membership add/reorder/removal retained old source dates,
paired imported identities and the explicit provider. Removing the provider's
membership visibly produced Invalid provider; restoring membership restored its
inherited icon. The only native save byte difference was three CRLF endings
normalized to LF: the body changed from 179 to 176 bytes and every other authored
body byte and its image snapshot remained unchanged. Both pristine 29-file
converter outputs retain exact manifest hashes, and original input/backups plus
all five review payloads remain unchanged. Guide and usage explain this editor
behavior without weakening converter byte-preservation requirements.

The native category starter created a future category. A handwritten member and
a member inserted through an adapted full template both appeared in contextual
Members/Gallery; the overview discovered the category. This used manual linked
properties, category body embeds and the documented extension recipe without
registry fields or additive templates.

The initial category rename exposed unquoted date variables becoming nested
YAML mappings during native link updates. Repair 81c57a7 quotes all full/generic/
starter date variables as literal strings. A red-before-green public workflow
test safely parses actual published template frontmatter, reserializes a
membership/provider change and proves both tokens remain strings and substitute
to calendar dates. PyYAML 6.0.3 is declared/pinned as a development dependency;
production serialization uses the existing JSON quoting. This adapts the
reference's syntax to observed native rename behavior while preserving its
bundled Templates/manual selection mechanism.

The corrected full template then survived a second native category rename:
membership/provider links updated and both date variables remained literal
quoted strings. Native insertion afterward produced the final category/provider,
blank optional overrides, 2026-10-05 date pickers, resolved title and no source
IDs. Members and Gallery showed all four expected members with inherited images;
table order remained Icon, Note, Inheritance, categories, created, updated, with
no decorative Appearance column. Native settings showed Templates folder and
YYYY-MM-DD format, and the current maintenance guidance was reviewed.

Private screenshots and read-only verification JSON remain ignored. Final
automatic gate: 495 tests passed in 45.60 seconds, clean Ruff lint/format on 91
files, pip check and git diff --check. No package installation or editable-install
repointing was required. Ticket 04 is resolved; checker/integrated workflow,
all-three-archive preservation, actual complete-vault native acceptance, final
review and the user's actual-vault verdict remain v2 delivery gates.
