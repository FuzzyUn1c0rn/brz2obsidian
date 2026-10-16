# Independent API preservation baseline

An API preservation baseline is prepared from source evidence before conversion,
including the private baseline introduced for #179. It is independent of the
adapter, normalized snapshots and migration records. The checker imports no
converter normalization or rendering code. Synthetic checker controls do not
establish actual Brain completeness or native qualification.

`tests.local_acceptance.api_manifest.load_baseline(path, expected_sha256)` takes
an independently recorded SHA-256, verifies the manifest and every bound file,
and returns a baseline. `check_api_vault(baseline, vault)` audits actual migration
assignments and physical payload bytes against its raw API facts. Changed input
requires independent requalification and a newly reviewed external fingerprint;
rehashing a changed capture is not acceptance.

Call `tests.local_acceptance.api_checker.audit_baseline(baseline)` before
conversion. It checks every scoped source fact, required outcome and payload,
the exact no-note state and independent one-way controls, and reports complete
population/payload/gap/equivalence totals. Call the vault checker after conversion;
it verifies the same baseline again before and after the audit. Source capture
encoding and identifiers remain governed by [the capture contract](local-api-capture.md).

The public `expected_asset`, `audit_baseline`, `check_api_vault` and
`check_api_component_vault` functions default to the unchanged profile version1.
Pass `profile_version="2"` or `profile_version="3"` explicitly for that reviewed
profile. Unknown versions refuse; a vault's profile/module/format versions must
agree with that selection and the capture contract. The baseline's original seal
remains unchanged. Profile3's finite additions are defined by the
[profile3 qualification](local-api-profile3-qualification.md) and capture contract; selecting a
manifest representation grants no additional source grammar.
Profile2 measures PNG/JPEG eligibility through complete Windows WIC pixel decoding
and checks each opaque ZIP's central directory without extraction or member CRC
claims. Missing decoder capability or a decoder resource bound leaves acceptance
unavailable. Its returned `resource_eligibility` map binds every added resource's
proof to actual source bytes; caller-supplied decoder booleans are never inputs.

The shared independent Markdown reference parser receives API-owned asset names
and roles directly. No BRZ record flags, archive paths, absent-note interpretation
or archive population assumptions supply API expectations. Local image ownership
and included item targets are checked against the complete API inventory.

The manifest accepts `brz2obsidian.api-acceptance/1` and
`brz2obsidian.api-acceptance/2`. Version1 keeps its existing bytes, results and
interpretation and refuses a `scope_inputs` field. Version2 requires explicit raw
exclusion authority in `scope_inputs`, even when both maps are empty. Manifest
representation and source profile are separate choices: version2 supports only
recognized profiles1/2/3 and applies each selected profile's existing predicates;
it does not grant profile3 forms to older profiles or change the default1.
Paths are literal relative POSIX paths inside the manifest's directory. Private
inputs and manifests stay ignored.

Version2 has a closed field set: its `schema` discriminator and every field in
the table below are required. Only `source_packet_ledger` and `http_responses`
are permitted additional fields. Version1 retains its existing optional-field
rules described in the table.

| Field | Source and meaning |
| --- | --- |
| `files` | Map of every used evidence/payload path to measured `length` and `sha256`. No credentials, headers, arbitrary transport errors or rendered-note URLs. |
| `brain` | Path to raw Brain GET object (`id`, `homeThoughtId`, `name`). |
| `scope` | Independently declared complete `thought_ids`, `relationship_ids`, `attachment_ids` arrays. Counts alone are insufficient. |
| `graphs` | Map of every scoped thought UUID to its raw graph response path. The documented full graph supplies `activeThought`, `links`, `attachments`, `parents`, `children`, `jumps`, `tags`, `type`. |
| `attachment_inventories` | Map of owner UUID to a separately successful authoritative attachment-array response. Optional in version1 except when a graph inventory is null; explicit for every included owner in version2, with complete repeated agreement. Null is never fabricated into a successful empty inventory. |
| `attachment_metadata` | Map of attachment UUID to `{status:200,path:...}` for its complete authoritative raw declaration; required by version2 and checked against graph/list observations. |
| `types` | Path to authoritative raw thought-type array. |
| `tags` | `{status:200,path:...}` for raw tag array, or exact qualified `{status:400,path:...}` plaintext failure plus zero-tag statistics. |
| `statistics` | Two paths to starting/ending raw same-Brain statistics. |
| `link_attachments` | Map of every included relationship UUID to its raw successful empty attachment-array response. Populated/unavailable content holds qualification. |
| `link_attachment_outcomes` | Explicit included-relationship status map, required by version2; successful empty inventories remain independently bound in `link_attachments`. |
| `relationship_metadata` | Map of included relationship UUID to `{status:200,path:...}` for its full authoritative raw record; required by version2. |
| `no_notes` | Map of each owner without a raw-note declaration to raw successful exact empty NotesDto wrapper path. This is separate from files owned by that thought. |
| `payloads` | Map of every local attachment UUID to `{status:200,path:...}` measured bytes, or reviewed `{status:404}` only for qualifying non-note TXT with measured same-owner PDF. External URLs have no payload entry. |
| `one_way_controls` | Native independent controls with `relationship_id`, `source_id`, `destination_id`, `direction` (5 or 7), `destination_hides_source:true`, bound `graph` and `evidence` paths. Both accepted one-way shapes need valid controls; they may come from a separate independently qualified control Brain. |
| `archive_matches` | Array of `{attachment_id,archive,member}` entries; optional in version1, explicitly present (possibly empty) in version2. Archive path is bound evidence; bytes must equal the measured live payload. Only these payloads have proven archived/live equivalence. All others remain explicitly live-only. |
| `qualification` | Independently written evidence paths establishing the complete scoped ID census, current graph/source assumptions and native observations, with non-atomic/time/build limits. |
| `scope_inputs` | Version2 only: an object with exactly `excluded_thoughts` and `excluded_relationships`. Each is a map from canonical UUID to exactly `{status:200,path:...}`, binding the full successful raw authoritative response through `files`. Empty maps are explicit. Version1 refuses this field. |

