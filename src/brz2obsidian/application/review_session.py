"""Lexical owned admission and explicitly driven pure legacy review work."""

import math
import time
from contextlib import closing, contextmanager
from dataclasses import dataclass
from threading import Event
from types import MappingProxyType
from uuid import uuid4

from pydantic import BaseModel

from brz2obsidian.application.update_subjects import review_subjects
from brz2obsidian.content_fingerprints import (
    ChildWork,
    CompletedWork,
    ContentOccurrence,
    CreatedResult,
    ExecutionContext,
    FingerprintResult,
    LegacyObject,
    ModelBudgetError,
    PendingCreated,
    PendingFingerprint,
    SourceSpan,
    advance_work,
    canonical_equal,
    consume_created,
    consume_request,
    issue_request,
    prospective_model,
)
from brz2obsidian.contracts import (
    ContentIdentity,
    InlineExactContent,
    LinkTargetFacts,
    LoadedReview,
    OpaqueContent,
    ReconciliationInput,
    ReconciliationSubject,
    ReviewPreflight,
    ReviewRefreshEvent,
    SavedReview,
    StructuredDocument,
    _structure_requires_inline,
)
from brz2obsidian.core.refresh import RefreshWork
from brz2obsidian.core.resolution import ActionWork, PlanWork
from brz2obsidian.core.resume import _load_result, _resume_result
from brz2obsidian.core.selected_effects import SelectedEffectsWork, _refused
from brz2obsidian.publication.content_session import ContentSession
from brz2obsidian.publication.legacy_content import ContentComparison, LegacyContentSlot
from brz2obsidian.review_codec import LegacyDecoder

# One immutable, input-independent refusal is fixed B. It contains no saved
# graph/effects/authority. Each session nevertheless reserves its retained M.
# Constructing it is not charged anew to a caller's node1 budget.
_LOAD_REFUSAL = _load_result("invalid_review")
_REFUSAL_M = (
    1024
    + 128 * 6
    + 3 * 16
    + sum(
        64 + 4 * len(value)
        for value in ("brz2obsidian.review-load-result", "refused", "invalid_review")
    )
)
# Ledger object/map, counter map, grants list, measurement object/map, bounded
# refusal/unwind cursor. These are named structural units, not heap sizes.
_FIXED_M = (
    _REFUSAL_M
    + 256
    + 256
    + 64 * 10
    + 256
    + 64 * 6
    + 64
    + 256
    + 256
    + 64 * 14
    + 128
    + 256
    + 2 * 64
    + 64
    + 4 * len("Prospective model reservation exhausted")
    + 256
    + 256
    + 64 * 7
    + 128
)  # one measured-shape result/call frame
_GRANT_M = 256 + 64 * 4 + 16 + 2 * 64


@dataclass(frozen=True)
class ReviewBudget:
    metadata_limit: int
    node_limit: int
    depth_limit: int
    decoded_limit: int
    raw_work_limit: int
    encoded_limit: int
    request_limit: int
    step_limit: int
    timeout: float
    cancel: Event

    def __post_init__(self):
        for name, maximum, minimum in (
            ("metadata_limit", 64 << 20, 0),
            ("node_limit", 1048576, 1),
            ("depth_limit", 256, 1),
            ("decoded_limit", 64 << 20, 0),
            ("raw_work_limit", 128 << 20, 0),
            ("encoded_limit", 128 << 20, 0),
            ("request_limit", 4096, 0),
            ("step_limit", 2000000, 0),
        ):
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError("Invalid review " + name)
        if (
            type(self.timeout) not in (int, float)
            or not math.isfinite(self.timeout)
            or not 0 < self.timeout <= 120
        ):
            raise ValueError("Invalid review timeout")
        if not isinstance(self.cancel, Event):
            # Preserve the public budget validation exception.
            raise ValueError("Review cancellation requires an Event")  # noqa: TRY004


