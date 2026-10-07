# Extended controlled relationship fixture

Observed and exported on 2026-10-03 in TheBrain 15; inspected read-only with Windows Python 3.14.8. Supports [Verify reverse arrows and one-way relationship behavior](../issues/08-reverse-and-one-way-evidence.md). The user authorized edits to this synthetic Brain. No real Brain was edited.

## Input and preservation checks

- Final archive: [relationship-fixture-extended.brz](../../../tmp/legacy/brz/relationship-fixture-extended.brz), 6,852 bytes.
- SHA-256: `c8b06e3da9e96c289be2ba4cb4741d3075bc390b71a2cd235605c320404e3a27`.
- Exchange format 5; eight thoughts (seven ordinary and one system), seven relationships, no attachment payloads. ZIP CRC checks passed.
- The original [relationship-fixture.brz](../../../tmp/legacy/brz/relationship-fixture.brz) remains byte-for-byte unchanged, with SHA-256 `53fd9fd22249a59875d3525774e1bb27c8b66830b3d84430b4ababdf0675ae6a`.
- All four original relationship records match except for `SyncSentId` bookkeeping. Original thought IDs, names, kinds, and other content fields survive; only sync bookkeeping, activation timestamps, and CHILD's display-modification timestamp changed.
- An intermediate arrow-only export is retained locally as `brz/relationship-fixture-arrow-only.brz`. It is not the final acceptance fixture.

The [verification script](inspect_relationship_fixture.py) checks the full original relationship records except sync bookkeeping, the permitted thought-metadata differences, endpoint integrity, unique records/names, and all expected relationship signatures. Run from the repository root:

```powershell
.\.venv\Scripts\python.exe .scratch/brz-to-obsidian/research/inspect_relationship_fixture.py
```

## Controls and resulting records

Added REVERSE_ARROW, ONE_WAY_FORWARD, and ONE_WAY_REVERSE by dragging from CHILD's jump gate into empty graph space. Link Properties shows CHILD as its left endpoint and each new thought as its right endpoint. Ordinary clicks on the central direction button cycle through default, forward arrow, and reverse arrow. **Right-clicking that button exposes a separate `One Way` option.** Selecting it adds a bar to the direction symbol. This is distinct from selecting a plain arrow.

All ordinary relationships below have `Kind=1`, `Meaning=1`, and no custom link type.

| Endpoint A | Endpoint B | Relation | Direction | Observed meaning |
| --- | --- | ---: | ---: | --- |
| PARENT | CHILD | 1 | -1 | Original default parent/child relationship. |
| CHILD | PEER | 3 | -1 | Original default jump, with no explicit arrow. |
| CHILD | ARROW | 1 | 1 | Original child relationship with an A→B arrow; One Way is absent. |
| CHILD | REVERSE_ARROW | 3 | 3 | Jump with an arrow pointing B→A; One Way is absent. |
| CHILD | ONE_WAY_FORWARD | 3 | 5 | Jump with A→B arrow and the explicit One Way option enabled. |
| CHILD | ONE_WAY_REVERSE | 3 | 7 | Jump with B→A arrow and the explicit One Way option enabled. |

The system relationship to PARENT remains `Kind=1`, `Relation=1`, `Meaning=6`, `Direction=-1`. This investigation does not establish its purpose.

The new observations corroborate the [first-party direction flags already collected](brz-preservation.md): bit 1 directed, bit 2 backward, bit 4 one-way. Value 3 is B→A without one-way, 5 is A→B with one-way, and 7 is B→A with one-way. The negative default sentinel remains a separate case. No value 0 or custom-type default was exercised.

## Navigation and visibility observations

The One Way option affects which neighbor normally appears in the Plex; it is not merely an arrow decoration.

- From CHILD, ONE_WAY_FORWARD appears and can be clicked. After visiting PARENT and reopening ONE_WAY_FORWARD through search, CHILD does not appear in that thought's graph.
- After opening ONE_WAY_REVERSE through search from ONE_WAY_FORWARD, CHILD appears with the arrow pointing toward CHILD. After visiting PARENT and then CHILD, ONE_WAY_REVERSE does not appear in CHILD's graph.
- REVERSE_ARROW remains visible from CHILD despite its arrow pointing toward CHILD. A plain backward arrow does not produce the same neighbor suppression as the backward one-way setting.
- Immediately navigating from CHILD to ONE_WAY_FORWARD kept CHILD visible in green as the previous thought, even with One Way enabled. Independent navigation was therefore necessary to distinguish the relationship's normal visibility from navigation context. One Way does not remove either endpoint from search or history.

These are observed Plex behaviors in this test Brain. They do not establish every view's behavior, access restrictions, or custom-type inheritance. Source relationship meaning must remain distinguishable from the navigation behavior available in Obsidian; the vault-model ticket chooses its representation.

## Local screenshot evidence

Screenshots and archives remain under ignored `brz/`. These links are local evidence, not published source content.

- [Reverse-arrow properties](../../../tmp/legacy/brz/fixture-screenshots/reverse-arrow-properties.jpg).
- [Reverse One Way selected in its context menu](../../../tmp/legacy/brz/fixture-screenshots/one-way-option-selected.jpg).
- [Forward one-way properties](../../../tmp/legacy/brz/fixture-screenshots/one-way-forward-properties.jpg).
- [Reverse one-way properties](../../../tmp/legacy/brz/fixture-screenshots/one-way-reverse-properties.jpg).
- [Forward destination opened independently, with CHILD absent](../../../tmp/legacy/brz/fixture-screenshots/one-way-forward-independent-view.jpg).
- [Reverse destination opened independently, with CHILD visible](../../../tmp/legacy/brz/fixture-screenshots/one-way-reverse-independent-view.jpg).
- [CHILD opened through PARENT, with reverse one-way thought absent](../../../tmp/legacy/brz/fixture-screenshots/extended-child-independent-view.jpg).

## Acceptance cases for the later specification

Use this table as ground truth for interpreting source relationship fields. The user later accepted simplifying arrow/one-way presentation in [Choose note identity, relationships, and vault layout](../issues/03-vault-model.md): hierarchy must survive, and ordinary connections should be easy to use. These observations do not require emulating TheBrain's direction or visibility controls in the vault. Deliberate uncreated targets for empty thoughts are also accepted; suppressing a thought merely because TheBrain hides it in one navigation context remains distinct from that policy. Any retained archival direction fields can be checked against this fixture without adding them to everyday note navigation.
