# Compatible-view navigation candidate

One narrow proposal for [#246](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/246):
how to reach a separately reviewed compatible member view when the existing shared
category keeps an incompatible custom dashboard.

Open `proposal.html` directly in a browser. It uses no server, dependencies,
external resources or persistence. Links preview distinct synthetic destinations.
`overview.md` and `source-reference.md` contain the exact candidate Obsidian markup.
The existing category note and the generator's prior fixtures are unchanged.

The import overview exposes the existing shared category, the clearly labelled
compatible linked-members view and the source-reference content as three distinct
destinations. The source-reference note repeats the existing-category and
compatible-view links above the preserved source content/attachment section.
The additional navigation is proposed only for an explicitly reviewed compatible
view; it does not silently add the view or alter the authored dashboard.

This extends the accepted CAT-P2/P3 organization in
[the canonical verdict](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/246#issuecomment-6299604312).
It proposes CAT-P4 organization/navigation only. Names, exact folder spellings,
typography and final wording remain illustrative. No human verdict is inferred.

## Proposed CAT-P4 scope

After the user chooses to create a separately reviewed compatible member view,
give it a distinct, clearly labelled link beside the shared category in the
import-specific overview and in the source-reference note. Preserve the existing
category/dashboard bytes. Keep the source content visibly separate with its own
overview link and reference-note section. These links identify different
destinations; the existing category link keeps its existing target.

Planned production checks: independently assert distinct exact targets and
descriptive labels in both generated notes; assert existing dashboard bytes are
unchanged; compare the actual generated navigation in native Obsidian to the
accepted organization. Prior Obsidian 1.14.4 evidence establishes the compatible
Base's two-row result in the synthetic People case, not these new navigation
links. This browser explanation does not establish native rendering/navigation.

No new native batch is needed to ask this organization question. A final native
check of generated markup would follow if this candidate is accepted.

## Scope reconciliation

| ID | Already accepted product behavior | Remaining presentation status |
| --- | --- | --- |
| CAT-P1 | Explicit per-category separate/reuse mapping; a name match only suggests a candidate; mappings remembered by source identity. | Mapping-screen layout/wording belongs with the final GUI specification; the fixture is illustrative. No new policy verdict is needed. |
| CAT-P5 | Reviewed mapping changes show affected memberships/links, protect manual edits, and block the whole update while real conflicts remain unresolved. | Identity/conflict-review presentation belongs with the final GUI. A fictional membership conflict needs no user data-resolution verdict. |
| CAT-P6 | Readable Brain tag namespace by default; existing-tag reuse requires explicit mapping; remember mappings. | Final tag-mapping explanation/layout belongs with the GUI. No accepted product behavior is reopened. |

Concise user decision: **Should the compatible members view have its own clearly
labelled link in both the import overview and source-reference note, alongside the
link to the preserved shared category?**

Recommendation: yes. The meaningful alternative is exposing it only through the
source-reference note, which keeps the overview smaller but adds a navigation
step to find members. Neither option inserts links into the authored dashboard.
No extra visual variants or fictional conflict decisions are needed.
