# Current proposal review

`core.prepare_review(facts, preflight=...)` constructs an immutable version-1
`brz2obsidian.review-plan`. `core.resolve_review(plan, action)` returns a
version-1 `brz2obsidian.review-transition`. The plan is the full-operation review
gate. Its approvals are review evidence, not an executable partial apply payload.
No function reads a vault, Git, storage, clock or process, or claims publication,
rollback or recovery.

Every action is a closed, versioned record naming its decision ID, proposal ID,
expected generation, stable change ID, exact reviewed assumptions, domain and
choice. Refused or stale actions record no approval and preserve exact comparison
bytes. No action accepts a path list: producers offer the current and source
paths, and normalized target safety remains authoritative.

The plan retains initial `facts` and derived `producer_facts`. Resolution replays
its admitted actions from those initial facts and rejects altered proposals,
results, readiness, approvals or derived facts. A decision ID cannot be reused.
Choices stay within the current generation; a refresh belongs to the separate
refresh boundary and advances the generation. `core.validate_review(plan)` exposes
this same reconstruction for a saved plan when no new action is requested. It
validates only supplied facts and does not claim fresh filesystem observation.
Load/replay must use this admission rule. Association records a proposed repair;
it never changes observed identity or reports the repair complete. An explicit
rename delegates only an
exact offered producer choice. It invalidates affected content approvals while
retaining independent approvals whose exact change assumptions still agree.
The optional safe rename offer preserves the authored path by default; bulk
content approval grants no rename authority.

## Outcomes and explicit choices

Comparisons retain exact original, current, incoming and proposed result bytes.
Unchanged and preservation outcomes need no new approval. Compatible text
changes have an inspectable group summary, member IDs, byte total and individual
comparisons. The group assumption binds exactly those eligible members and their
assumptions. Bulk approval admits only those members. Conflicts, configuration,
mapping changes, identity repair, restoration and format choices retain distinct
action domains. Rename and attachment alternatives also require their explicit
producer admission rules. One remaining required choice, stale fact, unsafe
validation or consent requirement blocks the whole operation.

Text choices select exact current, exact incoming or a validated whole-file
edited candidate. The current choice records preservation with
`source_accepted=False`; an edited choice likewise does not claim acceptance of
the incoming source. Incoming and compatible approval record source acceptance.
A current choice can preserve opaque bytes without automatic interpretation;
applicable identity, exact normalized fact binding and selected target safety
still run. Exact normalized comparison binding runs for every explicit outcome;
an incoming or edited choice cannot discard unbound original/current/incoming
facts. Only the selected outcome's target semantics are required, so a discarded
unsafe incoming alternative cannot veto safe exact current preservation.
Restoration decline remembers the exact reviewed source version;
restoration requires a validated exact incoming candidate.

`obsidian.inspect_text_candidate` is an in-memory outer safety interpreter for
format 7. It admits UTF-8 text with optional YAML frontmatter, comments and
harmless nested YAML that the automatic merge grammar does not own. It rejects
ambiguous/unclosed frontmatter, unsupported encoding/control bytes, semantic
duplicate YAML keys, non-string top-level keys and invalid imported identity or
membership values. It supplies exact byte spans, source-neutral identity
components, selected membership targets and appearance facts. Core independently
checks canonical identity, required identity components, exact content/span
binding, property/component/target uniqueness, inherited target path safety and
affected appearance consistency. Exact current/incoming alternatives retain the
corresponding bound membership identity/path meaning and appearance value. An
edited label or prose change cannot reinterpret an existing membership alias;
explicit mapping choices remain limited to offered mapping meaning. An unchanged
pre-existing unrelated appearance warning does not forbid a safe choice. This safety interpretation does not grant
generated-section ownership or automatic merge authority.

Candidate approvals retain an immutable candidate assumption binding exact bytes
and normalized safety facts, with explicit dependencies on reviewed comparison
assumptions. A safe Boolean or arbitrary path list cannot substitute for these
facts. The automatic structure grammar and ownership rules remain described in
[structure-grammar.md](structure-grammar.md).

## Configuration memory

Ordinary supported source-update configuration keeps use explicit
`review_domain="configuration"` memory. Generic content memory uses
`review_domain="content"` and cannot authorize configuration. Every memory has a
required nullable `configuration_context`; configuration requires a context and
content excludes it. The context binds profile ID/version, settings digest and
output format, in addition to the existing owner/facet and exact reviewed
incoming source bytes. Its configuration assumption must occur in historical
review provenance, so attaching a context cannot relabel generic content history
as configuration consent.

