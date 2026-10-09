"""Durable source-neutral contracts. No outer implementations or I/O."""

from contextlib import AbstractContextManager
from datetime import date
from typing import BinaryIO, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")


class SourceIdentity(Contract):
    source_id: str
    module_id: str
    module_version: str
    format_version: str
    source_sha256: str
    snapshot_digest: str


class Issue(Contract):
    code: str
    severity: Literal["warning", "error"] = "error"
    phase: str
    message: str
    affected: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    rule_id: str | None = None
    guidance: str
    leftover_path: str | None = None


class MigrationError(Exception):
    def __init__(self, issues: tuple[Issue, ...], receipt=None):
        super().__init__("; ".join(issue.message for issue in issues))
        self.issues = issues
        self.receipt = receipt


class MigrationRefused(MigrationError):
    pass


class MigrationFailed(MigrationError):
    pass


class ReferenceSpan(Contract):
    start: int
    end: int
    expected_original: str
    kind: Literal["item", "image"]
    target: str
    display_text: str
    document_digest: str
    source_target: str | None = None
    destination_start: int | None = None
    destination_end: int | None = None


class DeclaredAppearance(Contract):
    """Owned declarations; raw source encoding remains independent evidence."""

    icon_asset_id: str | None = None
    foreground_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    background_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class CalendarDates(Contract):
    """Source-encoded calendar components, without timezone conversion."""

    created: date | None = None
    updated: date | None = None


class VideoPresentation(Contract):
    """Reviewed display facts, independently of the preserved external URI."""

    provider: Literal["youtube"]
    embed_uri: str
    start_seconds: int = Field(default=0, ge=0)


class IconSnapshot(Contract):
    """Planned image snapshot, independent of editable dashboard properties."""

    item_key: str
    explicit_icon_asset_id: str | None = None
    appearance_category_key: str | None = None
    effective_icon_asset_id: str | None = None


class Item(Contract):
    key: str
    original_identity: str
    naming_seed: str = Field(pattern=r"^[0-9a-f]+$")
    title: str
    label: str | None = None
    role: Literal["ordinary", "definition", "tag", "system"] = "ordinary"
    live: bool = True
    document_ids: tuple[str, ...] = ()
    resource_ids: tuple[str, ...] = ()
    declared_appearance: DeclaredAppearance | None = None
    calendar_dates: CalendarDates | None = None
    evidence: tuple[str, ...] = ()


class Relationship(Contract):
    key: str
    kind: Literal["hierarchy", "related", "tag", "system", "classification"]
    item_a: str
    item_b: str
    evidence: tuple[str, ...] = ()


class ClassificationAssignment(Contract):
    relationship_key: str
    definition_key: str
    item_key: str
    evidence: tuple[str, ...] = ()


class Document(Contract):
    key: str
    owner: str
    text: str
    text_digest: str
    original_asset_id: str | None
    original_copy_omitted: bool = False
    references: tuple[ReferenceSpan, ...] = ()
    evidence: tuple[str, ...] = ()


class Asset(Contract):
    asset_id: str
    owner: str
    naming_seed: str = Field(pattern=r"^[0-9a-f]+$")
    original_name: str
    display_name: str | None = None
    role: Literal["note_original", "file", "image", "icon", "url", "directory"]
    availability: Literal["present", "absent", "external"]
    actual_length: int | None = None
    actual_sha256: str | None = None
    external_uri: str | None = None
    video_presentation: VideoPresentation | None = None
    evidence: tuple[str, ...] = ()


class OriginalEvidence(Contract):
    """Canonical JSON preserves every original value, order, omission and null.

    JSON is retained as immutable text; renderer decodes it only for its record.
    Root bytes are separately copied through assets when relevant.
    """

    key: str
    kind: Literal["records", "payload"]
    original_json: str


class SourceFinding(Contract):
    kind: str
    rule_id: str
    affected: tuple[str, ...] = ()
    observed_json: str
    evidence: tuple[str, ...] = ()


class SourceGap(Contract):
    """Reviewed absence semantics; raw source scalars belong to its finding."""

    owner: str
    asset_id: str
    role: Literal["ordinary_note", "definition_note", "definition_icon"]
    rule_id: str
    evidence: tuple[str, ...] = ()


