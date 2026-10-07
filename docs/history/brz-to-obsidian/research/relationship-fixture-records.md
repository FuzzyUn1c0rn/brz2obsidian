# Controlled relationship fixture: exported records

Inspected read-only on 2026-10-03 with Windows Python 3.14.8. Supports [Verify hierarchy and default direction with a controlled export](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/57). Compare these records with the [saved UI observations](relationship-fixture-ui.md).

## Input

- Archive: `brz/relationship-fixture.brz`, created by the user in TheBrain 15.
- Size: 5,059 bytes.
- SHA-256: `53fd9fd22249a59875d3525774e1bb27c8b66830b3d84430b4ababdf0675ae6a`.
- Exchange format: 5. ZIP CRC validation passed.
- Five thought records and four relationship records. Each expected synthetic name occurs exactly once. Only the synthetic names are reproduced here.

## Comparison with the UI

All three ordinary fixture relationships have `Kind=1` and `Meaning=1`.

| Endpoint A | Endpoint B | Relation | Direction | Observed UI behavior |
| --- | --- | ---: | ---: | --- |
| PARENT | CHILD | 1 | -1 | PARENT above CHILD, connected through hierarchy gates, with no visible arrowhead. |
| CHILD | PEER | 3 | -1 | PEER connected through the jump gates, with no visible arrowhead; its properties display a double-headed navigation/direction symbol. |
| CHILD | ARROW | 1 | 1 | ARROW is a child of CHILD; the visible arrow points toward ARROW, and properties show a right-pointing symbol from CHILD toward ARROW. |

The extra system relationship has `Kind=1`, `Relation=1`, `Meaning=6`, `Direction=-1` and connects a system item to PARENT. It must be distinguished from the three ordinary relationships; this fixture does not establish its user-facing purpose.

## Established interpretations and limits

1. For the observed ordinary `Relation=1` records, **A is the parent and B is the child**. This agrees with the observed endpoint gates and thought positions. This clears the earlier orientation uncertainty for the supplied format-5 cases.
2. `Relation=3` represents the observed jump relationship. Stored A/B order alone does not establish an arrow: the default CHILD–PEER jump has `Direction=-1` and no visible arrow.
3. `Direction=-1` is the **default sentinel**, matching the default hierarchy and jump presentation without an explicit arrow in this test Brain. Handle the sentinel before any bitmask decoding; negative one would otherwise appear to have every bit set. The fixture does not establish how inheritance from a custom link type or other settings would affect this sentinel.
4. `Direction=1` corresponds to the observed explicit A→B arrow. The [documented direction flags](brz-preservation.md) distinguish directed bit 1, backward bit 2, and one-way bit 4. This fixture's ARROW relationship has only bit 1, so it is **directed without the one-way flag**. It must not be described as a verified one-way relationship. The real smaller archive separately exercises flags 5 and 7; their flag meanings remain grounded in the cited first-party documentation.

The fixture is sufficient for its parent/child orientation and default-direction questions despite the directed child replacing the originally requested one-way jump. It also supplies an additional observed direction value. Custom-type defaults and one-way UI/navigation behavior were unexercised in this original fixture. The later [extended fixture](extended-relationship-fixture.md) separately verifies reverse-arrow and explicit one-way jumps and their Plex behavior; custom-type defaults remain unverified.

## Acceptance cases to carry into the specification

- Parent/child rendering uses PARENT as the parent of CHILD, without interpreting an explicit arrow as the definition of hierarchy.
- Jump rendering preserves CHILD–PEER as a nonhierarchical connection and applies no forced arrow to the default sentinel.
- Source interpretation distinguishes CHILD→ARROW from its child relationship; the one-way flag remains absent. The later [vault-model discussion](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/53) accepts simplifying direction presentation while retaining hierarchy, so this does not require a separate directional mechanism in everyday notes.
- Direction handling checks the sentinel separately and retains the source flag value. Any unexercised inheritance behavior is covered by the chosen supported-feature boundary or requires further evidence.

## Reproduction

Read `thoughts.json` and `links.json` from the ZIP using BOM-aware UTF-8 and per-line JSON parsing. Resolve each link's `ThoughtIdA`/`ThoughtIdB` against thought IDs, then compare the four expected synthetic names and the fields `Kind`, `Relation`, `Meaning`, and `Direction`. Do not rely on collection ordering or UUID sort order. Validate CRCs with Python's `zipfile.ZipFile.testzip()` and fingerprint the unchanged archive with SHA-256.
