# Independent API preservation baseline

The private baseline for #179 is prepared from source evidence before conversion.
It is independent of the adapter, normalized snapshots and migration records.
The checker imports only the standard library. Synthetic checker controls do not
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

Both public audit functions default to the unchanged profile version1. Pass
`profile_version="2"` explicitly for the reviewed four-shape alternative. Unknown
versions refuse; a vault's profile/module/format versions must agree with that
selection and the capture contract. The baseline's original seal remains unchanged.
Profile2 measures PNG/JPEG eligibility through complete Windows WIC pixel decoding
and checks each opaque ZIP's central directory without extraction or member CRC
claims. Missing decoder capability or a decoder resource bound leaves acceptance
unavailable. Its returned `resource_eligibility` map binds every added resource's
proof to actual source bytes; caller-supplied decoder booleans are never inputs.

The shared independent Markdown reference parser receives API-owned asset names
and roles directly. No BRZ record flags, archive paths, absent-note interpretation
or archive population assumptions supply API expectations. Local image ownership
and included item targets are checked against the complete API inventory.

The manifest schema is `brz2obsidian.api-acceptance/1`. Paths are literal relative
POSIX paths inside its directory. Private inputs and manifests stay ignored.

| Field | Source and meaning |
| --- | --- |
| `files` | Map of every used evidence/payload path to measured `length` and `sha256`. No credentials, headers, arbitrary transport errors or rendered-note URLs. |
| `brain` | Path to raw Brain GET object (`id`, `homeThoughtId`, `name`). |
| `scope` | Independently declared complete `thought_ids`, `relationship_ids`, `attachment_ids` arrays. Counts alone are insufficient. |
| `graphs` | Map of every scoped thought UUID to its raw graph response path. The documented full graph supplies `activeThought`, `links`, `attachments`, `parents`, `children`, `jumps`, `tags`, `type`. |
| `attachment_inventories` | Optional map of owner UUID to a separately successful authoritative attachment-array response, required when the graph's attachment inventory is null. Null is never fabricated into a successful empty inventory. |
| `types` | Path to authoritative raw thought-type array. |
| `tags` | `{status:200,path:...}` for raw tag array, or exact qualified `{status:400,path:...}` plaintext failure plus zero-tag statistics. |
| `statistics` | Two paths to starting/ending raw same-Brain statistics. |
| `link_attachments` | Map of every included relationship UUID to its raw successful empty attachment-array response. Populated/unavailable content holds qualification. |
| `no_notes` | Map of each owner without a raw-note declaration to raw successful exact empty NotesDto wrapper path. This is separate from files owned by that thought. |
| `payloads` | Map of every local attachment UUID to `{status:200,path:...}` measured bytes, or reviewed `{status:404}` only for qualifying non-note TXT with measured same-owner PDF. External URLs have no payload entry. |
| `one_way_controls` | Native independent controls with `relationship_id`, `source_id`, `destination_id`, `direction` (5 or 7), `destination_hides_source:true`, bound `graph` and `evidence` paths. Both accepted one-way shapes need valid controls; they may come from a separate independently qualified control Brain. |
| `archive_matches` | Optional array of `{attachment_id,archive,member}` entries. Archive path is bound evidence; bytes must equal the measured live payload. Only these payloads have proven archived/live equivalence. All others remain explicitly live-only. |
| `qualification` | Independently written evidence paths establishing the complete scoped ID census, current graph/source assumptions and native observations, with non-atomic/time/build limits. |

Retained raw API observations may establish facts at their recorded times when
sealed and independently reviewed. They are not a current atomic snapshot.
Archived facts become API expectations only after the exact relevant live fields
or bytes have been matched; archive IDs or lengths alone do not prove equivalence.
Every actual scoped payload outcome and every required byte is audited. Discovery,
capture and final runtime/GUI acceptance retain the parent specification's gates.

The five qualified statistics counters are compared before/after; `dateGenerated`
records when statistics were produced and is not a content counter. It remains
fingerprinted source evidence without creating a false content-drift verdict.

When graphs contain known excluded neighbors, a source projection may remove only
those neighbors and their associations. Bind its raw response length/hash, exact
safe removed identities/roles/access/forgotten markers, transformation method and
limitations in `qualification`. Included DTO values remain unchanged. Independently
review the authoritative exclusion evidence; archive role numbers or meaning6 alone
cannot establish a live System endpoint. Private content refuses before retention.
