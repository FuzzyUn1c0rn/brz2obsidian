"""Closed pure legacy fields and exact, single-request proof continuations.

Nothing in this module can acquire bytes. Occurrences name reconstructed input
positions; they neither locate storage nor establish availability.
"""

from dataclasses import dataclass
from types import UnionType
from typing import Annotated, ForwardRef, Literal, Union, get_args, get_origin

from pydantic import BaseModel, Discriminator, Tag
from pydantic.version import VERSION as _PYDANTIC_VERSION
from pydantic_core import __version__ as _PYDANTIC_CORE_VERSION

from .contracts import (
    ContentIdentity,
    ImmutableContentReference,
    InlineExactContent,
    OpaqueContent,
    _content_kind,
    legacy_content_fields,
)

_declared_schema = None
_CONTENT_DISPATCH_PINNED = (
    _PYDANTIC_VERSION == "2.13.5" and _PYDANTIC_CORE_VERSION == "2.46.5"
)
# One fixed schema-matching cursor: four frames and two three-slot argument
# views. It is reused after each matcher returns, never an input-sized graph.
_CONTENT_DISPATCH_WORKSPACE_M = 4 * 128 + 2 * (64 + 16 * 3)


def _content_branches(annotation, metadata):
    """Recognize only the source-pinned owned callable tagged declaration."""
    if not _CONTENT_DISPATCH_PINNED:
        return None
    annotation, discriminator = _content_discriminator(annotation, metadata)
    if (
        discriminator is None
        or discriminator.discriminator is not _content_kind
        or discriminator.custom_error_type is not None
        or discriminator.custom_error_message is not None
        or discriminator.custom_error_context is not None
        or get_origin(annotation) not in (Union, UnionType)
    ):
        return None
    branches = get_args(annotation)
    if len(branches) != 2:
        return None
    if not _tag_matches(branches[0], InlineExactContent, "inline"):
        return None
    if not _tag_matches(branches[1], OpaqueContent, "opaque"):
        return None
    return branches


def _content_discriminator(annotation, metadata):
    discriminator = None
    for rule in metadata:
        if type(rule) is Discriminator:
            if discriminator is not None:
                return annotation, None
            discriminator = rule
    if get_origin(annotation) is Annotated:
        arguments = get_args(annotation)
        for rule in arguments[1:]:
            if type(rule) is Discriminator:
                if discriminator is not None:
                    return annotation, None
                discriminator = rule
        annotation = arguments[0]
    return annotation, discriminator


def _tag_matches(branch, model, name):
    if get_origin(branch) is not Annotated:
        return False
    arguments = get_args(branch)
    return (
        len(arguments) == 2
        and arguments[0] is model
        and type(arguments[1]) is Tag
        and type(arguments[1].tag) is str
        and arguments[1].tag == name
    )


# Closed source-audited predicate inventories. Collection/raw work is additional
# in _ModelInventory.validators; these counts cover the scalar tests/branches.
_VALIDATOR_STEPS = {
    "canonical_name": 2,
    "validate_reference": 9,
    "compatibility_reference": 4,
    "available_original": 4,
    "consistent_existence": 2,
    "distinct_outputs": 2,
    "ordered": 1,
    "typed_value": 12,
    "bounded_distinct_fields": 13,
    "exact_span": 2,
    "exact_version_change": 10,
    "selected_output_membership": 12,
    "unique_subjects_and_facts": 16,
    "conservative_result": 30,
    "consistent_readiness": 12,
    "consistent_identity_state": 4,
    "explicit_distinct_repairs": 3,
    "meaningful_reviewed_fingerprints": 4,
    "exact_reviewed_version": 16,
    "safe_historical_path": 1,
    "safe_removed_path": 1,
    "exact_payload_version": 1,
    "explicit_availability": 10,
    "qualified_query": 2,
    "bound_fragment_and_membership_evidence": 12,
    "exact_distinct_occurrences": 8,
    "truthful_validation_result": 2,
    "distinct_consents": 2,
    "truthful_availability": 2,
    "consistent_effects": 10,
    "coherent_saved_value": 4,
    "coherent_loaded_value": 4,
    "current_authority_only_after_resume": 8,
}
_FIELD_VALIDATORS = frozenset(
    (
        "integer_record_version",
        "relative_vault_path",
        "unique_reviewed_assumptions",
        "explicit_unready_boolean",
    )
)


def _resolved_annotation(annotation):
    if isinstance(annotation, (str, ForwardRef)):
        # Invalid declared schema retains established validation behavior.
        raise ValueError("Unresolved owned contract annotation")  # noqa: TRY004
    origin = get_origin(annotation)
    if origin is Literal:
        return
    children = get_args(annotation)
    if origin is Annotated:
        children = children[:1]
    for child in children:
        if child is not Ellipsis:
            _resolved_annotation(child)


