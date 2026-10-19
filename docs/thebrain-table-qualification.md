# Plain Markdown tables (#237)

The user requires every table to render as a plain editable Markdown table.
This amendment covers the shared BRZ adapter and `local-api.note-formatting.v1`
under profiles 1/2/3. The [public controls](../tests/fixtures/local_api_profile/complete-tables.json)
come from independently audited source facts and invented public content.

The retained source accounts for 740 thoughts (360 exact original notes and 380
no-note records) and 61 tables in 17 notes, including all 13 Wireshark tables.
Read-only TheBrain 15 observation confirms that undeclared first rows have no
structural header distinction: words, boldness and styling cannot identify one.
Render every such table consistently with empty Markdown headings and a separator,
then every authored row as data. Put one space in every empty header cell so
Obsidian Live Preview recognizes the native editable table. Do not infer roles from content or titles.

```markdown
| | |
|---|---|
|Field|Meaning|
|`src == 192.0.2.1`|Matches the example source.|
```

Only an explicit Markdown separator establishes an authored header. Styling
metadata supplies no header meaning. Once row structure establishes the table,
discard any well-formed attached `:(table="..."):` suffix opaquely: keys, values,
order and width counts do not limit plain Markdown output. Reuse an entirely
empty structural first row as the neutral header rather than duplicating it.

Recognize consecutive active edge-pipe rows in a top-level Markdown paragraph,
with at least two rows, at least two columns and equal cell counts. Preserve empty
and trailing cells. Existing parser ownership protects code, comments and escaped
examples; headings, ordinary prose/pipeline/link-label pipes and nested containers
are not table rows. A table may follow prose or images: insert an ordinary blank
paragraph boundary when needed, retaining neighboring text and reference bindings.
No title, vocabulary, style or image-prefix classifier is needed.

The observed imported form `||` followed by one two-cell row is an empty structural
header: native source displays two empty cells followed by the two data cells.
Write the matching empty Markdown header/separator and preserve both data cells.
The native-expanded `|||` form follows the same empty-header rule. Other unequal
row widths remain malformed. Never drop a first data row or a command.

Keep emphasis, links, escaped delimiters and inline code. Reuse existing code-pipe
normalization, including literal backslashes inside code. Active unescaped `{nl}`
inside table cells becomes the already-supported attribute-free `<br>`; keep
repeated/trailing breaks. Code/comment/escaped markers stay literal. No custom
HTML table, styling, new source-profile identifier or contract is introduced.

Native source also establishes the exact table-cell spelling
`` `curl -I [https://example.invalid`](https://example.invalid) `` (and `-i`)
as visible command text plus its URL link. Normalize only this complete cell
pattern with a parser-owned single-backtick code prefix and identical HTTP(S)
URL label/destination to `` [`curl -I https://example.invalid`](https://example.invalid) ``.
The complete command becomes clickable. Literal/code examples, differing targets,
ordinary valid links and prose are unchanged; this is no general link repair.

Original bytes remain unchanged. Existing exact adaptation spans, before/after
text, scoped digests and final reference bindings apply. Report neutral headings
and discarded styling as actual presentation adaptations that preserve source
content. Malformed table-shaped content retains its source and actionable finding;
a warning is never proof that an intended table converted successfully.

Frozen validation must match complete current or complete prior Documents AND
formatting findings, including exact compact-header 7bda output, 52ca table/header/link behavior, pre237,
older color and existing BOM alternatives.
Preserve prior sealed identities; reject invented cells, edits, references,
findings or original bytes. Never mix old/new row interpretations.

Public SourceModule/Session and selected BRZ/API Workflow controls verify these
facts and existing literals/separators/width/colors. Measure production line/branch
coverage, contexts and time. Complete source/output reconciliation covers all 61
tables. Independent actual Obsidian review covers all 13 Wireshark Reading tables,
distinct Live Preview/editable forms and additional audited formats. These remain
separate from parser success and the final maintained ordinary checks.
