"""Durable source-neutral contracts. No outer implementations or I/O."""

import json
import unicodedata
from collections.abc import Mapping
from contextlib import AbstractContextManager
from datetime import date
from hashlib import sha256
from typing import Annotated, BinaryIO, Literal, Protocol, runtime_checkable

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    PrivateAttr,
    Tag,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic_core import core_schema


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

    kind: Literal[
        "literal_text",
        "markdown_insert",
        "image_unavailable",
        "markdown_insert_image_unavailable",
    ] = "literal_text"
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


class PayloadReader(Protocol):
    def open_payload(self, asset_id: str) -> AbstractContextManager[BinaryIO]: ...


@runtime_checkable
class PayloadReadViews(Protocol):
    """Optional finite copy reader; original session verification stays forceful.

    The view validates selected/consumed bytes and closes with a complete source
    check. Its lifetime ends before the publisher validates staged output.
    """

    def payload_read_view(self) -> AbstractContextManager[PayloadReader]: ...


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
        # Legacy workers need not build review validators until first use.
        defer_build=True,
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
        if value is None:
            return value
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


class ContentIdentity(ReconciliationContract):
    """Exact-value name established by co-admission, not byte availability."""

    content_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)

    @model_validator(mode="after")
    def canonical_name(self):
        if self.content_id != f"sha256:{self.sha256}:{self.size}":
            raise ValueError("Content identity spelling is not canonical")
        return self


class ImmutableContentReference(ReconciliationContract):
    """An immutable locator whose supplied bytes must validate before use."""

    content_id: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)


def _content_model_equal(left, right):
    if type(left) is not type(right):
        return NotImplemented
    return (
        left.__pydantic_private__ == right.__pydantic_private__
        and left.__pydantic_extra__ == right.__pydantic_extra__
        and all(
            getattr(left, name) == getattr(right, name)
            for name in type(left).model_fields
            if name != "occurrence"
        )
    )


def _content_model_hash(value):
    return hash(
        (
            type(value),
            tuple(
                getattr(value, name)
                for name in type(value).model_fields
                if name != "occurrence"
            ),
        )
    )


def _content_mapping_gate(value, info):
    if (
        isinstance(value, Mapping)
        and {"kind", "identity", "occurrence"}.intersection(value)
        and (info.context or {}).get("current_content") is not True
    ):
        raise ValueError("Current content mappings require an explicit codec context")
    return value


def _content_json_gate(value, info):
    if {"kind", "identity", "occurrence"}.intersection(value.model_fields_set) and (
        info.context or {}
    ).get("current_content") is not True:
        raise ValueError("Current content JSON requires an explicit codec context")
    return value


def _content_core_schema(cls, source, handler):
    # Preserve Pydantic's JSON byte decoding. Typed constructors explicitly opt
    # into declarations; schema-driven mappings retain the legacy default.
    schema = handler(source)
    cached = cls.__dict__.get("__pydantic_core_schema__")
    owned = handler.resolve_ref_schema(cached) if isinstance(cached, dict) else None
    if schema is owned and schema["type"] == "json-or-python":
        return schema
    schema = schema.copy()
    reference = schema.pop("ref", None)
    cursor = schema
    while cursor["type"] in ("function-before", "function-after", "function-wrap"):
        cursor["schema"] = cursor["schema"].copy()
        cursor = cursor["schema"]
    if cursor["type"] != "model" or cursor["cls"] is not cls:
        raise TypeError("Unexpected owned content schema")
    cursor["custom_init"] = False
    return core_schema.json_or_python_schema(
        json_schema=core_schema.with_info_after_validator_function(
            _content_json_gate, schema
        ),
        python_schema=core_schema.with_info_before_validator_function(
            _content_mapping_gate, schema
        ),
        ref=reference,
    )


def legacy_content_fields(value):
    """The two old content fields, without materializing an enclosing graph."""
    if type(value) is not InlineExactContent:
        raise ValueError("Legacy content requires available inline bytes")
    return (("data", value.data), ("reference", value.reference))


def _copy_content(value, update, deep):
    original = value.__deepcopy__() if deep else value
    changes = {} if update is None else dict(update)
    if (
        "occurrence" in changes
        and changes["occurrence"] is not None
        and changes["occurrence"] != value.occurrence
    ):
        raise ValueError("A content copy cannot assign another occurrence")
    fields = {name: getattr(original, name) for name in type(original).model_fields}
    changed_bytes = (
        type(value) is InlineExactContent
        and "data" in changes
        and changes["data"] != value.data
    )
    if changed_bytes and "identity" not in changes:
        fields["identity"] = None
    fields.update(changes)
    # The constructor checks every field, including unknown updates, exact
    # inline identity and the complete historical reference declaration.
    result = type(value)(**fields)
    if changed_bytes or result.identity != value.identity:
        if changes.get("occurrence") is not None:
            raise ValueError("Changed content cannot retain an old occurrence")
        object.__setattr__(result, "occurrence", None)
    object.__setattr__(result, "__pydantic_private__", original.__pydantic_private__)
    object.__setattr__(
        result, "__pydantic_fields_set__", value.model_fields_set | changes.keys()
    )
    return result


