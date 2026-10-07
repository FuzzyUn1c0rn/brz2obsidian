# Uncreated Obsidian targets and empty-thought coverage

Investigated 2026-10-03 for [Verify uncreated targets and empty-thought hierarchy coverage](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/59). This note supports the user's chosen preference for uncreated targets instead of empty Markdown files, shallow `Notes/` and `Attachments/` folders, and readable simple relationships. It records facts and limits; it does not select the final representation or implement a converter.

**Finding:** Standard Obsidian supports links to uncreated notes and can show those targets in Graph. An uncreated target cannot itself contain outgoing links or properties. Both real archives contain ordinary hierarchy relationships with two contentless endpoints, so references from content-bearing notes alone cannot preserve every hierarchy relationship. One tag in archive A also has actual note text.

## First-party Obsidian evidence

| Question | Evidence | Qualification |
| --- | --- | --- |
| Can a target exist as a link before its file exists? | **Documented:** create an internal link to a non-existing note; it appears in a muted color. [Link notes](https://obsidian.md/help/link-notes). | This is a reference to a future file, rather than a file containing an empty note. |
| Does Obsidian discover unresolved targets? | **Documented public API:** `MetadataCache.unresolvedLinks` maps each source file to unknown destinations and their reference counts; `resolvedLinks` maps sources to destination files. [Obsidian API declarations](https://github.com/obsidianmd/obsidian-api/blob/master/obsidian.d.ts#L4258-L4269). | The public declarations document the cache contract, not the internal resolver implementation. |
| Can Graph show them? | **Documented:** Graph's **Existing files only** filter controls whether non-existing targets are shown. Graph circles are notes; lines are internal links. Graph arrows show link direction. [Graph view](https://obsidian.md/help/plugins/graph). | Visibility depends on settings. The documented graph represents links, without a parent/child or jump edge type. |
| What happens when the user follows an uncreated link? | **Documented:** the beginner guide creates the target note by Ctrl-clicking the link (Cmd-click on macOS). [Link notes](https://obsidian.md/help/link-notes). | The file then exists. This preference does not prevent the user from creating it later. Exact Reading view and Graph-click behavior remains a trial item. |
| Where is a qualified target created? | **Documented:** folder paths begin at the vault root and use `/` on Windows. A link to a missing note creates it at the supplied folder path. [Internal links](https://obsidian.md/help/links). **Documented:** an explicit folder path overrides **Default location for new notes**. [Settings](https://obsidian.md/help/settings#Default%20location%20for%20new%20notes). | The synthetic example `[[Notes/Empty]]` therefore specifies `Notes/Empty.md` at the vault root. Test the installed app with `Notes/` already present. Missing-folder creation is not established here. |
| What is known about duplicate names? | **Documented:** **Shortest path when possible** generates the shortest unique file path; **Absolute path in vault** uses the full root-based path. [Settings](https://obsidian.md/help/settings#New%20link%20format). **Documented public API:** `fileToLinktext` uses the filename if unique and the full path otherwise; `getFirstLinkpathDest` returns a best match or null. [Obsidian API declarations](https://github.com/obsidianmd/obsidian-api/blob/master/obsidian.d.ts#L4231-L4257). | **Inference:** a bare basename cannot safely identify distinct thoughts with colliding names. A unique qualified target distinguishes paths, but two source thoughts assigned the same `Notes/<name>.md` still collide. Exact fallback, tie-breaking and case comparison require a trial. |
| Do incoming links become backlinks after creation? | **Documented:** the guide creates an absent target and then navigates from its **Linked mentions** backlink to the referring note. [Link notes](https://obsidian.md/help/link-notes). The Backlinks plugin shows incoming internal links and their context for the active note. [Backlinks](https://obsidian.md/help/plugins/backlinks). | Backlink behavior for a target that is still absent, exact refresh timing after creation, and duplicate-target resolution remain trial items. |

The internal-link documentation also permits custom display text, such as `[[Notes/Empty|Readable label]]`, and warns about special link characters. **Inference:** display text and target identity are separate; giving two references different labels does not create two target files. [Internal links](https://obsidian.md/help/links).

## Inherent limits, separated from UI uncertainty

**Inference from documented storage:** properties are YAML stored at the top of a file. An uncreated target therefore has no place for its own properties, original ID, aliases, tags, source dates, label, body text or attachment list. Such information can be retained elsewhere, but it is not metadata on that target. An inline link label is not a stored alias. [Properties](https://obsidian.md/help/properties), [Aliases](https://obsidian.md/help/aliases).

**Inference from documented link indexing:** outgoing links are links in the active note, and the link cache records a source file for each resolved or unresolved destination. A missing target has no source file in which to place its own outgoing links. Incoming links can refer to it; they cannot make it own a link to another target. [Outgoing links](https://obsidian.md/help/plugins/outgoing-links), [Obsidian API declarations](https://github.com/obsidianmd/obsidian-api/blob/master/obsidian.d.ts#L4258-L4269).

**Hierarchy consequence:** if synthetic `Empty parent` and `Empty child` are both uncreated, writing links to both in a third note produces references from that third note. It does not create a native Graph edge from parent to child. A readable list or hierarchy record elsewhere can retain the source relationship and context, while its Graph edges will reflect that record's links. Likewise, an isolated absent thought needs a reference somewhere to be represented at all. These are storage/graph consequences, not unresolved UI behaviors. [Graph view](https://obsidian.md/help/plugins/graph), [Obsidian API declarations](https://github.com/obsidianmd/obsidian-api/blob/master/obsidian.d.ts#L4258-L4269).

Simple links and backlink context can preserve readable hierarchy meaning, but the native graph does not document typed hierarchy edges. The user has accepted loss of explicit arrow and one-way details; this research does not reopen that decision.

## Local aggregate inspection of the two real archives

**Observed:** [inspect_uncreated_targets.py](inspect_uncreated_targets.py) reads the ZIPs and JSON records in memory using installed Windows Python **3.14.8**. Nothing is extracted, modified, uploaded or fetched from an external reference. It emits counts and archive checksums only. Archive A/B are the same real inputs and order as [BRZ preservation evidence](brz-preservation.md); their measured SHA-256 values match that inventory. The repository also contains small fixtures: the real inputs were selected by the inventory byte sizes, not by taking the first two BRZ files.

Definitions used in the counts:

- **Ordinary thought:** `Kind=1`. Tags (`Kind=4`) are counted separately.
- **No nonblank note text:** no physical note with non-whitespace text after UTF-8 BOM decoding. Empty `Notes.md` placeholders count as empty, including those with `NoteType=0`.
- **No substantive content:** no nonblank thought-note text, no archived non-note internal file/image, and no external file/URL/directory reference. Decorative icon attachments and labels/colors are reported separately, rather than automatically requiring a content note. Universal identity/date metadata does not count as substantive content.
- **Strictly undecorated empty:** additionally has no other attachment record, including icons or missing-payload records, and no nonblank label. This supplementary definition makes the effect of decoration explicit.
- **Ordinary hierarchy/jump relationship:** `Kind=1`, `Meaning=1`, both endpoint thoughts `Kind=1`; hierarchy `Relation=1` or `2`, jump `Relation=3`. Arrow settings do not change this classification. An item is isolated only when it has no incident live relationship of any meaning.

| Ordinary-thought content measure | A | B |
| --- | ---: | ---: |
| Ordinary thoughts | 63 | 58 |
| With nonblank thought-note text | 39 | 31 |
| Without nonblank thought-note text | 24 | 27 |
| Empty text, with an empty physical note placeholder | 3 | 3 |
| Empty text, with external references | 4 | 3 |
| Empty text, with archived non-note internal files/images (excluding icons) | 0 | 6 |
| Empty text, with icon files | 1 | 4 |
| Empty text, with nonblank source labels | 1 | 0 |
| Empty text, with explicit foreground-color field | 0 | 0 |
| Empty text, with missing-payload attachment metadata | 0 | 6 |
| No substantive content | **20** | **18** |
| Strictly undecorated empty | 18 | 18 |

**Observed detail:** A's four empty-text external-reference owners each have a URL attachment. B's three likewise have URLs; its six empty-text internal-file owners each have an archived PDF and an absent type-15 attachment record. B's four icon-bearing owners overlap its other-content owners. Missing type-15 payloads therefore add no additional contentless owners; their meaning remains unresolved in [BRZ preservation evidence](brz-preservation.md). The row counts overlap and must not be summed. Among A's 20 thoughts without substantive content, one has an icon and a different one has a label.

| Relationships and isolation | A | B |
| --- | ---: | ---: |
| Hierarchy relationships with both ordinary endpoints lacking nonblank note text | 11 | 23 |
| Jump relationships with both ordinary endpoints lacking nonblank note text | 0 | 0 |
| Hierarchy relationships with both ordinary endpoints lacking substantive content | **7** | **4** |
| Distinct ordinary endpoints in those contentless hierarchy relationships | 10 | 6 |
| Jump relationships with both ordinary endpoints lacking substantive content | 0 | 0 |
| Hierarchy relationships with both endpoints strictly undecorated empty | 6 | 4 |
| Isolated ordinary thoughts without substantive content | 0 | 0 |
| Isolated empty items across all thought kinds | **1 tag** | 0 |

These measured empty-to-empty relationships are the concrete coverage gap for an approach that writes relationship lists only in content-bearing endpoint files. The evidence requires some readable place for those relationships; it does not select that place. No isolated empty ordinary thought is exercised in these inputs, but one isolated empty tag is.

| Tag content | A | B |
| --- | ---: | ---: |
| Tags | 12 | 0 |
| Tags with nonblank thought-note text | **1** | 0 |
| Tags with physical note files | 1 | 0 |
| Tags with other attachment records or external references | 0 | 0 |

The content-bearing tag is different from the isolated empty tag. **Inference:** representing every source tag solely as an Obsidian tag would need another place for that one tag's note content. Whether it receives a note or another readable representation is a later design decision.

Reproduce from the repository root without printing private source names:

```powershell
$archiveA = @(Get-ChildItem -LiteralPath 'brz' -Filter '*.brz' -File | Where-Object Length -eq 45016149)
$archiveB = @(Get-ChildItem -LiteralPath 'brz' -Filter '*.brz' -File | Where-Object Length -eq 153693431)
if ($archiveA.Count -ne 1 -or $archiveB.Count -ne 1) { throw 'Real archive selection is ambiguous.' }
.\.venv\Scripts\python.exe .scratch/brz-to-obsidian/research/inspect_uncreated_targets.py $archiveA[0].FullName $archiveB[0].FullName
```

## Behaviors to verify in the later synthetic vault trial

No Obsidian UI automation was performed for this ticket. Record the installed app version and core settings; use synthetic data only.

1. From a note in `Notes/`, link to `[[Notes/Empty]]`, with `Notes/` already present. Verify muted link appearance, Graph visibility with **Existing files only** toggled, exact file placement when created, and backlinks after creation. Repeat with each default-new-note location to verify the explicit path override.
2. Repeat with a folder-qualified Markdown link and a current-file-relative Markdown link. The documentation's root-based examples do not settle every relative/fallback case described in [the prior representation note](obsidian-representation.md#path-bases-documented-examples-versus-unverified-resolution).
3. Add existing duplicate basenames in different folders and unresolved distinct qualified targets. Test bare-name ambiguity, whether an existing same-basename file shadows a qualified absent target, case variants, and whether repeated qualified references combine as expected. Do not assume tie-breaking from the API's phrase "best match."
4. Check Reading view and Graph clicks, missing-folder behavior, unresolved-target backlink visibility, and cache refresh after creation. These are more specific than the documented Ctrl-click beginner flow.
5. Show two unresolved targets in a readable third-note hierarchy record; confirm that the displayed context is usable and that native Graph connections originate at the record. Confirm any eventually selected representation covers the measured 7/4 empty-to-empty hierarchy relationships and the isolated empty tag.

This evidence covers the observed two real format-5 exports and the current first-party documentation. It does not establish general behavior for every BRZ note encoding, undocumented attachment type, or Obsidian resolver edge case.