A reconstructed equivalent ordinary configuration update may retain current
bytes under this memory after current safety checks. Changed incoming bytes or
relevant semantic context reopen distinct configuration review. A converter or
source-module release alone does not change this semantic context. Local edits
remain exact; a current-byte fingerprint is not the memory condition. A
deliberately deleted configuration retains the deletion default and offers explicit restoration or
decline. A decline uses configuration-domain/context-bound source memory and
reopens when that source version or semantic context changes. Onboarding
and format transitions always retain their operation-specific choices: source
memory cannot approve them, claim an established target-format baseline or
relabel retained authored bytes as pristine generated output.

## Preflight and consent

Required preflight facts distinguish idle, active, incomplete and recovery
states; supported, absent, unsupported-version, unsupported-state, corrupt and
unknown state; and explicit consent requirements. Missing facts do not mean no
requirement. Absent state requires a separate onboarding operation. A supported
state carries the outer interpreter's observed schema/version and compatibility
classification; the core does not invent a future persistence schema.

Tracking and storage requirements disclose their normalized policy and bind
scoped assumptions. Required ordinary tracking/storage and admitted built-in
storage transforms need explicit consent. Custom filters, encryption, LFS,
hooks, drivers, unsupported layouts and unknown policies remain refused. Decline
blocks readiness; a later explicit acceptance can replace that decline only at
current assumptions. Storage consent binds selected paths, exact content and
candidate effects: both binary outputs, explicit associated link replacements
and their relevant target context. A nullable single-file result cannot describe
these effects. Changing an affected selected effect reopens required storage
consent. Consent cannot override active/recovery, state, format, identity or
target refusal.


## Link and binary composition

The outer candidate interpreter requires an explicit source path, document ID,
path mode and complete bounded link registry/state facts. It interprets the
chosen bytes through the shared link interpreter. Core re-resolves normalized
queries using `validate_link_document`; cached meaning or a candidate-provided
historical baseline cannot waive validation. A warning baseline derives only
from actual current `LinkContext` document, registry and target facts. Supplied
current documents and consumed current target versions must bind exact observed
inventory content, path and existence before lookup or deduplication. Complete
inventory can prove no file exists at an explicitly described source-gap or
intentionally uncreated target. Absence does not infer either intent. A present
file contradicts a claimed absent target.

When link context is supplied, compatible approval requires independently
interpreted exact result bytes at the effective selected path. Interpretation at
a different source path cannot authorize preserved authored-path relative links.
Unavailable result interpretation excludes bulk approval and requires an explicit
independently interpreted whole-file candidate. Source-neutral attested cases
without a link context retain their existing contract. The `text-links` producer
assumption binds the current/source/effective-path interpretations and relevant
lookup competitors, collisions, selected target versions and nested membership
facts. Unrelated unused registry files are excluded. A separate `rename-links`
assumption binds re-resolved inbound queries, meaning, observation association
and relevant lookup/member context to both rename admission and change/group
provenance. Unrelated backlink prose is nonsemantic for rename when its lookup,
meaning and association are unchanged. A separately reviewed write still binds
that document's exact bytes.

Binary choices use required nullable action/approval attachment fields, explicit
`current`, `incoming` or `both` selection, and the public exact attachment
candidate validator. The selection binds proposal, generation, owner/facet,
reviewed change and exact assumptions to the review action. There is no edited
binary payload choice. Restoration uses a validated incoming binary selection;
ordinary current preservation emits only the appropriate content/configuration
source memory. An operation-specific format/onboarding current choice can
preserve validated observed absence without inventing deletion history,
original bytes, ordinary source memory or source acceptance.

The full-plan gate derives one effective set of selected files. Exact binary
outputs and changed associated documents must agree with independently chosen
text outputs. Unchanged associated documents are validation proof; they do not
compete with an independent prose-only write. Selected link meanings are then
checked against actual selected outputs, paths and target facts. A text candidate
cannot make an unselected staged binary version available. A note rename also
revalidates existing backlinks and the renamed document's relative links.
Unresolved competing writes or affected meaning changes block the complete plan;
comparison and approved alternative bytes remain inspectable and unchanged.
Remembered text preservation revalidates consumed current targets rather than
silently trusting a previous review.


Affected-link coverage derives from the independent observed inventory, rather
than the subset of supplied registry or document records. When selected bytes,
paths or normalized target meaning change, every present potential note in that
bounded inventory needs an exact bound, supported, complete link document.
Omitted documents, opaque potential backlinks or omitted registry layers leave
coverage unavailable and block whole-plan readiness. An explicit validated safe
resource record with matching canonical owner/facet, a positively associated
`AttachmentFacts` target and exact observed payload can exclude a
binary file; omission or relabelling an unassociated file cannot establish that
resource classification. Supplied
current queries are independently re-resolved before they establish meaning.
Known absence/status facts still distinguish a source gap or intentionally
uncreated target. Exact source-unchanged preservation introduces no new effect
requiring interpretation of opaque current files. Keeping configuration current
likewise does not introduce the discarded incoming file's effects.
