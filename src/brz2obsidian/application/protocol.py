"""Bounded UTF-8 wire codec, independent of Qt and conversion policy."""

import json
from uuid import UUID

from brz2obsidian.application.contracts import (
    DiagnosticOmission,
    ProtocolError,
    WorkerRequest,
    WorkerResponse,
)

REQUEST_LIMIT = 256 * 1024
RESPONSE_LIMIT = 16 * 1024 * 1024
STDERR_LIMIT = 64 * 1024


class ProtocolFailure(ValueError):
    """Untrustworthy wire data; raw data is never included in its message."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolFailure("Duplicate JSON field")
        result[key] = value
    return result


def _required_fields(value, fields):
    if not isinstance(value, dict) or not fields.issubset(value):
        raise ProtocolFailure("Missing required nested safe result content")


def _decode(data, model, maximum):
    if len(data) > maximum or not data.endswith(b"\n") or data.count(b"\n") != 1:
        raise ProtocolFailure("Invalid terminal framing or size")
    try:
        parsed = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
        if (
            not isinstance(parsed, dict)
            or "schema" not in parsed
            or "schema_version" not in parsed
        ):
            raise ProtocolFailure("Missing protocol schema")
        if model is WorkerResponse and (
            ("result" in parsed) == ("protocol_error" in parsed)
        ):
            raise ProtocolFailure("Exactly one terminal payload is required")
        for nested in (
            parsed.get("result"),
            parsed.get("arguments", {}).get("reviewed")
            if isinstance(parsed.get("arguments"), dict)
            else None,
        ):
            if nested is not None and (
                not isinstance(nested, dict)
                or "schema" not in nested
                or "schema_version" not in nested
            ):
                raise ProtocolFailure("Missing result schema")
        result = parsed.get("result")
        if model is WorkerResponse and result is not None:
            required = {
                "schema",
                "schema_version",
                "operation",
                "outcome",
                "status",
                "counts",
                "findings",
                "field_errors",
                "reviewed",
                "publication",
                "destination",
                "checked",
                "pending",
                "review_required",
                "diagnostic_text",
                "diagnostic_omission",
            }
            if not isinstance(result, dict) or not required.issubset(result):
                raise ProtocolFailure("Missing minimum safe result content")
            for collection in ("findings", "field_errors"):
                for finding in result[collection]:
                    _required_fields(
                        finding, {"code", "severity", "message", "field", "path"}
                    )
            if result["diagnostic_omission"] is not None:
                _required_fields(
                    result["diagnostic_omission"], {"findings_count", "reason"}
                )
            if result["publication"] is not None:
                _required_fields(
                    result["publication"], {"state", "destination", "receipt_verified"}
                )
        if isinstance(result, dict) and result.get("reviewed") is not None:
            review = result["reviewed"]
            if "schema" not in review or "schema_version" not in review:
                raise ProtocolFailure("Missing review schema")
        return model.model_validate_json(data)
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise ProtocolFailure("Invalid protocol content") from error


def decode_request(data: bytes) -> WorkerRequest:
    return _decode(data, WorkerRequest, REQUEST_LIMIT)


def rejected_request_response(data: bytes) -> WorkerResponse | None:
    """Echo only an unambiguous UUID and known operation on invalid requests.

    Malformed framing/JSON or an untrustworthy identity cannot be correlated;
    the worker then returns EOF/exit 1 instead of inventing an identity.
    """
    if len(data) > REQUEST_LIMIT or not data.endswith(b"\n") or data.count(b"\n") != 1:
        return None
    try:
        parsed = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
        identity, operation = parsed["request_id"], parsed["operation"]
        if (
            type(identity) is not str
            or str(UUID(identity)) != identity
            or operation
            not in (
                "inspect",
                "validate_destination",
                "convert_reviewed",
                "check_vault",
            )
        ):
            return None
        return WorkerResponse(
            request_id=identity,
            operation=operation,
            protocol_error=ProtocolError(
                code="invalid_request", message="The worker request is invalid."
            ),
        )
    except ValueError, TypeError, KeyError, RecursionError:
        return None


def decode_response(data: bytes, request: WorkerRequest) -> WorkerResponse:
    response = _decode(data, WorkerResponse, RESPONSE_LIMIT)
    if (
        response.request_id != request.request_id
        or response.operation != request.operation
    ):
        raise ProtocolFailure("Response correlation failed")
    return response


def encode_request(request: WorkerRequest) -> bytes:
    data = request.model_dump_json(by_alias=True).encode("utf-8") + b"\n"
    if len(data) > REQUEST_LIMIT:
        raise ProtocolFailure("Request exceeds the wire limit")
    return data


def encode_response(response: WorkerResponse) -> bytes:
    excluded = {"protocol_error"} if response.result is not None else {"result"}
    data = (
        response.model_dump_json(by_alias=True, exclude=excluded).encode("utf-8")
        + b"\n"
    )
    if len(data) > RESPONSE_LIMIT and response.result is not None:
        result = response.result
        omitted = len(result.findings) + (
            result.diagnostic_omission.findings_count
            if result.diagnostic_omission
            else 0
        )
        # The backend's safe report starts with selected paths/versions/outcome.
        # Retain a bounded prefix of that already-safe text as well as explicit
        # omission; do not fabricate missing context or inspect source evidence.
        context = result.diagnostic_text[:8192]
        report = f"brz2obsidian diagnostic report\nOperation: {result.operation}\nOutcome: {result.outcome}\nStatus: {result.status}\nDiagnostic findings omitted: {omitted} (response_limit).\nThe safe diagnostic report exceeded the worker response limit.\nAvailable safe context (possibly incomplete):\n{context}\n"
        bounded = result.model_copy(
            update={
                "findings": (),
                "diagnostic_text": report,
                "diagnostic_omission": DiagnosticOmission(findings_count=omitted),
            }
        )
        response = response.model_copy(update={"result": bounded})
        data = (
            response.model_dump_json(by_alias=True, exclude=excluded).encode("utf-8")
            + b"\n"
        )
    if len(data) > RESPONSE_LIMIT:
        raise ProtocolFailure("Authoritative result exceeds the wire limit")
    return data
