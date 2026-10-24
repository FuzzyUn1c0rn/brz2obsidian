# Editable-vault state walkthrough

Open `index.html` by double-click. It is one self-contained HTML file with no
dependencies, server, installation, browser storage or real Git/filesystem actions.
The coordinator's convenience server serves the same file at
`http://127.0.0.1:8765/git/`.

This is the LOGIC branch of the `prototype` skill for
[#244](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/244), on the retained
`codex/editable-vault-wayfinder` feature root starting at
`fc16aeac77655b5c8dc48070f247079c475e18ba`. It is separate from GUI direction B.
No production source or repository metadata is changed by this artifact.

## Question and decision boundary

Can the user understand and accept the proposed state/recovery behavior: which
source and vault versions are distinct, what a review approves, why an update
stops, and how later writing survives interruption or latest Undo?

All clicks are synthetic transitions. Human acceptance of the behavior cannot
establish Git safety, persistence, semantic merging or power-loss durability.
The separate [experiment report](README-experiment.md) owns actual mechanism
observations. Its recorded bounded runs on Git 2.55.0.windows.5 preserved
the user index/staged entries/HEAD/branches/tag/configuration, round-tripped
the sampled exact bytes, and detected actual partial publication in fresh
processes while preserving subsequently edited affected content. The experiment
report binds these observations to its authoritative run, source hash and timing;
this walkthrough does not
extend those results to every simulated state or accepted conditional target.

No human verdict has been supplied or inferred. Independent review and the
user's behavior verdict remain separate gates for the coordinator.

## Drive the model

The current-state panel always renders the selected note's previous converted
source, current vault and incoming source, identity/path, review decision,
whole-update gates, review memory, saved-review state, operation state and
conceptual history. A retained-operation disclosure exposes the preimage and
accepted result during recovery/Undo. Guided feedback repeats the current and
proposed vault body beside the steps. Inspect other items with the selector or
their View buttons. Full state is labelled prose, rather than a JSON dump.

Free-play actions are always available; illegal transitions return an explanation.
Some less-common actions are in the “Change the surroundings / recover”
disclosure. Guided tabs reset to known inputs, and each step is an actual action
button. Refreshing clears everything, including simulated saved review.

| Guided case | Behavior put under pressure | Accepted source |
| --- | --- | --- |
| Three versions | Source-only and vault-only changes, independent synthetic fields, conflicting date, compatible approval cannot bypass whole-update gate | #243 P01–P03 |
| Remember my choice | Keep vault for the reviewed source; repeat input no-op; changed incoming content needs review | #243 P07–P08 |
| Identity & files | Moved path retained; duplicate identity blocks guessed match; explicit resolution; binary keep-both paths and reviewed reference links | #243 P04, P09 |
| Saved & stale | Save/resume unchanged assumptions; later vault edit invalidates dependent approval | #243 P10–P11 |
| Interrupted update | Partial publication, later writing, restart detection, block new update, review before finish/restore | #240 recovery, #248 H07 |
| Latest Undo | Review before reversal, later-edit protection, only latest applied operation | #240 recovery |
| Absence & deletion | Retain source disappearance; respect local deletion; offer restoration only for changed incoming content | #243 P05–P06, P14 |
| Missing history | No pristine-byte inference from identities/current vault; explicit preservation-first onboarding; separate output-format gate | #243 P12, #248 H03–H07, ADR 0006 |
| Storage choices | Specific built-in exact-byte choice; separate affected exclusion inclusion; changed effective custom filter refuses | #248 C05–C06, C10 |

The initial model uses collection `Brain-A` and illustrative source-item IDs;
binary payloads are labels. Its independent-fields example has deliberately
explicit boundaries. No arbitrary Markdown/properties/links merge is proved.
The duplicate-identity example is a resolution exercise rather than an actual
file copy. Configuration/category mappings and unrelated vault diagnostics are
not additional simulated policy systems. Their requirements remain in #240,
#243 and the final specifications.

The expandable compatibility note summarizes all relevant conditional-target,
refusal, exclusion and history-portability boundaries without creating a new
matrix or offering generic bypasses. The complete authoritative C01–C17 and
H01–H09 matrices remain in [#248](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/248).
Only the storage/exclusion/custom-filter path is interactive here; the other
compatibility/portability cases are explanatory policy, not demonstrated support.

## Portable logic and contract recommendations

The first script contains `VaultModel`, a pure `initial`/`reduce` model plus
read-only proposal/gate helpers. It has no DOM, filesystem, Git, clock or network
access. The second script is the throwaway presentation shell. The reducer is
an implementation discussion candidate, not production code or an accepted
persisted schema.

Independent review found and repaired a simulation policy bypass: after an effective custom filter appeared, Undo could previously proceed after stale re-review. A shared pre-write guard now refuses save/checkpoint, publication, interruption publication, recovery finish/restore, Undo preparation/application and onboarding while storage policy is unsupported. Review choices and external-edit simulations remain inspectable; they cannot authorize a refused write. The same guard is used before each applicable transition.

The behavior suggests explicit public contracts for:

- Preparation returning current input assumptions, item findings, proposed
  outcomes and unresolved requirements, before any application.
- Review decisions scoped to collection/item identity and actual reviewed
  incoming/vault/policy assumptions, plus changed-input invalidation.
- Distinct previous converted-source and accepted vault versions, meaningful
  checkpoint boundaries, repeat-input no-op and source-scoped keep-vault memory.
- Whole-update application with concrete not-applied, applying/recovery-required
  and completed outcomes; history recording alone cannot report completion.
- Recovery inventory of before/planned/later-divergent content, explicit
  resolutions and no overwrite of later writing; recovery before new update.
- Latest Undo as a separate reviewed proposal with later-edit protection.
- Missing-history/onboarding and output-format incompatibility as explicit gates,
  never inferred pristine bytes or silent format conversion.

Exact names, schemas, durability, filesystem failure cases, Git version support
and semantic reconciliation are owned by experiment evidence and final
specification #247. The lifecycle labels here are illustrative, not settled API
names. Restore of matching history copies and advanced compatibility detection
are not implemented by this page.

## Development observations and independent-review handoff

The author drove all nine guides through their visible controls in an owned CUA
in-app browser tab, at the coordinator's localhost URL. The observed expected
stops/completions are retained at
`tmp/merge-wayfinding/git/walkthrough/guided-observations.json`.
After those observations, targeted checks covered refined Undo target/table
presentation, recovery comparison and the keep-decision input assumption. No
formal tests or production verification runner was used for this throwaway demo.

Sampled desktop presentation: three-version cards, selector/table buttons,
free-play controls/disclosures, guided tabs and enabled/disabled step buttons,
warning/normal status text, retained-version disclosure, keyboard focus, anchor
navigation and vertical scrolling. Screenshots and the final observation record
are under `tmp/merge-wayfinding/git/walkthrough/`. These are author development
observations, not independent presentation acceptance. Narrow/native Windows
rendering remains unverified; this artifact is a browser logic demo and is not
the approved application GUI.

Independent reviewer should assess the exact current `index.html` and this
README against #240/#243/#248 and ADRs 0002–0007, drive representative guides
including a refused transition and later-edited recovery/Undo, and ensure all
evidence claims agree with the separate experiment. Proposed user verdict
questions are rendered per guide. The three central questions are:

1. Is “keep my vault wording for this source version; ask again when it changes”
   understandable?
2. Is the difference between saved review, still-current approval and a completed
   filesystem update clear?
3. Are finish/restore recovery and latest Undo understandable when later writing
   must first be reviewed and retained?

The coordinator records any actual human answer and returns policy discrepancies
to their decision owner. This file records no approval.

Repair verification: focused visible-control browser checks reproduce the policy-changed Undo sequence, recovery finish/restore after later-edit resolution, save/onboarding refusal, and finish/interruption/begin refusal after an operation has started. Displayed file/history state remained unchanged and terminal state stayed applied, recovery-review or applying as appropriate. The recorded observations are in `tmp/merge-wayfinding/git/walkthrough/policy-repair-observations.json`. Independent reassessment remains pending.
