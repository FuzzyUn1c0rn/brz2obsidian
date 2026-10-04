# Verify the purpose and state of attachment text records

Status: resolved
Type: research
Labels: wayfinder:research
Parent: [Find the route to version 2 for the Software Engineering Brain](../map.md)
Blocked by: none
Assignee: /root/attachment_text_evidence
Research branch: `research/brz-v2-attachment-text`

## Question

What first-party evidence establishes the meaning of TheBrain attachment Type 15 and absent file state 2, especially zero-length TXT records whose filename stem matches an archived PDF attachment identity?

Investigate official API/SDK documentation, guides and staff explanations. Separate the purpose of a text-extraction/indexing record, physical file state, source length and effects on viewing versus searching a PDF. The native source task is checking the supplied owners and a controlled PDF; this ticket supplies documentation or source definitions that observation alone cannot prove. Do not infer a universal meaning from filenames or relax a warning rule.

Save one concise primary-source-cited findings document under `../research/`. Record a bounded negative result and an explicit evidence limitation if current public sources cannot establish an enum meaning. Keep private source records and URLs out of public findings.

## Comments

- 2026-10-04: Native observation confirms a PDF opens; source comparison additionally found TXT filename stems matching PDF attachment IDs. A focused documentation investigation is needed to distinguish provenance from a naming correlation.

## Answer

The [primary-source findings](../research/attachment-text-evidence.md) establish PDF text extraction for indexing, separate filename/content search, and the distinction between an attachment reference and its available file. The current official API lists numeric attachment types without a name for 15 and supplies no archive file-state definition. The bounded investigation found no authoritative Type-15/state-2 mapping or explanation for these zero-length omissions.

This is an evidence limit, not permission to treat missing bytes as harmless. Native controls may establish behavior for a particular build and sample; a reviewed coverage decision still owns acceptance, preservation and warnings. Research captured on `research/brz-v2-attachment-text`, commit `061da760e6130c095e0c623b69c45b24f611445e`; the report was copied into this map's research directory.
