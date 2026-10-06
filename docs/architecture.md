# Reusable migration interfaces

`contracts.py` owns version-3 strict, closed, frozen Pydantic values with
immutable nested tuples. Generic modules treat identities/keys as opaque;
source modules supply stable hexadecimal naming seeds. Original JSON is
independently retained as immutable text and embedded directly in the record,
preserving numeric precision, raw dates and omitted/null distinctions.
Sessions and binary streams are scoped outer resources rather than model fields.

Version 2 adds `Item.role="definition"`, `Relationship.kind="classification"`
and immutable `ClassificationAssignment(relationship_key, definition_key,
item_key, evidence)` values on `SourceSnapshot.classification_assignments`.
Every classification relationship must correspond to exactly one assignment;
members are distinct ordinary items and definitions are live definition items.
The TheBrain adapter additionally joins each populated `TypeId` to exactly one
matching exported instance relationship in both directions. These facts remain
independent of hierarchy and source tags. The core requires contract version 3
even when both supplied snapshot and policy claim the same older version.

The shared contract includes optional immutable destination-independent facts:
`Item.declared_appearance` uses `DeclaredAppearance(icon_asset_id,
foreground_color, background_color)` with normalized `#RRGGBB` colours;
`Item.calendar_dates` uses `CalendarDates(created, updated)` with Python date
values, strict JSON date round-tripping and no timezone conversion;
`Asset.video_presentation` uses `VideoPresentation(provider="youtube", embed_uri,
start_seconds)` with a nonnegative start. The TheBrain adapter now supplies
declared appearance and dates. It recognizes one owned decorative icon,
normalizes only the reviewed signed opaque ARGB colour range, and derives
calendar components from valid creation/overall-modification timestamps without
timezone conversion. Missing/null/empty dates remain empty; invalid populated
dates and unreviewed colour encodings refuse. Exact source values and omitted/null
distinctions remain in independent original evidence. Reviewed YouTube metadata
supplies validated identity/timing facts for a fresh native embed; the exact
external resource URI and original VideoHtml remain separate evidence. Conversion
does not execute archived HTML or fetch remote resources.

`MigrationPlan.icon_snapshots` and read-only `Inspection.icon_snapshots` contain
immutable `IconSnapshot(item_key, explicit_icon_asset_id,
appearance_category_key, effective_icon_asset_id)` decisions for created notes.
An owned icon wins; otherwise the validated classification supplies its
definition's icon. The renderer rejects altered snapshot obligations. The
generated member `icon` property remains empty when using a category default;
the ordinary/member body receives a separately editable reference to the effective
image. Category notes place Parents/Children directly after the heading when
present, followed by contextual Members/Gallery, and omit a generated
introductory image. Their icon properties,
copied assets and neutral effective-icon decisions remain available to Bases.
Source labels, authored Markdown/images, resources and Related navigation follow the
dashboard views. Adaptations identify this presentation without claiming a
category body snapshot that was not generated.
Each source image is copied once through its existing ownership/path assignment,
and decorative images remain outside Resources. Untyped icon-only items remain
uncreated under the existing selection policy.
Before generating an icon property or body snapshot, the Obsidian renderer
requires the selected target to have a reviewed image extension: AVIF, BMP,
GIF, JPEG/JPG, PNG, SVG or WebP. Other selected kinds, including ICO, are
refused before publication. Inspection retains neutral icon evidence with
destination feasibility pending; it does not establish renderability. The
core remains independent of this destination policy, and unselected decorative
payloads are still preserved without creating a note or image presentation.

All imported item notes, including materialized source tags and definitions,
receive the canonical core: linked `categories`, optional single
`appearance_category` and local-image `icon`, optional `created`/`updated`,
native `tags`/`aliases` lists,
and paired opaque `source_collection_id`/`source_item_id`. Native scalar links
and identity strings use JSON quoting, which is safe YAML; dates use ISO
calendar spelling. Aliases and semantic properties are not inferred from prose.
Source tags retain their independent native adaptation. Migration item records
retain declared appearance, normalized dates, original metadata evidence and
snapshot decisions; adaptations distinguish these generated additions from
authored content and full source evidence. Migration run time remains separate.
Declared colours remain source/migration evidence; generated note properties,
templates, property-type configuration and Base views omit colour fields.

