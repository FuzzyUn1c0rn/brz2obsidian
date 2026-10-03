# Creating parent notes for uncovered hierarchy relationships

Investigated 2026-10-03 for [Quantify creating parents for uncovered hierarchy relationships](../issues/10-parent-materialization-evidence.md). This note evaluates the user's proposal: when neither endpoint of a parent/child relationship otherwise has a note file, create its parent so the relationship can be written in an endpoint's Parents or Children list. It supplies counts and coverage facts; it does not select the representation or a production algorithm.

**Finding:** In the two real archives, this rule would require **5 additional ordinary-thought notes in A and 2 in B**. Those are both the counts obtained by creating every distinct parent of an initially uncovered relationship and the smallest covers restricted to those parent candidates. Every edge order gives the same count for these two inputs. Order dependence remains possible for other graphs.

## Scope and reproducible inspection

The initial content-note criterion is unchanged from [uncreated-target evidence](uncreated-targets.md): substantive thought-note text, archived non-note internal files/images, or external file/URL/directory references qualify; empty `Notes.md` placeholders, decorative icons, labels, colors and identity/date metadata do not qualify by themselves. This yields **43 initial content-bearing ordinary thoughts in A and 40 in B**, with **20/18 ordinary thoughts initially lacking a note** under that criterion.

