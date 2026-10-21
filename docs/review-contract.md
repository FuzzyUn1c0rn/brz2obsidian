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

The plan retains current-epoch `facts` and derived `producer_facts`; its ordered
`history` preserves the original initial facts, actions and refresh events.
Resolution reconstructs that history in its original epochs and rejects altered
proposals, results, readiness, approvals or derived facts. A decision ID cannot be reused.
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
independently interpreted whole-file candidate. Generic source-neutral cases likewise supply bounded exact normalized link
documents, canonical registry and target states. A null link context is unknown
for selected byte/path/meaning effects, not evidence of a link-free scope. The `text-links` producer
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


Canonical lookup coverage also derives from independent current inventory. Every
present potential file needs one canonical current registry identity/path and
exact current target state; a reduced registry cannot relabel an existing file
as a missing pre-existing link, even after consistent public reinterpretation.
Unknown observations remain uncertainty and never count as proven absence.
An explicit changed-source current choice, and remembered current policy, require
this current lookup proof and their bound current document. Removing the whole
context or a consumed canonical lookup cannot create preservation consent or
new source memory. These requirements remain distinct from unrelated backlink
document coverage: a safe exact configuration keep needs current consumed proof,
whereas newly selected bytes/path/meaning also need potential backlink coverage.
Exact source-unchanged opaque preservation and proved observed absence introduce
no new effect requiring that interpretation. A generic synthetic link-free case
can supply explicit exact empty-occurrence facts; a real outer interpreter must
establish those facts for its format, and cannot substitute an unbound safe flag.


## Selective refresh and immutable consent history

`core.refresh_review(plan, facts, *, preflight)` validates the original review,
advances the same proposal by exactly one generation, recomputes comparisons and
returns a `ReviewTransition`. Accepted refresh means the supplied facts were
processed; new or changed choices remain unresolved. An old action token keeps
its original expected generation and cannot approve the new generation.

Every plan has closed version-1 `ReviewHistory`: exact initial facts/preflight
and an ordered tuple of original `ReviewAction` and `ReviewRefreshEvent` records.
`validate_review` reconstructs these epochs in order and compares the complete
canonical result. Refresh events expose old/new versioned dependency nodes,
changed keys, transitive invalidation and typed retention/applicability evidence.
These fields are recomputed during reconstruction; supplied retained/ready flags,
changed edges, graphs or results cannot authorize a choice. Decision IDs remain
reserved across the whole history. No record claims a new filesystem observation.

A retained approval preserves its exact original result, path, candidate, source
memory and explicit-user or compatible-bulk provenance. `ReviewRetention` binds
that original member to current applicability. A bulk decision can retain an
unchanged member after its group ID or siblings change; it does not replay the
old group against new members. Edited and binary candidates are independently
revalidated against fresh exact facts. Removing an unsafe approval or producer
choice triggers another graph/effect pass until the affected set stabilizes.

`ReviewProducerApplicability` preserves original normalized association/rename
decisions while binding their unchanged current assumptions to the new epoch.
The preceding canonical review must actually have admitted that exact decision;
a stale, refused or ignored record cannot be revived by mere presence. Public
`reconcile` retains strict current-epoch admission. Only canonical review's
private producer evaluation receives reconstructed applicability evidence.
Observed repair stays required until independently supplied identity facts
establish it. This evidence is neither a new action nor actual file repair.

`ReviewAttachmentApplicability` is a derived validation view, separate from the
original approval. Its original selected outputs and explicit associated-document
writes are identified against the original admitted context. Fresh independently
bound unrelated documents/registry entries supply current validation proof; they
do not become selected writes. Exact originally written document preimages and
query meanings must remain valid. Current public selection admission stays
strict, including its original generation. The graph, effective-output gate and
storage consent consume the same derived view; original tokens/candidates remain
immutable. New collisions, lookup competitors, fragments or membership meanings
invalidate dependent choices, while unrelated context changes can retain them.

Dependency nodes expose producer kind, semantic fingerprint and actual edges.
Current bytes/existence/path, available original/source facet bytes, semantic
profile/settings/output format, used mappings/targets/query competitors, identity,
safety, policy/history, candidates, selected effects and scoped consents participate
where consumed. Reverse transitive closure includes removed edges. Unknown or
missing indispensable provenance, conflicting definitions and cycles refuse
retention. Source-memory historical graphs are validated independently; their
old fingerprints are not compared with new local bytes. Unusable records remain
in supplied history rather than being pruned or treated as originals.

Complete current lookup proof starts from independent inventory rows and includes
canonical registry/state bindings and required current documents. Missing context,
unknown inventory or omitted backlinks cannot prove a selected effect safe.
A genuinely required global history/operation/safety change may invalidate all
consumers; global reset is not the default. Source-neutral exact no-effect opaque
preservation keeps its existing conservative boundary.

Semantic output identity excludes informational module-release metadata while
retaining its provenance. Established-original and section-basis validation use
the same projection as fingerprints. No converter-version field is invented.
Mapping scope excludes only records proven unused by supported structure; unknown
syntax cannot establish non-use. Safety admission keeps the relevant attestation
and excludes changes solely to which other subjects share it.

Configuration source memory retains its original domain, reviewed source version,
profile/settings/output-format context and reviewed provenance across epochs.
Content memory cannot become configuration consent. Safe new local writing may
be preserved by independently applicable same-source policy after current safety
checks; this does not claim the exact old approval covered newly observed bytes.
Changed source/context reopens review, and onboarding/format choices stay separate.
Refresh performs no save/load, apply, cleanup, restoration or recovery; consumers
must supply fresh observations, and later persistence uses canonical validation.
