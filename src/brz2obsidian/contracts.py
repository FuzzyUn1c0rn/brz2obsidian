"""Durable source-neutral contracts. No outer implementations or I/O."""

import json
import unicodedata
from contextlib import AbstractContextManager
from datetime import date
from hashlib import sha256
from typing import BinaryIO, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")


class SourceIdentity(Contract):
    source_id: str
    module_id: str
    module_version: str
    format_version: str
    source_sha256: str
    snapshot_digest: str


class DiagnosticSubject(Contract):
    """Small display metadata, never a note body or transport error."""

    kind: Literal["item", "document", "asset", "relationship"]
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def plain_name(cls, value):
        if any(unicodedata.category(char).startswith("C") for char in value):
            raise ValueError("Diagnostic names must be printable plain text")
        return value


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
    subject: DiagnosticSubject | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class MigrationError(Exception):
    def __init__(self, issues: tuple[Issue, ...], receipt=None):
        super().__init__("; ".join(issue.message for issue in issues))
        self.issues = issues
        self.receipt = receipt


class MigrationRefused(MigrationError):
    pass


class MigrationFailed(MigrationError):
    pass


class ImagePresentationNormalization(Contract):
    """Exact scoped declaration replaced by ordinary responsive presentation."""

    declaration: str
    start: int
    end: int
    document_digest: str
    basis: Literal["document.text/unicode_codepoints"] = (
        "document.text/unicode_codepoints"
    )
    presentation: Literal["responsive"] = "responsive"


class ReferenceSpan(Contract):
    start: int
    end: int
    expected_original: str
    kind: Literal["item", "image"]
    target: str
    display_text: str
    table_cell: bool = False
    document_digest: str
    source_target: str | None = None
    destination_start: int | None = None
    destination_end: int | None = None
    presentation_normalization: ImagePresentationNormalization | None = None


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


class TextAdaptation(Contract):
    """An exact edit from scoped source text into the document's adapted text."""

    kind: Literal["literal_text", "markdown_insert"] = "literal_text"
    start: int
    end: int
    before: str
    after: str
    adapted_start: int
    adapted_end: int
    source_digest: str
    source_basis: Literal["scoped_source_text/unicode_codepoints"] = (
        "scoped_source_text/unicode_codepoints"
    )
    adapted_basis: Literal["document.text/unicode_codepoints"] = (
        "document.text/unicode_codepoints"
    )


class Document(Contract):
    key: str
    owner: str
    text: str
    text_digest: str
    original_asset_id: str | None
    original_copy_omitted: bool = False
    references: tuple[ReferenceSpan, ...] = ()
    text_adaptations: tuple[TextAdaptation, ...] = ()
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
    contract_version: Literal[7] = 7
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
    contract_version: Literal[7] = 7
    entry_required: bool = True
    finding_dispositions: tuple[FindingDisposition, ...] = ()


class Counts(Contract):
    image_presentation_normalizations: int | None = None
    text_adaptations: int | None = None
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
    document_key: str | None = None
    owner: str | None = None
    evidence: tuple[str, ...] = ()
    text_edit: TextAdaptation | None = None


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
    text_adaptations: tuple[TextAdaptation, ...] = ()
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
    schema_version: Literal[7] = 7
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


