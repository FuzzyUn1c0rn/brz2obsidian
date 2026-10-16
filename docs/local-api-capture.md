# Local API capture encoding, version 1

This is the normative encoding contract for [#180](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/180), under [#177](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/177). It uses the independently qualified [local API profile](local-api-profile.md), the existing [contract version 7](../src/brz2obsidian/contracts.py) and [source-neutral architecture](adr/0001-source-neutral-core.md). Independent acceptance and delivery status belong in the issue and handoffs. The library tickets implement the digests and exercise these fixed vectors through SourceModule/SourceSession; this document changes no runtime behavior.

## Identifiers and compatibility

The exact `identifiers` object is:

```json
{"format_id":"thebrain-local-api-capture","format_version":"1","module_id":"thebrain-local-api","module_version":"1","profile_id":"thebrain-local-api-reviewed","profile_version":"1","contract_version":7}
```

`LOCAL_API_POLICY` binds profile ID/version, module ID/version, format version and contract version to these exact values. SourceIdentity.source_id is the verified canonical Brain UUID; its module_id/module_version/format_version match this object. Unknown versions or mismatches refuse before conversion. A changed mapping or encoding requires a reviewed version change. A changed converter/policy compatibility still requires review even if source content happens to match. This contract does not alter BRZ identity.

The capture has four canonical UTF-8 metadata files, `source.json`, `snapshot.json`, `metadata.json`, `audit.json`; zero or more generated `payload/<16 lowercase hex digits>.bin` files; and `manifest.json`. Paths here are generated storage keys relative to a private session-owned directory, never source filenames, URLs or absolute paths. The exact file inventory is closed. Manifest and frozen session state bind the capture before the session is yielded.

## CJSON1 canonical bytes

Let `C(value)` be the following unique byte encoding. These rules apply recursively to every canonical document and embedded JSON text.

- Values are objects with unique string keys, arrays, Unicode scalar strings, integers, true, false or null. All non-integer numbers, NaN/infinity and lone surrogates refuse. Boolean values remain booleans and cannot satisfy integer schema fields. Strict input JSON rejects duplicate keys, a BOM, invalid UTF-8, leading-zero integer spellings and the lexical spelling `-0`; semantic integer zero is valid. Surrogate escape pairs decode to their Unicode scalar before encoding.
- Objects emit `{`, key/value pairs separated by `,`, keys separated from values by `:`, then `}`. Sort keys by the lexicographic order of their unsigned UTF-8 bytes. Arrays emit `[` and `]` with `,` separators in their specified semantic order. Emit no insignificant whitespace, BOM or terminal newline.
- Strings use double quotes. Escape only quote as `\"`, backslash as `\\`, and each U+0000 through U+001F as exactly six ASCII bytes `\u00xx` with lowercase hex. Emit every other scalar as its literal UTF-8 bytes, including slash, DEL, non-ASCII, U+2028 and U+2029. Do not use short escapes such as `\n`, ASCII-only escaping, Unicode normalization, case folding, trimming or newline conversion.
- Integers emit ordinary base-ten ASCII with an optional minus sign and no plus sign, leading zero, exponent or decimal point. Emit booleans/null as the exact lowercase JSON literals. Numeric schema fields have their specified bounds; parsing cannot silently coerce a float, boolean or string to an integer.

Object member order and insignificant input JSON whitespace do not carry source meaning. Explicit null and absent fields are distinct; never fill missing source fields merely to equalize identity. Preserve authored names, labels, aliases, URI query values, exact text/newlines and source timestamp strings. Source dates are not converted to acquisition dates or rounded. Canonical contract defaults are materialized only in the normalized snapshot, where the model defines them.

## Scoped source document

`source.json` contains exactly `{identifiers,brain,records,inventories,scope,payloads}`. Every field is required. All UUID values are canonical lowercase nonzero UUID strings. Hex digests are exactly 64 lowercase hex characters. A key is a nonempty logical identity, never a position in a response, storage path or endpoint. Unknown document fields refuse.

| Field | Exact schema and meaning |
| --- | --- |
| identifiers | Exact object above. |
| brain | `{id,name,homeThoughtId}` from the qualified Brain; name is an authored string, Home is an included ordinary item. |
| records | Array of `{key,domain,owner_id,value}`. Unique key and domain/identity; sort by key UTF-8 bytes. domain is one of brain,thought,link,attachment,graph,no_note,note_text,statistics,exclusion. owner_id is Brain ID for brain/thought/link/statistics, thought ID for graph/attachment/no_note/note_text; Brain ID for exclusion. value follows the closed domain rules below. |
| inventories | Exactly `{ordinary_ids,type_ids,tag_ids}`: included authoritative ordinary/type/tag UUID sets, sorted by UTF-8 bytes. No duplicates, speculative excluded IDs or search stubs. |
| scope | Exactly `{policy,decisions}`. policy is `public-live-ordinary-type-tag-v1`. decisions is an array of `{key,rule_id,outcome,subjects,evidence}` sorted by unique key beginning `scope:`; subjects and evidence are unique sorted logical-key sets. rule_id is a qualified profile rule. outcome is included,excluded_forgotten,excluded_system,excluded_association,tag400_zero or missing_txt404. Include each observed decision affecting scope/availability; no invented undiscovered exclusions. |
| payloads | Array of `{asset_id,owner_id,availability,actual_length,actual_sha256,external_uri}` sorted by unique asset_id. asset_id/owner_id match the normalized Asset and source attachment. availability is present,absent or external. Present has measured nonnegative integer length and measured digest, external_uri=null. Absent has all three nullable fields null and the exact reviewed TXT404 decision. External has length/hash null and the exact authored URI. No empty-byte substitute for unavailable content. |

Record keys are `brain:<B>`, `thought:<id>`, `link:<id>`, `attachment:<id>`, `graph:<owner>`, `no_note:<owner>`, `note_text:<owner>`, `statistics:start`, `statistics:end` or `exclusion:<id>`, with the UUID matching the corresponding value. Evidence references resolve only to an existing records.key, `inventory:ordinary_ids`, `inventory:type_ids`, `inventory:tag_ids`, `payload:<asset_id>` or an exact existing decision.key. A decision cannot reference itself or form a reference cycle. Subject references use the corresponding source record/payload logical identity; excluded subjects may use `thought:<id>`/`link:<id>` without a full content record only when their exclusion decision supplies the qualified minimal evidence. Missing references refuse. The two statistics records are mandatory; equal repeated counters do not disappear. The brain record value equals brain. Every included thought/link/attachment and acquired graph has its corresponding scoped record. No-note and note_text are mutually exclusive for an owner. A note_text record holds scoped source Markdown before formatting adaptations and reference rebinding; it is distinct from the adapted Document.text.

Domain value schemas preserve every admitted field's scalar value, omission or null. The profile determines required fields and refusal of unsupported declarations; this list grants no additional semantic meaning. It is a retention allowlist, not permission to drop a qualified content-bearing field. If new meaningful fields cannot be represented safely under these rules, refuse and qualify a version change.

| Domain | Allowed value fields |
| --- | --- |
| brain | Exactly id,name,homeThoughtId. |
| thought | id,brainId,creationDateTime,modificationDateTime,name,cleanedUpName,typeId,displayModificationDateTime,forgottenDateTime,linksModificationDateTime,acType,kind,label,aliases,foregroundColor,backgroundColor. Keep source scalar types; aliases retains source ordering if it is an admitted array. |
| link | id,brainId,creationDateTime,modificationDateTime,name,cleanedUpName,typeId,kind,color,thickness,thoughtIdA,thoughtIdB,relation,direction,meaning. Endpoint A/B and directional values retain their orientation; never sort endpoints. |
| attachment | id,brainId,sourceId,sourceType,creationDateTime,modificationDateTime,name,position,fileModificationDateTime,type,isNotes,dataLength,location. Preserve authored external locations, including query values. position uses the exact decimal projection below. dataLength is declared evidence and never substitutes for measured actual_length. |
| graph | Exactly parents_ids,children_ids,jump_ids,sibling_ids,tag_ids,type_ids,link_ids,attachment_ids. Each is a unique UUID set sorted by UTF-8 bytes, projected from qualified joins/ownership. These are scoped inventories, not raw response wrappers. Excluded associations are removed; their safe decision remains in scope. |
| no_note | Exactly brainId,sourceId,sourceType,modificationDateTime,markdown,html,text, with the qualified empty-wrapper values. Do not retain a nonempty rendered wrapper, rendered URL or arbitrary response body. |
| note_text | Exactly `{text}`: qualified strict-UTF-8 scoped Markdown string, without excluded associations/content. |
| statistics | Exactly thoughts,thoughtTypes,tags,forgottenThoughts,links: qualified nonnegative integers. Omit unrelated operational metrics, including unqualified floating-point ratios. |
| exclusion | Only id,brainId,acType,kind,forgottenDateTime from authoritative excluded-item metadata, preserving admitted omission/null/value. Required predicate fields and identity must qualify the forgotten/system decision. No name,label,note,resource or other content. |

Attachment position is the one admitted non-integer source field: the schema declares number/double. Before CJSON1, parse its finite JSON number token as exact decimal arithmetic (never binary float) and represent it as `{decimal:"<value>"}`. This tagged object is the capture representation of a source number, not an authored object/string. Use it for integral positions too. Canonical decimal text has optional minus, ordinary base-ten digits, no plus/exponent/leading zeros, and an optional fractional part with all trailing zeros removed; omit the decimal point when no fractional digits remain. All zero values encode as `"0"`; `1`, `1.0` and `1e0` positions encode identically as `{decimal:"1"}`. Position token negative zero is a schema-level source numeric value normalized to zero; the strict CJSON1 input rejection of lexical `-0` still applies to retained canonical documents. Boolean/string/nonfinite positions refuse. Source metadata retains this explicit tagged representation in original_json too. This preserves numeric value and meaningful position without rounding or treating transport numeric spelling as content. Estimate expanded digit/encoded length before allocating a decimal string; enforce the configured remaining capture/metadata byte budget, including copies embedded in evidence. A short exponent token cannot cause unbounded expansion. A budget excess produces a safe typed limit failure, never rounding/truncation. Other source numeric fields must satisfy the profile's strict integer predicates; no blanket decimal/stringify fallback is allowed. A successful capture contains no unknown or contradictory admitted facts. Duplicated equivalent observations yield one logical record; audit records acquisition separately. Contradictory repeated observations refuse rather than selecting first/last.

Excluded items do not have full thought/link/note records. Scope subjects retain their canonical logical IDs only; a decision key identifies the affected item/association, its profile rule identifies the exclusion, and evidence references the corresponding minimal exclusion record. An excluded association decision also names the known excluded endpoint and affected included endpoint as logical subjects; it retains no names or arbitrary relationship content. Evidence never points to unretained private content or itself. The decision outcome records the qualified meaning, not arbitrary source text. Included decisions refer to actual records. Private content refuses acquisition; no successful capture can label private material as an exclusion exception.

Scope decisions are explicit content facts: removal/addition of an observed exclusion or a reviewed missing-file decision changes source identity. Discovery limits/counters are audit, while verified source statistics/included inventory and the qualified tag400 outcome are source facts. A tag400 decision records the failed classified inventory and its zero-tag corroborating source facts; it never becomes a successful empty response. A missing_txt404 decision names the TXT and successfully preserved same-owner PDF and refers to their metadata/payload facts; it makes no equivalence claim.

A raw note copy containing excluded associations is omitted under the profile. Its unsafe bytes are never retained in a payload or evidence string. The scoped note_text and explicit decision bind the permitted content. Original attachment metadata stays only if safe. Absence of an omitted original copy is not an absent Asset fabricated by this encoding.

## Normalized snapshot and meaningful ordering

`snapshot.json` is the complete JSON representation of SourceSnapshot contract7, with every defined default/null field materialized and no extra fields. Convert dates to their specified `YYYY-MM-DD` strings. It includes its final complete identity, original_evidence, findings, source_gaps, generated_presentations and accounting; no field is silently excluded because it is inconvenient to hash. All references resolve to the same frozen captured facts.

In `OriginalEvidence.original_json` and `SourceFinding.observed_json`, strict-parse the admitted safe JSON, apply the domain/set rules, and replace the string's text with `C(parsed).decode(UTF-8)`. It remains a JSON string in the contract, so the outer encoder escapes it. Do not substitute an object. Original evidence contains only scoped source declarations/payload facts and safe scope decisions, never audit, acquisition times, response position, headers, raw rendered wrappers, storage keys or endpoint data. Evidence pointers are stable logical source record/decision keys, not API request sequence numbers. OriginalEvidence.key is its unique logical evidence key. This permits equivalent transport responses to have equal snapshot identity.

The following is the exhaustive list of unordered snapshot arrays. Sort strings by UTF-8 bytes and composite records lexicographically by the listed tuple. Duplicate identities refuse; identical repeated transport observations must already have been collapsed. Sort findings by their full canonical object bytes and reject duplicate identical findings.

| Path | Sort key |
| --- | --- |
| items,relationships,documents,original_evidence | key |
| assets | asset_id |
| classification_assignments | relationship_key,definition_key,item_key |
| findings | C(canonical finding) bytes |
| source_gaps | owner,asset_id,role,rule_id |
| generated_presentations | owner,source_gap_asset_id,kind |
| accounting.entries | identity |
| every evidence array,findings[].affected,accounting.entries[].references | unique string set |
| items[].document_ids,items[].resource_ids | unique string set |

All other arrays preserve order, including Document.references, Document.text_adaptations, authored arrays in original values and generated_presentations[].image_asset_ids. The latter must already satisfy the contract's canonical_asset_identity order. Do not reorder text spans/edits, source aliases or positional resource declarations to force identity equality. Original scope/payload/graph JSON uses the explicitly enumerated source set rules. Whitespace within a JSON text string or authored Markdown is data even when surrounding JSON whitespace is not.

## Content digest preimages

`H` is SHA-256 returning lowercase hex. Prefix literals below are ASCII, with exactly one final LF (byte0A). Concatenate bytes directly; do not hash hexadecimal text or include file lengths/newlines unless present in C(value).

```text
source_sha256 = H(b"brz2obsidian.local-api.source.v1\n" + C(source))
snapshot_digest = H(b"brz2obsidian.local-api.snapshot.v1\n" + C(snapshot_without_own_digest))
```

`snapshot_without_own_digest` is the fully canonical snapshot with exactly `identity.snapshot_digest` omitted, not set to null/empty/zero. All other identity fields remain, including the computed source_sha256 and verified Brain/module/format versions. Compute source_sha256 first, then snapshot_digest, then put both in the final SourceIdentity. Source has no identity digest fields, snapshot record, file hash or manifest reference, so neither calculation is recursive. C(source), C(snapshot_without_own_digest) and full C(snapshot) are three distinct byte sequences. Manifest file.actual_sha256 is always the ordinary unframed SHA-256 of the complete exact stored file bytes. In particular source.json file hash is not source_sha256, and finalized snapshot.json file hash is not snapshot_digest; never compare these different domains as if they were interchangeable.

Neither content preimage contains endpoint/port, transport response order, request counters, credentials, storage keys, audit method/limits/times or machine paths. Safe source modification timestamps, authored values and normalized text/evidence remain bound. Different content/scope/payload association/availability/bytes change source_sha256; any normalized fact/evidence/accounting change changes snapshot_digest. The snapshot digest also changes when its bound source_sha256 changes. An irrelevant port/time/storage relocation does not make a review stale by content identity; independently required converter/policy compatibility still applies. GUI source/acquisition-configuration changes still invalidate inspection under the parent workflow; digest equality does not override that rule.

## Audit and metadata

`metadata.json` is exactly `{identifiers,identity,schema_sha256,desktop_build}`. identity is the complete final SourceIdentity. schema_sha256 is the assessed schema's actual digest; desktop_build is the observed build string. They are bound capture metadata and compatibility evidence, not authored content. Module/profile validation must reject an unqualified schema/build combination rather than use a hash comparison as semantic qualification.

`audit.json` is exactly `{atomic,method,started_at,finished_at,limits,requests,consistency_limits}`. atomic is false; method is `bounded-read-only-local-api`. Acquisition timestamps are UTC strings `YYYY-MM-DDTHH:MM:SS.ffffffZ`, with start no later than finish. They describe acquisition, never source modification times. Requests record every acquisition request, including qualified failures, in chronological records with unique consecutive sequence integers starting at1. They are not a substitute for independent source preservation or a completeness guarantee. Each request is exactly `{sequence,operation,brain_id,subject_id,status,outcome,started_at,finished_at,actual_length}`. subject_id is the requested canonical UUID or null; brain_id matches the capture. operation is one of brain,statistics,search,types,tags,thought,graph,link,attachments,note,attachment-content. status is the HTTP status integer. outcome is success,tag_inventory_zero_exception or missing_txt_404. success requires the qualified HTTP200 shape; tag_inventory_zero_exception requires tags/400 and its exact profile corroboration; missing_txt_404 requires attachment-content/404 and its exact profile corroboration. No arbitrary status/body qualifies an exception. Request start/finish must be ordered and contained within the acquisition interval. actual_length is measured response-byte count. These counts do not certify payload preservation.

limits has exactly initial_search_results,search_budget_ms,search_max_response_bytes,max_search_results,request_timeout_ms,max_response_bytes,max_total_capture_bytes,max_requests,max_traversal_items,max_payload_bytes. All are positive integers except optional max_search_results=null. Values record the actual configured bounds and must satisfy parent defaults/configuration rules; integer milliseconds avoid floating encodings. Requests/counters, transport order and operational bounds are integrity-bound audit and excluded from content digests. Successful audit cannot erase failed tag400/TXT404 outcomes. Unsupported/authentication/timeout/interruption failures prevent a yielded complete capture and produce safe typed issues instead.

consistency_limits is exactly `["non-atomic-multi-request","captured-copy-integrity-only","empirical-discovery-no-completeness-guarantee"]`, in that order. Inspection releases its session; conversion reacquires. The API spans multiple requests over time. Editing or syncing can produce mixed source states. Captured-copy integrity does not prove that every object coexisted, that the live Brain stayed unchanged, or that API discovery is universally complete. atomic=false is evidence, not a per-import warning requiring extra authorization.

## Separate integrity manifest

`manifest.json` is exactly `{format_id,format_version,source_sha256,snapshot_digest,files,payload_bindings,integrity_sha256}`. Format values match identifiers. files is sorted by unique storage_key, each entry exactly `{role,storage_key,actual_length,actual_sha256}`. The four required roles source,snapshot,metadata,audit use the respective exact `<role>.json` storage keys. Every retained payload has role payload and a unique generated `payload/<16 lowercase hex digits>.bin` key. Length/hash are measured over the complete exact stored bytes, including any corruption; compare to the frozen expected values, never refresh expected hashes during verification. Canonical metadata files have no terminal newline.

payload_bindings is sorted by unique asset_id, with entries exactly `{asset_id,owner_id,storage_key}`. It covers every present source/snapshot Asset exactly once and none of the absent/external assets. Each key names one payload file and each payload file has exactly one binding. Do not share a file between different asset identities even when bytes match. Owner,asset ID,availability,length/hash must agree with source.json, snapshot.json, metadata.identity and measured bytes. Declared dataLength is independently retained evidence. Missing/external assets have no invented storage or empty payload file.

files lists every retained regular file except manifest.json. Reject missing/extra files, directories other than the defined payload directory, duplicate paths or duplicate singleton metadata roles, absolute/drive/UNC/dot/percent/backslash paths, symlinks/reparse points and path aliases/case variants. Payload storage may be relocated only by constructing a new integrity manifest; source/snapshot content identities remain the same if content facts do. Renaming/swapping two payloads with identical bytes still fails an unchanged association manifest. The payload role may repeat when each file has its own unique generated storage key and one-to-one asset binding. Recomputed manifests do not authorize a changed capture.

```text
integrity_sha256 = H(b"brz2obsidian.local-api.integrity.v1\n" + C(manifest_without_own_digest))
```

Omit exactly integrity_sha256, leaving all other manifest fields. Manifest does not list its own bytes; this avoids self-reference. Persist the final manifest canonically and keep its expected root, final SourceIdentity and frozen snapshot associated in private session state. verify_consistency checks manifest syntax/canonical bytes, the pinned root, complete files/associations, exact measured file hashes, document shapes, identity equality and recomputed content digests against that frozen state. It checks the retained copy and never rereads the live Brain. Altered audit or metadata can preserve source_sha256/snapshot_digest and must still fail integrity; altered payload bytes/ownership association must also fail. Integrity is corruption detection against a pinned expected capture, not a signature or proof against an attacker replacing both capture and trusted root.

A session is yielded only when these checks are satisfiable and everything is frozen. Unknown/unavailable/closed-session payload access refuses; closing revokes streams and cleans only the owned capture. Existing staged payload verification/publication and teardown receipt semantics remain required in later implementation.

The first retained-document verification performs all canonical, content-digest,
binding and pinned-root checks. Later calls may reuse that same-session semantic
proof only after checking the complete storage inventory, ownership/aliases,
pinned manifest and every file's full measured length/hash, including unrequested
payloads. The exact checked metadata bytes and trusted identity/audit/profile/root/
associations must match the initial proof. This avoids reparsing unchanged
documents on every payload open; it never trusts timestamps, skips payload hashes,
refreshes expected hashes or adopts changed metadata. Bytes used for comparison
or parsing must themselves have been measured and checked. Encoding and identity
rules remain unchanged; repeated whole-capture hashing still has a cost.

## Secret and provenance boundary

Use allowlisted semantic projections before any write, exception rendering or diagnostic. Do not retain API keys, authorization/cookie/other header values, service-issued transport tokens, rendered-note wrappers/URLs, request URLs, raw response/error text, raw exception reprs in any file, embedded JSON, source evidence, manifest, audit, result, log, worker message or vault output. Configured origins/ports are excluded from retained capture documents; validated credential-free connection configuration remains available to outer acquisition/UI/worker wiring as required by the parent specification. Hashing a file does not make retaining its unsafe contents acceptable. Request identity is symbolic operation plus validated Brain/subject ID. Failures use a safe finite classification and counts, not arbitrary remote/system text. Partial/failure artifacts obey the same boundary.

Authored external destinations are source data. Preserve the qualified URI exactly, including an authored query such as `?token=authored-value`; never apply a key-name redaction rule that changes authored content. The boundary is provenance: a service-issued rendered-note URL is discarded, an authored external attachment URI is preserved. If provenance is unknown or sensitive service data occurs in an unqualified source shape, refuse rather than guessing. This contract grants no new rendered fallback.

## Independent vector obligations

The separately authored [fixed vectors](../tests/fixtures/local_api_capture/) specify literal canonical bytes and expected SHA-256 values without using the future product encoder. They cover primitives/escaping/Unicode, omitted versus null, strict invalid encodings, equal reordered inventories/responses/changed ports/times/storage, meaningful authored order/text/source-date differences, scope/availability/ownership changes, both content domains, exact self-field omission and integrity tampering with audit,metadata,payload bytes,associations,files and expected root. Secret controls cover headers/service tokens in every retained form while preserving an authored external query. Fixture container files are readable JSON and are not themselves capture documents or digest preimages. Their literal canonical_utf8/hex fields specify exact bytes; never substitute container file bytes for those values. Fixture expectations are an independent contract oracle; later code must meet them rather than regenerate expected output from itself. Manual review and fixed vectors establish this encoding slice; later implementation, complete live preservation, GUI and aggregate delivery gates remain separate required work.


| Fixed fixture | Coverage |
| --- | --- |
| [canonical-vectors.json](../tests/fixtures/local_api_capture/canonical-vectors.json) |13 literal byte/hash cases and10 strict rejection controls, including UTF-8 ordering,C0 escapes,non-NFC,CRLF,missing/null and malformed JSON. |
| [capture-vectors.json](../tests/fixtures/local_api_capture/capture-vectors.json) |9 full source/snapshot/manifest captures. CAP01 baseline; CAP02 equivalent reordered/environment/time/storage case; CAP03-CAP09 authored title,alias order,source timestamp,bytes,scope,position and measured-length changes. |
| [capture-controls.json](../tests/fixtures/local_api_capture/capture-controls.json) |30 integrity/schema controls,12 transport-secret/authored-URI controls,12 exact-decimal literals and7 decimal/budget refusals. |


## Explicit profile2 alternative

For acquisition using the independently qualified [additive resource profile2](local-api-profile.md#additive-profile2-resource-qualification), the exact identifiers object above has one alternative: `profile_version` is `"2"`. Every other field remains identical: format_id=`thebrain-local-api-capture`,format_version=`1`,module_id=`thebrain-local-api`,module_version=`1`,profile_id=`thebrain-local-api-reviewed`,contract_version=7. CJSON1,the three domain prefixes,closed file/domain schemas,own-field omission,ordering rules,secret exclusions and integrity/session associations are unchanged. No actual_format field or new source domain is introduced.

The outer LOCAL_API_POLICY and capture identifiers must explicitly select the same reviewed profile version. A version1 capture remains bound to version1 support; it cannot silently acquire version2 semantics. Unknown versions or policy/identifier mismatch refuse. A reviewed version1 identity is incompatible with version2 until another inspection/review because profile_version participates in C(source) and its bound source_sha256; the snapshot and integrity digests consequently differ. No automatic profile fallback or replacement of old fixed expectations is permitted.

All three original version1 fixture files remain byte-for-byte unchanged as committed. The separately authored [profile2 capture literal](../tests/fixtures/local_api_capture/profile2-capture-vector.json) supplies one independent case changing only the profile identifier and consequent source/snapshot/metadata/manifest hash bindings. It specifies the version alternative using existing format1 facts,not a new canonical encoder or a claim of runtime support. Resource-v2 positive/negative controls independently qualify the additional roles/formats. Actual stored-byte file hashes remain unframed and distinct from content digests as above.


## Explicit profile3 alternative

Profile 3 adds `profile_version="3"` as an explicit identifier alternative with
all other format1 identifiers, contract7, CJSON1, digest domains and self-field
omission rules unchanged. `LOCAL_API_POLICY_V3` is the matching outer policy.
The [independently qualified table](local-api-profile3-qualification.md) bounds
source semantics; profile selection never grants blanket role/extension support.
Live, sealed and reopened captures inherit profile2 support under profile3 and
retain exact profile matching. Direct module/session defaults remain profile1;
explicit profiles1/2 preserve their semantics. Unknown or mismatched identifiers
refuse. Generic custom policy/module composition remains caller-owned.

The [independently authored profile3 literal](../tests/fixtures/local_api_capture/profile3-capture-vector.json)
is an additional oracle; older fixture bytes and expectations remain unchanged.
Its framed source/snapshot/integrity expectations differ solely because profile
identity is bound. Ordinary retained-file hashes remain unframed. Operational
host/capture/storage paths are excluded from content identity; authored external
locations and their derived URI/display facts remain content-bound. Pinned
mutations refuse even with recomputed untrusted manifests. A fresh valid capture
with valid changed content receives a different identity and needs a new review;
independent original-source preservation is established by baseline comparison.


Profile3 external references retain their exact type/location/null authored name
and declaration joins. Normalized external file/directory assets bind their
original_name to that raw path, display_name to its final Windows segment and
external_uri to the established pure Windows URI helper. Availability is external,
actual length/hash are null and no payload binding or local storage is permitted.
These conditions apply during construction, sealing and verification, including
when untrusted hashes are recreated. Raw separator spelling remains content-bound
even if two paths derive the same URI; a valid path change needs a fresh review.
No capture domain or encoding/framing change is required.