class _Ledger:
    def __init__(self, budget):
        self.budget = budget
        self.deadline = time.monotonic() + budget.timeout
        self.used = {
            name: 0
            for name in ("decoded", "raw_work", "encoded", "request", "step", "node")
        }
        self.metadata = self.text = 0
        self._grants = []
        self._failed_workspace = 0
        self.check()
        self.retain_metadata(_FIXED_M)

    def check(self):
        if self.budget.cancel.is_set() or time.monotonic() >= self.deadline:
            raise OSError("Review cancelled or time budget exhausted")

    def remaining(self, name):
        return getattr(self.budget, name + "_limit") - self.used[name]

    def take(self, name, count):
        self.check()
        if type(count) is not int or count < 0 or count > self.remaining(name):
            raise OSError("Review " + name + " budget exhausted")
        self.used[name] += count

    def node(self, depth):
        if depth > self.budget.depth_limit:
            raise OSError("Review depth budget exhausted")
        self.take("node", 1)

    def retain_metadata(self, size):
        self.check()
        if size < 0 or self.metadata + size > self.budget.metadata_limit:
            raise OSError("Review metadata budget exhausted")
        self.metadata += size

    def release_metadata(self, size):
        if not 0 <= size <= self.metadata:
            raise OSError("Invalid retained metadata release")
        self.metadata -= size

    def raw_pass(self, size):
        self.take("raw_work", size + 1)

    def _shape(self, model, value, *, reconstruction):
        # One bounded cursor per depth. No merged per-input union field map.
        # The calculator object/header is already in the fixed session escrow.
        workspace = self.budget.depth_limit * 128
        self.retain_metadata(workspace)
        try:
            try:
                shape = prospective_model(
                    model,
                    value,
                    node_limit=self.remaining("node"),
                    step_limit=self.remaining("step"),
                    depth_limit=self.budget.depth_limit,
                    metadata_limit=self.budget.metadata_limit - self.metadata,
                    reconstruction=reconstruction,
                )
            except ModelBudgetError as error:
                self._record_walk(error.nodes, error.steps)
                raise
            self._record_walk(shape.nodes, shape.steps)
            self.check()
        except BaseException:
            # The exception traceback can retain the entire calculator stack.
            # Do not release its workspace until the public handler has exited.
            self._failed_workspace += workspace
            raise
        self.release_metadata(workspace)
        return shape

    def _record_walk(self, nodes, steps):
        # The pure walker checked each visit against these delegated quotas.
        # Record consumed work even if cancellation/deadline is now exhausted.
        if nodes > self.remaining("node") or steps > self.remaining("step"):
            raise OSError("Prospective work exceeded its delegated quota")
        self.used["node"] += nodes
        self.used["step"] += steps

    def admit_metadata(self, value):
        shape = self._shape(None, value, reconstruction=False)
        self.retain_metadata(shape.retained)
        return shape.retained

    def construct(self, model, value):
        shape = self._shape(model, value, reconstruction=True)
        if shape.raw_work > self.remaining(
            "raw_work"
        ) or shape.encoded > self.remaining("encoded"):
            raise OSError("Model validation work budget exhausted")
        # Reserve the graph, all attempted-branch scratch, and a lifetime record
        # before the sole model_validate entry below. Old grants stay live.
        self.take("step", 4)  # grant insertion, transfer and eventual unwind
        self.retain_metadata(shape.retained + shape.temporary + _GRANT_M)
        grant = {
            "retained": shape.retained,
            "temporary": shape.temporary,
            "value": None,
            "failed": False,
        }
        self._grants.append(grant)
        try:
            self.take("raw_work", shape.raw_work)
            self.take("encoded", shape.encoded)
            result = model.model_validate(value)
        except BaseException:
            # The exception can still retain a failed validator's self/input.
            # The caller retires this grant after its sanitized handler exits.
            grant["failed"] = True
            raise
        grant["value"] = result
        grant["temporary"] = 0
        self.release_metadata(shape.temporary)
        return result

    def release_failed(self):
        # A construction failure stops the operation, so its grant is last.
        # This uses the unwind work reserved before construction, not take().
        self.release_metadata(self._failed_workspace)
        self._failed_workspace = 0
        if self._grants and self._grants[-1]["failed"]:
            grant = self._grants.pop()
            self.release_metadata(grant["retained"] + grant["temporary"] + _GRANT_M)

    def reserve_file_cleanup(self):
        # close() currently copies the file map into (path, identity) pairs.
        # Reserve pair+tuple slot and exists/lstat/unlink iteration before I/O.
        self.take("step", 4)
        self.retain_metadata(96 + 16)

    def retire(self):
        self._grants.clear()
        # Returned pure graphs can remain with the caller. Do not report their
        # charged M as freed or reset cumulative work on lexical close.