# Reconciliation facts are in-memory source-neutral values. They describe review;
# they confer no filesystem or history authority.
def reconciliation_subject_id(module_id, collection_id, item_id, facet):
    """Stable source-facet scope shared by proposals and remembered provenance."""
    encoded = json.dumps(
        (module_id, collection_id, item_id, facet),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return sha256(encoded).hexdigest()


class ReconciliationContract(Contract):
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        ser_json_bytes="base64",
        val_json_bytes="base64",
        revalidate_instances="always",
    )

    @field_validator("schema_version", mode="before", check_fields=False)
    @classmethod
    def integer_record_version(cls, value):
        if type(value) is not int:
            raise ValueError("Record version must be an integer")
        return value

    @classmethod
    def model_validate_json(cls, json_data, **kwargs):
        def unique_fields(pairs):
            values = {}
            for key, value in pairs:
                if key in values:
                    raise ValueError(f"Duplicate field: {key}")
                values[key] = value
            return values

        json.loads(json_data, object_pairs_hook=unique_fields)
        return super().model_validate_json(json_data, **kwargs)

    @field_validator(
        "path",
        "current_path",
        "source_path",
        "target_path",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def relative_vault_path(cls, value):
        if (
            not isinstance(value, str)
            or any(c in value for c in "\\:\x00")
            or any(part in ("", ".", "..") for part in value.split("/"))
        ):
            raise ValueError("A canonical relative vault path is required")
        return value

    @field_validator("reviewed_assumptions", check_fields=False)
    @classmethod
    def unique_reviewed_assumptions(cls, value):
        if len({assumption.key for assumption in value}) != len(value):
            raise ValueError("Duplicate reviewed assumption keys")
        return value


class ImmutableContentReference(ReconciliationContract):
    """An immutable locator whose supplied bytes must validate before use."""

    content_id: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)


class ExactContent(ReconciliationContract):
    """Available bytes, optionally retaining a validated immutable locator.

    A locator alone is never available content. Outer stores materialize bytes
    before invoking this contract; equality in reconciliation uses those bytes.
    """

    data: bytes
    reference: ImmutableContentReference | None = None

    @model_validator(mode="after")
    def validate_reference(self):
        if self.reference is not None and (
            len(self.data) != self.reference.size
            or sha256(self.data).hexdigest() != self.reference.sha256
        ):
            raise ValueError(
                "Immutable content reference does not match available bytes"
            )
        return self


class OutputIdentity(ReconciliationContract):
    collection_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    module_version: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    output_format: int = Field(ge=1)
    settings_digest: str = Field(min_length=1)


class ContentVersion(ReconciliationContract):
    status: Literal["known", "unknown"]
    content: ExactContent | None
    unavailable_digest: str | None

    @model_validator(mode="after")
    def available_original(self):
        if (self.status == "known") != (self.content is not None):
            raise ValueError(
                "Known originals require available exact content; "
                "unknown originals cannot contain invented content"
            )
        if self.status == "known" and self.unavailable_digest is not None:
            raise ValueError("Available originals do not use an unavailable digest")
        return self


class CurrentContent(ReconciliationContract):
    existence: Literal["present", "absent", "unknown"]
    path: str
    content: ExactContent | None

    @model_validator(mode="after")
    def consistent_existence(self):
        if (self.existence == "present") != (self.content is not None):
            raise ValueError("Only present current files have available content")
        return self


class FormatBaselineOutput(ReconciliationContract):
    item_id: str = Field(min_length=1)
    facet: str = Field(min_length=1)
    content: ExactContent


class SupportedFormatBaseline(ReconciliationContract):
    """Outer-validated established generated output, never authored current bytes."""

    schema_id: Literal["brz2obsidian.supported-format-baseline"]
    schema_version: Literal[1]
    identity: OutputIdentity
    source_version: str = Field(min_length=1)
    outputs: tuple[FormatBaselineOutput, ...]

    @model_validator(mode="after")
    def distinct_outputs(self):
        keys = [(o.item_id, o.facet) for o in self.outputs]
        if len(set(keys)) != len(keys):
            raise ValueError("Established baseline outputs must be distinct")
        return self


class FormatOperation(ReconciliationContract):
    """Normalized generation capability and source-version facts from outer validation.

    Source versions identify validated source content, never archive paths or times.
    Establishment records bind available generated bytes to identity and source.
    """

    schema_id: Literal["brz2obsidian.format-operation"]
    schema_version: Literal[1]
    kind: Literal["source_update", "onboarding", "format_transition"]
    recorded_generation: Literal["supported", "unavailable", "unknown"]
    baseline_source_version: str | None = Field(min_length=1)
    target_source_version: str | None = Field(min_length=1)
    established_baseline: SupportedFormatBaseline | None


