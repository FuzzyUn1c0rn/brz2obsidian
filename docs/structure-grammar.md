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
  Keys must be unique string keys. Case-insensitive YAML boolean/null spellings
  (`true`, `false`, `null`, `yes`, `no`, `on`, `off`, `y`, `n`) are excluded, so
  semantic aliases such as `true`/`True` cannot masquerade as distinct properties.
  Blank/comment lines, indentation, merge keys, mappings,
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
Known membership/relationship/resource sections use the explicit ownership and
interpretation facts below.

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


## Memberships and appearance

`interpret_structure(..., membership_targets=registry)` recognizes `categories`
and `tags` as membership roles only when a supplied registry establishes their
meaning. Without that authority they remain opaque list fields. Lists use the
existing format-7 `[]` or two-space `- scalar` block grammar. Category values must
be quoted relative wiki links, with optional display aliases; parent traversal,
external URLs, embeds and heading/block fragments are excluded. Tags use string
tokens matching `[\w/-]+`. Null/scalar membership properties are unsupported.
Unknown, unsafe, ambiguous or duplicate semantic entries require review.

The shared immutable `ReferenceTarget` family has schema ID
`brz2obsidian.reference-target`, integer version 1, stable `target_id`, `kind`
(category/tag/relationship/resource), exact validated `representations`, a
`validation_fingerprint` and safe/unsafe/unknown `status`. File targets also carry
`canonical_path` and the existing `IdentityTargetFacts`; category and relationship
targets carry the existing `ImportedItemIdentity`. Resources use their stable
asset/version target ID and tags their stable tag ID. Tags have no file target.
The caller establishes canonical identity and unique aliases; a basename does
not establish identity. Core checks safe containment, canonical relative paths,
NFC/casefold normalized keys, reserved-name/path-spelling guards, and independent
duplicate identity/path/ID and ancestor-path checks.
Two retained versions of one asset need distinct target IDs and paths.

Required `StructuredDocument.memberships` and `owned_sections` tuples are empty
when no authority is available. `MembershipSet` binds a field key, neutral role,
exact prefix and ordered `MembershipEntry` bytes to the complete declared field.
Every entry carries its exact representation and selected target facts. The core
checks input reconstruction, field-kind/target consistency and result semantic
uniqueness separately. It copies current entries, aliases, order and unrelated
raw gaps exactly, then appends validated source-only additions in source order.
A source reorder cannot reorder current entries, and an unchanged source entry
removed locally is not reintroduced. For an empty current list, the insertion
prefix comes from the exact bound incoming field, rather than arbitrary edited
result bytes. Source removals and remaps currently require explicit review;
additive reconciliation never silently removes a current membership.

`StructureComparison.prior_mappings` and `incoming_mappings` are required tuples
of version-1 `brz2obsidian.classification-mapping` records. They use stable source
`classification_id`, kind and target ID; `source_label` is informational. A label
rename preserves the mapping and does not invalidate semantic assumptions.
Duplicate/ambiguous mappings or a removed/remapped prior assignment require
review. This supplies protection for mappings already established by the caller;
it selects no arbitrary-vault reuse/remapping policy.

Required nullable `appearance_field` identifies an independent neutral role.
The interpreter tags `appearance_category`; the core preserves its exact current
value, including null or an explicitly empty string. Membership order never
selects a provider. A pre-existing choice outside memberships is retained and
reported as the nonblocking normalized result issue `appearance_not_member`;
it does not block an unrelated safe addition. A source removal/remap still needs
review, including when it harms the preserved appearance relationship. No
substitute is inferred.

## Known generated sections

`interpret_structure(..., section_bases=bases, section_targets=registry)` accepts
only uniquely located `## Parents`, `## Children`, `## Related` relationship
sections and `## Resources` resource sections. This initial grammar permits
nonempty `- [[relative target|optional alias]]` lists and blank lines. Every entry
must resolve uniquely through the supplied `ReferenceTarget` registry, including
its canonical identity/path and safety facts. Unknown or ambiguous basename
aliases, external/embed links, duplicate semantic entries, missing/duplicate (including case/space variants)
headings and uncertain boundaries remain unresolved. A heading without a basis
establishes no ownership. Unsupported material stays exact in whole-file
alternatives or in an unchanged source gap.

A version-1 `brz2obsidian.generated-section-basis` is a validated generation
record from the outer history/interpretation boundary. It contains the available
exact original document, original output identity, source version, item/facet,
section ID/kind, exact original section span, heading bytes and generation
fingerprint. It is not a cryptographic certificate or a claim of actual apply.
Core binds these facts to the actual subject/baseline/source/output before using
them. An OID, hash, arbitrary heading or unbound reviewed flag cannot supply the
missing original content or establish ownership.

The outer interpreter emits required `owned_sections` and required
`StructureComparison.section_bases`. It aligns prose gaps independently and
emits whole-section original-coordinate edits. The core independently checks
section byte binding, order, identities and target uniqueness; each changed
section must be exactly one complete atomic edit. It refuses partial edits even
when they would textually merge. Independent changes in different owned sections
combine, while divergence within one section requires review. The candidate
rebuilds and independently checks section spans after scalar/membership/prose
splicing, including UTF-8 byte-offset changes. Current unrelated gaps and local
relationship/resource representations remain exact.

These content rules apply equally to notes, dashboards, templates and guides.
Configuration retains its distinct explicit format/configuration review choice.
Compatible results are unapproved proposals. Exact unchanged incoming bytes keep
the earlier preservation path, including opaque current structures. Scoped
structure assumptions include selected target validation, mapping meaning and
bound generation records, without unused registry entries or informational
source labels. Saved decisions, publication and revalidation remain separate.