The renderer adds category dashboard embeds, a Home-linked `Categories.md`
overview and three shared native `.base` files under `Templates/Bases/`.
Member queries use `list(categories).contains(this)` with the embedding category
identity; their filters exclude Templates/Attachments folders and descendants,
not filename substrings. Overview/provider role guards require a Markdown note
under Categories with the native categories tag. Native image formulas validate
a local nonempty supported-image target before applying an explicit override or
the current valid appearance category's image. Provider validity is separate
from icon override validity, so blank and invalid providers remain distinguishable
without losing a valid override. Membership order never selects a provider.
The source-neutral planner activates and accounts for all Base/overview/native
configuration obligations; renderer adaptations identify added entry/dashboard
content. The native core plugin configuration enables Bases and navigation,
and app configuration keeps Home/bookmarks while enabling link-preserving renames.
Open contextual member Bases through dashboards; standalone Bases have no
embedding category. The renderer also enables bundled Templates, configures its
folder and ISO insertion dates, and manifests canonical property-type settings.
Full templates and future-category starters initialize linked metadata without
imported identities; they neither bind automatically to categories nor enforce
continuing schemas. See [maintenance conventions](vault-maintenance.md).

## Public boundaries

| Operation | Responsibility |
| --- | --- |
| `SourceModule.open(source_ref)` | Context-managed session exposing durable snapshot, source identity, scoped `open_payload(asset_id)` and `verify_consistency()` |
| `core.analyze(snapshot, policy)` | Pure consistency, entry/reference/accounting validation and reviewed finding disposition |
| `core.plan(analysis)` | Pure selections, deterministic naming, created/uncreated targets, resources, graph/tags and edits |
| `obsidian.render(plan, run_metadata)` | Pure generated bytes, copy obligations, manifest and reserved paths |
| `publication.publish(artifacts, payloads, destination)` | Fresh-destination checks, streamed staging, hashes/lengths/manifest verification, commit and owned cleanup |
| `Workflow.inspect(source_ref)` | Shared preparation and planned result with destination/publication checks pending |
| `Workflow.convert(source_ref, destination)` | Fresh preparation, render/publish, session closure and durable actual result |
| `vault_check.check_vault(vault)` | Source-independent contained reads of actual mutable vault conventions and a separate strict version-1 checker result |
| `cli.main(argv)` | Arguments, default wiring, text/JSON presentation and exit-code translation |

The `vault_check` package depends inward on the shared `Contract` policy and
data parsers only. It owns all convention-checking behavior and filesystem
error translation without source, workflow, renderer or publisher dependencies.
The CLI loads migration wiring only for inspect/convert; check-vault operates
with those outer imports unavailable. Its contracts and outcomes are distinct
from migration evidence and receipts. See [checker scope and schema](vault-checker.md).

Operations below Workflow return contracts or raise `MigrationRefused` /
`MigrationFailed` with structured immutable issues on known refusals/failures.
Workflow translates known errors, I/O failures and contract validation errors
into `RunResult`; unexpected programming errors propagate. Warnings accompany
successful results. A receipt describes actual verified publication and survives
later teardown failure.

## Dependency direction and source composition

Contracts import no outer implementation. Core depends inward on contracts and
pure libraries, with no I/O, BRZ enums, UUID interpretation or source paths.
Renderer depends on contracts/core with no source parsing or filesystem access.
Publisher depends on contracts and contains no naming/migration policy. Source
modules interpret formats and depend inward on contracts. Generic Workflow
depends on contracts/core and injected protocols, without importing concrete
source/rendering/publication or CLI modules. Generic initializers preserve this.

`SourceModuleBinding` combines an opener and reviewed `SourcePolicy` through
ordinary composition. `application.wiring.default_workflow()` selects
`BrzSourceModule`, `BRZ_POLICY`, `ObsidianRenderer` and `FilesystemPublisher`.
The source adapter recognizes exact anomaly predicates and supplies versioned
rule IDs/evidence; generic analysis matches explicit profile rule/kind/disposition.
Unknown rules and incompatible versions refuse. There is no registry framework
or runtime warning allowlist.

The test-only Folio adapter in `tests/support/folio_source.py` uses non-UUID
identities and another on-disk format. The original substitution fixture and
its richer classification/icon/date/video fixture prove the same generic modules
work with source/CLI/wiring imports blocked. Folio calendar triplets and explicit
neutral presentation facts are independently authored rather than decoded from
TheBrain metadata. Folio is not a supported production source format.

## Compose a workflow