class FormatReview(ReconciliationContract):
    old_identity: OutputIdentity
    target_identity: OutputIdentity
    original_known: bool
    baseline_source_version: str | None = Field(min_length=1)
    target_source_version: str | None = Field(min_length=1)
    output_role: Literal["note", "dashboard", "template", "guide", "configuration"]
    choices: tuple[Literal["keep_current", "use_target", "edit_result"], ...]
    configuration_choice: bool
    target_generated: ExactContent | None
    target_eligible: bool


class StructureSpan(ReconciliationContract):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end < self.start:
            raise ValueError("Structure span ends before its start")
        return self


class StructureField(ReconciliationContract):
    key: str = Field(min_length=1)
    kind: Literal["scalar", "identity", "opaque"]
    identity_component: Literal["collection", "item", "module"] | None
    value: str | int | bool | None
    scalar_type: Literal["string", "integer", "boolean", "null", "date", "opaque"]
    span: StructureSpan
    value_span: StructureSpan

    @model_validator(mode="after")
    def typed_value(self):
        if self.identity_component is not None and self.kind != "identity":
            raise ValueError("Identity components require an identity field")
        if self.kind == "identity" and (self.scalar_type != "string" or not self.value):
            raise ValueError("Imported identity facts require nonempty text identity")
        expected = {
            "string": str,
            "date": str,
            "integer": int,
            "boolean": bool,
            "null": type(None),
            "opaque": type(None),
        }[self.scalar_type]
        if type(self.value) is not expected or (self.kind == "opaque") != (
            self.scalar_type == "opaque"
        ):
            raise ValueError("Structured scalar type and value must agree")
        if (
            not self.span.start
            <= self.value_span.start
            <= self.value_span.end
            <= self.span.end
        ):
            raise ValueError("Scalar value span must stay within its field")
        return self


class StructuredDocument(ReconciliationContract):
    schema_id: Literal["brz2obsidian.structured-document"]
    schema_version: Literal[1]
    output_format: int = Field(ge=1)
    content: ExactContent
    status: Literal["supported", "unsupported", "opaque"]
    issues: tuple[str, ...]
    fields: tuple[StructureField, ...]
    body: StructureSpan

    @model_validator(mode="after")
    def bounded_distinct_fields(self):
        if self.body.end != len(self.content.data):
            raise ValueError("Structure body must end at available content boundary")
        keys = [f.key for f in self.fields]
        if len(set(keys)) != len(keys):
            raise ValueError("Structured property keys must be unique")
        components = [
            f.identity_component
            for f in self.fields
            if f.identity_component is not None
        ]
        if len(set(components)) != len(components):
            raise ValueError("Imported identity components must be unique")
        end = 0
        for field in self.fields:
            if field.span.start < end or field.span.end > self.body.start:
                raise ValueError(
                    "Structure fields must be ordered, disjoint and before body"
                )
            end = field.span.end
        return self


class StructureByteEdit(ReconciliationContract):
    span: StructureSpan
    expected: bytes
    replacement: bytes

    @model_validator(mode="after")
    def exact_span(self):
        if self.span.end - self.span.start != len(self.expected):
            raise ValueError("Edit expected bytes must match span length")
        return self


class StructureComparison(ReconciliationContract):
    schema_id: Literal["brz2obsidian.structure-comparison"]
    schema_version: Literal[1]
    original: StructuredDocument
    current: StructuredDocument
    incoming: StructuredDocument
    alignment: Literal["supported", "ambiguous", "unsupported"]
    issues: tuple[str, ...]
    local_edits: tuple[StructureByteEdit, ...]
    source_edits: tuple[StructureByteEdit, ...]


class ReconciliationSubject(ReconciliationContract):
    item_id: str = Field(min_length=1)
    facet: str = Field(min_length=1)
    path: str
    baseline: ContentVersion
    current: CurrentContent
    incoming: ExactContent | None
    interpretation: Literal["supported", "opaque", "unsupported"]
    title: str | None = None
    source_target: IdentityTargetFacts
    output_role: Literal["note", "dashboard", "template", "guide", "configuration"]
    structure: StructureComparison | None


