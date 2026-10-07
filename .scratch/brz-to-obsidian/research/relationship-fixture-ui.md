# Controlled relationship fixture: UI observations

Observed on 2026-10-03 in the user's open TheBrain 15 window, Brain tab `CONTROLLED_EXPORT`. Supports [Verify hierarchy and default direction with a controlled export](../issues/07-relationship-fixture.md).

## Observed relationships

| Relationship | UI evidence |
| --- | --- |
| PARENT is parent of CHILD | With CHILD active, PARENT appears above it. The connection joins PARENT's bottom gate to CHILD's top gate. No arrowhead is visible on this connection. |
| CHILD has a jump relationship to PEER | PEER appears to the left of CHILD. The connection joins their side jump gates. No arrowhead is visible on the graph line. The link-properties panel shows endpoint names CHILD and PEER with a double-headed direction/navigation symbol between them. |
| CHILD points toward ARROW | ARROW appears below CHILD, connected through CHILD's bottom gate and ARROW's top gate. An arrowhead points toward ARROW. The link-properties panel shows CHILD at the left, ARROW at the right, and a right-pointing symbol between them. |

ARROW is shown as a directed child relationship, rather than the directed jump relationship originally requested. This is still useful fixture evidence: it exercises hierarchy placement together with an explicit arrow. The ordinary PEER jump separately exercises the default direction. The export can establish the field values for these observed cases; a directed-jump variant can be added later if needed.

The symbols above are observations, not a claim about the exported direction bitmask or the precise one-way flag. Those meanings must be checked against the export. No relationship properties were edited during inspection; only context menus and link-properties panels were opened and dismissed.

## Local screenshot evidence

- [Fixture overview](../../../tmp/legacy/brz/fixture-screenshots/fixture-overview.jpg)
- [Explicit arrow properties](../../../tmp/legacy/brz/fixture-screenshots/explicit-arrow-properties.jpg)

Screenshots are stored under the existing ignored `brz/` directory as local evidence. These observations alone do not establish stored A/B orientation or `Direction=-1` interpretation. The subsequent [export comparison](relationship-fixture-records.md) establishes orientation and the observed default sentinel, and identifies ARROW's exported direction as 1 with no one-way bit.