@dataclass(frozen=True)
class _OccurrenceBinding:
    occurrence: tuple
    registration: object
    identity: ContentIdentity
    historical: object
    origin: tuple


@dataclass(frozen=True)
class _ClosureState:
    bindings: object
    physical: object
    view: object
    comparison: object
    epoch: int


class ReviewSession:
    def __init__(self, observed, *, scratch_parent, budget):
        if type(budget) is not ReviewBudget:
            raise ValueError("Explicit review budget required")
        self._ledger = _Ledger(budget)
        self._ledger.retain_metadata(2048)
        self._content = ContentSession(observed, scratch_parent=scratch_parent)
        self._closure = _ClosureState(
            MappingProxyType({}), MappingProxyType({}), None, None, 0
        )
        self._staged_bindings = None
        self._physical = {}
        self._record = None
        self._closed = False
        self._selected = None
        self._scope = None
        self._operation_key = None
        self._operation_ordinal = self._next_ordinal = self._input_ordinal = 0
        self._outstanding = None

    @property
    def _epoch(self):
        return self._closure.epoch

    @property
    def _comparison(self):
        return self._closure.comparison

    def _invalidate(self):
        self._operation_key = self._outstanding = self._selected = None

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *exc):
        self.close()

    def _check(self):
        if self._closed:
            raise OSError("Review session is closed")
        self._ledger.check()
        if self._scope is not None:
            self._scope.check(self._content)

    @contextmanager
    def _operation(self):
        try:
            self._check()
            if self._scope is not None:
                raise OSError("Nested review operation")
            self._ledger.retain_metadata(
                512 + 80 * (len(self._closure.bindings) + len(self._closure.physical))
            )
            self._staged_bindings = dict(self._closure.bindings)
            self._physical = dict(self._closure.physical)
            self._operation_ordinal += 1
            self._next_ordinal = 0
            self._operation_key = object()
            with self._content._operation(self._ledger) as scope:
                self._scope = scope
                yield
        except BaseException:
            self._invalidate()
            raise
        finally:
            self._operation_key = self._outstanding = None
            self._staged_bindings = None
            self._scope = None

    def _begin_input(self, path):
        self._check()
        self._ledger.retain_metadata(768 + 16 * len(path))
        if self._record is None:
            self._record = uuid4().hex
        self._input_ordinal += 1
        occurrence = (self._record, "input", self._input_ordinal) + path
        return self._content._prepare_decoded(
            self._record, occurrence, self._ledger, self._scope
        )

    def _finish_input(self, transaction, historical, *, inline):
        registration = transaction.finish(historical)
        reference = registration.reference
        occurrence = transaction.occurrence
        if occurrence in self._staged_bindings:
            raise OSError("Duplicate input occurrence")
        identity = ContentIdentity(
            content_id=f"sha256:{reference.sha256}:{reference.size}",
            sha256=reference.sha256,
            size=reference.size,
        )
        value = OpaqueContent(
            identity=identity, reference=historical, occurrence=occurrence
        )
        self._staged_bindings[occurrence] = _OccurrenceBinding(
            occurrence,
            registration,
            identity,
            historical,
            registration.origin,
        )
        return self._text(value) if inline else value

    def _binding(
        self, occurrence, identity, historical, *, published=False, inline=None
    ):
        self._check()
        bindings = self._closure.bindings if published else self._staged_bindings
        binding = bindings.get(occurrence)
        if (
            binding is None
            or binding.identity != identity
            or binding.historical != historical
            or binding.origin != binding.registration.origin
        ):
            raise OSError("Content differs from its actual owned logical registration")
        self._content._check_prepared(binding.registration, self._scope)
        reference = binding.registration.reference
        if (identity.sha256, identity.size) != (reference.sha256, reference.size):
            raise OSError("Registered content identity changed")
        if inline is not None:
            position, equal = 0, True
            with closing(
                self._content._read_owned(
                    binding.registration.backing,
                    reference,
                    self._ledger,
                    self._scope,
                )
            ) as chunks:
                for block in chunks:
                    equal = (
                        inline[position : position + len(block)] == block
                    ) and equal
                    position += len(block)
            if not equal or position != len(inline):
                raise OSError("Inline bytes differ from the actual owned occurrence")
        return binding

    def _semantic_value(self, binding):
        reference = binding.registration.reference
        self._ledger.text += reference.size
        raw = bytearray()
        with closing(
            self._content._read_owned(
                binding.registration.backing,
                reference,
                self._ledger,
                self._scope,
            )
        ) as chunks:
            for block in chunks:
                raw.extend(block)
        return InlineExactContent(
            data=bytes(raw),
            identity=binding.identity,
            reference=binding.historical,
            occurrence=binding.occurrence,
        )

    def _text(self, value):
        binding = self._binding(
            value.occurrence,
            value.identity,
            value.reference,
            inline=value.data if type(value) is InlineExactContent else None,
        )
        if type(value) is InlineExactContent:
            return value
        return self._semantic_value(binding)

    def _semantic_alias(self, value, available):
        """Reuse actual semantic bytes after verifying this exact registration."""
        self._binding(
            value.occurrence, value.identity, value.reference, inline=available.data
        )
        # New Inline/identity records, their fixed field maps, canonical identity
        # spelling/hash and constructor workspace. The bytes already exist as T;
        # this constructor retains their alias rather than materializing U again.
        self._ledger.retain_metadata(
            1024
            + 128 * 5
            + 1024
            + 128 * 3
            + 64
            + 4 * 80
            + 320
            + 256
            + 64 * 4
            + 256
            + 64 * 3
            + 256
            + 320,
        )
        self._ledger.take("raw_work", len(available.data) + 1)
        return InlineExactContent(
            data=available.data,
            identity=value.identity,
            reference=value.reference,
            occurrence=value.occurrence,
        )

    def _semantic_input(self, models, values):
        if StructuredDocument in models and values.get("content") is not None:
            body = values.get("body")
            if (
                type(body) is dict
                and type(body.get("start")) is int
                and type(body.get("end")) is int
                and 0 <= body["start"] <= body["end"] == values["content"].identity.size
                and _structure_requires_inline(
                    values.get("status"),
                    values.get("fields"),
                    values.get("memberships"),
                    values.get("appearance_field"),
                    values.get("owned_sections"),
                    body.get("start"),
                )
            ):
                values["content"] = self._text(values["content"])
        if (
            ReconciliationSubject in models
            and values.get("attachment") is None
            and values.get("interpretation") == "supported"
        ):
            for key in ("baseline", "current"):
                version = values.get(key)
                if type(version) is dict and version.get("content") is not None:
                    version["content"] = self._text(version["content"])
            if values.get("incoming") is not None:
                values["incoming"] = self._text(values["incoming"])
            comparison = values.get("structure")
            if type(comparison) is dict:
                for name, version in (
                    ("original", values.get("baseline")),
                    ("current", values.get("current")),
                    ("incoming", values.get("incoming")),
                ):
                    document = comparison.get(name)
                    available = (
                        version.get("content") if type(version) is dict else version
                    )
                    content = (
                        document.get("content") if type(document) is dict else None
                    )
                    if (
                        type(content) is OpaqueContent
                        and type(available) is InlineExactContent
                        and content.identity == available.identity
                    ):
                        document["content"] = self._semantic_alias(content, available)
        structure = values.get("structure")
        supported_structure = (
            type(structure) is dict and structure.get("status") == "supported"
        )
        if (
            LinkTargetFacts in models
            and (values.get("anchors") or supported_structure)
            and values.get("content") is not None
        ):
            values["content"] = self._text(values["content"])
        return values

    def _admit_values(self, value, path=()):
        """Register actual new inline inputs; recheck every opaque occurrence."""
        self._ledger.check()
        self._ledger.node(len(path) + 1)
        if type(value) in (InlineExactContent, OpaqueContent):
            binding = self._staged_bindings.get(value.occurrence)
            if binding is not None:
                if binding.identity != value.identity:
                    raise OSError("Altered registered content value")
                if binding.historical == value.reference:
                    self._binding(
                        value.occurrence,
                        value.identity,
                        value.reference,
                        inline=value.data
                        if type(value) is InlineExactContent
                        else None,
                    )
                    return value
                if type(value) is OpaqueContent:
                    raise OSError("Altered opaque historical reference")
            if type(value) is OpaqueContent:
                raise OSError("Opaque content is outside this review session")
            transaction = self._begin_input(path)
            try:
                for start in range(0, len(value.data), 65536):
                    transaction.write(value.data[start : start + 65536])
                admitted = self._finish_input(
                    transaction, value.reference, inline=False
                )
                # A fresh owned registration supplies provenance. Public copies
                # cannot assign another occurrence or retain changed bytes.
                return InlineExactContent(
                    data=value.data,
                    identity=value.identity,
                    reference=value.reference,
                    occurrence=admitted.occurrence,
                )
            except BaseException:
                transaction.abort()
                raise
        if isinstance(value, BaseModel):
            updates = {
                name: self._admit_values(getattr(value, name), path + (name,))
                for name in type(value).model_fields
            }
            return value.model_copy(update=updates)
        if type(value) is tuple:
            return tuple(
                self._admit_values(child, path + (index,))
                for index, child in enumerate(value)
            )
        return value

    def _build_closure(self, bindings, physical, epoch):
        self._check()
        previous = (
            ()
            if self._closure.view is None
            else tuple(self._closure.view.records.values())
        )
        self._ledger.retain_metadata(
            768 + 80 * (len(previous) + len(bindings) + len(physical))
        )
        registry = {record.reference.content_id: record for record in previous}
        for record in (
            *tuple(binding.registration for binding in bindings.values()),
            *physical.values(),
        ):
            prior = registry.get(record.reference.content_id)
            if prior is not None and prior is not record:
                raise OSError("Conflicting actual registration identity")
            registry[record.reference.content_id] = record
        records = tuple(registry.values())
        view = self._content._registration_view(records, self._ledger, self._scope)
        comparison = ContentComparison(
            self._content,
            tuple(record.reference for record in records),
            raw_work_limit=self._ledger.remaining("raw_work"),
            metadata_limit=self._ledger.budget.metadata_limit - self._ledger.metadata,
            node_limit=self._ledger.remaining("node"),
            timeout=max(0.001, self._ledger.deadline - time.monotonic()),
            cancel=self._ledger.budget.cancel,
            _ledger=self._ledger,
            _scope=view,
        )
        return _ClosureState(
            MappingProxyType(dict(bindings)),
            MappingProxyType(dict(physical)),
            view,
            comparison,
            epoch,
        )

    def _coadmit(self):
        candidate = self._build_closure(
            self._staged_bindings, self._physical, self._epoch + 1
        )
        self._check()
        self._closure = candidate

    def _answer(self, request):
        self._check()
        if (
            self._outstanding is None
            or self._outstanding.request is not request
            or request.token.operation is not self._operation_key
            or request.epoch != self._epoch
        ):
            raise OSError("Fingerprint request belongs to another closure")

        def translate(node):
            self._ledger.node(1)
            if type(node) is ContentOccurrence:
                recipe, occurrence, _, _ = node.occurrence
                if recipe != "copy":
                    raise OSError("Proof occurrence is outside the admitted closure")
                binding = self._binding(
                    occurrence,
                    node.identity,
                    node.reference,
                    published=True,
                    inline=node.inline,
                )
                reference = binding.registration.reference
                if self._comparison.identity(reference) != binding.identity:
                    raise OSError("Proof occurrence is outside the admitted closure")
                return LegacyContentSlot(reference, binding.historical)
            if type(node) is LegacyObject:
                return LegacyObject(
                    tuple((key, translate(child)) for key, child in node.fields)
                )
            if type(node) is tuple:
                return tuple(translate(child) for child in node)
            return node

        evidence = self._comparison.project_legacy(
            translate(request.tree),
            dialect=request.dialect,
            raw_work_limit=self._ledger.remaining("raw_work"),
            encoded_byte_limit=self._ledger.remaining("encoded"),
            metadata_limit=self._ledger.budget.metadata_limit - self._ledger.metadata,
            node_limit=self._ledger.remaining("node"),
            depth_limit=self._ledger.budget.depth_limit,
            timeout=max(0.001, self._ledger.deadline - time.monotonic()),
            cancel=self._ledger.budget.cancel,
            _ledger=self._ledger,
        )
        return FingerprintResult(request, evidence.sha256, evidence.encoded_size)

    def _answer_created(self, request):
        self._check()
        if (
            self._outstanding is None
            or self._outstanding.request is not request
            or request.token.operation is not self._operation_key
            or request.token.epoch != self._epoch
            or request.recipe != "review-composition/1"
            or request.size != sum(span.end - span.start for span in request.spans)
        ):
            raise OSError("Created request belongs to another closure")
        if (
            type(request.role) is not tuple
            or len(request.role) != 3
            or request.role[0] != "composed-document"
            or any(type(part) is not str for part in request.role)
        ):
            raise OSError("Invalid Created output role")
        self._ledger.retain_metadata(1536 + 80 * (len(self._closure.bindings) + 1))
        for span in request.spans:
            if (
                type(span) is not SourceSpan
                or type(span.source) is not ContentOccurrence
            ):
                raise OSError("Unknown Created source operation")
            source = span.source
            if (
                type(span.start) is not int
                or type(span.end) is not int
                or not 0 <= span.start <= span.end <= source.identity.size
            ):
                raise OSError("Invalid Created source span")
            self._binding(
                source.occurrence,
                source.identity,
                source.reference,
                published=True,
                inline=source.inline,
            )
        if self._record is None:
            self._record = uuid4().hex
        occurrence = (
            self._record,
            "created",
            self._operation_ordinal,
            request.token.ordinal,
        )
        if occurrence in self._closure.bindings:
            raise OSError("Created occurrence was already registered")
        transaction = self._content._begin_created(
            request, occurrence, self._ledger, self._scope
        )
        try:
            for span in request.spans:
                source = span.source
                binding = self._binding(
                    source.occurrence, source.identity, source.reference, published=True
                )
                reference = binding.registration.reference
                if self._comparison.identity(reference) != source.identity:
                    raise OSError(
                        "Created source is outside the whole admitted closure"
                    )
                position = 0
                with closing(
                    self._content._read_owned(
                        binding.registration.backing,
                        reference,
                        self._ledger,
                        self._scope,
                    )
                ) as chunks:
                    for block in chunks:
                        self._ledger.take("step", 1)
                        start, end = (
                            max(span.start - position, 0),
                            min(span.end - position, len(block)),
                        )
                        if start < end:
                            transaction.write(block[start:end])
                        position += len(block)
            registration = transaction.finish(None)
            reference = registration.reference
            identity = ContentIdentity(
                content_id=f"sha256:{reference.sha256}:{reference.size}",
                sha256=reference.sha256,
                size=reference.size,
            )
            binding = _OccurrenceBinding(
                occurrence, registration, identity, None, registration.origin
            )
            if registration.origin != ("CREATED", request, occurrence):
                raise OSError("Created registration has another origin")
            bindings = dict(self._closure.bindings)
            bindings[occurrence] = binding
            candidate = self._build_closure(bindings, self._physical, self._epoch + 1)
            semantic = self._semantic_value(binding)
            content = OpaqueContent(
                identity=identity, reference=None, occurrence=occurrence
            )
            result = CreatedResult(request, content, semantic, candidate.epoch)
            consume_created(request, result)
            if candidate.comparison.identity(reference) != identity:
                raise OSError("Created result was not coadmitted")
            self._content._check_prepared(registration, self._scope)
            self._check()
            self._closure = candidate
            self._staged_bindings = bindings
            return result
        except BaseException:
            transaction.abort()
            raise

    def _drive(self, work):
        try:
            return self._drive_work(work)
        except BaseException:
            self._invalidate()
            raise

    def _drive_work(self, work):
        stack, returned = [], None
        while True:
            self._ledger.check()
            if self._operation_key is None:
                raise OSError("Review operation was invalidated")
            self._ledger.take("step", 1)
            self._ledger.retain_metadata(256)
            context = ExecutionContext(
                self._operation_key,
                self._operation_ordinal,
                self._epoch,
                self._next_ordinal,
            )
            result = advance_work(work, returned, context=context)
            returned = None
            if type(result) is ChildWork:
                stack.append(result.parent)
                work = result.child
            elif type(result) in (PendingFingerprint, PendingCreated):
                if self._outstanding is not None:
                    raise OSError("Another review request is pending")
                self._ledger.take("request", 1)
                self._ledger.retain_metadata(512)
                self._outstanding = issue_request(result, context)
                self._next_ordinal += 1
                returned = (
                    self._answer(result.request)
                    if type(result) is PendingFingerprint
                    else self._answer_created(result.request)
                )
                consume_request(
                    self._outstanding, returned, result.continuation, self._epoch
                )
                self._outstanding = None
                work = result.continuation
            elif type(result) is CompletedWork:
                if not stack:
                    return result.value
                returned, work = result.value, stack.pop()
            else:
                work = result

    def _replay(self, plan):
        history = plan.history
        canonical = self._drive(
            PlanWork(history.initial_facts, history.initial_preflight)
        )
        for event in history.events:
            work = (
                RefreshWork(canonical, event.facts, event.preflight)
                if isinstance(event, ReviewRefreshEvent)
                else ActionWork(canonical, event, self._epoch)
            )
            transition = self._drive(work)
            if transition.status != "accepted":
                return None
            canonical = transition.plan
        return canonical if canonical_equal(canonical, plan) else None

    def load_review(self, raw):
        with self._operation():
            self._check()
            self._record = uuid4().hex
            self._selected = None
            try:
                if type(raw) is SavedReview:
                    # Typed caller graph is an explicit convenience cost. The
                    # first caller-dependent reconstruction is guarded before
                    # any registration/closure or opaque planner work.
                    saved = self._ledger.construct(SavedReview, raw)
                    saved = self._admit_values(saved)
                else:
                    decoded = LegacyDecoder(raw, self).decode()
                    saved = self._ledger.construct(SavedReview, decoded)
                self._coadmit()
                canonical = self._replay(saved.plan)
                if canonical is None:
                    result = _LOAD_REFUSAL
                else:
                    result = _load_result(
                        "loaded", saved, self._drive(SelectedEffectsWork(canonical))
                    )
            except ValueError, TypeError, OSError, RecursionError:
                self._invalidate()
                result = _LOAD_REFUSAL
            self._ledger.release_failed()
            return result

    def _admit_current(self, admission, facts):
        """Corroborate only current physical claims, never source/risk authority."""
        if admission.status != "supported" or not admission.inventory_complete:
            raise OSError("Complete supported physical admission required")
        self._ledger.retain_metadata(256 + 64 * len(admission.inventory))
        inventory = {row.path: row for row in admission.inventory}

        def current(path, existence, content):
            self._ledger.take("step", 1)
            row = inventory.get(path)
            if existence in (
                "absent",
                "missing",
                "intentionally_uncreated",
                "known_source_gap",
            ):
                if row is not None:
                    raise OSError("Absent current claim contradicts fresh inventory")
                return
            if existence == "unknown":
                return
            if existence != "present" or content is None or row is None:
                raise OSError("Present current claim lacks fresh physical content")
            if row.exclusion in ("cache", "temporary") or (row.size, row.sha256) != (
                content.identity.size,
                content.identity.sha256,
            ):
                raise OSError("Current claim differs from freshly admitted bytes")
            if path not in self._physical:
                self._ledger.retain_metadata(1024 + 4 * len(path))
                reference = self._content._acquire_current(
                    path,
                    self._ledger,
                    self._scope,
                )
                self._physical[path] = self._content._prepare_registered(
                    reference, self._ledger, self._scope
                )

        for subject in facts.subjects:
            value = subject.current
            current(value.path, value.existence, value.content)
            if subject.operation_reversal is not None:
                for output in subject.operation_reversal.outputs:
                    value = output.current
                    current(value.path, value.existence, value.content)
        for item in facts.identity_inventory:
            value = item.current
            current(value.path, value.existence, value.content)
        context = facts.link_context
        if context is not None:
            for document in context.current_documents:
                current(document.source_path, "present", document.content)
            for fact in context.current_target_facts:
                targets = [
                    row
                    for row in context.current_targets
                    if row.target_id == fact.target_id
                ]
                for target in targets:
                    if target.canonical_path is not None:
                        current(target.canonical_path, fact.existence, fact.content)

    def resume_review(self, loaded, facts, *, preflight, admission):
        """Resume after an immediate same-reader public scoped ``inspect``.

        That existing eager inspection is an explicit outer prerequisite and is
        outside this facade's bounded decoding/proof claim. Its physical facts
        do not replace the caller's separately trusted source/risk context.
        """
        try:
            return self._resume_review(
                loaded, facts, preflight=preflight, admission=admission
            )
        finally:
            self._content._observation._discard_fresh_scope()

    def _resume_review(self, loaded, facts, *, preflight, admission):
        with self._operation():
            self._check()
            self._selected = None
            try:
                # Consumption precedes validation and every dependent replay;
                # errors cannot leave a reusable latest-inspection slot.
                purpose = (
                    "format_transition"
                    if facts.format_operation.kind == "format_transition"
                    else None
                )
                physical, subjects = self._content._observation._consume_fresh_scope(
                    admission,
                    purpose=purpose,
                    ledger=self._ledger,
                )
                loaded = self._ledger.construct(LoadedReview, loaded)
                self._ledger.admit_metadata(loaded)
                loaded = self._admit_values(loaded, ("loaded",))
                self._record = uuid4().hex
                facts = self._ledger.construct(ReconciliationInput, facts)
                self._ledger.admit_metadata(facts)
                facts = self._admit_values(facts, ("fresh",))
                preflight = self._ledger.construct(ReviewPreflight, preflight)
                self._physical.clear()
                self._admit_current(physical, facts)
                self._coadmit()
                canonical = self._replay(loaded.saved.plan)
                if canonical is None:
                    return _resume_result("refused", "invalid_review", loaded)
                effects = self._drive(SelectedEffectsWork(canonical))
                required = review_subjects(facts, canonical, effects=effects)
                actual = {(row.path, row.subject_id) for row in subjects}
                if not all((row.path, row.subject_id) in actual for row in required):
                    raise OSError(
                        "Fresh scoped admission omits a current or output target"
                    )
                if canonical_equal(facts, canonical.facts) and canonical_equal(
                    preflight, canonical.preflight
                ):
                    return _resume_result("resumed", "unchanged", loaded, canonical)
                refreshed = self._drive(RefreshWork(canonical, facts, preflight))
                return (
                    _resume_result("resumed", "refreshed", loaded, refreshed.plan)
                    if refreshed.status == "accepted"
                    else _resume_result(refreshed.status, refreshed.code, loaded)
                )
            except ValueError, OSError, RecursionError:
                self._invalidate()
                return _resume_result("refused", "invalid_review", loaded)

    def select_review_effects(self, plan):
        with self._operation():
            self._check()
            self._selected = None
            try:
                plan = self._admit_values(plan)
                self._coadmit()
                canonical = self._replay(plan)
                if canonical is None:
                    return _refused("invalid_plan")
                effects = self._drive(SelectedEffectsWork(canonical))
                if effects.status == "selected":
                    self._selected = effects
                return effects
            except ValueError, OSError, RecursionError:
                self._invalidate()
                return _refused("invalid_plan")

    def stage_effect(self, effect):
        with self._operation():
            self._check()
            self._coadmit()
            if self._selected is None or not any(
                canonical_equal(effect, row)
                and effect.content.occurrence == row.content.occurrence
                for row in self._selected.files
            ):
                raise OSError("Effect was not selected in this review session")
            binding = self._binding(
                effect.content.occurrence,
                effect.content.identity,
                effect.content.reference,
                published=True,
                inline=effect.content.data
                if type(effect.content) is InlineExactContent
                else None,
            )
            reference = binding.registration.reference
            if self._comparison.identity(reference) != effect.content.identity:
                raise OSError("Selected effect lacks registered bytes")
            return self._content._stage_decoded(
                reference, self._ledger, self._closure.view
            )

    def close(self):
        self._closed = True
        self._invalidate()
        self._staged_bindings = None
        self._physical.clear()
        self._content._observation._discard_fresh_scope()
        try:
            self._content.close()
        finally:
            self._ledger.retire()
