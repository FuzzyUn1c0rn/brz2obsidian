# Accepted specification coverage

Status: resolved
Approved: 2026-10-06

This maps every numbered requirement in the accepted [specification](spec.md) to
the approved [ticket breakdown](ticket-breakdown.md). Numbers here are local to
this implementation effort, not the Wayfinder map. Individual acceptance
criteria are linked from the breakdown and the implementation index.

## Ticket key

| Ticket | Title |
| --- | --- |
| 01 | Exclude forgotten thoughts throughout inspection and conversion |
| 02 | Display owned images when an ordinary thought note is absent |
| 03 | Keep category dashboards usable through missing type notes and icons |
| 04 | Preserve ordinary-to-category hierarchy in both directions |
| 05 | Prove the combined conversion and publication guarantees |
| 06 | Extend the independent raw-source audit to the new conversion policy |
| 07 | Audit complete preservation across all four original archives |
| 08 | Verify actual converted vaults in native Obsidian |
| 09 | Deliver the reviewed release after actual-vault user acceptance |

## User Stories

| Stories | Delivery/proof tickets |
| --- | --- |
| 1–11 | 02, 06, 07, 08 |
| 12–18 | 01, 02, 05, 06, 07, 08 |
| 19–20 | 02, 03, 05, 06, 07 |
| 21–26 | 03, 05, 06, 07, 08 |
| 27–31 | 03, 04, 05, 06, 07, 08 |
| 32–39 | 01, 05, 06, 07 |
| 40–46 | 02, 03, 05, 06, 07, 08 |
| 47–48 | 02, 03, 05, 06, 07 |
| 49–50 | 01, 02, 03, 04, 05, 06, 09 |
| 51–53 | 05, 06, 07 |
| 54–57 | 01, 04, 05, 06, 07 |
| 58–59 | 02, 03, 05, 06, 07, 08 |
| 60–62 | 01, 02, 03, 04, 05, 06, 09 |
| 63–65 | 06, 07 |
| 66 | 08 |
| 67 | 09 |
| 68 | 02, 06, 07, 09 |
| 69–70 | 01, 02, 03, 04, 05, 06, 07, 08, 09 |

## Implementation Decisions

| Decisions | Delivery/proof tickets |
| --- | --- |
| 1–3 | 01, 02, 03, 04, 05, 06, 07, 09 |
| 4–7 | 01, 04, 05, 06, 07 |
| 8 | 01, 02, 05, 06, 07, 08 |
| 9–12 | 02, 05, 06, 07, 08 |
| 13–14 | 03, 05, 06, 07, 08 |
| 15–16 | 03, 04, 05, 06, 07, 08 |
| 17–18 | 02, 03, 05, 06, 07, 08 |
| 19–20 | 01, 02, 03, 04, 05, 06, 07 |
| 21–23 | 01, 02, 03, 04, 05, 06, 07, 08, 09 |
| 24 | 06, 07, 08, 09 |
| 25 | 01, 02, 03, 04, 05, 06, 07, 08, 09 |

## Testing Decisions

| Decisions | Delivery/proof tickets |
| --- | --- |
| 1–3 | 01, 02, 03, 04, 05, 06, 09 |
| 4–6 | 02, 03, 05, 06 |
| 7 | 01, 04, 05, 06, 07 |
| 8 | 03, 04, 05, 06, 07, 08 |
| 9 | 02, 03, 05, 06, 07, 08 |
| 10–11 | 01, 02, 03, 04, 05, 06 |
| 12–13 | 06, 07 |
| 14–16 | 06, 07, 08, 09 |
| 17 | 01, 02, 03, 04, 05, 06, 07, 08, 09 |
| 18 | 08, 09 |
| 19 | 09 |
| 20 | Confirmed by the user on 2026-10-06; all tickets retain these boundaries |

## Scope and proof distinctions

The unaltered original Management & Leadership archive is mandatory and cannot
be replaced by a recovery export; all three earlier pinned originals remain
mandatory for cumulative acceptance. Recovery exports are different source
identities. Present Markdown always wins; no syntax repair,
inferred missing prose, invented authored order, card-to-icon conversion, routine
TheBrain retrieval or blanket state-3 support is introduced. Default exclusion
never becomes an output exclusion ledger or a keyword/pixel eraser.

Supplied Documents, generated presentations and missing-source facts stay
distinct. Measured inspect source facts are not publication receipts. The
source-free checker is a read-only convention tool, not a preservation oracle.
Complete original-input audits, strategically sampled native actual-output review and the actual user
verdict are separate mandatory gates. Private source identities/assets/vaults
remain local; public findings contain aggregate evidence and honest limits.

The user's 2026-10-06 implementation steering changes visual-review breadth to
strategic sampling, with explicit distinct-behavior/special-case coverage and
recorded limits. Full automated preservation obligations and requirement mapping
remain unchanged. See [the sampling policy](../../docs/testing.md#visual-sampling-policy).
