# Verify hierarchy and default direction with a controlled export

Status: resolved
Type: task
Labels: wayfinder:task
Parent: [Find the route from a BRZ archive to an Obsidian vault](../map.md)
Blocked by: none
Assignee: /root

## Question

Obtain a BRZ export with known parent/child and jump relationships so that stored A/B hierarchy orientation and the common `Direction=-1` value can be verified against TheBrain's UI before choosing user-facing labels.

The [archive research](../research/brz-preservation.md) documents explicit direction flags, but the primary sources inspected do not establish these two export-specific details. The fixture is a fact-gathering prerequisite, not a vault prototype or a request to alter the real Brains.

## Human checklist

1. Create a small separate Brain with thoughts named `PARENT`, `CHILD`, `PEER`, and `ARROW`.
2. Make `PARENT` the parent of `CHILD`. Keep this hierarchy relationship's direction settings at their defaults.
3. Make a default jump link between `CHILD` and `PEER`. Record what the UI displays for direction and, if available, the link's direction setting.

   Here, "default" means an ordinary Jump relationship with its link properties left untouched. Drag from `CHILD`'s side jump gate into empty graph space and name the new thought `PEER`. If `PEER` already exists and is visible, drag from that gate onto `PEER`. The current [official Thoughts and Links tutorial](https://www.thebrain.com/support/tutorials#Thoughts-and-Links) covers these relationships. Earlier F8/main-menu guidance came from a version-12 guide and was not verified for this installation. In TheBrain 15, inspect **Settings → User → Keyboard**, with **Only Show Assigned** enabled, for the actual configured shortcuts, as explained by [TheBrain staff](https://forums.thebrain.com/post/problems-with-tb15-windows-shortcuts-dont-work-13864925).

4. Make a jump link between `CHILD` and `ARROW` with an explicit one-way arrow pointing from `CHILD` to `ARROW`.
5. Export this Brain as a BRZ into `brz/`, preferably named `relationship-fixture.brz`, and confirm the intended relationships and displayed default direction.

An alternative is to identify these same known relationships, their thought names, and their displayed direction in one existing export. That can resolve this task if the observations unambiguously establish the same evidence; a separate fixture is easier to reproduce.

## Agent follow-up

Claim the ticket before inspecting the new evidence. Read the export in place, match the synthetic thought names to their records, and compare endpoint order, relation fields, and direction values with the stated UI behavior. Record the fixture fingerprint and aggregate conclusions; add a focused regression case to the later specification's acceptance checks. Update the research interpretation without treating a negative sentinel as a bitmask.

Resolve only after stored hierarchy orientation and default direction are established. If observations remain ambiguous, record the exact additional observation needed.

## Comments

- 2026-10-03: Created after investigating both real exports. A concise fixture request was sent to the user while the research results were integrated.
- 2026-10-03: The user chose to create the controlled export and is working on it. After the desktop restart, `python` still resolves to Python 3.14.8; PATH now finds its launcher in `C:\Users\stefa\AppData\Local\Python\bin` before the WindowsApps alias. The fixture has not yet been added.
- 2026-10-03: The user clarified that the application is TheBrain 15. Updated UI guidance to avoid assuming older documented keyboard/menu bindings; the required fixture relationships are unchanged.
- 2026-10-03: The user reports successfully creating the jump link to `PEER`. The controlled export and its displayed direction have not yet been inspected.
- 2026-10-03: The user authorized inspection and screenshots of the open test Brain in TheBrain 15. Claimed to inspect the live fixture; resolution still requires comparison with the exported records.
- 2026-10-03: Inspected `CONTROLLED_EXPORT` and saved [UI observations and local screenshot links](../research/relationship-fixture-ui.md). PARENT/CHILD hierarchy and the PEER jump are visible; ARROW is a directed child relationship, which is useful for the evidence task despite differing from the originally requested directed jump. No properties were edited. Released the claim while waiting for the fixture BRZ; reclaim before comparing records with these observations.
- 2026-10-03: The user added `brz/relationship-fixture.brz` (5,059 bytes). Reclaimed to compare its records with the saved UI observations.

## Answer

Resolved on 2026-10-03. The user created the controlled Brain and export; the assistant inspected the live UI, saved local screenshots, and compared the ZIP records read-only. [Exported-record evidence](../research/relationship-fixture-records.md) holds the fingerprint, field table, caveats, and acceptance cases; [UI observations](../research/relationship-fixture-ui.md) hold the visual ground truth.

- The observed ordinary child relationships store parent A / child B. The PEER jump stores `Relation=3`.
- The default hierarchy and jump store `Direction=-1`, matching no explicit visible arrow in this fixture. Treat this as a sentinel before decoding flags; custom link-type inheritance remains unexercised.
- The CHILD→ARROW child relationship stores `Direction=1`, confirming explicit A→B direction independently of hierarchy. It lacks the separate one-way bit, so the original one-way-jump request was not reproduced; that does not prevent resolution of this task's orientation and default-direction questions.
- The fixture's CRC check passed. Carry its three ordinary relationship cases into the later specification; [Choose note identity, relationships, and vault layout](03-vault-model.md) is now unblocked.
