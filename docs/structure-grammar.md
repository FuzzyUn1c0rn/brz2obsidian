# Initial structure interpretation and reconciliation

`brz2obsidian.obsidian.interpret_structure(content, output_format=7)` reads exact
in-memory `ExactContent` into immutable `StructuredDocument` facts.
`align_structure(original, current, incoming)` supplies original-body-coordinate
byte edits in a `StructureComparison`. The caller attaches that comparison to a
`ReconciliationSubject.structure`; `None` means interpretation is unavailable.
The pure `core.reconcile` consumes these source-neutral facts. It never parses
YAML, Markdown, delimiters or encodings and never invokes a textual/Git merge.

These are the initial automatic bounds, not a promise to interpret every
format-7 file. Unsupported content remains available as exact original/current/
incoming alternatives for later whole-file review. This interface performs no
filesystem access, rendering, choice resolution or application.

## Bytes and frontmatter

- Format 7 only. Input must be strict UTF-8 without a BOM, NUL, lone carriage
  returns or control bytes other than tab/newline. LF and CRLF may coexist;
  offsets and retained output always address the actual bytes.
- A document may have no frontmatter. If present, the first line must be exactly
  `---` followed by LF/CRLF, and another exact `---` line closes it. An opening
  line beginning with `---` but containing other characters is ambiguous.
- Each property begins in column zero. Keys match `[A-Za-z_][A-Za-z0-9_]*`;
  after the colon there is either no value or exactly one separating space.
  Keys must be unique. Blank/comment lines, indentation, merge keys, mappings,
  custom tags, aliases/anchors, block scalars and multiline values are excluded.
- Scalars are JSON double-quoted strings, strict decimal integers, lowercase
  `true`/`false`/`null`, empty values, valid ISO `YYYY-MM-DD` dates, or plain
  strings matching `[A-Za-z_][\w ./-]*`. Ambiguous YAML boolean/null spellings,
  leading-zero or noninteger numeric forms and other YAML constructs are
  excluded. Dates and quoted date-looking strings have different scalar types;
  booleans and integers also retain distinct types. JSON escapes are interpreted
  only to establish meaning; source bytes are retained for splicing.
- Empty `[]` and block sequences of scalar entries indented exactly two spaces
  are accepted as opaque fields. Their bytes may be retained, but changes to
  their meaning are outside this task's automatic scalar subset.
- `source_collection_id` and `source_item_id` are imported identity facts. Each
  must be a nonempty string. The interpreter tags their source-neutral identity components as collection/item.
  Core compares declared components with the already selected canonical identity
  and rejects contradictions; it never selects or repairs an association.
  Automatic combination never changes identity;
  identity association/repair is a separate explicit review responsibility.

The normalized field includes its complete byte span and its scalar value span.
Scalar replacement uses only the current value span: current key spelling,
separating bytes, order, line endings, unrelated properties and the remaining
current document stay exact. Comments are conservatively excluded rather than
silently discarded. The renderer's existing output is not rewritten.

## Prose alignment

When the incoming body is identical to the original body, no prose alignment is
needed: preserve the exact current body, including arbitrary authored structure.
An opaque/uncertain document still cannot authorize a changed-file combination;
unchanged incoming whole-file bytes retain the earlier exact-preservation fast
path before interpreting structure.

When source prose changes, the initial grammar permits complete plain-text lines
with unique line contents in each version, including blank lines. Repeated lines
(including repeated blank lines) and reordered matching anchors require review. Markdown block headings, lists,
quotes, fences/code, tables, raw HTML, wiki links and inline link destinations are
outside automatic prose alignment. A heading establishes no generated ownership.
Generated membership/relationship/resource sections require their separate
ownership/interpretation facts in later tasks.

Alignment uses exact byte lines and unique anchors to produce explicit edits;
it supplies no merged result. The core independently verifies that applying each
side's bounded, ordered expected-byte edits to the original body reproduces that
side's complete body. It combines disjoint original-coordinate changes, preserves
identical changes already present locally, and refuses overlap or insertions at
an ambiguous changed boundary. Replacements use spans, never global matching
string replacement. Unicode offsets count UTF-8 bytes, not characters.

## Candidate checks and review facts

The initial scalar subset changes values of existing scalar keys. Incoming key
additions/removals, removed current keys, field-kind changes and incoming opaque
field changes require review. Additional current-only keys remain exact. Local
and incoming divergent edits to the same scalar require review. Scalar semantic
types participate in comparison. Independent scalar and prose edits may combine.

Documents are bound to exact supplied original/current/incoming content and their
output formats. Contracts check bounded/disjoint ordered fields, unique keys,
scalar type/value consistency and imported identity shape. Core checks identity
meaning remains unchanged and constructs a new validated normalized document for
the proposed bytes. Property uniqueness is checked on that candidate separately
from edit alignment; a clean textual merge cannot waive it. A known example is
local/source insertion of the same property at different positions, which can
merge textually while introducing duplicate keys.

A compatible result remains unapproved. Unresolved inputs retain all exact
whole-file alternatives; no encoding conversion or inferred pristine baseline
occurs. A result already exactly present in the current file needs no new choice.
Every structure-produced change retains scoped structure/version/content,
interpretation, baseline/current/incoming, identity, format and safety assumptions
for later selective decision invalidation. No other subject's structure enters
its assumption fingerprint. Actual publication, saved decisions and fresh-process
revalidation remain consumer responsibilities.