class ReconciliationInput(ReconciliationContract):
    schema_id: Literal["brz2obsidian.reconciliation-input"]
    schema_version: Literal[1]
    proposal_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    baseline_identity: OutputIdentity
    incoming_identity: OutputIdentity
    subjects: tuple[ReconciliationSubject, ...]
    format_operation: FormatOperation
    inventory: Literal["complete", "partial", "unreadable"]
    safety_facts: tuple[SafetyFact, ...]
    identity_inventory: tuple[IdentityInventoryItem, ...]
    association_decisions: tuple[IdentityAssociationDecision, ...] = ()
    rename_decisions: tuple[RenamePathDecision, ...] = ()
    source_version_memory: tuple[SourceVersionMemory, ...]
    preservation_decisions: tuple[PreservationDecision, ...] = ()

    @model_validator(mode="after")
    def unique_subjects_and_facts(self):
        identities = [(s.item_id, s.facet) for s in self.subjects]
        keys = [f.key for f in self.safety_facts]
        if len(set(identities)) != len(identities) or len(set(keys)) != len(keys):
            raise ValueError("Duplicate subjects or safety fact keys")
        items = {s.item_id for s in self.subjects}
        if any(
            not set(f.subjects) <= items or len(set(f.subjects)) != len(f.subjects)
            for f in self.safety_facts
        ):
            raise ValueError("Safety scopes must name distinct available subjects")
        inventory_keys = [item.entry_id for item in self.identity_inventory]
        if len(set(inventory_keys)) != len(inventory_keys):
            raise ValueError("Duplicate inventory entry IDs")
        decisions = (
            self.association_decisions
            + self.rename_decisions
            + self.preservation_decisions
        )
        if len({decision.decision_id for decision in decisions}) != len(decisions):
            raise ValueError("Duplicate identity/rename decision IDs")
        for family in (self.association_decisions, self.rename_decisions):
            decision_items = [decision.item_id for decision in family]
            if (
                len(set(decision_items)) != len(decision_items)
                or not set(decision_items) <= items
            ):
                raise ValueError("Decisions must name distinct known source items")
        memory_ids = [
            record.provenance.decision_id for record in self.source_version_memory
        ]
        if len(set(memory_ids)) != len(memory_ids) or set(memory_ids) & {
            d.decision_id for d in decisions
        }:
            raise ValueError("Remembered and new decision IDs must be distinct")
        preservation_scopes = [
            (d.item_id, d.facet) for d in self.preservation_decisions
        ]
        if len(set(preservation_scopes)) != len(preservation_scopes) or not set(
            preservation_scopes
        ) <= set(identities):
            raise ValueError(
                "Preservation decisions must name distinct known source facets"
            )
        return self


class SafetyFact(ReconciliationContract):
    """Outer validation bound to a fingerprint and explicit affected item IDs.

    Empty subjects means global scope. Every subject needs identity, target,
    candidate and operation attestations; no absent attestation implies safety.
    Additional mapping, link, policy and history facts retain the same gate.
    """

    key: str = Field(min_length=1)
    kind: Literal[
        "identity",
        "target",
        "candidate",
        "operation",
        "history",
        "policy",
        "mapping",
        "link",
        "content",
    ]
    fingerprint: str = Field(min_length=1)
    status: Literal["safe", "unsafe", "unknown", "active", "recovery_required"]
    subjects: tuple[str, ...]


class ProposalAssumption(ReconciliationContract):
    key: str
    kind: Literal[
        "baseline",
        "current",
        "incoming",
        "identity",
        "inventory",
        "interpretation",
        "format",
        "structure",
        "target",
        "candidate",
        "operation",
        "history",
        "policy",
        "mapping",
        "link",
        "content",
        "memory",
    ]
    fingerprint: str
    depends_on: tuple[str, ...]


class ChangeProvenance(ReconciliationContract):
    producer: Literal[
        "exact-bytes/v1",
        "identity-review/v1",
        "format-review/v1",
        "structure/v1",
        "preservation/v1",
    ]
    rule: Literal[
        "unknown_original",
        "source_absent",
        "local_absent",
        "source_unchanged",
        "unsupported_interpretation",
        "already_current",
        "divergent",
        "source_only",
        "unsafe_input",
        "identity_resolution",
        "rename_review",
        "onboarding_required",
        "format_review",
        "format_source_uncertain",
        "structure_combined",
        "structure_conflict",
        "structure_unbound",
        "structure_unsupported",
        "structure_identity_conflict",
        "structure_ambiguous",
        "local_deleted",
        "restoration_required",
        "remembered_keep",
        "remembered_decline",
        "preservation_decision",
    ]