def resolved_contract_fields(model):
    """Input-independent schema build from the one closed owned namespace.

    This fixed schema workspace is B, not caller metadata or a content cache.
    No input can contribute a class, annotation, namespace or executable.
    """
    global _declared_schema
    if _declared_schema is None:
        from . import contracts

        namespace = vars(contracts)
        models = tuple(
            value
            for value in namespace.values()
            if isinstance(value, type)
            and (
                issubclass(value, contracts.ReconciliationContract)
                or value is contracts.SourceIdentity
            )
            and value.__module__ == contracts.__name__
        )
        fields = {}
        for cls in models:
            cls.model_rebuild(_types_namespace=namespace)
            decorators = cls.__pydantic_decorators__
            if (
                not decorators.model_validators.keys() <= _VALIDATOR_STEPS.keys()
                or not decorators.field_validators.keys() <= _FIELD_VALIDATORS
            ):
                raise ValueError("Owned validator inventory requires a source update")
            for field in cls.model_fields.values():
                _resolved_annotation(field.annotation)
            fields[cls] = cls.model_fields
        _declared_schema = fields
    if model not in _declared_schema:
        raise ValueError("Unknown owned contract class")
    return _declared_schema[model]


@dataclass(frozen=True)
class ModelReservation:
    """Prospective structural units, deliberately distinct from process memory.

    A model owns an object header (256), instance/private field maps (2*256),
    a field-set header (256), and map/set entries (2*64 per declared field).
    Tuples/lists own a64-unit header and16 per slot; mappings/sets use256+64
    per entry. Strings use64+4 per code point; bytes retain a64-unit header
    with their actual bytes charged separately to T/caller-owned inline data.
    Validation workspace separately reserves one256+64*fields mapping per
    model, tuple scratch slots and a64-unit stack frame per maximum depth.
    These pinned conservative conventions do not assert a universal allocator
    bound. Repeated field occurrences count again for reconstruction work.
    """

    retained: int
    temporary: int
    nodes: int
    steps: int
    text: int
    raw_work: int = 0
    encoded: int = 0


class ModelBudgetError(ValueError):
    def __init__(self, nodes, steps):
        super().__init__("Prospective model reservation exhausted")
        self.nodes, self.steps = nodes, steps


def _contract_options(annotation):
    if type(annotation) is tuple:
        return tuple(
            model for child in annotation for model in _contract_options(child)
        )
    _resolved_annotation(annotation)
    if get_origin(annotation) is Annotated:
        return _contract_options(get_args(annotation)[0])
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return (annotation,)
    return tuple(
        model for child in get_args(annotation) for model in _contract_options(child)
    )


