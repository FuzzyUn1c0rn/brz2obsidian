# Home-thought source evidence

Investigated 2026-10-03 for [Verify how BRZ identifies the home thought](../issues/11-home-thought-evidence.md). This report distinguishes documented source semantics, observed archive behavior, and unresolved limits. Private thought names, IDs, note text, and assigned filenames are omitted.

**Verified for the inspected format-5 exports:** find the `settings.json` record whose `Id` is standard UUIDv5(namespace=`meta.BrainId`, name=`"20"`). Its string `Value` is the designated home thought UUID. Resolve that UUID against `thoughts.json.Id`, then use the same source-ID-to-vault-target assignment used by every internal link.

## Primary documentation

The official guide describes setting a thought as the Home thought through Thought Properties. That is a designation applied to a thought, rather than a requirement that the thought have a particular name or parent count. This guide describes TheBrain 13; the native observation below separately verifies TheBrain 15. [TheBrain 13 User Guide, page 106](https://assets.thebrain.com/documents/TheBrain13/TheBrain13-User-Guide_v04.pdf).

The official API's `BrainDto` schema has an explicit `homeThoughtId` property with JSON type `string` and format `uuid`, alongside `id` and `name`. The schema was fetched on the investigation date and identified API version 1.0.5. It corroborates the existence of explicit home identity, but does **not** document the BRZ setting-key derivation. [Official OpenAPI source](https://api.bra.in/v1/docs.json).

A TheBrain moderator explains that opening a Brain in a new tab activates its Home thought, separately from returning to the last active thought of a previous session. This is documentation of a specific opening context; it does not establish all reopening and session-restoration behavior across builds. [TheBrain 15 staff clarification](https://forums.thebrain.com/post/opening-any-brain-always-activates-the-home-thought-13861438).

No consulted first-party reference documented the decimal setting name or the UUID derivation below. Those findings are local reverse-engineering evidence, not a published compatibility guarantee.

## Exact real inputs

The script reads these exact paths, not whichever exports are smallest. It rejects changed fingerprints before inspecting them. These match the earlier [archive inventory](brz-preservation.md).

| Input | Repository path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| A | `brz/D&D_ The Rise of Anzoras 2026-10-03.brz` | 45,016,149 | `84405276897f27f188a9f33453aac94cfdac6a4dfaaeecf8f0bd5a46454b7be4` |
| B | `brz/Dungeons & Dragons 2026-10-03.brz` | 153,693,431 | `20b6085239b82ba7c4a6951d07a53243c3d7ddd00fcd3d6b91115cd7170c26b0` |

Both declare exchange format 5. The user identifies the exporting application as TheBrain 15; its exact build is not encoded in these archives. Inspection used Windows Python 3.14.8 and read ZIP members in memory, with CRC checks and BOM-aware per-line JSON parsing. No resource was extracted, uploaded, or changed.

## Deterministic setting recognition

**Observed:** `settings.json` records have `Id`, `BrainId`, and string `Value` fields, with creation/modification and optional sync fields. They have no named Home key. Each real archive contains exactly one `Value` that is an exact canonical UUID of a live thought. This is useful evidence, but is insufficient by itself to call that thought Home.

The setting IDs differ between Brains. A search over explicit namespace/name hypotheses found an exact match in all three independent Brain namespaces:

```python
setting_id = str(uuid.uuid5(uuid.UUID(meta["BrainId"]), "20"))
```

The name is the UTF-8 decimal text **`"20"`**, not the thought title and not binary integer bytes. Standard UUIDv5 uses the namespace UUID and SHA-1 over the name, as specified by the Python documentation. No custom GUID endian conversion is used. [Python UUIDv5 documentation](https://docs.python.org/3/library/uuid.html#uuid.uuid5).

The derived setting ID has one record in each archive. Its `Value` is the home thought UUID, which resolves against `thoughts.json.Id`; the controlled change below establishes this interpretation. As supporting evidence of the namespace convention, all 27 A settings, all 25 B settings, and all five settings in each controlled export match UUIDv5 of their own Brain ID and a decimal name in the tested range 0 through 999. This does not identify the semantics of those other numeric settings.

| Measure | A | B | Original controlled export | Changed-home export |
| --- | ---: | ---: | ---: | ---: |
| Settings records | 27 | 25 | 5 | 5 |
| Records matching UUIDv5(BrainId, `"20"`) | 1 | 1 | 1 | 1 |
| Home UUID resolves to live thought | Yes | Yes | Yes | Yes |
| Home thought Kind | 1 | 1 | 1 | 1 |
| Home ordinary parents | 0 | 0 | 0 | 1 |

The original controlled home is **PARENT**; the changed-home export designates **CHILD**, which has an ordinary parent. Parentlessness in the first three cases is a coincidence, not an identity rule. Ordinary hierarchy roots, last activation timestamps, title similarity, the first thought record, or the only thought-valued setting must not substitute for the derived-key lookup and validated designation.

## Controlled native observation

**Observed by the root agent in the native TheBrain 15 UI:** in the controlled Brain, activating CHILD and then clicking Home returned to PARENT. CHILD visibly has PARENT above it. This verifies the baseline designation and its correspondence to the candidate value in the original export.

The human then set CHILD as Home and authorized the root agent to perform the remaining steps. The root activated PEER and verified it active, exported through File → Export → Brain Archive, and renamed the newly generated archive to `brz/controlled-home-child.brz`. After the export, clicking Home activated CHILD; the Home tooltip also read CHILD, with PARENT visibly above it. The original exports were not overwritten.

The root saved a [synthetic native Home-result screenshot](</C:/Users/stefa/projects/brz2obsidian/brz/prototype-vaults-r1/ui-evidence/thebrain-changed-home.jpg>) showing central CHILD and parent PARENT. The Home tooltip was verified in the prior UI observation; the screenshot is evidence of the resulting thought/context, not a tooltip capture. The original fixture's fingerprint was also independently rechecked unchanged by the root.

| Controlled input | Bytes | SHA-256 |
| --- | ---: | --- |
| Original `brz/relationship-fixture.brz` | 5,059 | `53fd9fd22249a59875d3525774e1bb27c8b66830b3d84430b4ababdf0675ae6a` |
| Changed `brz/controlled-home-child.brz` | 6,976 | `aa29d7aa0afb687f8b4ffdd490220c3c2e198c729681083fe5065b3bb55dfbf0` |

**Observed in the source records:** both exports have the same Brain ID and therefore the same derived setting ID. Its `Value` changed from the UUID of PARENT to the UUID of CHILD. Among settings present in both exports, only numeric setting 20 changed its `Value`; sync/date metadata is not part of that comparison. PEER is the uniquely most recently activated thought in the changed export. CHILD has one ordinary parent, PARENT, and is not titled Home. ZIP CRCs and both recorded fingerprints passed.

Together, the native Home result and the changed source value establish the home semantics of this derived key for the observed format. The experiment distinguishes home from last activation, title, and parentlessness. It does not establish universal compatibility across TheBrain versions or guarantee the meaning of the same number in an unverified exchange format.

## Resolving the assigned vault target

Join the designated home UUID to the converter's source-ID-to-target assignment. Do not regenerate a filename independently from its source title: collisions, sanitization, and the accepted Home prefix must share the same assignment used by all internal links. The accepted root-level home note is a materialized target even when its source content is empty; its source role does not create new hierarchy edges.

The Review Vault record as initially generated can be joined read-only by archive label and source UUID. A has exactly one reserved target and a selected created note for its home. B has exactly one reserved target but is outside the selected slice and remains uncreated there. This is a prototype boundary, not authorization to omit the home note from a full migration. The accepted home presentation and native startup/bookmark checks belong to the [vault trial](vault-trial.md).

## Absent or invalid designation limits

Every inspected archive has one valid home setting. **Actual TheBrain fallback behavior when the setting is absent, duplicated, malformed, or points to a nonlive thought has not been observed.** No such fallback is inferred from documentation or graph topology.

The probe separately exercises in-memory altered copies of the synthetic record lists: removing the derived setting yields `absent`; replacing its value with an empty string yields `invalid_uuid_value`; using the nil UUID yields `nonlive_reference`. These exercise evidence detection only. They are not archives imported into TheBrain and do not establish its fallback behavior. The probe also distinguishes duplicate settings and duplicate thought identities.

Converter reporting, refusal, and explicit override policy remain decisions for [Choose the conversion and failure contract](../issues/05-conversion-contract.md). Preserve the original setting fields for traceability; do not silently claim a guessed root is the source Home.

## Reproduction and capture

[inspect_home_thought.py](inspect_home_thought.py) is a read-only investigation aid with aggregate stdout. Run it from its managed research worktree with Windows Python 3.14.8:

```powershell
.\.venv\Scripts\python.exe -B .scratch/brz-to-obsidian/research/inspect_home_thought.py --source-root 'C:\Users\stefa\projects\brz2obsidian' --controlled-after 'C:\Users\stefa\projects\brz2obsidian\brz\controlled-home-child.brz' --vault-record 'C:\Users\stefa\projects\brz2obsidian\brz\prototype-vaults-r1\Review Vault\migration-record.json'
```

The optional `--vault-record` checks prototype target assignment; omit it if that artifact is unavailable. With `--controlled-after`, the probe verifies the changed export's known fingerprint and checks the same source Brain, the PARENT-to-CHILD designation change, uniquely latest PEER activation, and the home thought's ordinary parent. It never prints real thought names, IDs, source text, or target paths.

The managed capture worktree is `C:\Users\stefa\.codex\worktrees\research-home-thought\brz2obsidian`, branch `codex/research-home-thought`. The final capture pointer and resolution are recorded in the research ticket. This is research for the specification, not production conversion code.