class ProposedChange(ReconciliationContract):
    change_id: str
    subject_id: str
    item_id: str
    facet: str
    path: str
    target_path: str
    original: ExactContent | None
    current: ExactContent | None
    incoming: ExactContent | None
    result: ExactContent | None
    disposition: Literal[
        "no_change",
        "preserve_vault",
        "compatible",
        "unresolved",
        "refused",
        "identity_resolution",
        "stale",
        "source_absent",
        "local_deleted",
        "restoration",
    ]
    requires_decision: bool
    provenance: ChangeProvenance
    assumptions: tuple[ProposalAssumption, ...]
    decision_dependencies: tuple[str, ...]
    source_version: str | None
    identity_review: IdentityReview
    rename_review: RenameReview | None
    format_review: FormatReview | None
    structure_result: StructuredDocument | None
    preservation_review: PreservationReview | None

    @model_validator(mode="after")
    def conservative_result(self):
        if self.structure_result is not None and (
            self.result is None
            or self.structure_result.content.data != self.result.data
            or self.structure_result.status != "supported"
        ):
            raise ValueError(
                "Structured candidate facts must bind the exact available result"
            )
        unresolved = (
            "unresolved",
            "refused",
            "identity_resolution",
            "stale",
            "restoration",
        )
        if self.identity_review.repair_required and self.disposition not in unresolved:
            raise ValueError(
                "Observed identity repairs remain required independently of a content choice"
            )
        if self.target_path != self.path and (
            self.rename_review is None
            or self.rename_review.status != "accepted"
            or self.rename_review.source_path != self.target_path
            or self.rename_review.current_path != self.path
        ):
            raise ValueError(
                "A changed target path requires the exact reviewed source rename"
            )
        if self.disposition in unresolved:
            if self.result is not None or not self.requires_decision:
                raise ValueError("Unresolved/refused changes cannot choose a result")
        elif self.disposition == "local_deleted":
            if (
                self.current is not None
                or self.result is not None
                or self.requires_decision
            ):
                raise ValueError(
                    "Suppressed local deletion retains absence without selecting bytes"
                )
        elif self.disposition == "compatible":
            if self.result is None or not self.requires_decision:
                raise ValueError("Compatible results still require review")
        elif (
            self.requires_decision
            or self.result is None
            or self.current is None
            or self.result.data != self.current.data
        ):
            raise ValueError(
                "Preservation/no-change results must keep exact current bytes"
            )
        return self


class ReconciliationFinding(ReconciliationContract):
    code: Literal[
        "identity_mismatch",
        "format_transition_required",
        "unsupported_format",
        "profile_transition_required",
        "inventory_uncertain",
        "current_unavailable",
        "missing_safety_facts",
        "unsafe_assumption",
        "unsafe_identity_target",
        "current_inventory_mismatch",
        "stale_identity_decision",
        "unsafe_identity_decision",
        "identity_repair_incomplete",
        "stale_rename_decision",
        "unsafe_rename_target",
        "unsafe_rename_decision",
        "stale_preservation_decision",
        "unsafe_preservation_decision",
        "format_source_changed",
        "format_target_unsupported",
        "format_outputs_unavailable",
    ]
    subject_id: str | None
    blocking: bool
    assumption_keys: tuple[str, ...]