class _ModelInventory:
    """Closed structural accounting, not an allocator/process-memory estimate.

    Each visit/constructor/validator operation checks its quota before work.
    The caller reserves128 units per depth for this cursor's annotation/value,
    field iterator, alternative index and return counters. Schema tuples/maps
    are fixed B; this walk never builds an input-sized field/alternative map.
    """

    def __init__(self, node_limit, step_limit, depth_limit, metadata_limit, validate):
        self.node_limit, self.step_limit = node_limit, step_limit
        self.depth_limit, self.metadata_limit = depth_limit, metadata_limit
        self.validate = validate
        self.retained = self.temporary = self.nodes = self.steps = 0
        self.text = self.raw_work = self.encoded = 0

    def charge(self, *, nodes=0, steps=0, retained=0, temporary=0):
        if (
            nodes > self.node_limit - self.nodes
            or steps > self.step_limit - self.steps
            or retained + temporary
            > self.metadata_limit - self.retained - self.temporary
        ):
            raise ModelBudgetError(self.nodes, self.steps)
        self.nodes += nodes
        self.steps += steps
        self.retained += retained
        self.temporary += temporary

    def sequence(self, count, *, pairs=False):
        self.charge(
            steps=count, temporary=64 + 16 * count + (96 * count if pairs else 0)
        )

    def mapping(self, count):
        self.charge(steps=count, temporary=256 + 64 * count)

    def error(self, depth):
        # Code/context header, input reference and a bounded location tuple.
        self.charge(temporary=256 + 16 * depth, steps=1)

    @staticmethod
    def field(value, name, default=None):
        return (
            value.get(name, default)
            if type(value) is dict
            else getattr(value, name, default)
        )

    def path(self, value):
        if type(value) is str:
            self.charge(steps=len(value))
            pieces = value.count("/") + 1
            # Forbidden-character scans, split and piece checks; substrings
            # together contain at most the original number of characters.
            self.charge(
                steps=4 * len(value) + pieces,
                temporary=64 + 16 * pieces + 64 * pieces + 4 * len(value),
            )

    def json_bound(self, value, depth):
        if depth > self.depth_limit:
            raise ModelBudgetError(self.nodes, self.steps)
        self.charge(nodes=1, steps=1)
        if isinstance(value, BaseModel):
            fields = resolved_contract_fields(type(value))
            self.mapping(len(fields))
            result = 2
            for name in fields:
                result += (
                    12 * len(name)
                    + 4
                    + self.json_bound(getattr(value, name), depth + 1)
                )
            return result
        if type(value) in (tuple, list):
            self.sequence(len(value))
            result = 2
            for child in value:
                result += 1 + self.json_bound(child, depth + 1)
            return result
        if type(value) is str:
            return 2 + 12 * len(value)
        if type(value) is int:
            return 2 + value.bit_length()
        if value is None or type(value) is bool:
            return 5
        raise ValueError("Uninventoried validator JSON value")

    def json_hash(self, value, depth):
        size = self.json_bound(value, depth)
        # ensure_ascii JSON text, encoded bytes and SHA object/digest coexist.
        self.charge(temporary=64 + 4 * size + 64 + size + 256 + 320)
        self.raw_work += size + 1
        self.encoded += size

    def compare_content(self, left, right):
        self.charge(steps=1)
        if type(left) is InlineExactContent and type(right) is InlineExactContent:
            self.raw_work += len(left.data) + len(right.data) + 2

    def compare_span(self, content, span, expected):
        self.charge(steps=1)
        if type(content) is InlineExactContent and type(expected) is bytes:
            start, end = self.field(span, "start", 0), self.field(span, "end", 0)
            length = min(max(0, end - start), len(content.data))
            self.charge(temporary=64 + length)
            # Slice materialization and the comparison read of both byte values.
            self.raw_work += 2 * (length + 1) + len(expected) + 1

    def validators(self, model, value, depth):
        name = model.__name__
        get = lambda key, default=None: self.field(value, key, default)
        # Model-level after validators can raise one error after field parsing.
        for validator in model.__pydantic_decorators__.model_validators:
            self.charge(steps=_VALIDATOR_STEPS[validator])
            self.error(depth)
        if name in (
            "InlineExactContent",
            "ContentIdentity",
            "SupportedFormatBaseline",
            "StructureField",
            "StructuredDocument",
            "OperationReversalOutput",
            "OperationReversalTarget",
        ):
            self._content_validator_work(name, get)
        elif name in (
            "ReconciliationInput",
            "UpdateProposal",
            "ProposedChange",
            "IdentityAssociationDecision",
            "SourceMemoryProvenance",
            "SourceVersionMemory",
            "RetainedAttachmentOwnership",
            "AttachmentRemovalContinuation",
        ):
            self._decision_validator_work(name, get, depth)
        else:
            self._evidence_validator_work(name, get)

    def _reversal_target_work(self, get):
        owned, rows = get("owned_targets", ()), get("outputs", ())
        self.sequence(len(owned), pairs=True)
        self.sequence(len(rows), pairs=True)
        for count in (len(owned), len(owned), len(rows), len(rows), len(owned)):
            self.mapping(count)
        for _ in range(2):
            self.sequence(len(rows))
            self.mapping(len(rows))
        self.charge(steps=len(rows) * len(owned))

    def _content_validator_work(self, name, get):
        if name == "InlineExactContent":
            data = get("data")
            if type(data) is bytes:
                self.raw_work += len(data) + 1
            # Hash object/digest/canonical spelling plus nested identity model.
            self.charge(temporary=256 + 320 + 512 + 1024 + 128 * 3 + 256 + 64 * 3)
        elif name == "ContentIdentity":
            size = get("size", 0)
            digits = size.bit_length() + 1 if type(size) is int else 1
            self.charge(temporary=64 + 4 * (72 + digits), steps=1)
        elif name == "SupportedFormatBaseline":
            count = len(get("outputs", ()))
            self.sequence(count, pairs=True)
            self.mapping(count)
        elif name == "StructureField":
            self.mapping(6)
        elif name == "StructuredDocument":
            count = len(get("fields", ()))
            self.sequence(count)
            self.mapping(count)
            self.sequence(count)
            self.mapping(count)
            self.charge(steps=count)
        elif name == "OperationReversalOutput":
            self.compare_content(get("produced"), get("target"))
        elif name == "OperationReversalTarget":
            self._reversal_target_work(get)

    def _decision_validator_work(self, name, get, depth):
        if name == "ReconciliationInput":
            self._reconciliation_input_work(get)
        elif name == "UpdateProposal":
            count = len(get("changes", ()))
            self.sequence(count)
            self.mapping(count)
            self.sequence(count)
            self.mapping(count)
            self.charge(steps=len(get("findings", ())) + 2 * count)
        elif name == "ProposedChange":
            structure = get("structure_result")
            if structure is not None:
                self.compare_content(self.field(structure, "content"), get("result"))
            self.compare_content(get("result"), get("current"))
        elif name == "IdentityAssociationDecision":
            self.mapping(len(get("disassociate_entry_ids", ())))
        elif name == "SourceMemoryProvenance":
            for assumption in get("reviewed_assumptions", ()):
                self.charge(steps=1)
                self.mapping(len(self.field(assumption, "fingerprint", "")))
                self.mapping(16)
                self.mapping(64)
        elif name == "SourceVersionMemory":
            self._source_memory_work(get, depth)
        elif name in ("RetainedAttachmentOwnership", "AttachmentRemovalContinuation"):
            self.path(
                get("source_path" if name == "RetainedAttachmentOwnership" else "path")
            )

    def _reconciliation_input_work(self, get):
        subjects, safety = get("subjects", ()), get("safety_facts", ())
        self.sequence(len(subjects), pairs=True)
        self.sequence(len(safety))
        self.mapping(len(subjects))
        self.mapping(len(safety))
        self.mapping(len(subjects))
        for fact in safety:
            self.charge(steps=1)
            count = len(self.field(fact, "subjects", ()))
            self.mapping(count)
            self.mapping(count)
        count = len(get("identity_inventory", ()))
        self.sequence(count)
        self.mapping(count)
        association, rename, preservation = (
            get(key, ())
            for key in (
                "association_decisions",
                "rename_decisions",
                "preservation_decisions",
            )
        )
        decisions = len(association) + len(rename) + len(preservation)
        self.sequence(len(association) + len(rename))
        self.sequence(decisions)
        self.mapping(decisions)
        for family in (association, rename, preservation):
            self.sequence(len(family), pairs=True)
            self.mapping(len(family))
            self.mapping(len(family))
            self.mapping(len(subjects))
        count = len(get("source_version_memory", ()))
        self.sequence(count)
        self.mapping(count)
        self.mapping(count)
        self.mapping(decisions)
        self.mapping(min(count, decisions))

    def _source_memory_work(self, get, depth):
        self.sequence(4)
        scope = tuple(
            get(key, "") for key in ("module_id", "collection_id", "item_id", "facet")
        )
        self.json_hash(scope, depth + 1)
        context = get("configuration_context")
        if context is not None:
            self.json_hash(scope, depth + 1)
            self.json_hash(context, depth + 1)
        self.mapping(8)
        self.mapping(2)
        self.mapping(10)
        self.charge(temporary=10 * (64 + 4 * 96) + 64 + 4 * 96)
        provenance = get("provenance")
        count = len(self.field(provenance, "reviewed_assumptions", ()))
        self.mapping(count)
        self.mapping(count)
        self.mapping(4)
        self.charge(steps=3 * count + 10)

    def _evidence_validator_work(self, name, get):
        if name == "LinkTargetFacts":
            self._target_evidence(get)
        elif name == "LinkDocument":
            self._link_occurrences(get)
        elif name in ("LinkDocumentValidation", "AttachmentCandidateValidation"):
            count = len(get("findings", ()))
            if name == "AttachmentCandidateValidation":
                count += len(get("link_findings", ()))
                self.sequence(count)
            self.charge(steps=count)
        elif name == "ReviewPreflight":
            self.mapping(len(get("consents", ())))
        elif name == "SelectedReviewEffects":
            files, removals = get("files", ()), get("remove_paths", ())
            self.sequence(len(files))
            for count in (len(files), len(removals)):
                self.mapping(count)
                self.sequence(count)
                self.sequence(count)
                self.mapping(count)
                self.charge(steps=count * (count.bit_length() + 1))
            self.mapping(min(len(files), len(removals)))
            for path in removals:
                self.charge(steps=1)
                self.path(path)

    def _target_evidence(self, get):
        anchors = get("anchors", ())
        self.sequence(len(anchors))
        for anchor in anchors:
            self.charge(steps=1)
            total = 0
            spans = self.field(anchor, "spans", ())
            parts = self.field(anchor, "raw_parts", ())
            for span, part in zip(spans, parts):
                self.compare_span(get("content"), span, part)
            for part in parts:
                self.charge(steps=1)
                length = len(part)
                self.charge(temporary=64 + length)
                self.raw_work += length + 1
                total += length + 1
            fragment = self.field(anchor, "fragment")
            encoded = 4 * len(self.field(fragment, "value", ""))
            self.charge(temporary=128 + total + encoded)
            self.raw_work += 2 * (total + encoded + 2)
        structure = get("structure")
        if structure is not None:
            self.compare_content(self.field(structure, "content"), get("content"))
            count = 0
            for membership in self.field(structure, "memberships", ()):
                self.charge(steps=1)
                count += len(self.field(membership, "entries", ()))
            self.sequence(count)

    def _link_occurrences(self, get):
        occurrences = get("occurrences", ())
        self.mapping(len(occurrences))
        for occurrence in occurrences:
            self.charge(steps=1)
            self.compare_span(
                get("content"),
                self.field(occurrence, "span"),
                self.field(occurrence, "raw", b""),
            )

    def _tag_repr_bound(self, value, depth):
        """Bound invalid-tag formatting without invoking caller repr/hash/eq."""
        if depth > self.depth_limit:
            raise ModelBudgetError(self.nodes, self.steps)
        self.charge(nodes=1, steps=1)
        kind = type(value)
        if kind is str:
            self.charge(steps=len(value))
            return 2 + 12 * len(value)
        if kind is bytes:
            self.charge(steps=len(value))
            return 3 + 4 * len(value)
        if kind is int:
            return 2 + value.bit_length()
        if value is None or kind is bool:
            return 5
        if kind in (tuple, list):
            size = 2
            for child in value:
                size += 2 + self._tag_repr_bound(child, depth + 1)
            return size
        if kind is dict:
            size = 2
            for key, child in value.items():
                size += 4 + self._tag_repr_bound(key, depth + 1)
                size += self._tag_repr_bound(child, depth + 1)
            return size
        raise ValueError("Uninventoried content discriminator tag")

    def _tagged_content(self, branches, item, depth):
        # Match the actual owned discriminator without invoking a caller Mapping
        # getter. Other input kinds produce tag-not-found; arbitrary tag values
        # are never compared, hashed or formatted by this prewalk.
        self.charge(steps=1, temporary=16 + 256 + 64 * 3)
        kind = type(item)
        tag = (
            "inline"
            if kind is InlineExactContent
            else "opaque"
            if kind is OpaqueContent
            else item.get("kind", "inline")
            if kind is dict
            else None
        )
        if type(tag) is str:
            self.charge(steps=len(tag) + 1)
            if tag == "inline":
                self.walk(branches[0], item, depth + 1)
                return
            if tag == "opaque":
                self.walk(branches[1], item, depth + 1)
                return
        self.error(depth)
        if tag is not None:
            size = self._tag_repr_bound(tag, depth + 1)
            # Formatted tag text and its UTF8 spelling can coexist in the
            # pinned Rust invalid-tag error context. Selected models do not.
            self.charge(temporary=64 + 4 * size + 64 + 4 * size)
            self.raw_work += 4 * size + 1

    def walk(self, annotation, item, depth, *, metadata=()):
        if not self._begin_walk(annotation, item, depth, metadata):
            return
        origin = get_origin(annotation)
        if origin is Annotated:
            self.walk(get_args(annotation)[0], item, depth + 1)
            return
        if origin in (Union, UnionType) or type(annotation) is tuple:
            alternatives = (
                annotation if type(annotation) is tuple else get_args(annotation)
            )
            for alternative in alternatives:
                # Separate attempted graphs/errors; never merge equal field names.
                self.walk(alternative, item, depth + 1)
            return
        selected = self._walk_model_type(annotation, item)
        if selected is not None:
            self._walk_model(selected, item, depth)
            return
        if type(item) is dict:
            self.charge(retained=256 + 64 * len(item))
            for name, child in item.items():
                self.walk(None, name, depth + 1)
                self.walk(None, child, depth + 1)
            return
        if type(item) in (tuple, list):
            self.charge(
                nodes=1 if self.validate else 0,
                retained=64 + 16 * len(item),
                temporary=64 + 16 * len(item) if self.validate else 0,
            )
            args = get_args(annotation)
            for index, child in enumerate(item):
                child_type = (
                    args[0]
                    if len(args) == 2 and args[1] is Ellipsis
                    else args[index]
                    if index < len(args)
                    else None
                )
                self.walk(child_type, child, depth + 1)
            return
        self._walk_leaf(item, depth)

    def _begin_walk(self, annotation, item, depth, metadata):
        if depth > self.depth_limit:
            raise ModelBudgetError(self.nodes, self.steps)
        self.charge(nodes=1, steps=1)
        if self.validate:
            branches = _content_branches(annotation, metadata)
            if branches is not None:
                self._tagged_content(branches, item, depth)
                return False
        if self.validate and annotation is type(None) and item is not None:
            # A None leaf checks the existing input, not its descendants.
            # Keep a conservative input-alias and error/location allowance.
            self.charge(temporary=16)
            self.error(depth)
            return False
        return True

    @staticmethod
    def _walk_model_type(annotation, item):
        selected = (
            annotation
            if isinstance(annotation, type) and issubclass(annotation, BaseModel)
            else None
        )
        if selected is None and isinstance(item, BaseModel) and annotation is None:
            selected = type(item)
        return selected

    def _walk_extra_fields(self, selected, item, fields, depth):
        for name, child in item.items():
            self.charge(steps=1)
            if name not in fields:
                self.walk(None, name, depth + 1)
                if (
                    self.validate
                    and selected.__module__ == "brz2obsidian.contracts"
                    and selected.model_config.get("extra") == "forbid"
                    and type(name) is str
                ):
                    # Pinned Python-input ExtraForbidden retains the
                    # already owned input by reference, not a rebuilt
                    # subtree. Keep key/location and error charges.
                    self.charge(nodes=1, steps=1, temporary=16)
                else:
                    self.walk(None, child, depth + 1)
                self.error(depth + 1)

    def _walk_model(self, selected, item, depth):
        fields = (
            resolved_contract_fields(selected)
            if selected.__module__ == "brz2obsidian.contracts"
            else selected.model_fields
        )
        if isinstance(item, selected) and type(item) is not selected:
            raise ValueError("Caller-defined model subclasses are not owned schemas")
        if type(item) is not dict and type(item) is not selected:
            self.error(depth)
            return
        self.charge(
            nodes=1 if self.validate else 0,
            retained=1024 + 128 * len(fields),
            temporary=256 + 64 * len(fields) if self.validate else 0,
        )
        for name, field in fields.items():
            self.charge(steps=1)
            child = self.field(
                item, name, None if field.is_required() else field.default
            )
            self.walk(field.annotation, child, depth + 1, metadata=field.metadata)
            if self.validate:
                self.error(depth + 1)
                self.charge(steps=1 + len(field.metadata))
                if type(child) is str and any(
                    getattr(rule, "pattern", None) is not None
                    for rule in field.metadata
                ):
                    self.charge(steps=len(child))
                if name in ("path", "current_path", "source_path", "target_path"):
                    self.path(child)
                if name == "reviewed_assumptions" and type(child) in (tuple, list):
                    self.mapping(len(child))
        if self.validate:
            self.validators(selected, item, depth)
        if type(item) is dict:
            self._walk_extra_fields(selected, item, fields, depth)

    def _walk_leaf(self, item, depth):
        if isinstance(item, BaseModel):
            # A failed ordinary-union alternative does not inspect attributes of
            # a model of another type, but its error/work remains accounted.
            self.error(depth)
        elif type(item) is str:
            self.charge(retained=64 + 4 * len(item))
        elif type(item) is bytes:
            self.charge(retained=64)
            self.text += len(item)
        elif item is None or type(item) is bool:
            self.charge(retained=16)
        elif type(item) is int:
            self.charge(retained=64 + (item.bit_length() + 7) // 8)
        else:
            raise ValueError("Unsupported prospective model value")


def prospective_model(
    model,
    value,
    *,
    node_limit,
    depth_limit,
    step_limit=None,
    metadata_limit=(1 << 63),
    reconstruction=None,
):
    """Inventory every declared attempt before constructing a caller graph."""
    inventory = _ModelInventory(
        node_limit,
        node_limit if step_limit is None else step_limit,
        depth_limit,
        metadata_limit,
        model is not None if reconstruction is None else reconstruction,
    )
    try:
        if inventory.validate and _CONTENT_DISPATCH_PINNED:
            inventory.charge(temporary=_CONTENT_DISPATCH_WORKSPACE_M)
        inventory.walk(model, value, 1)
    except ModelBudgetError:
        raise
    except ValueError, TypeError, AttributeError, KeyError:
        # Invalid typed/model-construct input still consumed prospective work.
        # The public facade sanitizes the reason; no partial count is forgotten.
        raise ModelBudgetError(inventory.nodes, inventory.steps) from None
    return ModelReservation(
        inventory.retained,
        inventory.temporary,
        inventory.nodes,
        inventory.steps,
        inventory.text,
        inventory.raw_work,
        inventory.encoded,
    )


@dataclass(frozen=True)
class LegacyObject:
    fields: tuple


@dataclass(frozen=True)
class ContentOccurrence:
    identity: ContentIdentity
    occurrence: tuple
    reference: ImmutableContentReference | None
    inline: bytes | None = None


@dataclass(frozen=True)
class ExecutionContext:
    operation: object
    operation_ordinal: int
    epoch: int
    next_ordinal: int


@dataclass(frozen=True)
class RequestToken:
    operation: object
    operation_ordinal: int
    ordinal: int
    epoch: int
    kind: str
    scope: tuple


def request_token(context, kind, scope):
    return RequestToken(
        context.operation,
        context.operation_ordinal,
        context.next_ordinal,
        context.epoch,
        kind,
        scope,
    )


@dataclass(frozen=True)
class FingerprintRequest:
    recipe: str
    dialect: str
    scope: tuple
    epoch: int
    tree: object
    occurrences: tuple[ContentOccurrence, ...]
    token: RequestToken


@dataclass(frozen=True)
class FingerprintResult:
    request: FingerprintRequest
    sha256: str
    encoded_size: int


def consume_fingerprint(request, result):
    """Consume only the full concrete pending recipe, never a named hash map."""
    if (
        type(request) is not FingerprintRequest
        or type(result) is not FingerprintResult
        or result.request is not request
        or result.request.token is not request.token
        or type(result.sha256) is not str
        or len(result.sha256) != 64
        or any(c not in "0123456789abcdef" for c in result.sha256)
        or type(result.encoded_size) is not int
        or result.encoded_size < 0
    ):
        raise ValueError("Fingerprint result does not match the pending request")
    return result.sha256


def legacy_fields(value):
    """Declared v1 field order/omission, shared by proofs and refs traversal."""
    if type(value) is InlineExactContent:
        yield from legacy_content_fields(value)
        return
    if type(value) is OpaqueContent:
        raise ValueError("Opaque fields require an admitted occurrence recipe")
    for name, field in type(value).model_fields.items():
        child = getattr(value, name)
        if field.exclude or field.exclude_if is not None and field.exclude_if(child):
            continue
        yield name, child


def legacy_tree(value, *, scope=(), path=()):
    """Build a closed old-field recipe; caller reserves its prospective shape."""
    if isinstance(value, (InlineExactContent, OpaqueContent)):
        if type(value) is OpaqueContent and value.occurrence is None:
            raise ValueError("Opaque proof occurrence lacks input provenance")
        return ContentOccurrence(
            value.identity,
            ("copy", value.occurrence, scope, path),
            value.reference,
            value.data if type(value) is InlineExactContent else None,
        )
    if isinstance(value, BaseModel):
        return LegacyObject(
            tuple(
                (name, legacy_tree(child, scope=scope, path=path + (name,)))
                for name, child in legacy_fields(value)
            )
        )
    if type(value) is dict:
        return LegacyObject(
            tuple(
                (name, legacy_tree(child, scope=scope, path=path + (name,)))
                for name, child in value.items()
            )
        )
    if type(value) in (tuple, list):
        return tuple(
            legacy_tree(child, scope=scope, path=path + (index,))
            for index, child in enumerate(value)
        )
    if type(value) is bytes:
        import base64

        return base64.urlsafe_b64encode(value).decode("ascii")
    if value is None or type(value) in (bool, int, str):
        return value
    raise ValueError("Unsupported legacy field type")


def fingerprint_request(value, *, dialect, scope, epoch, context=None):
    tree = legacy_tree(value, scope=scope)
    occurrences = []
    pending = [tree]
    while pending:
        node = pending.pop()
        if type(node) is ContentOccurrence:
            occurrences.append(node)
        elif type(node) is LegacyObject:
            pending.extend(child for _, child in reversed(node.fields))
        elif type(node) is tuple:
            pending.extend(reversed(node))
    if context is None:
        context = ExecutionContext(object(), 0, epoch, 0)
    return FingerprintRequest(
        "legacy-content/1",
        dialect,
        scope,
        context.epoch,
        tree,
        tuple(occurrences),
        request_token(context, "fingerprint", (dialect, scope)),
    )


def inline_fingerprint(request):
    """Synchronous existing-inline evaluator; caller-owned bytes remain inline."""
    import base64
    import hashlib
    import json

    def encode(node):
        if type(node) is ContentOccurrence:
            if node.inline is None:
                raise ValueError("Opaque proof requires the owned outer driver")
            return {
                "data": base64.urlsafe_b64encode(node.inline).decode("ascii"),
                "reference": None
                if node.reference is None
                else node.reference.model_dump(),
            }
        if type(node) is LegacyObject:
            return {key: encode(child) for key, child in node.fields}
        if type(node) is tuple:
            return [encode(child) for child in node]
        return node

    raw = json.dumps(
        encode(request.tree),
        ensure_ascii=True,
        sort_keys=request.dialect != "Ju",
        separators=(",", ":") if request.dialect == "Jc" else None,
    ).encode("utf-8")
    return FingerprintResult(request, hashlib.sha256(raw).hexdigest(), len(raw))


def canonical_equal(left, right):
    """Compare the complete legacy field tree, including every reference field.

    The request-driven caller first co-admits both complete content closures. The
    inline caller still compares the actual bytes. Occurrence names are recipes,
    not old wire fields and not a substitute for this correspondence.
    """
    content = (InlineExactContent, OpaqueContent)
    if isinstance(left, content) or isinstance(right, content):
        if not isinstance(left, content) or not isinstance(right, content):
            return False
        if left.reference != right.reference:
            return False
        if type(left) is InlineExactContent and type(right) is InlineExactContent:
            return left.data == right.data
        return left.identity == right.identity
    if isinstance(left, BaseModel) or isinstance(right, BaseModel):
        if type(left) is not type(right):
            return False
        a, b = tuple(legacy_fields(left)), tuple(legacy_fields(right))
        return len(a) == len(b) and all(
            ka == kb and canonical_equal(va, vb)
            for (ka, va), (kb, vb) in zip(a, b, strict=True)
        )
    if type(left) is tuple or type(right) is tuple:
        return (
            type(left) is type(right)
            and len(left) == len(right)
            and all(canonical_equal(a, b) for a, b in zip(left, right, strict=True))
        )
    return type(left) is type(right) and left == right


@dataclass(frozen=True)
class ChildWork:
    child: object
    parent: object


@dataclass(frozen=True)
class CompletedWork:
    value: object


@dataclass(frozen=True)
class PendingFingerprint:
    request: FingerprintRequest
    continuation: object


@dataclass(frozen=True)
class SourceSpan:
    source: ContentOccurrence
    start: int
    end: int


def source_span(value, start, end):
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start <= end <= value.identity.size
    ):
        raise ValueError("Invalid composition source range")
    return SourceSpan(
        ContentOccurrence(
            value.identity,
            value.occurrence,
            value.reference,
            value.data if type(value) is InlineExactContent else None,
        ),
        start,
        end,
    )