class GeneratedPresentation(Contract):
    """Generated display obligations, never supplied authored references."""

    owner: str
    source_gap_asset_id: str
    kind: Literal["note_images"] = "note_images"
    image_asset_ids: tuple[str, ...]
    ordering: Literal["canonical_asset_identity"] = "canonical_asset_identity"


class SourceGapDiagnostic(Contract):
    gap: SourceGap
    owner_target: str
    owner_created: bool
    outcome: Literal["image_fallback", "unknown_note", "neutral_icon"]
    provider_key: str | None = None
    affected_member_keys: tuple[str, ...] = ()
    image_asset_ids: tuple[str, ...] = ()


class GeneratedPresentationTarget(Contract):
    presentation: GeneratedPresentation
    note_path: str
    image_paths: tuple[str, ...]


class AccountingEntry(Contract):
    identity: str
    disposition: Literal["normalized", "retained_only", "unresolved"]
    references: tuple[str, ...]


class SourceAccounting(Contract):
    entries: tuple[AccountingEntry, ...]


class SourceSnapshot(Contract):
    contract_version: Literal[4] = 4
    identity: SourceIdentity
    collection_title: str
    entry_key: str | None
    items: tuple[Item, ...]
    relationships: tuple[Relationship, ...] = ()
    classification_assignments: tuple[ClassificationAssignment, ...] = ()
    documents: tuple[Document, ...] = ()
    assets: tuple[Asset, ...] = ()
    original_evidence: tuple[OriginalEvidence, ...] = ()
    findings: tuple[SourceFinding, ...] = ()
    source_gaps: tuple[SourceGap, ...] = ()
    generated_presentations: tuple[GeneratedPresentation, ...] = ()
    accounting: SourceAccounting


class FindingDisposition(Contract):
    rule_id: str
    kind: str
    disposition: Literal["warning", "refuse"]
    issue_code: str
    message: str
    guidance: str
    permits_absent_payload: bool = False


class SourcePolicy(Contract):
    profile_id: str
    profile_version: str
    module_id: str
    module_version: str
    format_version: str
    contract_version: Literal[4] = 4
    entry_required: bool = True
    finding_dispositions: tuple[FindingDisposition, ...] = ()


class Counts(Contract):
    source_gaps: int | None = None
    generated_presentations: int | None = None
    planned_generated_embeds: int | None = None
    actual_generated_embeds: int | None = None
    source_items: int | None = None
    source_relationships: int | None = None
    source_references: int | None = None
    present_assets: int | None = None
    planned_notes: int | None = None
    planned_assets: int | None = None
    planned_references: int | None = None
    actual_notes: int | None = None
    actual_assets: int | None = None
    actual_files: int | None = None
    actual_references: int | None = None
    source_tags: int | None = None
    tag_memberships: int | None = None
    native_tag_memberships: int | None = None
    uncreated_tag_memberships: int | None = None
    created_tag_items: int | None = None
    uncreated_tag_items: int | None = None
    source_definitions: int | None = None
    classification_assignments: int | None = None
    typed_members: int | None = None
    planned_category_notes: int | None = None
    actual_category_notes: int | None = None
    planned_support_files: int | None = None
    actual_support_files: int | None = None


class Analysis(Contract):
    snapshot: SourceSnapshot
    policy: SourcePolicy
    entry_key: str
    issues: tuple[Issue, ...] = ()
    counts: Counts


class ItemTarget(Contract):
    item_key: str
    original_identity: str
    original_title: str
    relative_path: str
    created: bool
    creation_reasons: tuple[str, ...]
    vault_tag_token: str | None = None


class AssetTarget(Contract):
    asset_id: str
    relative_path: str | None
    resource_link: str | None = None


class Adaptation(Contract):
    kind: str
    affected: str
    description: str


class TagTarget(Contract):
    tag_key: str
    original_identity: str
    original_name: str
    token: str


class TagMembership(Contract):
    relationship_key: str
    tag_key: str
    item_key: str
    native: bool


class SupportArtifact(Contract):
    relative_path: str
    purpose: Literal[
        "report",
        "migration_record",
        "configuration",
        "listing",
        "overview",
        "guide",
        "template",
        "base",
        "starter",
    ]


