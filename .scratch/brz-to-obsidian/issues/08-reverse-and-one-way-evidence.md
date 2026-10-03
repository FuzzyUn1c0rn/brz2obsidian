# Verify reverse arrows and one-way relationship behavior

Status: resolved
Type: task
Labels: wayfinder:task
Parent: [Find the route from a BRZ archive to an Obsidian vault](../map.md)
Blocked by: none
Assignee: /root

## Question

Extend the controlled TheBrain 15 fixture with reverse-arrow and explicitly one-way jump relationships, then compare their UI behavior with a separate export. This provides observed evidence for direction flags beyond the default and forward-arrow cases already established.

Preserve the original PARENT/CHILD/PEER/ARROW cases. Add distinct synthetic thoughts for a reverse arrow and one-way direction cases. Inspect the available direction controls before choosing settings, record the actual relationship and navigation behavior, and export the extended fixture under a new BRZ filename. Do not assume that an arrow is itself a one-way relationship.

Link local screenshots and a field comparison as evidence assets. Resolve once the new field values and observed UI behavior are recorded, including any unexercised limits.

## Comments

- 2026-10-03: The user explicitly authorized extending the controlled Brain in the application. The previous fixture investigation remains resolved; this task covers the additional evidence.

## Answer

Resolved on 2026-10-03. Extended the synthetic CONTROLLED_EXPORT Brain with REVERSE_ARROW, ONE_WAY_FORWARD, and ONE_WAY_REVERSE. Saved a separate `brz/relationship-fixture-extended.brz`, local screenshots, and a read-only verification script. [Extended fixture evidence](../research/extended-relationship-fixture.md) contains the fingerprint, controls, record table, navigation observations, checks, and limits.

- Reverse arrow without One Way stores `Direction=3` (B→A); forward One Way stores 5 (A→B), and reverse One Way stores 7 (B→A). All three added relationships are ordinary jumps (`Relation=3`).
- One Way is enabled through a right-click on the central direction button in Link Properties. Ordinary clicks alone cycle default/forward/reverse arrow states.
- Independently opening the thoughts confirms directional neighbor visibility. Direct arrival can keep the preceding thought visible, so that context must not be mistaken for the relationship's normal visibility. Both thoughts remain searchable.
- The baseline archive is unchanged. All original relationship fields remain identical except sync bookkeeping; the expected thought-metadata changes are recorded. Both archives pass CRC checks.
- Carry the verified direction cases into the vault design and acceptance checks. Custom link-type defaults, direction value 0, and non-Plex view behavior remain unexercised; this investigation does not claim them.
