# Verify uncreated targets and empty-thought hierarchy coverage

Status: resolved
Type: research
Labels: wayfinder:research
Parent: [Find the route from a BRZ archive to an Obsidian vault](../map.md)
Blocked by: none
Assignee: /root/uncreated_targets

## Question

What can standard Obsidian represent using links to files that do not yet exist, and what needs special handling when migrating empty TheBrain thoughts without creating note files?

Verify against first-party sources: link discovery/Graph representation, clicking to create a target, explicit folder-path placement, duplicate-name ambiguity, backlinks after creation, and what metadata or outgoing relationships cannot exist on an uncreated target. Distinguish documented behavior from inference and behavior that must be tested in the vault trial.

Read both real archives locally and report aggregate counts only: ordinary thoughts without nonblank note text, other content associated with those thoughts, hierarchy/jump relationships whose endpoints both lack content, and isolated empty thoughts. Also identify whether tags have content requiring a note. Do not reproduce private titles, IDs, paths within attachments, or note text, and do not upload source data.

Capture findings in a single research note. This informs the still-open vault representation; it does not choose that representation or implement a converter.

## Comments

- 2026-10-03: The user selected uncreated note links for empty thoughts and accepted simplifying directional relationships. Evidence gathering supports that preference and the requirement to preserve hierarchy.
- 2026-10-03: Completed first-party documentation research and read-only aggregate inspection with Python 3.14.8. No private source content was published or uploaded; no Obsidian UI trial or production implementation was performed.

## Answer

See [Uncreated Obsidian targets and empty-thought coverage](../research/uncreated-targets.md) and its [reproducible aggregate inspection script](../research/inspect_uncreated_targets.py).

Obsidian documents uncreated links, Graph visibility, Ctrl-click creation at explicit vault-root folder paths, and backlinks after creation. First-party API declarations corroborate source-file-based unresolved-link indexing and path disambiguation. Exact resolver precedence, unresolved backlinks, Markdown path variants, missing folders and installed-app click behavior remain explicit synthetic vault-trial items.

Real archive A/B have 24/27 ordinary thoughts without nonblank note text, but 4/9 of those have substantive external references or local files. With icon decoration and labels counted separately, 20/18 ordinary thoughts lack substantive content. There are **7/4 ordinary hierarchy relationships with both endpoints in that group**, and no such jump relationships. An absent target cannot own an outgoing link or properties; those empty-to-empty relationships need readable context elsewhere if both endpoints stay uncreated.

Neither real archive has an isolated empty ordinary thought. A has one isolated empty tag and a different tag with actual note text, so the chosen tag representation needs to account for both. The note distinguishes substantive emptiness from the stricter no-decoration count and states the inspection limits. The evidence is sufficient for the next representation and vault-trial decisions; it does not choose a final design.
