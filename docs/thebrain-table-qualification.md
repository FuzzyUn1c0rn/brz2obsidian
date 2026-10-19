# Complete TheBrain table qualification (#237)

This amendment bounds `local-api.note-formatting.v1` under profiles 1, 2 and 3,
and the shared BRZ thought-note adapter. The accepted [issue237](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/237)
requires complete rendered tables, preserved contents and independently observed
source meaning. Independent review must accept these predicates and the
[public controls](../tests/fixtures/local_api_profile/complete-tables.json) before
runtime acceptance expands. This document alone is not a qualification verdict.

## Source facts and representation

The independently audited retained source accounts for 740 thoughts: 360 exact
original notes and 380 successful no-note records. Every original byte length,
SHA-256 and text matches retained source evidence. Scanning all pipe-containing
lines, without selecting on warnings or declarations, finds 61 intended tables in
17 notes, including all 13 Wireshark blocks. There are 41 ordinary content tables
and 20 imported number/command tables; only one has a color declaration. Protected
code, prose, link-label and heading pipes are separately inventoried. No source
HTML tables, nested/list/quote tables or ordinary Markdown separators occur in
this capture; existing public controls still protect those boundaries.

Read-only TheBrain15 observations independently establish that undecorated source
has no structural heading marker. First rows with column-label words and first
rows containing actual data have the same generic source row roles and styling.
Content, title, boldness and vocabulary cannot establish a header. Therefore use
empty neutral native Markdown headings followed by a separator, and retain every
undecorated authored row as content in order. Generated structural cells do not
consume authored cells. Labels and their emphasis stay visible in their original
row. This is a presentation adaptation, not a claim of semantic headings.

For example, the issue's illustrative `Field/Meaning` source becomes:

```markdown
|||
|---|---|
|Field|Meaning|
|`src == 192.0.2.1`|Matches the example source.|
|`dst == 192.0.2.2`|Matches the example destination.|
```

The issue's earlier illustration assumed a known heading role absent from this
serialized source family. The clarified representation preserves all those cells
while also preserving data-first key/value and six-column record tables. Existing
ordinary Markdown separators and the separately qualified width/color declaration
families retain their explicit header semantics and alignment.

## Closed undecorated-block predicate

The CommonMark block parser must own a top-level paragraph. A candidate consists
of at least two consecutive edge-pipe rows, wholly occupying that paragraph.
Each structural row boundary is an unescaped leading/trailing pipe outside
parser-owned inline code or comments. Ordinary rectangular tables have at least
two columns and equal widths. Preserve intentional empty and trailing cells.

One additional observed context is qualified: the table occupies the paragraph
suffix, and all preceding inline content consists solely of parser-owned images
and whitespace/breaks. Insert a blank paragraph boundary before the table and
preserve all images, destinations and reference bindings. A text, ordinary link,
inline-code or mixed prose/image prefix does not qualify. Existing leading UTF-8
signature interpretation runs before this predicate; do not treat a signature as
a guessed content heading.

Fenced/indented code, code spans (including multiline spans), comments, escaped
examples, headings and ordinary prose/pipeline text remain protected. Do not
extract a table-shaped subrange from a literal container. No new nested/list/quote
interpretation is granted. Unknown source declarations remain outside the new
predicate and retain existing behavior.

## Imported blank structural row

The exact additional form is one empty `||` row followed by exactly one two-cell
data row in the same qualified paragraph context. TheBrain Rich Text/accessibility
shows two empty first-row cells, then the two data cells. The raw one-cell marker
is therefore a blank structural row whose displayed width follows the data row,
not a one-column data record. Normalize it to a complete two-column empty native
heading and separator, preserving both data cells. Do not add another empty data
row, drop a command cell, infer a title, or pair/clamp away line content. Other
unequal-width input is not authorized by this exception.

## Cell content and exact edits

Preserve row/column order, emphasis, Markdown links, escaped literal pipes,
escaped backticks, inline code and empty cells. Parser-owned code pipes use the
existing narrowly generated `<code>` element with encoded pipes; preserve literal
backslashes inside code. Native source confirms that ordinary escaped OR pipes
show `||`, while code containing a backslash-pipe displays both characters.
Do not apply ordinary-text unescaping inside code.

Replace active unescaped `{nl}` markers only inside admitted table cells, outside
parser-owned inline code/comments, with attribute-free `<br>`. Preserve repeated
and trailing markers in order. Native source confirms actual breaks, including
an in-cell paragraph at `{nl}{nl}`. The complete source inventory contains no
code-owned marker. Code/comment/escaped markers stay literal. This uses the
existing attribute-free `br` qualification and admits no additional authored HTML.

Original source bytes are retained unchanged. Every change has exact nonempty
source `before`, destination `after`, source/adapted spans and the original scoped
UTF-8 digest. Reference tracing runs after edits; table references keep exact
normalized spans and table-cell status. Images before an inserted paragraph
boundary remain outside table cells. No source meaning enters the source-neutral
core or renderer; interpretation stays in the TheBrain adapter.

## Reporting and malformed content

A neutral-heading adaptation emits an existing `formatting_loss` finding stating
that blank native headings preserve every source row. Its exact block/edit and
safe affected-note context are available in the Migration report. This is distinct
from the color-only warning. Converting `{nl}` into equivalent supported breaks
needs exact edit evidence but no separate invented loss.

A structurally table-shaped active block that fails qualified boundaries/widths
retains its exact source text and an actionable malformed/ambiguous table finding.
Literal examples and ordinary prose do not acquire a table adaptation. Unresolved
intended tables remain unresolved acceptance, regardless of warning counts; final
source/output reconciliation must account for all 61 discovered tables.

## Sealed and reopened compatibility

Capture format1, profile identifiers, contracts and digest framing remain
unchanged. New acquisition always uses the current interpretation; changed
normalized contents need a fresh compatible inspection/review. Frozen validation
rederives and matches a complete Document plus its exact formatting findings
against current or complete prior interpretations: pre237 undecorated text,
and the older precolor interpretation. Existing leading-signature compatibility
is retained only within applicable prior alternatives. Legacy documents retain
their text, references, adaptations, findings, original bytes and identities.
Do not authorize a mixture of old/new rows or findings based on supplied metadata.
A changed cell, span, digest, reference or finding must fail exact binding.

## Independent controls and acceptance

Public source/session controls use independently stated synthetic cells and
literal expected adaptations, including neutral-headed labels/data/six-column
records, intentional empty columns, pipe/code/backtick ownership, links/breaks,
blank-marker and image-prefix forms. Protect prose/literals/malformed cases and
existing Markdown separators, width and color declarations. Selected BRZ/local API
Workflow compositions verify publication, original bytes and migration evidence;
sealed/reopened controls verify exact current/legacy semantics and tamper refusal.

The complete private inventory and source observations retain their own input
identities. Fresh output reconciliation checks every table, not merely parser
counts. Independent actual Obsidian review checks all 13 Wireshark tables in
Reading view, distinct formats in Live Preview/editability, and each additional
audited format. Source qualification, structural/content checks, measured test
coverage and native destination acceptance are separate evidence. This amendment
claims no future arbitrary pipe-text coverage or final actual-vault verdict.