@dataclass(frozen=True)
class CreatedRequest:
    token: RequestToken
    role: tuple
    size: int
    spans: tuple[SourceSpan, ...]
    recipe: str = "review-composition/1"


@dataclass(frozen=True)
class CreatedResult:
    request: CreatedRequest
    content: object
    semantic: InlineExactContent
    epoch: int


@dataclass(frozen=True)
class PendingCreated:
    request: CreatedRequest
    continuation: object


@dataclass(frozen=True)
class OutstandingRequest:
    request: object
    continuation: object


def issue_request(pending, context):
    if type(pending) not in (PendingFingerprint, PendingCreated):
        raise ValueError("Unknown request kind")
    kind = "fingerprint" if type(pending) is PendingFingerprint else "created"
    request = pending.request
    if type(request) is not (
        FingerprintRequest if kind == "fingerprint" else CreatedRequest
    ):
        raise ValueError("Pending work has the wrong concrete request kind")
    token = request.token
    if (
        type(token) is not RequestToken
        or token.operation is not context.operation
        or (token.operation_ordinal, token.ordinal, token.epoch, token.kind)
        != (context.operation_ordinal, context.next_ordinal, context.epoch, kind)
        or getattr(pending.continuation, "pending", None) is not request
        or token.scope
        != ((request.dialect, request.scope) if kind == "fingerprint" else request.role)
    ):
        raise ValueError("Request is outside the current operation")
    return OutstandingRequest(request, pending.continuation)