class InlineExactContent(ReconciliationContract):
    """Available exact bytes; default serialization retains the v1 shape."""

    data: bytes
    reference: ImmutableContentReference | None = None
    kind: Literal["inline"] = "inline"
    identity: ContentIdentity | None = None
    occurrence: tuple[str | int, ...] | None = Field(default=None, exclude=True)

    def __init__(self, /, **data):
        self.__pydantic_validator__.validate_python(
            data, self_instance=self, context={"current_content": True}
        )

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return _content_core_schema(cls, source, handler)

    def __eq__(self, other):
        return _content_model_equal(self, other)

    def __hash__(self):
        return _content_model_hash(self)

    def model_copy(self, *, update=None, deep=False):
        return _copy_content(self, update, deep)

    @model_validator(mode="after")
    def validate_reference(self):
        digest = sha256(self.data).hexdigest()
        identity = ContentIdentity(
            content_id=f"sha256:{digest}:{len(self.data)}",
            sha256=digest,
            size=len(self.data),
        )
        if self.identity is not None and self.identity != identity:
            raise ValueError("Inline content identity differs from its exact bytes")
        object.__setattr__(self, "identity", identity)
        if self.reference is not None and (
            len(self.data) != self.reference.size or digest != self.reference.sha256
        ):
            raise ValueError(
                "Immutable content reference does not match available bytes"
            )
        return self

    @model_serializer(mode="wrap")
    def content_encoding(self, handler, info):
        fields = handler(self)
        if (info.context or {}).get("current_content") is True:
            return fields
        return {
            name: fields[name]
            for name, _ in legacy_content_fields(self)
            if name in fields
        }


ExactContent = InlineExactContent


class OpaqueContent(ReconciliationContract):
    """An exact-value declaration that confers no byte availability."""

    kind: Literal["opaque"] = "opaque"
    identity: ContentIdentity
    reference: ImmutableContentReference | None = None
    occurrence: tuple[str | int, ...] | None = Field(default=None, exclude=True)

    def __init__(self, /, **data):
        self.__pydantic_validator__.validate_python(
            data, self_instance=self, context={"current_content": True}
        )

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return _content_core_schema(cls, source, handler)

    def __eq__(self, other):
        return _content_model_equal(self, other)

    def __hash__(self):
        return _content_model_hash(self)

    def model_copy(self, *, update=None, deep=False):
        return _copy_content(self, update, deep)

    @model_validator(mode="after")
    def compatibility_reference(self):
        if self.reference is not None and (
            self.reference.sha256 != self.identity.sha256
            or self.reference.size != self.identity.size
        ):
            raise ValueError("Historical reference differs from content identity")
        return self

    @model_serializer(mode="wrap")
    def content_encoding(self, handler, info):
        if (info.context or {}).get("current_content") is not True:
            raise ValueError("Opaque content has no v1 inline serialization")
        return handler(self)


def _content_kind(value):
    if type(value) is InlineExactContent:
        return "inline"
    if type(value) is OpaqueContent:
        return "opaque"
    if isinstance(value, Mapping):
        return value.get("kind", "inline")
    return None


ContentValue = Annotated[
    Annotated[InlineExactContent, Tag("inline")]
    | Annotated[OpaqueContent, Tag("opaque")],
    Discriminator(_content_kind),
]


def same_content(left, right):
    """Compare bytes or exact-value declarations; this grants no availability."""
    if left is None or right is None:
        return left is right
    if type(left) is InlineExactContent and type(right) is InlineExactContent:
        return left.data == right.data
    return left.identity == right.identity


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
    content: ContentValue | None
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
    content: ContentValue | None

    @model_validator(mode="after")
    def consistent_existence(self):
        if (self.existence == "present") != (self.content is not None):
            raise ValueError("Only present current files have available content")
        return self


class FormatBaselineOutput(ReconciliationContract):
    item_id: str = Field(min_length=1)
    facet: str = Field(min_length=1)
    content: ContentValue


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

    automatic_merge: bool = Field(default=False, exclude_if=lambda value: not value)
    schema_id: Literal["brz2obsidian.format-operation"]
    schema_version: Literal[1]
    kind: Literal[
        "source_update", "onboarding", "format_transition", "attachment_cleanup"
    ]
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
    target_generated: ContentValue | None
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


class ReferenceTarget(ReconciliationContract):
    schema_id: Literal["brz2obsidian.reference-target"]
    schema_version: Literal[1]
    target_id: str = Field(min_length=1)
    kind: Literal["category", "tag", "relationship", "resource", "note"]
    canonical_path: str | None
    identity: ImportedItemIdentity | None
    target: IdentityTargetFacts | None
    representations: tuple[str, ...]
    validation_fingerprint: str = Field(min_length=1)
    status: Literal["safe", "unsafe", "unknown"]


class MembershipEntry(ReconciliationContract):
    target: ReferenceTarget
    representation: str
    raw: bytes

    @property
    def target_id(self):
        return self.target.target_id


class MembershipSet(ReconciliationContract):
    field_key: str
    kind: Literal["category", "tag"]
    prefix: bytes
    entries: tuple[MembershipEntry, ...]


class ClassificationMapping(ReconciliationContract):
    schema_id: Literal["brz2obsidian.classification-mapping"]
    schema_version: Literal[1]
    classification_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    kind: Literal["category", "tag"]
    source_label: str


class GeneratedSectionBasis(ReconciliationContract):
    schema_id: Literal["brz2obsidian.generated-section-basis"]
    schema_version: Literal[1]
    original: ExactContent
    output_identity: OutputIdentity
    source_version: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    facet: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    kind: Literal["relationship", "resource"]
    span: StructureSpan
    heading: bytes
    generation_fingerprint: str = Field(min_length=1)


class OwnedSection(ReconciliationContract):
    section_id: str = Field(min_length=1)
    kind: Literal["relationship", "resource"]
    span: StructureSpan
    raw: bytes
    entries: tuple[str, ...]
    targets: tuple[ReferenceTarget, ...]


def _structure_requires_inline(
    status, fields, memberships, appearance, sections, body_start
):
    return (
        status == "supported"
        or bool(fields)
        or bool(memberships)
        or appearance is not None
        or bool(sections)
        or body_start != 0
    )


