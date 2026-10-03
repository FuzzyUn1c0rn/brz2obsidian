# Quantify creating parents for uncovered hierarchy relationships

Status: resolved
Type: research
Labels: wayfinder:research
Parent: [Find the route from a BRZ archive to an Obsidian vault](../map.md)
Blocked by: 09
Assignee: /root/uncreated_targets

## Question

How many additional ordinary-thought note files would the user's proposal require in the two real archives: if neither endpoint of a parent/child relationship otherwise has a note file, create the parent so the relationship can appear in an endpoint's Parents or Children list?

Use the substantive-content criterion from [Verify uncreated targets and empty-thought hierarchy coverage](09-uncreated-target-evidence.md). Inspect the existing archives locally and emit aggregate counts only. Count distinct parents among initially uncovered edges, then examine whether a parent created for one edge also covers other edges. Show whether input order changes a naive sequential strategy and quantify small-set coverage alternatives without selecting a production algorithm. Use synthetic examples for explanation and preserve the distinction between source hierarchy orientation and arrow direction.

This research informed the representation choice subsequently accepted in [Choose note identity, relationships, and vault layout](03-vault-model.md). It supplies evidence rather than production implementation.

## Comments

- 2026-10-03: User clarified the proposal applies when **neither** endpoint has a note, rather than to every parent. The active design discussion is evaluating this alternative to a shared hierarchy index.
- 2026-10-03: Completed local aggregate subset/permutation analysis using Python 3.14.8. No source content was exposed or uploaded, no destination files were created, and no production algorithm was selected.

## Answer

See [Creating parent notes for uncovered hierarchy relationships](../research/parent-materialization.md) and its [bounded diagnostic script](../research/inspect_parent_materialization.py).

Archive A's seven initially uncovered ordinary hierarchy relationships involve **five distinct parents**; B's four involve **two**. Creating every such parent adds **5/2 notes**. The smallest covering subset restricted to those parent candidates is also **5/2**, with one smallest set in each archive: all candidates. Each candidate has a child outside the candidate set on at least one uncovered relationship, making that parent indispensable under this restriction.

Across all 5,040/24 edge orders, the sequential rule's minimum and maximum are both **5/2** for these archives. The research note uses synthetic A→B→C to show possible order dependence elsewhere: creating B first covers both edges with one file; creating A first leads to two. This is bounded evidence for the supplied archives, not a universal minimal-note algorithm or a design selection.