class MigrationPlan(Contract):
    analysis: Analysis
    source_identity: SourceIdentity
    profile_id: str
    profile_version: str
    item_targets: tuple[ItemTarget, ...]
    asset_targets: tuple[AssetTarget, ...]
    tag_targets: tuple[TagTarget, ...] = ()
    tag_memberships: tuple[TagMembership, ...] = ()
    tag_memberships_path: str | None = None
    isolated_item_keys: tuple[str, ...] = ()
    uncreated_related_pairs: tuple[tuple[str, str], ...] = ()
    support_artifacts: tuple[SupportArtifact, ...] = ()
    reserved_support_paths: tuple[str, ...] = ()
    icon_snapshots: tuple[IconSnapshot, ...] = ()
    source_gaps: tuple[SourceGapDiagnostic, ...] = ()
    generated_presentations: tuple[GeneratedPresentationTarget, ...] = ()
    adaptations: tuple[Adaptation, ...] = ()
    issues: tuple[Issue, ...] = ()
    counts: Counts


class GeneratedFile(Contract):
    relative_path: str
    content: bytes
    sha256: str


class CopyEntry(Contract):
    relative_path: str
    asset_id: str
    expected_length: int
    expected_sha256: str


class RunMetadata(Contract):
    converter_version: str
    renderer_version: str
    run_id: str
    run_time: str
    obsidian_version: str
    bookmark_time: int


class RenderedVault(Contract):
    source_identity: SourceIdentity
    renderer_version: str
    generated_files: tuple[GeneratedFile, ...]
    copies: tuple[CopyEntry, ...]
    manifest: tuple[str, ...]
    reserved_paths: tuple[str, ...] = ()
    support_artifacts: tuple[SupportArtifact, ...] = ()
    counts: Counts


class VerifiedFile(Contract):
    relative_path: str
    length: int
    sha256: str


class Receipt(Contract):
    destination: str
    source_identity: SourceIdentity
    manifest: tuple[VerifiedFile, ...]
    counts: Counts
    published: Literal[True] = True
    verified: Literal[True] = True


class DocumentInspection(Contract):
    """Durable document obligations without duplicating authored text in results."""

    key: str
    owner: str
    text_digest: str
    original_asset_id: str | None
    original_copy_omitted: bool = False
    references: tuple[ReferenceSpan, ...] = ()
    evidence: tuple[str, ...] = ()


class Inspection(Contract):
    item_targets: tuple[ItemTarget, ...]
    classification_assignments: tuple[ClassificationAssignment, ...] = ()
    asset_targets: tuple[AssetTarget, ...] = ()
    assets: tuple[Asset, ...] = ()
    documents: tuple[DocumentInspection, ...] = ()
    adaptations: tuple[Adaptation, ...] = ()
    support_artifacts: tuple[SupportArtifact, ...] = ()
    reserved_support_paths: tuple[str, ...] = ()
    icon_snapshots: tuple[IconSnapshot, ...] = ()
    source_gaps: tuple[SourceGapDiagnostic, ...] = ()
    generated_presentations: tuple[GeneratedPresentationTarget, ...] = ()
    tag_targets: tuple[TagTarget, ...] = ()
    tag_memberships: tuple[TagMembership, ...] = ()
    tag_memberships_path: str | None = None
    pending_checks: tuple[str, ...] = (
        "destination feasibility",
        "payload copy verification",
        "publication",
    )


class RunResult(Contract):
    schema_: Literal["brz2obsidian.result"] = Field(
        default="brz2obsidian.result", alias="schema"
    )
    schema_version: Literal[4] = 4
    converter_version: str
    operation: Literal["inspect", "convert"]
    outcome: Literal["clean", "warnings", "refused", "failed"]
    source_identity: SourceIdentity | None = None
    profile_id: str | None = None
    profile_version: str | None = None
    counts: Counts | None = None
    issues: tuple[Issue, ...] = ()
    inspection: Inspection | None = None
    receipt: Receipt | None = None


class SourceSession(Protocol):
    snapshot: SourceSnapshot
    source_identity: SourceIdentity

    def open_payload(self, asset_id: str) -> AbstractContextManager[BinaryIO]: ...
    def verify_consistency(self) -> None: ...


class SourceModule(Protocol):
    def open(self, source_ref: object) -> AbstractContextManager[SourceSession]: ...


class Renderer(Protocol):
    def render(
        self, plan: MigrationPlan, run_metadata: RunMetadata
    ) -> RenderedVault: ...


class Publisher(Protocol):
    def publish(
        self, artifacts: RenderedVault, payloads: SourceSession, destination: object
    ) -> Receipt: ...
