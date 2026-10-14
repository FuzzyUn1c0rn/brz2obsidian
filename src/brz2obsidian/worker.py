"""One request/one terminal response. stdout is exclusively UTF-8 protocol."""

import sys
from pathlib import Path

from brz2obsidian.application import operations
from brz2obsidian.application.contracts import ProtocolError, WorkerResponse
from brz2obsidian.application.protocol import (
    REQUEST_LIMIT,
    ProtocolFailure,
    decode_request,
    encode_response,
    rejected_request_response,
)


def main() -> int:
    data = b""
    try:
        data = sys.stdin.buffer.read(REQUEST_LIMIT + 1)
        request = decode_request(data)
    except ProtocolFailure, OSError:
        response = rejected_request_response(data)
        if response is not None:
            try:
                sys.stdout.buffer.write(encode_response(response))
                sys.stdout.buffer.flush()
            except OSError:
                pass
        return 1
    try:
        arguments = request.arguments
        if request.operation == "inspect":
            result = operations.inspect(arguments.source_selection)
        elif request.operation == "validate_destination":
            result = operations.validate_destination(
                Path(arguments.parent), arguments.vault_name
            )
        elif request.operation == "convert_reviewed":
            result = operations.convert_reviewed(
                arguments.source_selection,
                Path(arguments.parent),
                arguments.vault_name,
                arguments.reviewed,
                arguments.proceed_with_warnings,
            )
        else:
            result = operations.check_vault(Path(arguments.vault))
        response = WorkerResponse(
            request_id=request.request_id, operation=request.operation, result=result
        )
        exit_code = (
            0
            if result.outcome in ("clean", "valid")
            else 2
            if result.outcome in ("warnings", "issues")
            else 1
        )
    except Exception as error:  # noqa: BLE001 -- final process boundary; never expose exception/source data.
        unavailable = isinstance(error, NotImplementedError)
        response = WorkerResponse(
            request_id=request.request_id,
            operation=request.operation,
            protocol_error=ProtocolError(
                code="operation_unavailable" if unavailable else "internal_error",
                message="This operation is not available in this build."
                if unavailable
                else "The operation could not complete.",
            ),
        )
        exit_code = 1
    try:
        sys.stdout.buffer.write(encode_response(response))
        sys.stdout.buffer.flush()
    except ProtocolFailure, OSError:
        return 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