class StructuredDocument(ReconciliationContract):
    schema_id: Literal["brz2obsidian.structured-document"]
    schema_version: Literal[1]
    output_format: int = Field(ge=1)
    content: ContentValue
    status: Literal["supported", "unsupported", "opaque"]
    issues: tuple[str, ...]
    fields: tuple[StructureField, ...]
    body: StructureSpan
    memberships: tuple[MembershipSet, ...]
    appearance_field: str | None
    owned_sections: tuple[OwnedSection, ...]

    @model_validator(mode="after")
    def bounded_distinct_fields(self):
        if _structure_requires_inline(
            self.status,
            self.fields,
            self.memberships,
            self.appearance_field,
            self.owned_sections,
            self.body.start,
        ) and not isinstance(self.content, InlineExactContent):
            raise ValueError(
                "Semantic structure evidence requires available inline content"
            )
        if self.body.end != self.content.identity.size:
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
    prior_mappings: tuple[ClassificationMapping, ...]
    incoming_mappings: tuple[ClassificationMapping, ...]
    section_bases: tuple[GeneratedSectionBasis, ...]


class OperationReversalOutput(ReconciliationContract):
    """One retained selected output; its target ID is not a source item identity."""

    path: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    produced_existence: Literal["present", "absent"]
    produced: ContentValue | None
    current: CurrentContent
    target_existence: Literal["present", "absent"]
    target: ContentValue | None

    @model_validator(mode="after")
    def exact_version_change(self):
        if (
            (self.produced_existence == "present") != (self.produced is not None)
            or (self.target_existence == "present") != (self.target is not None)
            or (self.produced is None and self.target is None)
            or (
                self.produced is not None
                and self.target is not None
                and same_content(self.produced, self.target)
            )
            or self.current.existence == "unknown"
            or self.current.path != self.path
        ):
            raise ValueError(
                "Operation reversal requires an exact proven version change"
            )
        return self


class OperationReversalTarget(ReconciliationContract):
    """Outer-validated selected-output ownership and exact operation versions.

    Origin IDs join the retained canonical decision; they are not authority by
    themselves. Outer history verifies membership and complete inventories again
    before publication. No output row creates a source item or facet.
    """

    schema_id: Literal["brz2obsidian.operation-reversal-target"]
    schema_version: Literal[1]
    operation_id: str = Field(min_length=1)
    operation_kind: Literal["apply", "undo"]
    direction: Literal["finish", "restore"]
    operation_generation: int = Field(ge=1)
    history_fingerprint: str = Field(min_length=1)
    origin_change_id: str = Field(min_length=1)
    origin_decision_id: str = Field(min_length=1)
    owned_targets: tuple[ReferenceTarget, ...]
    outputs: tuple[OperationReversalOutput, ...]

    @model_validator(mode="after")
    def selected_output_membership(self):
        owned = [(t.target_id, t.canonical_path) for t in self.owned_targets]
        rows = [(r.target_id, r.path) for r in self.outputs]
        if (
            not rows
            or len(set(owned)) != len(owned)
            or len({t[1] for t in owned}) != len(owned)
            or len({r[1] for r in rows}) != len(rows)
            or not set(rows) <= set(owned)
        ):
            raise ValueError(
                "Operation reversal requires unique retained owned output joins"
            )
        for stage in ("produced", "target"):
            present = [
                r.target_id
                for r in self.outputs
                if getattr(r, stage + "_existence") == "present"
            ]
            if len(set(present)) != len(present):
                raise ValueError(
                    "One logical reversal target cannot occupy multiple present paths"
                )
        for row in self.outputs:
            if row.produced_existence != row.target_existence:
                continue
            target = next(t for t in self.owned_targets if t.target_id == row.target_id)
            if (
                len(self.outputs) != 1
                or len(self.owned_targets) != 1
                or target.kind != "note"
                or target.identity is not None
            ):
                raise ValueError("A byte reversal requires one identityless document")
        return self


class ReconciliationSubject(ReconciliationContract):
    item_id: str = Field(min_length=1)
    facet: str = Field(min_length=1)
    path: str
    baseline: ContentVersion
    current: CurrentContent
    incoming: ContentValue | None
    interpretation: Literal["supported", "opaque", "unsupported"]
    title: str | None = None
    source_target: IdentityTargetFacts
    output_role: Literal["note", "dashboard", "template", "guide", "configuration"]
    structure: StructureComparison | None
    attachment: AttachmentFacts | None
    automatic_attachment: AttachmentCandidate | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    automatic_attachment_links: tuple[LinkOccurrenceChoice, ...] = Field(
        default=(), exclude_if=lambda value: not value
    )
    automatic_result: ReviewedTextCandidate | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    operation_reversal: OperationReversalTarget | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


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
    link_context: LinkContext | None

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
            decision_items = [(decision.item_id, decision.facet) for decision in family]
            if len(set(decision_items)) != len(decision_items) or not set(
                decision_items
            ) <= set(identities):
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
        "attachment",
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
        "operation-reversal/v1",
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
        "operation_reversal",
        "attachment_cleanup",
    ]