def consume_created(request, result):
    if (
        type(request) is not CreatedRequest
        or type(result) is not CreatedResult
        or result.request is not request
        or result.request.token is not request.token
        or request.recipe != "review-composition/1"
        or request.size != sum(span.end - span.start for span in request.spans)
        or result.epoch != request.token.epoch + 1
        or type(result.semantic) is not InlineExactContent
        or type(result.content) not in (InlineExactContent, OpaqueContent)
        or result.content.identity != result.semantic.identity
        or result.content.identity.size != request.size
        or result.content.occurrence != result.semantic.occurrence
        or result.content.reference is not None
        or result.semantic.reference is not None
    ):
        raise ValueError("Created result does not match its issued recipe")
    return result


def consume_request(grant, result, continuation, epoch):
    if (
        type(grant) is not OutstandingRequest
        or continuation is not grant.continuation
        or type(result) not in (FingerprintResult, CreatedResult)
        or result.request is not grant.request
        or result.request.token is not grant.request.token
    ):
        raise ValueError("Response does not own the outstanding request")
    if type(grant.request) is FingerprintRequest:
        if epoch != grant.request.epoch:
            raise ValueError("Fingerprint response belongs to another epoch")
        consume_fingerprint(grant.request, result)
    elif type(grant.request) is CreatedRequest:
        consume_created(grant.request, result)
        if epoch != result.epoch:
            raise ValueError("Created response was not admitted in this epoch")
    else:
        raise ValueError("Unknown request kind")