```python
from brz2obsidian.application import SourceModuleBinding, Workflow
from brz2obsidian.obsidian import ObsidianRenderer
from brz2obsidian.publication import FilesystemPublisher
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY

workflow = Workflow(
    SourceModuleBinding(BrzSourceModule(), BRZ_POLICY),
    ObsidianRenderer(),
    FilesystemPublisher(),
)
inspection = workflow.inspect("source.brz")
result = workflow.convert("source.brz", "new-vault")
```

Replace the binding with a compatible source/profile fitting shared contracts.
Inspect before examining planned targets; conversion repeats validation.

## Invoke modules directly

```python
from brz2obsidian.contracts import RunMetadata
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import render
from brz2obsidian.publication import publish
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY

metadata = RunMetadata(
    converter_version="0.3.0",
    renderer_version="3",
    run_id="example-run",
    run_time="2026-10-04T00:00:00+00:00",
    obsidian_version="1.13.7",
    bookmark_time=1791072000000,
)
with BrzSourceModule().open("source.brz") as session:
    analysis = analyze(session.snapshot, BRZ_POLICY)
    migration_plan = plan(analysis)
    artifacts = render(migration_plan, metadata)
    receipt = publish(artifacts, session, "new-vault")
```

Keep the session open through publication. Context-managed payload streams are
revoked on closure; later session use fails. Plans/artifacts bind to source
SHA-256 and normalized snapshot digest. Publisher checks binding/consistency
before commit. Large assets are streamed. Pure renderer reads no clock;
metadata determines run facts and bookmark time. Workflow's default factory
reads time at the outer boundary; callers may inject a metadata factory.

## Result and migration-record schemas

`RunResult.model_dump_json(by_alias=True)` exposes `schema="brz2obsidian.result"`,
`schema_version=3`, `converter_version`, `operation`, `outcome`, `source_identity`,
`profile_id`, `profile_version`, `counts`, `issues`, `inspection`, `receipt`.
Unavailable fields/counts are `null`; issues is an array. Inspect returns planned
item/tag targets, classification assignments, asset targets/inventory,
`DocumentInspection` metadata (digests, original asset, traced references and
evidence, without authored text), adaptations, support artifacts, reserved
support paths and pending checks with no receipt. These are planned obligations;
inspection neither renders nor copies files. Convert returns no inspection
and, after commit, a receipt with actual inventory/counts. The result supports
`RunResult.model_validate_json(...)` round-tripping.

`migration-record.json` exposes `schema="brz2obsidian.migration"`, version 3,
converter/renderer versions, `source_identity`, profile identity, `run_metadata`,
`original_evidence`, `item_targets`, `asset_targets`, `relationships`,
`tag_memberships`, `classification_assignments`, `support_artifacts`,
`reserved_support_paths`, `adaptations`, `source_accounting`, `issues`, `counts` and
`obsidian_configuration`. Document metadata/digests/references/owner targets
are nested in item targets' `documents`; safe original bodies remain in copied
`.md.original` files. A scoped Document whose original contains excluded
references has `original_asset_id=null` and `original_copy_omitted=true`;
its complete included authored body remains active after exact span removals,
and no altered file is described as an exact original. Asset entries include normalized facts, assigned paths or
external links, `source_findings`, and `retained_documents` for owners without
ordinary targets. System relationships retain evidence without navigation.
There is no standalone top-level documents/findings collection.

Schema identities, workflow signatures, existing result fields and outcome/exit
behavior are retained. The closed shapes have changed explicitly: consumers
must accept version 3 rather than interpreting it as an earlier contract. The reviewed
TheBrain module/profile and renderer now use version `3`; BRZ format stays `5`.
`RunMetadata.renderer_version` must be `3` when invoking the renderer directly.
The alternate Folio adapter retains the earlier empty optional facts and also
exercises independently authored opaque category assignments, owned icons,
calendar triplets and explicit video facts. Its source format stays `folio/1`;
it imports only contracts and does not decode TheBrain fields.

The package and default workflow identify the converter as `0.3.0`. Migration
result/record schemas remain version 3, and the separately versioned convention
checker remains `brz2obsidian.vault-check` version 1. This release version does
not imply native acceptance. The accepted v2 audit remains historical evidence. Version-3 original-archive,
native and user acceptance remain tracked in the
[current implementation frontier](../.scratch/management-leadership-implementation/README.md).

Counts add `source_definitions`, `classification_assignments`, `typed_members`,
`planned_category_notes` / `actual_category_notes` and
`planned_support_files` / `actual_support_files`. Imported note counts include
definition and member notes; support counts are separate. Actual publication
counts remain unavailable until the publisher verifies and commits the files.
`SupportArtifact(relative_path, purpose)` describes each planned generated
support file and appears in the plan, rendered vault and migration record.
The publisher verifies those obligations before reporting actual support counts.

