# Determine what the BRZ export can preserve

Status: resolved
Type: research
Labels: wayfinder:research
Parent: [Find the route from a BRZ archive to an Obsidian vault](../map.md)
Blocked by: none
Assignee: /root/brz_evidence

## Question

Which content, identities, relationships, metadata, and associated files can be recovered from the two supplied BRZ archives, and what evidence supports each interpretation?

Inspect both actual archives without modifying them: `brz/D&D_ The Rise of Anzoras 2026-10-03.brz` and `brz/Dungeons & Dragons 2026-10-03.brz`. Verify their declared exchange formats and compare feature coverage. Establish the record formats, references, ordinary thoughts versus types and tags, relationship kind/meaning/direction fields, attachment ownership and file resolution, note syntax and embedded references, and treatment of tombstones or history. Check counts and cross-references rather than relying on a handful of sample records.

Use first-party TheBrain documentation or source where available to corroborate meanings. Separate observed structure, externally documented semantics, inference, and unresolved meanings. Identify missing payloads, unsupported features, and the limits of generalizing from these two exports. Do not invent an enum interpretation merely because it looks plausible.

Save a source-cited findings asset under `../research/`, with reproducible inspection details and aggregate findings that do not disclose private titles or note text. Research establishes evidence; later tickets choose the conversion policy.

## Comments

- 2026-10-03: The user updated the first export and added the larger `Dungeons & Dragons 2026-10-03.brz`; the hold is lifted. Research now covers both files. Their present sizes are 45,016,149 and 153,693,431 bytes respectively; the earlier inventory is historical evidence only.
- 2026-10-03: Waiting at the user's request for an export produced with the latest TheBrain. Do not start research against the initial export while this hold is in effect. On resumption, identify the new archive, update the source reference, and return this ticket to `ready-for-agent` before claiming it.
- 2026-10-03: The initial inventory found 73 ZIP entries: 13 root metadata files and 60 resources beneath UUID-shaped directories. Most collection files appear to use newline-delimited JSON despite their `.json` extensions. Counts and semantics need verification in this investigation.

## Answer

Resolved on 2026-10-03. [BRZ preservation evidence](../research/brz-preservation.md), [the aggregate inventory](../research/archive-inventory.json), and [the read-only inspection script](../research/inspect_brz.py) record the observations, primary sources, fingerprints, and reproducible checks. Research was captured on `research/brz-preservation`, commit `2daf78abd3f008fd9883f0f5d7aeffa49fab4f4b`, and integrated into the main checkout.

- Both updated exports use exchange format 5 and BOM-prefixed per-line JSON. They contain 76/58 thoughts, 129/57 relationships, and 60/50 physical resources. Independent inspection with Windows Python 3.14.8 reproduced the counts; ZIP CRC checks passed and all live relationship endpoints resolved.
- Notes, ordinary files, icons, and embedded images have resolvable payloads. All 75 observed local `brain://` thought links resolve. Tag assignments in the smaller Brain occur in relationship records even though every `TagIds` array is empty. Thought kind 5 is documented as a system object.
- The larger Brain adds duplicate titles, PDFs, WebP images, an external-directory reference, and nine type-15 text attachment records with absent payloads. The PDFs themselves are present. Type 15 and file state 2 have no confirmed meaning in the sources inspected; a derived-PDF-text interpretation remains an inference. Two smaller-Brain icons have metadata length discrepancies despite valid ZIP CRCs.
- The export's hierarchy A/B endpoint orientation and `Direction=-1` remain unverified. [Verify hierarchy and default direction with a controlled export](07-relationship-fixture.md) supplies the missing evidence before [Choose note identity, relationships, and vault layout](03-vault-model.md).
- Evidence covers the two inspected exports and their observed features. Types, typed links, events, custom fields, HTML notes, general legacy styling, and cross-Brain links are unexercised. [Choose the conversion and failure contract](05-conversion-contract.md) must settle unsupported features, external references, and missing/unclassified attachment data.
