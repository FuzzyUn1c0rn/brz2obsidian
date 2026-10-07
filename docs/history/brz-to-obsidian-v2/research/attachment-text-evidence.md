# Attachment text records: documentation evidence and limits

Checked: 2026-10-04. Scope: a bounded targeted pass over the current official API schema, its linked vendor example source, and staff explanations of attachment indexing and missing files. This report supplements [the archive comparison](source-differences.md); it does not define a new conversion rule.

**No authoritative definition of attachment `Type=15` or archived physical file state `2` was found.** First-party material establishes that PDF content can be extracted to text for indexing, but it does not identify the supplied zero-length absent TXT records as that output, explain their absence, or establish their effect on current PDF search.

## What primary sources establish

| Source | Established evidence | Limit |
| --- | --- | --- |
| [Current official OpenAPI JSON](https://api.bra.in/v1/docs.json), API version `1.0.5` | `AttachmentType` permits integers `0` through `15`, plus `100`, without symbolic names or descriptions. `AttachmentDto.type` and `sourceType` are integers; `dataLength` is nullable `int64`. Its fields and available schemas contain no attachment file-state field/enum. The by-location endpoint names only `2=ExternalFile`, `3=ExternalUrl`, and `8=ExternalDirectory`. | Membership in an API enum supplies no meaning for `15`; this API DTO is not a BRZ format-5 specification. Its silence cannot define archive state `2`. |
| [Vendor Blazor example attachment model](https://github.com/TheBrainTech/thebrain-api-quickstart-blazor/blob/master/TheBrainApiQuickstart/Data/Attachment.cs), linked by the API's introduction | The model likewise exposes integer `type` and `sourceType`, nullable `dataLength`, and no physical file-state field or named attachment enum. | This example adds no missing numeric definition. The [vendor API introduction](https://www.thebrain.com/blog/introducing-thebrain-api) describes the examples as demonstrations, not an export-format contract. |
| [Harlan's historical indexing explanation](https://forums.thebrain.com/post/4069lib-indexing-hanging-1998441) | The staff-provided log example has three separate steps: index a thought, convert its PDF attachment to a numbered TXT file, then index the converted TXT file. A hang during conversion may prevent the success log entry. | Establishes a historical extraction/indexing mechanism. The example uses the older PersonalBrain engine and numbered paths; it does not name Type 15, current GUID naming, zero-length metadata, archive omission rules, or state 2. |
| [Juan's TheBrain 14 indexing explanation](https://forums.thebrain.com/post/which-file-formats-are-index-by-thebrain14-13357727) | All file attachment names are indexed; contents are indexed for TXT, Markdown, PDF, Word, Excel, PowerPoint and notes. Staff separately discusses extraction failures and reindexing newly supported content. | Filename search and content search are distinct. Searchability cannot be inferred from a PDF preview or from the mere presence of an attachment record. |
| [John's integrity-scan explanation](https://forums.thebrain.com/post/integrity-scans-on-tb14-and-tb15-differ-13796998) | A database attachment reference can remain when its file cannot be located locally or on the server; the integrity scan removes that broken reference. Duplicate references and missing files are separate cases. | Establishes that record existence differs from physical availability, but supplies no numeric state definition and no special rule for extracted TXT records. This investigation did not run an integrity scan. |

## Application to the supplied evidence

The [archive comparison](source-differences.md) records four absent TXT declarations with `Type=15`, `NoteType=0`, `SourceType=2`, physical state `2`, and `DataLength=0`, alongside present PDF files. The parent investigation additionally found matching TXT filename stems and PDF attachment identities. That correlation is consistent with a derived-text hypothesis, but **does not prove the role or lifecycle of Type 15**. No source above binds the numeric type to extraction or defines that naming relationship.

Keep these questions separate:

- **Purpose:** first-party documentation establishes PDF-to-text indexing in general; Type 15 remains unidentified by authoritative numeric documentation.
- **Physical availability:** no TXT payload is present in the supplied archive. State `2` remains uninterpreted; it cannot be equated to deferred download, failed extraction, deleted content, or optional cache.
- **Length:** the declaration is zero. It does not establish why the producer wrote zero, whether extraction yielded no text, or whether bytes existed elsewhere.
- **Viewing:** the parent reports that the supplied PDF opens natively. That observation establishes viewing for the observed PDF/build, not TXT provenance or completeness of search.
- **Searching:** attachment-name indexing is separate from PDF-content extraction. These sources do not establish whether the supplied PDFs' content was indexed or whether absent TXT bytes affect current local/cloud search.

## Bounded negative result and confidence

Targeted official-domain/vendor-source searches for `AttachmentType`, `Type 15`, `DataLength`, `FileState`, and `HiddenAttachmentsText` did not locate an authoritative numeric mapping or state-2 definition. A user-posted AI explanation naming `HiddenAttachmentsText` is not a staff or vendor specification and was excluded as evidence. The current raw API schema and linked vendor model were read directly; no API key, private Brain request, native mutation, or archive modification was used.

Confidence is high in the quoted schema shapes and documented general indexing/availability distinctions; it is **insufficient for Type-15 identity, state-2 semantics, zero-length omission intent, or current search effects**. A controlled export can establish observed behavior for its exact build and sample. Universal semantics still require a vendor definition or stronger source evidence. This result does not authorize accepting these records or relaxing the existing missing-file warning/refusal boundary.