Retained raw API observations may establish facts at their recorded times when
sealed and independently reviewed. They are not a current atomic snapshot.
Archived facts become API expectations only after the exact relevant live fields
or bytes have been matched; archive IDs or lengths alone do not prove equivalence.
Every actual scoped payload outcome and every required byte is audited. Discovery,
capture and final runtime/GUI acceptance retain the parent specification's gates.

The five qualified statistics counters are compared before/after; `dateGenerated`
records when statistics were produced and is not a content counter. It remains
fingerprinted source evidence without creating a false content-drift verdict.

For existing version1 baselines, when graphs contain known excluded neighbors,
a source projection may remove only
those neighbors and their associations. Bind its raw response length/hash, exact
safe removed identities/roles/access/forgotten markers, transformation method and
limitations in `qualification`. Included DTO values remain unchanged. Independently
review the authoritative exclusion evidence; archive role numbers or meaning6 alone
cannot establish a live System endpoint. Private content refuses before retention.

## Raw exclusion authority and retained content

Version2 keeps the original raw graph/list/metadata observations and included-owner
Notes reads as independent source evidence. The two exclusion maps identify
successful raw authoritative observations, not safe projections or asserted
normalized records. Excluded thoughts require full wire fields, public access,
supported source role and qualified System/forgotten authority. Relationships
require identity, Brain and established endpoint agreement before exclusion is
derived. Included and excluded identities must be disjoint; repeated authoritative
observations must agree, including scalar types. Failed, private, unknown or
contradictory evidence cannot establish an exclusion. Do not retrieve an excluded
owner's authored graph, attachments or note to populate these maps.

The independently derived safe view retains only the permitted five-field thought
and four-field relationship exclusion projections. Full raw response requirements
remain separate from those minimal retained fields. Source qualification binds raw
lengths/hashes, removal method and limits. An identity-only projection is never a
substitute raw HTTP DTO. Archive roles or meaning6 alone cannot establish a live
System endpoint.

The observed declaration domain `D` and raw local-read outcomes remain complete,
including successful original Notes reads that become unsafe after qualified
scope removal. Let `O` contain originals affected by that removal, `A = D - O`
the retained Asset domain, and `P` the retained owned payloads that are actually
available and openable. Version2 `audit_baseline` derives `retention` lists named
`omitted_original_ids`, `retained_asset_ids` and `openable_payload_ids`. These are
results of independent raw-source qualification, never manifest inputs or values
borrowed from a converter result. The audit's attachment count remains `D` and
its present-payload count is `P`.

An omitted original remains a measured successful raw read in the baseline but
has no retained Asset, openable payload or copied original. It is not an absent
payload or a new source gap; direct `expected_asset` for it refuses. A safe empty
original with no scope removal remains retained and openable, even when its
owner's vault note is uncreated. Scope removal precedes image binding and final
adaptation and removes a complete recognized excluded phrase, including enclosed
images. Unsafe residual associations refuse. The derived safe text supplies fresh
Unicode digests and reference/edit coordinates. Nested Document records and
omission flags remain mandatory on uncreated targets; materialization follows
safe adapted content and the established creation rules.

## Complete vault and component checks

Use `check_api_vault(baseline, vault, profile_version=...)` for complete conversion
acceptance. Every version2 invocation requires the complete protocol, generated
support artifacts and reservations, source bindings and physical file census.
The requirement comes from this public boundary, independently of which fields
or files survive in the candidate. Deleting both support envelopes and every
generated support file cannot downgrade the audit to a partial check. Missing,
duplicate, wrong or undeclared support paths/purposes, unknown record regions and
unaccounted extra files refuse.

`check_api_component_vault(baseline, vault, profile_version=...)` is the explicit
boundary for partial synthetic component controls, including older fixture
controls. It preserves their declared component scope and source-bound minimal
file census. Its success never establishes complete-vault acceptance and cannot
replace `check_api_vault` on actual Workflow output. This distinction does not
change version1 or older-profile proof limits.

New source families, mixed expected facts and checker changes require separate
independent qualification of the exact original oracle before accepting its
audits. A schema seal, passing component control or structurally valid output
does not replace source completeness, image/source fidelity, native presentation
or the parent specification's remaining acceptance gates.