class UpdateProposal(ReconciliationContract):
    schema_id: Literal["brz2obsidian.update-proposal"]
    schema_version: Literal[1]
    proposal_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    changes: tuple[ProposedChange, ...]
    operation: Literal["source_update", "onboarding", "format_transition"]
    findings: tuple[ReconciliationFinding, ...]
    readiness: Literal["ready", "review_required", "refused"]
    ready: bool
    local_changes: tuple[str, ...]
    source_version_memory: tuple[SourceVersionMemory, ...]

    @model_validator(mode="after")
    def consistent_readiness(self):
        change_ids = [c.change_id for c in self.changes]
        subject_ids = [c.subject_id for c in self.changes]
        if len(set(change_ids)) != len(change_ids) or len(set(subject_ids)) != len(
            subject_ids
        ):
            raise ValueError("Proposal changes and subjects must be unique")
        required = (
            "refused"
            if any(f.blocking for f in self.findings)
            or any(c.disposition == "refused" for c in self.changes)
            else "review_required"
            if any(
                c.requires_decision
                or c.identity_review.repair_required
                or (c.rename_review is not None and c.rename_review.requires_decision)
                for c in self.changes
            )
            else "ready"
        )
        if self.readiness != required or self.ready != (required == "ready"):
            raise ValueError(
                "Proposal readiness must reflect every required review and safety finding"
            )
        return self


class ImportedItemIdentity(ReconciliationContract):
    collection_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)


class IdentityTargetFacts(ReconciliationContract):
    """Outer target facts; normalized_path uses Unicode NFC and casefold.

    Core independently checks that key, known unsafe spellings and inventory
    collisions. Containment and access/reparse validation remain outer facts.
    """

    normalized_path: str = Field(min_length=1)
    containment: Literal["contained", "outside", "unknown"]
    status: Literal["safe", "unsafe", "unknown"]


class IdentityInventoryItem(ReconciliationContract):
    entry_id: str = Field(min_length=1)
    identity_state: Literal["valid", "missing", "malformed", "inconsistent"]
    identity: ImportedItemIdentity | None
    raw_identity: str | None
    title: str
    current: CurrentContent
    target: IdentityTargetFacts

    @model_validator(mode="after")
    def consistent_identity_state(self):
        if self.identity_state == "valid" and self.identity is None:
            raise ValueError(
                "A valid observed identity requires its full source identity"
            )
        if self.identity_state == "missing" and self.identity is not None:
            raise ValueError("Missing identity cannot also claim a parsed identity")
        return self


class IdentityCandidate(ReconciliationContract):
    entry_id: str
    current: CurrentContent
    title: str
    identity_state: Literal["valid", "missing", "malformed", "inconsistent"]
    identity: ImportedItemIdentity | None
    suggestion: Literal["identity", "title", "path", "unassociated"]
    eligible: bool
    target_safe: bool
    assumptions: tuple[ProposalAssumption, ...]


class IdentityReview(ReconciliationContract):
    """Observed association and proposed repairs, with no claim of file repair.

    repair_required keeps the update unresolved while observed identities are
    absent, malformed or duplicated, even after an explicit association choice.
    """

    status: Literal["matched", "unresolved", "association_proposed", "stale", "refused"]
    reason: Literal[
        "unique_identity",
        "duplicate_identity",
        "identity_unavailable",
        "decision_stale",
        "decision_unsafe",
        "repair_incomplete",
        "association_proposed",
        "target_unsafe",
        "current_mismatch",
    ]
    selected_entry_id: str | None
    candidates: tuple[IdentityCandidate, ...]
    repair_required: bool
    disassociate_entry_ids: tuple[str, ...]
    decision_id: str | None
    provenance: Literal["unique_identity", "explicit_user", "unresolved"]
    assumptions: tuple[ProposalAssumption, ...]


class RenameReview(ReconciliationContract):
    current_path: str
    source_path: str
    status: Literal["offered", "accepted", "declined", "blocked", "stale"]
    requires_decision: bool
    decision_id: str | None
    provenance: Literal["explicit_user", "unresolved"]
    assumptions: tuple[ProposalAssumption, ...]


class IdentityAssociationDecision(ReconciliationContract):
    """Explicit candidate association and disassociation proposals for review."""

    schema_id: Literal["brz2obsidian.identity-association-decision"]
    schema_version: Literal[1]
    decision_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    collection_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    selected_entry_id: str = Field(min_length=1)
    disassociate_entry_ids: tuple[str, ...]
    reviewed_assumptions: tuple[ProposalAssumption, ...]
    provenance: Literal["explicit_user"]

    @model_validator(mode="after")
    def explicit_distinct_repairs(self):
        if (
            len(set(self.disassociate_entry_ids)) != len(self.disassociate_entry_ids)
            or self.selected_entry_id in self.disassociate_entry_ids
        ):
            raise ValueError(
                "Disassociation proposals must be distinct from the selected entry"
            )
        return self


