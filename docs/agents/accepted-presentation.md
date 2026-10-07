# Accepted presentation handoff

Use this procedure when a user approves a prototype or presentation example,
or when specifying, implementing or reviewing changes to that presentation.
It applies to visible generated artifacts as well as application UI.

## 1. Capture the approved details

Record the decision alongside the feature under `.scratch/<feature>/`. Use an
`Accepted presentation` section in its specification as the canonical record.
Before a specification exists, capture it in the prototype ticket's Answer;
when writing the specification, transfer the requirements and link the original
verdict as provenance.

Record:

- The user's verdict, date and approval scope, including any later corrections.
- The selected variant and exact reference commit/artifact. Include representative
  screenshots and the app/theme context where it affects the appearance.
- Stable requirement IDs for each approved detail: appearance, wording, placement
  and interactions. Include decision-rich example markup when it is more precise
  than prose, plus the intended test or native observation for each requirement.
- Which example details are illustrative and which remain undecided.

Resolve a variant choice into its distinguishing details; a label such as
"layout A" alone is insufficient. Use existing approval without requesting it
again. Clarify an uncertain detail only when it materially affects implementation.
Prototype approval covers its recorded scope, separately from final delivery.

Keep safe textual requirements and decision-rich examples in the versioned
record so they survive temporary-evidence cleanup. Handle private screenshots,
prototype captures and disposable output under [workspace housekeeping](../workspace.md).

Complete this step when every approved detail has a requirement ID, a reference
and a planned check, with unresolved details explicitly distinguished.

## 2. Carry requirements into the work

During specification and ticket breakdown, account for every presentation ID.
Each affected ticket links to the canonical section and has acceptance criteria
covering its IDs. Keep the full requirements in that one section rather than
copying them into every ticket or handoff.

Implement from the accepted reference. Derive automated expectations independently
of the renderer's current output. Check observable markup, text, ordering and
separate elements through the existing public testing seams; demonstrate a
regression check fails on the incorrect output before accepting the repair.
Use existing equivalent checks where they already cover the requirement.

Complete this step when every affected ID has applicable automated evidence or
is explicitly assigned to native verification. Passing syntax checks alone
leaves appearance requirements open.

## 3. Verify actual presentation independently

Assign final presentation verification to a reviewer who neither implemented
the changed presentation nor authored the native acceptance report being assessed.
Include the canonical requirements and exact reference in the review handoff.

Compare actual converter/application output with that reference, following
[strategic visual sampling](../testing.md#visual-sampling-policy). Combine cases
covering distinct behaviors; reuse earlier observations when the relevant output
and rendering context remain applicable. Markup tests verify structure; native
observation verifies the approved appearance, including titles, icons and panels.

Record the candidate commit, selected output, covered requirement IDs, automated
results, native evidence and any limits in the ticket/review record. For each ID,
report satisfied, failed or unverified. Repair and recheck affected failures;
refresh evidence when a relevant implementation or accepted requirement changes.

Complete presentation verification only when every affected ID is satisfied.
Keep any specification-required final user verdict as its separate delivery gate;
this procedure adds no extra approval round.

## Worked example: source-gap warning panels

The [accepted styling correction](../../.scratch/management-leadership-implementation/research/final-review.md#actual-vault-styling-follow-up)
records the rejected plain blockquotes, exact clarification/repair commits,
native evidence and eventual user acceptance. These example IDs describe that
accepted correction, rather than inferring all styling from the earlier A choice.

| ID | Accepted detail | Applicable evidence |
| --- | --- | --- |
| P1 | Native warning callouts with descriptive titles, warning icons and orange/tinted panels in the accepted native context. | Assert `> [!warning] Source note unavailable` and the other approved headers; observe the four notice types in combined native samples. |
| P2 | An ordinary source-gap notice appears above the available images. | Assert output ordering in the ordinary fallback workflow. |
| P3 | Adjacent source-gap notices remain separate warning panels. | Check distinct callout blocks and observe an adjacent pair natively. |
| P4 | Category Parents/Children follow the title, then notices, then Members/Gallery. | Check hierarchy/notice/Base ordering and observe a representative category. |

Existing [ordinary fallback tests](../../tests/application/test_absent_note_images_workflow.py),
[type-gap tests](../../tests/application/test_type_source_gaps_workflow.py),
[hierarchy tests](../../tests/application/test_category_hierarchy_workflow.py) and
[independent corruption controls](../../tests/local_acceptance/test_checker_v3.py)
provide reusable automated coverage. The accepted correction's report supplies
the separate native appearance evidence; the renderer and matching oracle output
alone would not establish that the approved presentation was preserved.
