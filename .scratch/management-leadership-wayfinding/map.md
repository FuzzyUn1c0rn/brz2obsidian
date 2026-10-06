# Find the implementation route for the Management & Leadership archive

Status: resolved
Labels: wayfinder:map

## Destination

An agreed route to successfully convert `brz/Management & Leadership
2026-10-05.brz`, expressed as an accepted implementation specification produced
with **to-spec**, followed by approved dependency-ordered implementation tickets
produced with **to-tickets**. Source gaps, conversion behavior and verification
must be settled enough that implementation can proceed without guessing.

## Notes

- Firm user requirement (2026-10-05): exclude forgotten thoughts from conversion.
  This is the default for all archives, with no forgotten content, references,
  visual artifacts or hidden identifying output. The
  [accepted policy](issues/04-conversion-policy.md#answer) owns its exact boundary;
  deliberate destination exclusion does not delete source records.
- Firm user requirement clarified during the policy session (2026-10-05):
  conversion of these image-bearing archives must work directly from the BRZ,
  without manually opening thoughts or retrieving attachments in TheBrain.
  The user confirms that the Pip Decks card images are important content.
  The recovered backup is investigation/reference evidence, not a prerequisite
  for routine conversion. The [accepted policy](issues/04-conversion-policy.md#answer)
  owns the automatic fallback, preservation limits and actionable source diagnostics.
- The user requested this new map on 2026-10-05 after v2 was delivered. This
  map ends at specification and ticket publication. Those artifacts must include
  actual complete-archive conversion, preservation, regression and native/user
  acceptance gates for the subsequent implementation effort.
- Start with the [completed archive assessment](research/archive-coverage.md).
  It establishes the exact-input refusal, state-3 absent notes/icons and
  ordinary-to-type hierarchy gap. Its successful diagnostic subset is incomplete
  and cannot establish preservation or acceptance of the original archive.
  The user noticed no export warnings. These are starting facts, not accepted
  missing-content or destination-design policies.
  Its original overview and finding records are retained in
  [assessment intake history](research/intake-history.md); this map's child
  frontier governs follow-up work.
- Reuse the [accepted v2 specification](../brz-to-obsidian-v2-implementation/spec.md),
  [source coverage](../../docs/source-coverage.md) and complementary earlier
  archives as the cumulative baseline. Do not reopen reviewed behaviors merely
  because this archive is larger. New source observations may justify reopening
  a boundary explicitly, with evidence and a user decision.
- Use the root [glossary](../../GLOSSARY.md) and
  [source-neutral-core ADR](../../docs/adr/0001-source-neutral-core.md). Keep
  thought types, category membership, ordinary hierarchy, inherited appearance
  and attachment Type/state distinct. Unknown state 3 is not a domain synonym
  for empty, deleted, optional or corrupt content.
- Follow the [local tracker](../../docs/agents/issue-tracker.md): select the first
  open, unblocked, unclaimed child by number; save `Status: claimed` and Assignee
  before work. Resolve by appending `## Answer` and linking its gist here. Refer
  to maps/tickets by their titles. Open children live under `issues/`; the map
  does not duplicate their index. Charting does not resolve human decisions.
- Use [research](C:/Users/stefa/.agents/skills/research/SKILL.md) for evidence,
  [prototype](C:/Users/stefa/.agents/skills/prototype/SKILL.md) for a concrete
  behavior/presentation review, and both
  [grilling](C:/Users/stefa/.agents/skills/grilling/SKILL.md) and
  [domain-modeling](C:/Users/stefa/.agents/skills/domain-modeling/SKILL.md) for
  decision sessions. Facts are the agent's work; the user chooses product
  behavior. Research may run in parallel; resolve at most one other decision
  ticket per session.
- Native source observation should identify the Brain/build and distinguish
  original-source inspection from controlled disposable export/restore behavior.
  Use computer-use when available and read its skill first. Use disposable
  controls for experiments; do not alter original content or run repairs on the
  user's Brain as an investigation shortcut. If native access requires the
  human, give a precise bounded checklist and record their actual observations.
- Keep private archive records, titles, URLs, note text, native screenshots and
  generated vaults under ignored local storage. Follow
  [workspace housekeeping](../../docs/workspace.md); new disposable work belongs
  in `tmp/ml-wayfinding/`. Existing assessment evidence is in `tmp/ml-assess/`.
  Durable research publishes aggregate findings and synthetic structural examples.
- Invoke [to-spec](C:/Users/stefa/.agents/skills/to-spec/SKILL.md) only after the
  source/policy/prototype prerequisites are resolved. Confirm the testing seams
  with the user as it requires. Then invoke
  [to-tickets](C:/Users/stefa/.agents/skills/to-tickets/SKILL.md), present the
  concrete vertical slices and genuine blockers for the user's review, and
  publish only the approved breakdown. Keep the implementation spec/index/
  tickets in a separate `.scratch/management-leadership-implementation/` area;
  map children hold decision evidence, not implementation slices.

## Decisions so far

- [Complete the four-archive feature comparison](issues/01-complete-archive-comparison.md):
  complete comparison confirms the two known blocker classes; newly observed
  cycles, tag icons, empty type-owned placeholders and ZIP resources fit v2,
  while other field/scalar/history changes remain retained evidence.
- [Establish state-3 evidence and recovery routes](issues/02-state-three-evidence.md):
  all 74 absent declarations are independently confirmed; numeric state meaning
  remains unknown, and first-party export guidance provides bounded full-content
  and isolated-restore controls for native observation.
- [Verify absent content and type hierarchy in native TheBrain](issues/03-native-source-observation.md):
  initial bounded probes recovered 13 files and confirmed multiple ordinary
  parents of a type independently of assignment; subsequent
  [active-note recovery](research/native-source-recovery.md) recovered all 60
  remaining active notes into a fully validated fresh source backup.
- [Agree missing-content policy and category hierarchy behavior](issues/04-conversion-policy.md):
  convert from the BRZ alone, visibly show available images beside absent notes,
  preserve present Markdown and report actionable source gaps; exclude forgotten
  content by default and show category hierarchy above Members/Gallery.
- [Review the agreed behavior in a representative vault prototype](issues/05-vault-prototype.md):
  the user selected the source-gap notice above available images; representative
  source checks and native review support the presentation and diagnostic design.
- [Agree acceptance checks and publish the implementation specification with to-spec](issues/06-implementation-specification.md):
  the user confirmed the testing boundaries; the accepted specification defines
  the archive-only behavior and complete preservation/regression/native gates.
- [Publish the approved implementation breakdown with to-tickets](issues/07-implementation-tickets.md):
  the user approved all nine slices and their dependencies; the separate
  [implementation index](../management-leadership-implementation/README.md)
  publishes the initial frontier and complete specification coverage.

## Not yet specified

The planning destination is complete: source evidence, conversion policy,
representative presentation, accepted specification and approved implementation
graph are recorded. Official state-3 semantics and the export-omission cause
remain unproven; the narrow accepted predicates do not depend on those claims.
Implementation defects or unsupported new evidence follow the separate tracker,
without inventing missing source content or weakening delivery gates.

## Out of scope

- Production implementation and release delivery during this planning map.
  They follow the published implementation frontier; its acceptance gates still
  belong in the specification and tickets.
- Merge/synchronization/overwrite of an existing vault, changes to unrelated
  retained user vaults, and modification of original Brain/export content.
- Blanket format-5 support, silent missing-file allowances, invented original
  bytes or authenticated-looking substitutions without evidence.
- New PDF body indexing, ZIP expansion, remote resource fetching, community
  plugin requirements or broader type inheritance solely because these resources
  or type endpoints occur here. Revisit only if a concrete in-scope need emerges.

## Comments

- 2026-10-06 (/root): Following the user's actual approval, to-tickets published
  the complete graph. This separate bookkeeping step resolves the final planning
  child and map. The user separately authorized an integration branch, a commit
  of session changes and implement-spec, then requested a final PR. Implementation
  proceeds under its own index; no successful full conversion is claimed here.

- 2026-10-06 (/root): Recorded the actual testing-boundary confirmation and
  finalized the accepted specification. The user explicitly requested to-tickets;
  the next child reviews its proposed slices and dependencies before publication.
- 2026-10-06 (/root): The
  [implementation specification draft](../management-leadership-implementation/spec.md)
  is complete and [reviewed](research/specification-review.md), including the
  independent included-source count correction. The specification child remains
  claimed pending the testing-boundary confirmation explicitly required by to-spec.
- 2026-10-06 (/root): Recorded the user's choice of layout A and resolved the
  prototype decision. The implementation-specification child is now unblocked;
  complete-archive migration and release acceptance remain subsequent gates.
- 2026-10-05 (/root): The
  [representative vault prototype](research/vault-prototype.md) is built from
  original archive bytes, independently checked and inspected in native Obsidian.
  The prototype child remains claimed pending the user's layout choice and
  presentation verdict; its preparation does not unblock the specification yet.
- 2026-10-05 (/root): Charted at the user's request. The destination explicitly
  includes to-spec followed by to-tickets and stops before implementation.
  Existing assessment findings are intake evidence; this map's children now
  govern follow-up decisions. Source-dependent human decisions remain open.
- 2026-10-05 (/root): Both background research children resolved with source-cited
  reports and isolated research-branch captures. Linked their findings above;
  no human policy/prototype/specification decision was resolved during charting.
- 2026-10-05 (/root): At the user's request, consolidated the initial assessment
  report and intake records into this effort, updated documentation/tooling
  references and removed the emptied assessment folder. The seven child tickets,
  their dependencies and unresolved decisions are unchanged. Private assessment
  run evidence keeps its existing `tmp/ml-assess/` location.
