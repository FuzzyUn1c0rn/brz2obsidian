# Reusable migration interfaces

`contracts.py` owns version-2 strict, closed, frozen Pydantic values with
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
independent of hierarchy and source tags. The core requires contract version 2
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
distinctions remain in independent original evidence. Video interpretation is a
later slice; an embed URI never replaces an external resource's original URI.

`MigrationPlan.icon_snapshots` and read-only `Inspection.icon_snapshots` contain
immutable `IconSnapshot(item_key, explicit_icon_asset_id,
appearance_category_key, effective_icon_asset_id)` decisions for created notes.
An owned icon wins; otherwise the validated classification supplies its
definition's icon. The renderer rejects altered snapshot obligations. The
generated member `icon` property remains empty when using a category default;
the body receives a separately editable reference to the effective image.
Each source image is copied once through its existing ownership/path assignment,
and decorative images remain outside Resources. Untyped icon-only items remain
uncreated under the existing selection policy.

All imported item notes, including materialized source tags and definitions,
receive the canonical core: linked `categories`, optional single
`appearance_category` and local-image `icon`, declared `foreground_color` and
`background_color`, optional `created`/`updated`, native `tags`/`aliases` lists,
and paired opaque `source_collection_id`/`source_item_id`. Native scalar links
and identity strings use JSON quoting, which is safe YAML; dates use ISO
calendar spelling. Aliases and semantic properties are not inferred from prose.
Source tags retain their independent native adaptation. Migration item records
retain declared appearance, normalized dates, original metadata evidence and
snapshot decisions; adaptations distinguish these generated additions from
authored content and full source evidence. Migration run time remains separate.

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
embedding category. Template configuration remains the next implementation slice.

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
| `cli.main(argv)` | Arguments, default wiring, text/JSON presentation and exit-code translation |

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
identities and another on-disk format. It proves the same generic modules work
with source/CLI imports blocked; it is not a supported production source format.

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
    converter_version="0.1.0",
    renderer_version="2",
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
`schema_version=2`, `converter_version`, `operation`, `outcome`, `source_identity`,
`profile_id`, `profile_version`, `counts`, `issues`, `inspection`, `receipt`.
Unavailable fields/counts are `null`; issues is an array. Inspect returns planned
item/tag targets, classification assignments, asset targets/inventory,
`DocumentInspection` metadata (digests, original asset, traced references and
evidence, without authored text), adaptations, support artifacts, reserved
support paths and pending checks with no receipt. These are planned obligations;
inspection neither renders nor copies files. Convert returns no inspection
and, after commit, a receipt with actual inventory/counts. The result supports
`RunResult.model_validate_json(...)` round-tripping.

`migration-record.json` exposes `schema="brz2obsidian.migration"`, version 2,
converter/renderer versions, `source_identity`, profile identity, `run_metadata`,
`original_evidence`, `item_targets`, `asset_targets`, `relationships`,
`tag_memberships`, `classification_assignments`, `support_artifacts`,
`reserved_support_paths`, `adaptations`, `source_accounting`, `issues`, `counts` and
`obsidian_configuration`. Document metadata/digests/references/owner targets
are nested in item targets' `documents`; original bodies remain in copied
`.md.original` files. Asset entries include normalized facts, assigned paths or
external links, `source_findings`, and `retained_documents` for owners without
ordinary targets. System relationships retain evidence without navigation.
There is no standalone top-level documents/findings collection.

Schema identities, workflow signatures, existing result fields and outcome/exit
behavior are retained. The closed shapes have changed explicitly: consumers
must accept version 2 rather than interpreting it as version 1. The reviewed
TheBrain module/profile and renderer now use version `2`; BRZ format stays `5`.
`RunMetadata.renderer_version` must be `2` when invoking the renderer directly.
The alternate Folio adapter uses the current contracts with empty classification
and optional appearance/date/video facts, while its source format stays `folio/1`.

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
Reserved future paths create no files. All imported created and intentional
uncreated names share the established sanitation, identity-marker collision and
120-unit stem limits; the publisher includes support reservations in its
240-unit absolute-path and collision checks. Per-category template paths can
reuse the already assigned distinct category stems under `Templates/`.

Every exported JSON record/field remains in original evidence independently
of normalized facts. Consumers needing exact numeric comparisons should use
an exact decimal JSON representation. Reproducibility compares logical decisions
and content while handling explicit run metadata, original evidence order and
reordered-source fingerprints separately. See [independent preservation](../.scratch/brz-to-obsidian-v1/research/real-export-acceptance.md).
