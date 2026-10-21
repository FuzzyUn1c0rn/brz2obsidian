# Bounded link interpretation and candidate validation

The S1 outer interpreter reads immutable in-memory bytes. It does not read a
vault, verify native navigation, or write a file. The core consumes closed,
source-neutral occurrence, target and inventory facts and never parses Obsidian
syntax. Callers must supply a complete, independently observed target scope;
claiming completeness is not a filesystem scan performed by S1.

## Accepted syntax

`obsidian.interpret_links` accepts wiki links and embeds (`[[path|display]]`,
`![[path]]`) and inline Markdown links/images (`[display](path)`). Markdown
destinations may use angle brackets and UTF-8 percent encoding. A declared path
mode selects vault-root, document-relative, or shortened lookup. Relative paths
are normalized without escaping the vault. Qualified and shortened note paths
may omit `.md`; resources retain their explicit extension. Exact validated
registry representations support named aliases. Multiple matching files or
representations remain ambiguous, including case/NFC collisions.

Plain-text heading and hierarchical heading fragments (`#Heading`, `#Outer#Inner`) and
Latin alphanumeric/hyphen block IDs (`#^block-id`) are supported. The target
interpreter supplies exact byte anchors and available target content; a digest
alone cannot establish a fragment. Duplicate anchors remain ambiguous. Fenced
and inline code and escaped link markers do not create link occurrences or
anchors. Display labels are retained separately from target identity. HTTP(S)
and mailto Markdown links have explicit external meaning.

Nested labels/destinations, Markdown titles and reference links, HTML link/embed tags,
unclosed syntax/code, invalid UTF-8/percent encoding, unsafe paths, formatted headings, multi-pipe
wiki aliases and unsupported fragment forms preserve exact bytes and return
unsupported facts. The supported subset is conservative: it does not claim to
cover every Obsidian or Markdown extension.

Syntax references checked on 2026-10-21:
[Obsidian internal links](https://help.obsidian.md/links) and
[Files and links settings](https://help.obsidian.md/settings). These document
wiki/Markdown links, path modes, display labels and fragments. They establish
syntax expectations, not native viewer acceptance.

## Registry and normalized facts

One registry entry represents each stable target ID and canonical file. A
membership or relationship producer may refer to the same file with a compatible
`note`, `category` or `relationship` role when stable ID, imported identity,
canonical path, validated target safety, status and exact spelling set agree. Producers do not concatenate
role records into duplicate registry entries. Per-list and per-section semantic
duplicates remain invalid. Resource/version target IDs are distinct from their
canonical imported owner plus content facet. Inventory associations and actions
are scoped by module, collection, item and explicit facet; unknown facet is not
automatic association authority.

`LinkTargetFacts` binds fragment anchors and normalized membership structure to
available exact bytes. Membership IDs must agree with that structure. Selected
target safety and canonical identity are validated independently of successful
text combination. Opaque whole-file preservation does not require a successful
structural merge. Present targets without indispensable available content remain
unknown; known source gaps and intentionally uncreated targets retain distinct
statuses.

## Candidate boundary

`core.validate_link_document(document, *, expected_content, expected_path,
targets, target_facts, inventory, baseline=None, affected_target_ids=())` returns
`LinkDocumentValidation(valid, findings)`. It revalidates immutable records,
exact bindings, selected lookup meaning, target identity/path safety, fragment
and membership facts. A baseline may retain an unchanged unrelated warning;
affected unsafe state and newly harmful meaning block validation. Retained
appearance-not-member diagnostics require a closed versioned
`LinkValidationBaseline(document, targets, target_facts, inventory)` from actual
prior interpreted facts. The validator re-resolves historical occurrences using
that registry, verifies exact old target/structure bindings and membership
spellings, and recomputes the old diagnostic. The same target identity/path and
appearance value may retain an independently established issue across unrelated
prose edits. Equal payload versions alone do not prove unchanged meaning when
registry aliases or membership facts change. Missing or contradictory prior
proof cannot establish a retained warning. Selected membership identity and
target safety remain mandatory. Cached external status cannot hide a retained
internal query. The prior document must have the same document/path/mode.
Attachment composition supplies the baseline from its actual current context;
review actions do not supply substitute historical evidence. Normalized syntax facts are supplied
by the bounded outer interpreter, rather than reconstructed by the core.

`core.validate_attachment_candidate(facts, selection, candidate)` additionally
requires the exact current proposal/generation/change and reviewed assumptions.
Offered binary choices are `current`, `incoming`, and `both`. Both keeps current
bytes/path and derives a distinct incoming version ID and an explicitly supplied
safe allocation slot, checked against complete current inventory and prospective
source/version targets, including file/directory collisions. Missing or unsafe
allocation makes only that alternative unavailable. Incoming extensions remain
explicit; optional source rename is a separate decision.

Each changed affected link requires its own old meaning, exact replacement
token, selected meaning, expected memberships and explicit-user provenance.
Candidate document bytes must equal those span replacements; other prose cannot
change through this seam. Reusing a token while replacing its target payload
still changes version meaning and requires review. Choosing both gives no
redirect consent. Edited associated link tokens compose with an offered binary
choice; arbitrary binary edits and arbitrary unrelated-target redirects are not
offered. Generic whole-text edited resolution belongs to the review layer.

Results contain typed findings and scoped content/inventory/target/link safety
assumptions. Equivalent bytes in different immutable locators have the same
semantic identity; unrelated target payload changes do not invalidate an
unrelated choice. These pure results establish neither whole-plan consent nor
actual apply, persistence, checkpoint, rollback, cleanup or recovery success.