def inline_created(request):
    from hashlib import sha256

    pieces = []
    for span in request.spans:
        source = span.source
        if (
            source.inline is None
            or len(source.inline) != source.identity.size
            or sha256(source.inline).hexdigest() != source.identity.sha256
            or not 0 <= span.start <= span.end <= source.identity.size
        ):
            raise ValueError("Composition requires available exact source bytes")
        pieces.append(source.inline[span.start : span.end])
    content = InlineExactContent(data=b"".join(pieces))
    return consume_created(
        request,
        CreatedResult(
            request,
            content,
            content,
            request.token.epoch + 1,
        ),
    )


def advance_work(work, returned=None, *, context=None):
    """One closed pure transition. No IO or caller-supplied executable exists."""
    from .core.attachment_validation import CandidateWork, advance_candidate
    from .core.reconciliation import ReconcileWork, advance_reconciliation
    from .core.resolution import (
        ActionWork,
        AttachmentActionWork,
        KeepCurrentWork,
        PlanWork,
        advance_action,
        advance_attachment_action,
        advance_keep_current,
        advance_plan,
    )

    if context is None:
        context = ExecutionContext(object(), 0, 0, 0)
    if type(work) is CandidateWork:
        return advance_candidate(work, returned)
    if type(work) is ReconcileWork:
        return advance_reconciliation(work, returned, context=context)
    if type(work) is PlanWork:
        return advance_plan(work, returned)
    if type(work) is AttachmentActionWork:
        return advance_attachment_action(work, returned, context)
    if type(work) is KeepCurrentWork:
        return advance_keep_current(work, returned, context)
    if type(work) is ActionWork:
        return advance_action(work, returned, context)
    return _advance_review_work(work, returned, context)