class ProposedChange(ReconciliationContract):
    change_id: str
    subject_id: str
    item_id: str
    facet: str
    path: str
    target_path: str
    original: ContentValue | None
    current: ContentValue | None
    incoming: ContentValue | None
    result: ContentValue | None
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
        "operation_reversal",
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
    attachment_review: AttachmentReview | None

    @model_validator(mode="after")
    def conservative_result(self):
        if self.structure_result is not None and (
            self.result is None
            or not same_content(self.structure_result.content, self.result)
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
            "operation_reversal",
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
            if self.result is None:
                raise ValueError("Compatible results require exact selected bytes")
        elif (
            self.requires_decision
            or self.result is None
            or self.current is None
            or not same_content(self.result, self.current)
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
        "link_context_unavailable",
        "link_context_invalid",
        "link_current_unsafe",
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
    operation: Literal[
        "source_update", "onboarding", "format_transition", "attachment_cleanup"
    ]
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


class IdentityInventoryItem(ReconciliationContract):
    entry_id: str = Field(min_length=1)
    facet: str | None = Field(min_length=1)
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
    facet: str | None = Field(min_length=1)
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
        "operation_owned",
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
    provenance: Literal[
        "unique_identity", "operation_owned", "explicit_user", "unresolved"
    ]
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
    facet: str = Field(min_length=1)
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
    facet: str = Field(min_length=1)
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


class ConfigurationMemoryContext(ReconciliationContract):
    profile_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    settings_digest: str = Field(min_length=1)
    output_format: int = Field(ge=1)


class SourceVersionMemory(ReconciliationContract):
    """Reviewed source-facet policy facts; no persisted history or original proof."""

    schema_id: Literal["brz2obsidian.source-version-memory"]
    schema_version: Literal[1]
    collection_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    facet: str = Field(min_length=1)
    source_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_incoming: ContentValue
    review_domain: Literal["content", "configuration"]
    configuration_context: ConfigurationMemoryContext | None
    choice: Literal["keep_vault", "decline_restoration"]
    provenance: SourceMemoryProvenance

    @model_validator(mode="after")
    def exact_reviewed_version(self):
        if (self.review_domain == "configuration") != (
            self.configuration_context is not None
        ):
            raise ValueError(
                "Configuration memory requires its semantic context; content memory excludes it"
            )
        if self.review_domain == "configuration":
            subject_id = reconciliation_subject_id(
                self.module_id, self.collection_id, self.item_id, self.facet
            )
            expected = sha256(
                json.dumps(
                    self.configuration_context.model_dump(mode="json"), sort_keys=True
                ).encode()
            ).hexdigest()
            if not any(
                a.key == "configuration:" + subject_id
                and a.kind == "policy"
                and a.fingerprint == expected
                for a in self.provenance.reviewed_assumptions
            ):
                raise ValueError(
                    "Configuration memory lacks its explicitly reviewed semantic context"
                )
        if self.reviewed_incoming.identity.sha256 != self.source_version:
            raise ValueError(
                "Remembered source version must match reviewed content identity"
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
    review_domain: Literal["content", "configuration"]
    choice: Literal["keep_vault", "decline_restoration"]
    provenance: Literal["explicit_user"]


class AttachmentDestination(ReconciliationContract):
    path: str
    target: IdentityTargetFacts


class RetainedAttachmentOwnership(ReconciliationContract):
    """Historical generated association, rederived by native history before writing."""

    schema_id: Literal["brz2obsidian.retained-attachment-ownership"]
    schema_version: Literal[1]
    association_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    generation: int = Field(ge=1, le=(1 << 63) - 1)
    identity: ImportedItemIdentity
    facet: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    mapping_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_size: int = Field(ge=0, le=(1 << 63) - 1)
    payload_mode: Literal["100644", "100755"]

    @model_validator(mode="after")
    def safe_historical_path(self):
        self.relative_vault_path(self.source_path)
        return self


class AttachmentRemovalContinuation(ReconciliationContract):
    """A native approved removal already absent in this finish observation."""

    schema_id: Literal["brz2obsidian.attachment-removal-continuation"]
    schema_version: Literal[1]
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    operation_kind: Literal["apply"]
    direction: Literal["finish"]
    operation_generation: int = Field(ge=1, le=(1 << 63) - 1)
    origin_intent_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    prepared_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    history_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    origin_change_id: str = Field(min_length=1)
    origin_decision_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    before_mode: Literal["100644", "100755"]
    before_size: int = Field(ge=0, le=(1 << 63) - 1)
    before_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def safe_removed_path(self):
        self.relative_vault_path(self.path)
        return self


class AttachmentFacts(ReconciliationContract):
    """Canonical resource association plus explicitly attested allocation slots."""

    current_target_id: str = Field(min_length=1)
    allocation_candidates: tuple[AttachmentDestination, ...]
    affected_documents: tuple[str, ...]
    retained_ownership: RetainedAttachmentOwnership | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    removal_continuation: AttachmentRemovalContinuation | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class AttachmentOutput(ReconciliationContract):
    target_id: str = Field(min_length=1)
    path: str
    content: ContentValue
    content_version: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def exact_payload_version(self):
        if self.content.identity.sha256 != self.content_version:
            raise ValueError("Attachment version must bind exact available bytes")
        return self


class AttachmentAlternative(ReconciliationContract):
    choice: Literal["current", "incoming", "both", "remove"]
    outputs: tuple[AttachmentOutput, ...]
    eligible: bool
    operation_bound: bool = Field(default=False, exclude_if=lambda value: not value)
    unavailable_reasons: tuple[
        Literal[
            "content_unavailable",
            "inventory_uncertain",
            "allocation_unavailable",
            "unsafe_target",
            "collision",
            "ownership_unavailable",
        ],
        ...,
    ]

    @model_validator(mode="after")
    def explicit_availability(self):
        if self.eligible:
            complete = (
                bool(self.outputs) and self.choice in ("current", "incoming")
                if self.operation_bound
                else len(self.outputs)
                == (0 if self.choice == "remove" else 2 if self.choice == "both" else 1)
            )
            if self.unavailable_reasons or not complete:
                raise ValueError(
                    "Eligible alternatives require their complete exact outputs"
                )
        elif not self.unavailable_reasons:
            raise ValueError(
                "Unavailable alternatives must explain their missing authority"
            )
        return self


class AttachmentReview(ReconciliationContract):
    incoming_source_path: str
    alternatives: tuple[AttachmentAlternative, ...]
    assumptions: tuple[ProposalAssumption, ...]
    links: tuple[AssociatedLinkReview, ...]
    link_inventory: Literal["complete", "partial", "unreadable", "unknown"]


class LinkFragment(ReconciliationContract):
    kind: Literal["heading", "block"]
    value: str = Field(min_length=1)


class LinkAnchor(ReconciliationContract):
    fragment: LinkFragment
    spans: tuple[StructureSpan, ...]
    raw_parts: tuple[bytes, ...]


class LinkQuery(ReconciliationContract):
    value: str = Field(min_length=1)
    mode: Literal["exact", "shortened"]
    spellings: tuple[str, ...]


class ReferenceDeclarationFacts(ReconciliationContract):
    status: Literal["absent", "blank", "valid", "invalid"]
    query: LinkQuery | None

    @model_validator(mode="after")
    def qualified_query(self):
        if (self.status == "valid") != (self.query is not None):
            raise ValueError("Only a valid reference declaration has a query")
        return self


class MembershipDeclarationFacts(ReconciliationContract):
    status: Literal["absent", "valid", "invalid"]
    queries: tuple[LinkQuery, ...]


class FileRoleFacts(ReconciliationContract):
    """Dialect-qualified roles bound to one exact file version and path."""

    path: str = Field(min_length=1)
    content_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    category: bool
    image_path: bool
    category_memberships: MembershipDeclarationFacts
    provider: ReferenceDeclarationFacts
    owned_icon: ReferenceDeclarationFacts


class LinkTargetFacts(ReconciliationContract):
    schema_id: Literal["brz2obsidian.link-target-facts"]
    schema_version: Literal[1]
    target_id: str = Field(min_length=1)
    existence: Literal[
        "present", "missing", "known_source_gap", "intentionally_uncreated", "unknown"
    ]
    content: ContentValue | None
    fragments: tuple[LinkFragment, ...]
    anchors: tuple[LinkAnchor, ...]
    structure: StructuredDocument | None
    memberships: tuple[str, ...]
    interpretation: Literal["supported", "unsupported", "unknown"]
    file_roles: FileRoleFacts | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    # Read-only association to retained generated content. It creates neither
    # a reconciliation subject nor permission to write this resource.
    resource_origin: RetainedAttachmentOwnership | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def bound_fragment_and_membership_evidence(self):
        if self.file_roles is not None and self.file_roles.content_sha256 != (
            None if self.content is None else self.content.identity.sha256
        ):
            raise ValueError("File roles must bind exact available target bytes")
        if tuple(a.fragment for a in self.anchors) != self.fragments:
            raise ValueError("Fragment facts require exact available anchors")
        for anchor in self.anchors:
            if (
                not isinstance(self.content, InlineExactContent)
                or not anchor.spans
                or len(anchor.spans) != len(anchor.raw_parts)
            ):
                raise ValueError("Fragment evidence requires available content")
            for span, raw in zip(anchor.spans, anchor.raw_parts, strict=True):
                if (
                    span.end > len(self.content.data)
                    or self.content.data[span.start : span.end] != raw
                ):
                    raise ValueError("Fragment evidence must bind exact target bytes")
            if b"#".join(anchor.raw_parts) != anchor.fragment.value.encode("utf-8"):
                raise ValueError("Fragment value must bind its normalized anchor parts")
        if self.structure is not None:
            if self.content is None or not same_content(
                self.structure.content, self.content
            ):
                raise ValueError("Target structure must bind exact available bytes")
            observed = tuple(
                e.target_id for m in self.structure.memberships for e in m.entries
            )
            if observed != self.memberships:
                raise ValueError(
                    "Target membership facts must bind normalized structure"
                )
        elif self.memberships:
            raise ValueError("Membership facts require exact normalized structure")
        return self


class LinkMeaning(ReconciliationContract):
    status: Literal[
        "resolved",
        "missing",
        "known_source_gap",
        "intentionally_uncreated",
        "unknown",
        "ambiguous",
        "unsupported",
        "inventory_uncertain",
        "unsafe",
        "fragment_missing",
        "fragment_ambiguous",
        "external",
    ]
    target_id: str | None
    target_identity: ImportedItemIdentity | None
    path: str | None
    target_version: str | None
    display_text: str
    fragment: LinkFragment | None
    candidates: tuple[str, ...]


class LinkOccurrence(ReconciliationContract):
    occurrence_id: str = Field(min_length=1)
    syntax: Literal["wiki", "markdown"]
    embedded: bool
    span: StructureSpan
    destination_span: StructureSpan
    raw: bytes
    query: LinkQuery | None
    meaning: LinkMeaning


class LinkDocument(ReconciliationContract):
    schema_id: Literal["brz2obsidian.link-document"]
    schema_version: Literal[1]
    document_id: str = Field(min_length=1)
    source_path: str
    content: ExactContent
    path_mode: Literal["vault", "relative", "shortened"]
    inventory: Literal["complete", "partial", "unreadable"]
    status: Literal["supported", "unsupported"]
    issues: tuple[str, ...]
    occurrences: tuple[LinkOccurrence, ...]

    @model_validator(mode="after")
    def exact_distinct_occurrences(self):
        end, keys = 0, set()
        for occurrence in self.occurrences:
            span, destination = occurrence.span, occurrence.destination_span
            if (
                occurrence.occurrence_id in keys
                or not end <= span.start < span.end <= len(self.content.data)
                or not span.start <= destination.start < destination.end <= span.end
                or self.content.data[span.start : span.end] != occurrence.raw
            ):
                raise ValueError(
                    "Link occurrence must bind distinct disjoint exact document bytes"
                )
            keys.add(occurrence.occurrence_id)
            end = span.end
        return self


class LinkContext(ReconciliationContract):
    schema_id: Literal["brz2obsidian.link-context"]
    schema_version: Literal[1]
    inventory: Literal["complete", "partial", "unreadable"]
    current_targets: tuple[ReferenceTarget, ...]
    incoming_targets: tuple[ReferenceTarget, ...]
    current_target_facts: tuple[LinkTargetFacts, ...]
    incoming_target_facts: tuple[LinkTargetFacts, ...]
    current_documents: tuple[LinkDocument, ...]
    incoming_documents: tuple[LinkDocument, ...]


class LinkValidationBaseline(ReconciliationContract):
    """Available prior document and complete normalized lookup evidence."""

    schema_id: Literal["brz2obsidian.link-validation-baseline"]
    schema_version: Literal[1]
    document: LinkDocument
    targets: tuple[ReferenceTarget, ...]
    target_facts: tuple[LinkTargetFacts, ...]
    inventory: Literal["complete", "partial", "unreadable"]


class AssociatedLinkReview(ReconciliationContract):
    document_id: str
    occurrence_id: str | None
    old: LinkMeaning | None
    incoming: LinkMeaning | None
    secondary: LinkMeaning | None
    status: Literal["review", "unchanged", "unsupported"]
    choices: tuple[Literal["keep_current", "use_incoming", "use_secondary"], ...]
    assumptions: tuple[ProposalAssumption, ...]


class LinkValidationFinding(ReconciliationContract):
    code: Literal[
        "link_unbound",
        "link_inventory_uncertain",
        "link_unsupported",
        "link_facts_invalid",
        "link_meaning_mismatch",
        "link_harmed",
        "existing_link_warning",
        "link_membership_invalid",
        "link_appearance_warning",
    ]
    document_id: str
    occurrence_id: str | None
    blocking: bool


class LinkDocumentValidation(ReconciliationContract):
    valid: bool
    findings: tuple[LinkValidationFinding, ...]

    @model_validator(mode="after")
    def truthful_validation_result(self):
        if self.valid != (not any(f.blocking for f in self.findings)):
            raise ValueError("Validation result must agree with its blocking findings")
        return self


class LinkOccurrenceChoice(ReconciliationContract):
    document_id: str = Field(min_length=1)
    occurrence_id: str = Field(min_length=1)
    old: LinkMeaning
    replacement: bytes
    selected: LinkMeaning | None
    expected_memberships: tuple[str, ...]
    provenance: Literal["explicit_user"]


class AttachmentSelection(ReconciliationContract):
    schema_id: Literal["brz2obsidian.attachment-selection"]
    schema_version: Literal[1]
    proposal_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    item_id: str = Field(min_length=1)
    facet: str = Field(min_length=1)
    reviewed_change_id: str = Field(min_length=1)
    reviewed_assumptions: tuple[ProposalAssumption, ...]
    choice: Literal["current", "incoming", "both", "remove"]
    link_choices: tuple[LinkOccurrenceChoice, ...]
    provenance: Literal["explicit_user"]


class AttachmentCandidate(ReconciliationContract):
    schema_id: Literal["brz2obsidian.attachment-candidate"]
    schema_version: Literal[1]
    outputs: tuple[AttachmentOutput, ...]
    documents: tuple[LinkDocument, ...]
    targets: tuple[ReferenceTarget, ...]
    target_facts: tuple[LinkTargetFacts, ...]


class AttachmentValidationFinding(ReconciliationContract):
    code: Literal[
        "attachment_facts_invalid",
        "attachment_stale_selection",
        "attachment_unsafe_input",
        "attachment_unavailable",
        "attachment_payload_mismatch",
        "attachment_target_invalid",
        "attachment_context_incomplete",
        "attachment_link_choice_invalid",
        "attachment_link_choice_missing",
        "attachment_document_changed",
        "attachment_link_invalid",
    ]
    document_id: str | None
    occurrence_id: str | None
    blocking: bool


class AttachmentCandidateValidation(ReconciliationContract):
    valid: bool
    findings: tuple[AttachmentValidationFinding, ...]
    link_findings: tuple[LinkValidationFinding, ...]

    @model_validator(mode="after")
    def truthful_validation_result(self):
        if self.valid != (
            not any(f.blocking for f in self.findings + self.link_findings)
        ):
            raise ValueError("Validation result must agree with its blocking findings")
        return self


class ReviewConsentRequirement(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-consent-requirement"]
    schema_version: Literal[1]
    consent_id: str = Field(min_length=1)
    kind: Literal["tracking", "storage"]
    requirement: Literal["not_required", "required", "unknown", "unsupported"]
    policy: Literal[
        "ordinary",
        "builtin_transform",
        "custom_filter",
        "encryption",
        "lfs",
        "hook",
        "driver",
        "unsupported_layout",
        "unknown",
    ]
    fingerprint: str = Field(min_length=1)
    disclosure: str = Field(min_length=1)
    subjects: tuple[str, ...]


class ReviewPreflight(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-preflight"]
    schema_version: Literal[1]
    operation_status: Literal[
        "idle", "active", "incomplete", "recovery_required", "unknown"
    ]
    state_status: Literal[
        "supported",
        "absent",
        "unsupported_version",
        "unsupported_state",
        "corrupt",
        "unknown",
    ]
    state_schema: str | None
    state_version: int | None
    state_fingerprint: str = Field(min_length=1)
    consents: tuple[ReviewConsentRequirement, ...]

    @model_validator(mode="after")
    def distinct_consents(self):
        if len({c.consent_id for c in self.consents}) != len(self.consents):
            raise ValueError("Review consent IDs must be unique")
        return self


class ReviewedProperty(ReconciliationContract):
    key: str = Field(min_length=1)
    span: StructureSpan
    raw: bytes
    identity_component: Literal["collection", "item", "module"] | None
    identity_value: str | None
    membership_kind: Literal["category", "tag"] | None
    representations: tuple[str, ...]
    targets: tuple[ReferenceTarget, ...]


class TextCandidateDocument(ReconciliationContract):
    schema_id: Literal["brz2obsidian.text-candidate-document"]
    schema_version: Literal[1]
    output_format: int = Field(ge=1)
    content: ExactContent
    status: Literal["safe", "unsafe", "unknown"]
    issues: tuple[str, ...]
    properties: tuple[ReviewedProperty, ...]
    body: StructureSpan
    appearance: str | None
    appearance_present: bool


class ReviewedTextCandidate(ReconciliationContract):
    schema_id: Literal["brz2obsidian.reviewed-text-candidate"]
    schema_version: Literal[1]
    content: ExactContent
    document: TextCandidateDocument
    links: LinkDocument
    link_targets: tuple[ReferenceTarget, ...]
    link_target_facts: tuple[LinkTargetFacts, ...]
    identity: ImportedItemIdentity
    target: IdentityTargetFacts
    validation_fingerprint: str = Field(min_length=1)
    status: Literal["safe", "unsafe", "unknown"]


type ReviewDomain = Literal[
    "reversal",
    "text",
    "compatible_group",
    "configuration",
    "mapping",
    "format",
    "identity",
    "rename",
    "restoration",
    "attachment",
    "tracking",
    "storage",
]


type ReviewChoice = Literal[
    "reverse",
    "remove",
    "approve",
    "current",
    "incoming",
    "edited",
    "accept",
    "decline",
    "associate",
    "keep_path",
    "source_path",
    "restore_incoming",
    "decline_restoration",
    "both",
]


class ReviewAction(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-action"]
    schema_version: Literal[1]
    decision_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    expected_generation: int = Field(ge=1)
    change_id: str = Field(min_length=1)
    reviewed_assumptions: tuple[ProposalAssumption, ...]
    domain: ReviewDomain
    choice: ReviewChoice
    candidate: ReviewedTextCandidate | None
    attachment_selection: AttachmentSelection | None
    attachment_candidate: AttachmentCandidate | None
    selected_entry_id: str | None
    disassociate_entry_ids: tuple[str, ...]


class ReviewApproval(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-approval"]
    schema_version: Literal[1]
    decision_id: str
    change_id: str
    domain: ReviewDomain
    choice: ReviewChoice
    attachment_selection: AttachmentSelection | None
    attachment_candidate: AttachmentCandidate | None
    result: ContentValue | None
    target_path: str
    assumptions: tuple[ProposalAssumption, ...]
    provenance: Literal["explicit_user", "compatible_bulk", "automatic_merge"]
    source_accepted: bool
    source_memory: SourceVersionMemory | None


class ReviewRequirement(ReconciliationContract):
    requirement_id: str
    domain: ReviewDomain
    change_id: str
    choices: tuple[ReviewChoice, ...]
    assumptions: tuple[ProposalAssumption, ...]


class ReviewChoiceAvailability(ReconciliationContract):
    choice: ReviewChoice
    enabled: bool
    reasons: tuple[str, ...]

    @model_validator(mode="after")
    def truthful_availability(self):
        if self.enabled != (not self.reasons):
            raise ValueError("Unavailable choices require their shared reason")
        return self


class ReviewChoiceOffer(ReviewRequirement):
    """Read-only action prerequisites; candidates still require full validation."""

    availability: tuple[ReviewChoiceAvailability, ...]

    @property
    def enabled_choices(self):
        return tuple(row.choice for row in self.availability if row.enabled)


class CompatibleReviewGroup(ReconciliationContract):
    group_id: str
    member_change_ids: tuple[str, ...]
    comparisons: tuple[ProposedChange, ...]
    count: int = Field(ge=1)
    proposed_bytes: int = Field(ge=0)
    assumptions: tuple[ProposalAssumption, ...]


class ReviewConsentDecision(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-consent-decision"]
    schema_version: Literal[1]
    decision_id: str
    consent_id: str
    kind: Literal["tracking", "storage"]
    choice: Literal["accept", "decline"]
    assumptions: tuple[ProposalAssumption, ...]
    provenance: Literal["explicit_user"]


class ReviewProducerApplicability(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-producer-applicability"]
    schema_version: Literal[1]
    original: IdentityAssociationDecision | RenamePathDecision
    proposal_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    reviewed_assumptions: tuple[ProposalAssumption, ...]


class ReviewAttachmentApplicability(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-attachment-applicability"]
    schema_version: Literal[1]
    decision_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    candidate: AttachmentCandidate


class ReviewDependencyNode(ProposalAssumption):
    schema_id: Literal["brz2obsidian.review-dependency-node"]
    schema_version: Literal[1]
    producer: Literal[
        "producer", "candidate", "selected", "coverage", "effect", "consent", "group"
    ]


class ReviewRetention(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-retention"]
    schema_version: Literal[1]
    decision_id: str = Field(min_length=1)
    subject_id: str
    domain: ReviewDomain
    origin_generation: int = Field(ge=1)
    origin_change_id: str
    current_change_id: str
    dependency_keys: tuple[str, ...]


class ReviewRefreshEvent(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-refresh-event"]
    schema_version: Literal[1]
    expected_generation: int = Field(ge=1)
    facts: ReconciliationInput
    preflight: ReviewPreflight
    previous_dependencies: tuple[ReviewDependencyNode, ...]
    dependencies: tuple[ReviewDependencyNode, ...]
    changed_keys: tuple[str, ...]
    invalidated_keys: tuple[str, ...]
    retained: tuple[ReviewRetention, ...]
    producer_applicability: tuple[ReviewProducerApplicability, ...]
    attachment_applicability: tuple[ReviewAttachmentApplicability, ...]


class ReviewKeepCurrentGroup(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-keep-current-group"]
    schema_version: Literal[1]
    group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    actions: tuple[ReviewAction, ...] = Field(min_length=1)


class ReviewHistory(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-history"]
    schema_version: Literal[1]
    initial_facts: ReconciliationInput
    initial_preflight: ReviewPreflight
    events: tuple[ReviewAction | ReviewRefreshEvent | ReviewKeepCurrentGroup, ...]


class ReviewPlan(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-plan"]
    schema_version: Literal[1]
    history: ReviewHistory
    producer_applicability: tuple[ReviewProducerApplicability, ...]
    attachment_applicability: tuple[ReviewAttachmentApplicability, ...]
    facts: ReconciliationInput
    producer_facts: ReconciliationInput
    preflight: ReviewPreflight
    proposal: UpdateProposal
    actions: tuple[ReviewAction, ...]
    approvals: tuple[ReviewApproval, ...]
    consents: tuple[ReviewConsentDecision, ...]
    requirements: tuple[ReviewRequirement, ...]
    groups: tuple[CompatibleReviewGroup, ...]
    blockers: tuple[str, ...]
    readiness: Literal["ready", "review_required", "refused"]
    ready: bool


class SelectedReviewFile(ReconciliationContract):
    """One exact selected result, before outer inventory and disk admission."""

    path: str
    subject_id: str = Field(min_length=1)
    content: ContentValue


class SelectedReviewEffects(ReconciliationContract):
    """Pure selected files and explicit displaced paths from one valid review."""

    schema_id: Literal["brz2obsidian.selected-review-effects"]
    schema_version: Literal[1]
    status: Literal["selected", "refused"]
    code: Literal["selected", "invalid_plan", "review_not_ready", "effect_conflict"]
    proposal_id: str | None
    generation: int | None
    files: tuple[SelectedReviewFile, ...]
    remove_paths: tuple[str, ...]

    @model_validator(mode="after")
    def consistent_effects(self):
        selected = self.status == "selected"
        if selected != (self.code == "selected") or selected != (
            self.proposal_id is not None and self.generation is not None
        ):
            raise ValueError("Selected effect status and identity must agree")
        paths = tuple(file.path for file in self.files)
        if paths != tuple(sorted(set(paths))) or self.remove_paths != tuple(
            sorted(set(self.remove_paths))
        ):
            raise ValueError("Selected effect paths must be unique and sorted")
        if set(paths) & set(self.remove_paths):
            raise ValueError("A selected file cannot also be removed")
        for path in self.remove_paths:
            self.relative_vault_path(path)
        if not selected and (self.files or self.remove_paths):
            raise ValueError("Refused effects cannot authorize files")
        return self


class ReviewTransition(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-transition"]
    schema_version: Literal[1]
    status: Literal["accepted", "stale", "refused"]
    code: Literal[
        "accepted",
        "wrong_proposal",
        "generation_changed",
        "assumptions_changed",
        "unknown_change",
        "choice_not_admitted",
        "invalid_candidate",
        "invalid_plan",
        "preflight_refused",
        "decision_id_reused",
        "unsafe_producer_choice",
        "attachment_invalid",
        "dependency_graph_invalid",
    ]
    plan: ReviewPlan


class SavedReview(ReconciliationContract):
    """Exact historical review value; no claim of currently observed state."""

    schema_id: Literal["brz2obsidian.saved-review"]
    schema_version: Literal[1]
    plan: ReviewPlan


class LoadedReview(ReconciliationContract):
    schema_id: Literal["brz2obsidian.loaded-review"]
    schema_version: Literal[1]
    saved: SavedReview
    readiness: Literal["revalidation_required"]
    ready: Literal[False]
    _historical_effects: SelectedReviewEffects | None = PrivateAttr(default=None)

    @property
    def historical_effects(self) -> SelectedReviewEffects | None:
        """Derived historical comparison only; never current write authority."""
        return self._historical_effects

    @field_validator("ready", mode="before")
    @classmethod
    def explicit_unready_boolean(cls, value):
        if type(value) is not bool:
            raise ValueError("Loaded readiness must be an explicit Boolean")
        return value


class ReviewSaveResult(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-save-result"]
    schema_version: Literal[1]
    status: Literal["saved", "refused"]
    code: Literal["saved", "invalid_review"]
    record: SavedReview | None

    @model_validator(mode="after")
    def coherent_saved_value(self):
        if (self.status == "saved") != (self.record is not None) or (
            self.status == "saved"
        ) != (self.code == "saved"):
            raise ValueError("Save success requires exactly its saved record")
        return self


class ReviewLoadResult(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-load-result"]
    schema_version: Literal[1]
    status: Literal["loaded", "refused"]
    code: Literal[
        "loaded",
        "invalid_record",
        "invalid_review",
        "unsupported_schema",
        "unsupported_version",
    ]
    loaded: LoadedReview | None
    ready: Literal[False]

    @field_validator("ready", mode="before")
    @classmethod
    def explicit_unready_boolean(cls, value):
        if type(value) is not bool:
            raise ValueError("Load readiness must be an explicit Boolean")
        return value

    @model_validator(mode="after")
    def coherent_loaded_value(self):
        if (self.status == "loaded") != (self.loaded is not None) or (
            self.status == "loaded"
        ) != (self.code == "loaded"):
            raise ValueError("Load success requires an unready loaded value")
        return self


class ReviewResumeResult(ReconciliationContract):
    schema_id: Literal["brz2obsidian.review-resume-result"]
    schema_version: Literal[1]
    status: Literal["resumed", "stale", "refused"]
    code: Literal[
        "unchanged",
        "refreshed",
        "invalid_loaded",
        "invalid_current_facts",
        "wrong_proposal",
        "generation_changed",
        "choice_not_admitted",
        "invalid_review",
        "dependency_graph_invalid",
    ]
    loaded: LoadedReview | None
    plan: ReviewPlan | None
    ready: bool

    @model_validator(mode="after")
    def current_authority_only_after_resume(self):
        if (self.status == "resumed") != (self.plan is not None) or self.ready != (
            self.plan is not None and self.plan.ready
        ):
            raise ValueError("Only a resumed current plan can confer readiness")
        if (self.status == "resumed") != (self.code in ("unchanged", "refreshed")) or (
            self.status == "resumed" and self.loaded is None
        ):
            raise ValueError("Resume success needs its loaded provenance")
        return self