An initially uncovered hierarchy relationship has two ordinary endpoints without such a note. It is a normal relationship (`Kind=1`, `Meaning=1`) whose endpoint thoughts have `Kind=1` and whose hierarchy relation is child (`Relation=1`) or parent (`Relation=2`). Parent orientation comes from `Relation`, **not** the independent arrow `Direction` field. The prior [BRZ preservation evidence](brz-preservation.md#relationship-meaning-and-direction) establishes those source distinctions. The real cases counted here all use `Relation=1`.

The investigation helper's broader `Relation=2` handling is exploratory. The [accepted first-version specification](../../brz-to-obsidian-v1/spec.md) admits only the verified `Relation=1` hierarchy cases; it does not claim initial support for `Relation=2`.

[inspect_parent_materialization.py](inspect_parent_materialization.py) reads the two ZIP archives locally without extracting, changing or uploading their content, reuses the earlier note/attachment parsing helpers, and emits aggregate counts only. It ran with Windows Python **3.14.8**; measured archive SHA-256 values match [the prior real-input inventory](brz-preservation.md#reproducible-inputs-and-method). The archive labels A/B retain that inventory's order.

For this bounded investigation the script checks all subsets of the candidate-parent set and every order of the initially uncovered relationships: 5,040 orders for A's seven edges and 24 for B's four. Its explicit bounds prevent treating this enumeration as a scalable converter algorithm. This is evidence for two small cases, not a production recommendation.

## Measured coverage and additional files

| Measure | A | B |
| --- | ---: | ---: |
| Initial content-bearing ordinary thoughts | 43 | 40 |
| Ordinary thoughts without substantive content | 20 | 18 |
| Ordinary hierarchy relationships | 66 | 56 |
| Initially uncovered ordinary hierarchy relationships | **7** | **4** |
| Distinct endpoints of initially uncovered relationships | 10 | 6 |
| Distinct parents of initially uncovered relationships | **5** | **2** |
| Extra notes if every such parent is created | **5** | **2** |
| Smallest subset of those parent candidates covering all initially uncovered relationships | **5** | **2** |
| Number of subsets achieving that smallest count | 1 | 1 |
| Extra notes from the sequential rule in archive record order | 5 | 2 |
| Extra notes from the sequential rule in reversed record order | 5 | 2 |
| Smallest sequential-rule count across all edge orders | **5** | **2** |
| Largest sequential-rule count across all edge orders | **5** | **2** |
| Resulting ordinary-thought note count (initial plus extra) | 48 | 42 |

Here **coverage** means that at least one endpoint has a note file where the relationship can appear in readable text. A created child can carry a Parents link to an uncreated parent; a created parent can carry a Children link to an uncreated child. This does not require both endpoint files. It also does not claim that Obsidian Graph becomes a typed hierarchy: Graph lines are internal links and its arrows represent the direction of those written links. [Graph view](https://obsidian.md/help/plugins/graph). The related storage limits remain in [uncreated-target evidence](uncreated-targets.md#inherent-limits-separated-from-ui-uncertainty).

**Why there is no reduction in these inputs:** two of A's parent candidates are also children in another initially uncovered relationship; none of B's candidates are. Materializing a parent can therefore cover a relationship where it is the child as well. Nevertheless, **each of A's five candidates and each of B's two candidates has at least one initially uncovered relationship to a child outside the parent-candidate set**. When creation is restricted to those parent candidates, that child cannot be selected, so its parent is indispensable. Hence the sole smallest cover is the complete candidate set, and every sequential order eventually creates all of it.

This is a minimum **within the stated parent-candidate restriction**. It is not a claim of a globally smallest selection allowing arbitrary children, different content criteria, other graph structures or different representation choices. The 48/42 totals concern ordinary thoughts only; A's content-bearing tag is separate.

## Why sequential order can matter elsewhere

Use a wholly synthetic hierarchy chain, where `A → B → C` means **A is parent of B, and B is parent of C**, rather than encoding TheBrain's visual arrow setting. None of the three initially qualifies for a content note.

| Processing order under “create the parent only when neither endpoint has a note” | Result |
| --- | --- |
| First B→C, then A→B | Create B. The second relationship already has endpoint B, so A stays uncreated. **One extra note.** |
| First A→B, then B→C | Create A, then create B because neither B nor C yet has a note. **Two extra notes.** |

A note for **B alone** can list `Parents: [[A]]` and `Children: [[C]]`, covering both hierarchy relationships. Creating A first cannot cover B→C. Thus the naive sequential rule may depend on edge order even though no variation occurred in the supplied archives. Sorting source records or choosing a subset are later algorithm decisions; this research does not settle either.

The final content-generation step would need to write all applicable relationship lists for the selected note set, including relationships whose materialized endpoint is the child. Otherwise choosing a sufficient set of files would not by itself guarantee readable coverage.

## Remaining scope limits

The parent proposal creates hierarchy-bearing notes with useful relationship content even though they lack substantive source text/files. The user subsequently accepted that rule in [Choose note identity, relationships, and vault layout](../issues/03-vault-model.md).

The measured cases have no ordinary jump relationship with two initially contentless endpoints and no isolated empty ordinary thought. The rule therefore covers the measured ordinary hierarchy gap, but this evidence does not claim it handles unseen empty-to-empty jumps or isolated thoughts. A's isolated empty tag and its different tag with substantive note text remain distinct tag-representation questions from [Verify uncreated targets and empty-thought hierarchy coverage](../issues/09-uncreated-target-evidence.md).

This investigation performed no Obsidian UI trial, generated no destination files, and reproduces no private titles, IDs, note text or attachment destinations. The subsequent [accepted vault trial](vault-trial.md) verified link creation, filenames, rendered relationship lists and navigation.

Reproduce from the repository root, selecting the same real inputs without printing their names:

```powershell
$archiveA = @(Get-ChildItem -LiteralPath 'brz' -Filter '*.brz' -File | Where-Object Length -eq 45016149)
$archiveB = @(Get-ChildItem -LiteralPath 'brz' -Filter '*.brz' -File | Where-Object Length -eq 153693431)
if ($archiveA.Count -ne 1 -or $archiveB.Count -ne 1) { throw 'Real archive selection is ambiguous.' }
.\.venv\Scripts\python.exe -B .scratch/brz-to-obsidian/research/inspect_parent_materialization.py $archiveA[0].FullName $archiveB[0].FullName
```