class RenamePathDecision(ReconciliationContract):
    """Choose the current or incoming source path; arbitrary paths are excluded."""

    schema_id: Literal["brz2obsidian.rename-decision"]
    schema_version: Literal[1]
    decision_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    collection_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    choice: Literal["keep_path", "source_path"]
    reviewed_assumptions: tuple[ProposalAssumption, ...]
    provenance: Literal["explicit_user"]


class SourceMemoryProvenance(ReconciliationContract):
    decision_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    reviewed_assumptions: tuple[ProposalAssumption, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def meaningful_reviewed_fingerprints(self):
        if any(
            not assumption.key
            or len(assumption.fingerprint) != 64
            or set(assumption.fingerprint) - set("0123456789abcdef")
            for assumption in self.reviewed_assumptions
        ):
            raise ValueError("Memory provenance needs named SHA256 review fingerprints")
        return self


class SourceVersionMemory(ReconciliationContract):
    """Reviewed source-facet policy facts; no persisted history or original proof."""

    schema_id: Literal["brz2obsidian.source-version-memory"]
    schema_version: Literal[1]
    collection_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    facet: str = Field(min_length=1)
    source_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_incoming: ExactContent
    choice: Literal["keep_vault", "decline_restoration"]
    provenance: SourceMemoryProvenance

    @model_validator(mode="after")
    def exact_reviewed_version(self):
        if sha256(self.reviewed_incoming.data).hexdigest() != self.source_version:
            raise ValueError(
                "Remembered source version must match available reviewed bytes"
            )
        scope = reconciliation_subject_id(
            self.module_id, self.collection_id, self.item_id, self.facet
        )
        required = {
            f"{scope}:{kind}": kind
            for kind in (
                "identity",
                "inventory",
                "baseline",
                "current",
                "incoming",
                "interpretation",
                "format",
                "structure",
            )
        } | {f"memory:{scope}": "memory", f"identity-review:{scope}": "identity"}
        reviewed = {a.key: a.kind for a in self.provenance.reviewed_assumptions}
        if any(reviewed.get(key) != kind for key, kind in required.items()):
            raise ValueError(
                "Memory provenance lacks mandatory review evidence for its source facet"
            )
        candidate_prefix = f"identity-candidate:{scope}:"
        if not any(
            key.startswith(candidate_prefix)
            and len(key) > len(candidate_prefix)
            and kind == "identity"
            for key, kind in reviewed.items()
        ):
            raise ValueError("Memory provenance lacks its reviewed identity candidate")
        safety = {
            kind
            for key, kind in reviewed.items()
            if key.startswith("safety:") and len(key) > len("safety:")
        }
        if not {"identity", "target", "candidate", "operation"} <= safety:
            raise ValueError(
                "Memory provenance lacks required reviewed safety attestations"
            )
        return self


class PreservationReview(ReconciliationContract):
    kind: Literal["source_absent", "local_deleted", "restoration", "keep_vault"]
    default_choice: Literal["keep_vault", "decline_restoration"]
    choices: tuple[
        Literal["keep_vault", "decline_restoration", "restore_incoming"], ...
    ]
    reviewed_source_version: str | None
    matched_memory_ids: tuple[str, ...]
    provenance: Literal["preservation_default", "source_memory", "explicit_user"]


class PreservationDecision(ReconciliationContract):
    """Current-generation keep/decline choice; restoration remains a later resolution."""

    schema_id: Literal["brz2obsidian.preservation-decision"]
    schema_version: Literal[1]
    decision_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    collection_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    facet: str = Field(min_length=1)
    reviewed_source_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_change_id: str = Field(min_length=1)
    reviewed_assumptions: tuple[ProposalAssumption, ...]
    choice: Literal["keep_vault", "decline_restoration"]
    provenance: Literal["explicit_user"]
