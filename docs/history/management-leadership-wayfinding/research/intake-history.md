# Initial assessment intake history

These are the original assessment overview and two finding records, preserved
when the user requested consolidation into this Wayfinder effort on 2026-10-05.
The statuses and references inside each record describe its historical intake
state. Active work follows the [Wayfinder map](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/9) and its `issues/`
frontier; these records do not create additional open tickets.

The [initial archive assessment](archive-coverage.md) retains exact-input and
diagnostic-subset evidence. Follow [Establish state-3 evidence and recovery
routes](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/72) for subsequent research,
[Verify absent content and type hierarchy in native TheBrain](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/73)
for source observations, and [Agree missing-content policy and category hierarchy
behavior](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/74) for the user's remaining decisions.

## Assessment request and completion

Original title: Assess the Management & Leadership archive against version 2

Original status: resolved
Original assignee: /root

The requested assessment is complete. This effort assesses the supplied archive
and records planning inputs; it does not accept a new implementation scope or
declare the archive successfully migrated.

Read the [archive coverage assessment](archive-coverage.md) for the
exact-input result, complete inventory, diagnostic subset trial, evidence limits
and recommended next decisions.

Two findings remain for triage before an implementation plan:

| Finding | Status | Next decision |
| --- | --- | --- |
| [01: State-3 missing notes and category icons](#state-three-payload-finding) | needs-triage | Establish source/export behavior and whether bytes can be recovered; then agree refusal or narrowly evidenced gap handling. |
| [02: Ordinary-to-type hierarchy](#hierarchy-to-type-finding) | needs-triage | Confirm visible source hierarchy and agree Parents/Children navigation involving category dashboards. |

The [new Wayfinder map](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/9) now governs
research, decisions, prototypes and the to-spec → to-tickets handoff. These
assessment findings remain intake evidence; work the map's child frontier
rather than treating this table as a second execution queue.

Use the accepted [v2 specification](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/11)
and [source coverage](../../../source-coverage.md) as the baseline. Keep earlier
archive feature classes working when future implementation scope is accepted.
Disposable private evidence is under `tmp/ml-assess/`, following
[workspace housekeeping](../../../workspace.md).

### Comments

- 2026-10-05: The user supplied `brz/Management & Leadership 2026-10-05.brz`
  after v2 acceptance and requested assessment before planning new features.
  The user reported **no export warnings noticed**. Original-input inspect and
  convert both refuse; a deliberately incomplete diagnostic subset succeeds.
  No production converter changes were made.

## State-three payload finding

Original title: Establish state-3 missing note and category-icon behavior

Original status: needs-triage
Type: research

### Finding

The supplied archive has 74 `AttachmentFileStates` entries with value `3`:
66 declared Markdown note payloads and eight category icons. None of their
expected payload paths exists in the archive. All declarations have nonzero
lengths. The v2 adapter rejects every state outside `{1, 2}` before examining
attachments, so this is the original-input inspection/conversion blocker.

See the [assessment](archive-coverage.md#state-3-payloads) for the
inventory, impact and evidence boundary. This is distinct from the 13 absent
TXT records already eligible for approved v2 warnings.

### Required evidence and decision

- Compare representative affected ordinary thoughts, the two affected type
  notes and all eight category icons with the original Brain's displayed
  content and files. A private item checklist is `tmp/ml-assess/source-review.md`.
- Record the actual source build/export choices; obtain a controlled export or
  disposable restore to distinguish omission, unavailable source content and
  any evidenced special state behavior. The user noticed no export warnings.
- Determine whether a fresh complete export or source recovery supplies the
  missing bytes. Another record's matching filename or byte length is
  insufficient evidence for substitution.
- If bytes remain absent, agree how a migration should communicate unavailable
  thought content and category appearance, including whether conversion must
  continue to refuse. Do not silently classify nonzero missing notes as empty.
- Only after this evidence, specify any adapter/profile, accounting, report,
  note-eligibility and icon-provider changes. Extend independent preservation
  facts and negative controls alongside production support.

This is an evidence ticket, not authorization to widen the state allowlist or
implement permissive conversion.

### Comments

- 2026-10-05: Follow-up now belongs to
  [Find the implementation route for the Management & Leadership archive](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/9),
  starting with [Establish state-3 evidence and recovery routes](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/72).
  This finding remains assessment evidence, not a competing execution ticket.

- 2026-10-05: Exact inspect and convert exit 1 with `invalid_source` / `Invalid
  attachment file state`; no vault is published. CRC and physical payload
  accounting pass independently. Unknown state semantics remain unresolved.

## Hierarchy-to-type finding

Original title: Preserve ordinary-to-type hierarchy as category navigation

Original status: needs-triage
Type: task

### Finding

There are 54 links with signature `(Kind, Relation, Meaning, Direction) =
(1, 1, 1, -1)` and endpoint roles ordinary thought → thought type. They connect
seven ordinary parents to 46 of the archive's 47 types. V2 accepts this hierarchy
signature for ordinary → ordinary and ordinary → tag, and refuses ordinary →
type. These links are separate from the 332 consistent type assignments.

See the [assessment](archive-coverage.md#hierarchy-to-thought-types).

### Proposed direction for review

Confirm source behavior, then preserve the ordinary parent's Children link to
the category dashboard and the dashboard's Parents link to the ordinary note.
Keep membership, hierarchy and appearance separate; these records do not
establish type inheritance. Existing source-neutral graph planning and rendering
appear able to express this navigation, so begin with a focused adapter-boundary
extension rather than an architecture change.

Before making this implementation-ready, specify source signatures/endpoints,
multiple-parent behavior, naming/collision handling, source evidence retention,
public workflow acceptance checks and independent full-archive predicates.
Other type-to-type, jump-to-type or subtype signatures remain outside the
observed scope.

### Comments

- 2026-10-05: Follow-up now belongs to
  [Find the implementation route for the Management & Leadership archive](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/9),
  beginning with [Complete the four-archive feature comparison](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/71)
  and then native observation and user decisions. This finding remains intake
  evidence, not an implementation-ready slice or competing execution ticket.

- 2026-10-05: Per-record decoding rejects exactly these 54 relationships and
  accepts the other 699. The diagnostic subset excludes these links, so its
  successful conversion does not establish their preservation or presentation.