def _advance_review_work(work, returned, context):
    from .core.resolution import (
        ApprovalWork,
        PreservedMemoryWork,
        ProducerActionWork,
        advance_approval,
        advance_preserved_memory,
        advance_producer_action,
    )
    from .core.review_composition import CompositionWork, advance_composition
    from .core.selected_effects import SelectedEffectsWork, advance_selected_effects

    if type(work) is CompositionWork:
        return advance_composition(work, returned, context)
    if type(work) is SelectedEffectsWork:
        return advance_selected_effects(work, returned)
    if type(work) is ProducerActionWork:
        return advance_producer_action(work, returned)
    if type(work) is PreservedMemoryWork:
        return advance_preserved_memory(work, returned)
    if type(work) is ApprovalWork:
        return advance_approval(work, returned)
    return _advance_refresh_work(work, returned)


def _advance_refresh_work(work, returned):
    from .core.refresh import (
        AttachmentViewsWork,
        ClosureWork,
        RefreshWork,
        advance_attachment_views,
        advance_closure,
        advance_refresh,
    )

    if type(work) is AttachmentViewsWork:
        return advance_attachment_views(work, returned)
    if type(work) is ClosureWork:
        return advance_closure(work, returned)
    if type(work) is RefreshWork:
        return advance_refresh(work, returned)
    raise ValueError("Unknown pure work frame")


def drive_inline(work):
    """Synchronous compatibility driver; this adds no caps to old inline calls."""
    stack, returned = [], None
    operation, epoch, ordinal = object(), 0, 0
    while True:
        context = ExecutionContext(operation, 0, epoch, ordinal)
        result = advance_work(work, returned, context=context)
        returned = None
        if type(result) is ChildWork:
            stack.append(result.parent)
            work = result.child
        elif type(result) in (PendingFingerprint, PendingCreated):
            grant = issue_request(result, context)
            ordinal += 1
            returned = (
                inline_fingerprint(result.request)
                if type(result) is PendingFingerprint
                else inline_created(result.request)
            )
            if type(result) is PendingCreated:
                epoch = returned.epoch
            consume_request(grant, returned, result.continuation, epoch)
            work = result.continuation
        elif type(result) is CompletedWork:
            if not stack:
                return result.value
            returned, work = result.value, stack.pop()
        else:
            work = result