`core/support.py` reserves the complete v2 static support namespace before
imported naming: root overview/guide, generic template and category/member
starters, member/gallery/overview/starter Bases and required configuration.
Only unused conditional listing paths remain reserved without files. All imported created and intentional
uncreated names share the established sanitation, identity-marker collision and
120-unit stem limits; the publisher includes support reservations in its
240-unit absolute-path and collision checks. Per-category template paths can
reuse the already assigned distinct category stems under `Templates/`; their
planned SupportArtifact obligations drive verified support accounting. The
generic template, complete category templates and category/member/Base starters
are generated support rather than imported note counts.

The renderer enables only required native plugins, including Bases/Templates,
configures `Templates` with ISO date insertion and canonical property types,
and preserves Home/bookmark/link settings. `obsidian_configuration` retains the
existing application configuration shape in migration-record schema 3.
`obsidian_core_plugins_configuration`, `obsidian_templates_configuration` and
`obsidian_property_types_configuration` explicitly retain the other generated
configuration dictionaries. Their actual files remain hash/length-manifested.

Templates provide the canonical new-object structure and insertion variables,
with linked membership/provider for category templates, a blank icon override
and no source identity. Manual Templates selection is independent of
membership-driven Bases; no template/base/vault_role registry exists. Existing
memberships are edited directly because full native templates can overwrite
shared scalar fields. `Vault guide.md` documents manual update dates, duplicate
lookup, meaningful entity links, source/new identity and reference adaptations.

Provably included JSON records and safe fields remain in original evidence
independently of normalized facts. Forgotten subjects, associated references
and unscopable history collections are omitted. Safe retained values preserve
exact numbers and omission/null distinctions. Consumers needing exact numeric comparisons should use
an exact decimal JSON representation. Reproducibility compares logical decisions
and content while handling explicit run metadata, original evidence order and
reordered-source fingerprints separately. See [current v2 independent preservation](../.scratch/brz-to-obsidian-v2-implementation/research/colour-property-refinement.md).

| Versioned component | Current value |
| --- | --- |
| Package / converter | `0.3.0` |
| Migration result / record schema | `3` |
| Snapshot / source policy contract | `3` |
| Reviewed TheBrain module / profile | `3` |
| Obsidian renderer | `3` |
| BRZ exchange format | `5` |
| Independent vault-check schema | `1` |

These versions describe different interfaces. A package release is not an
Obsidian application version or a change in the supplied archives' format.

## Included scope and reserved version-3 facts

The source adapter validates global container safety, identities, ownership,
local paths and valid ForgottenDateTime markers before selecting included
records. Raw ownership inspection follows nested containers and serialized
JSON without rewriting retained strings; duplicate-key ownership declarations
all participate in transitive associated-record omission. Unsafe reference
errors use static messages rather than echoing raw targets. Only included items
and incident-safe relationships/assignments reach
planning. Excluded providers contribute no membership or inherited appearance;
a forgotten Home refuses rather than selecting a replacement. Names and
selection use the included graph. No exclusion ledger or individual excluded
count is serialized. Safe source fingerprints and collection identity remain.

Snapshot `source_gaps` holds `SourceGap(owner, asset_id, role, rule_id, evidence)`;
roles distinguish ordinary notes, definition notes and definition icons.
`generated_presentations` holds `GeneratedPresentation(owner, source_gap_asset_id,
kind, image_asset_ids, ordering)`, separate from Documents and ReferenceSpans.
Plans and inspections reserve `SourceGapDiagnostic` (owner target/existence,
outcome, provider and affected members, selected images) and
`GeneratedPresentationTarget` (note path and ordered image paths). The migration
record serializes the same two planned collections. Reviewed ordinary-note
absences carry separate ordered image presentations. Definition-note absences
carry unknown-note diagnostics without a Document or reconstructed presentation.
Definition-icon absences retain owned declarations but yield no effective icon;
their diagnostics identify the provider and only included members without an
explicit icon override. The renderer verifies these joins against the canonical
plan before producing resolving provider/member notices and report links.
Membership and appearance_category remain available for native Base defaults.
Counts reserve source_gaps,
generated_presentations, planned_generated_embeds and actual_generated_embeds;
actual counts stay unknown during inspection. These optional closed shapes do
not assign BRZ numeric meanings to the generic core.
