"""Bounded local HTTP reads, with no redirects or retained transport secrets."""

import http.client
import ipaddress
import json
import socket
import threading
import zlib
from datetime import UTC, datetime
from decimal import Decimal
from functools import partial
from urllib.parse import urlsplit

from .capture import pairs
from .errors import check_cancel, failure, refuse


def timestamp():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class NegativeZeroInteger(int):
    """Raw -0 kept distinct until field qualification; not a CJSON1 integer.

    Strict integer fields reject this type. A later attachment-position decoder
    can explicitly normalize its numeric value under that field's decimal rule.
    """


def _verify_response_end(response):
    if response.length not in {None, 0}:
        refuse("A required local API response ended before its declared length")


def _interrupt_response(connected_socket, expired):
    expired.set()
    try:
        if connected_socket is not None:
            connected_socket.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def _response_outcome(
    response, operation, allow_tag_error, allow_missing_txt, allow_missing_image
):
    if 300 <= response.status < 400:
        raise failure("api_redirect_refused", "Local API redirects are not followed")
    if response.status in {401, 403}:
        raise failure("api_authentication_failed", "The local API denied access")
    if (
        (allow_missing_txt or allow_missing_image)
        and operation == "attachment-content"
        and response.status == 404
    ):
        return "missing_image_404" if allow_missing_image else "missing_txt_404"
    if response.status != 200 and not (
        allow_tag_error and operation == "tags" and response.status == 400
    ):
        raise failure(
            "api_request_failed",
            "A required attachment was not found by the local API"
            if operation == "attachment-content" and response.status == 404
            else "A required local API request failed",
        )
    return None


class _ResponseBody:
    def __init__(self, client, operation, response, sink, bounded_icon):
        self.client = client
        self.operation = operation
        self.sink = sink
        self.bounded_icon = bounded_icon

        self.setting = (
            "search_max_response_bytes"
            if operation == "search"
            else "max_payload_bytes"
            if operation == "attachment-content"
            else "max_response_bytes"
        )
        self.cap = getattr(client.config, self.setting)
        encoding = response.getheader("Content-Encoding", "").lower().strip()
        if encoding not in {"", "identity", "gzip"}:
            refuse("The local API used an unsupported content encoding")
        self.decoder = (
            zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
        )
        self.chunks = []
        self.total = self.compressed = 0
        self.icon_prefix = b""
        self.secret_tail = b""
        self.secret = client._token.encode("utf-8")

    def read_limit(self):
        limit = (
            min(65536, self.cap - self.total + 1)
            if self.bounded_icon
            else min(65536, self.cap + 1)
        )
        if self.bounded_icon and len(self.icon_prefix) < 4:
            limit = min(limit, 4 - len(self.icon_prefix))
        return limit

    def consume(self, chunk, remaining_budget):
        self.compressed += len(chunk)
        if self.compressed > 2 * self.cap + 65536:
            refuse(
                self.setting + " compressed transport bound exhausted",
                "incomplete_source",
            )
        while True:
            remaining_budget()
            decoded = self._decode(chunk)
            if self.bounded_icon and len(self.icon_prefix) < 4:
                self._qualify_icon(decoded)
            self._record_decoded(decoded)
            remaining_budget()
            if self.decoder and self.decoder.unconsumed_tail:
                chunk = self.decoder.unconsumed_tail
            else:
                break

    def finish(self, remaining_budget):
        if self.decoder and (not self.decoder.eof or self.decoder.unused_data):
            refuse("Compressed local API response is incomplete or unsupported")
        remaining_budget()
        return b"".join(self.chunks), self.total

    def _decode(self, chunk):
        decode_limit = self.cap - self.total + 1
        if self.bounded_icon:
            decode_limit = min(65536, decode_limit)
            if len(self.icon_prefix) < 4:
                decode_limit = min(decode_limit, 4 - len(self.icon_prefix))
        return self.decoder.decompress(chunk, decode_limit) if self.decoder else chunk

    def _qualify_icon(self, decoded):
        from .icons import encoded_limit

        self.icon_prefix += decoded[: 4 - len(self.icon_prefix)]
        if len(self.icon_prefix) == 4:
            selected_cap = encoded_limit(self.icon_prefix, self.cap)
            if selected_cap < self.cap:
                self.setting = "icon_family"
            self.cap = selected_cap

    def _record_decoded(self, decoded):
        self.total += len(decoded)
        if (
            self.client._response_bytes + self.total
            > self.client.config.max_total_capture_bytes
        ):
            refuse(
                "max_total_capture_bytes aggregate response bound exhausted",
                "incomplete_source",
            )
        if self.total > self.cap:
            refuse(self.setting + " response bound exhausted", "incomplete_source")
        if self.operation == "attachment-content":
            if self.secret in self.secret_tail + decoded:
                refuse("Transport credentials cannot be retained as source content")
            self.secret_tail = (self.secret_tail + decoded)[-len(self.secret) :]
        if self.sink is None:
            self.chunks.append(decoded)
        else:
            self.sink.write(decoded)


class LocalHttp:
    def __init__(self, config, token, brain_id, clock, *, cancel=None):
        self.config, self._token, self.brain_id, self.clock = (
            config,
            token,
            brain_id,
            clock,
        )
        self.requests = []
        self._response_bytes = 0
        self.started_at = timestamp()
        self.cancel = cancel

    def ensure_safe(self, value):
        if isinstance(value, str):
            if self._token in value:
                refuse("Transport credentials cannot be retained as source content")
        elif isinstance(value, dict):
            for key, child in value.items():
                self.ensure_safe(key)
                self.ensure_safe(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                self.ensure_safe(child)

    def _check(self, deadline):
        check_cancel(self.cancel)
        if deadline is not None and self.clock() >= deadline:
            refuse("search_timeout wildcard deadline exhausted", "incomplete_source")

    def _request_timeout(self, deadline):
        self._check(deadline)
        if len(self.requests) >= self.config.max_requests:
            refuse("max_requests acquisition limit exhausted", "incomplete_source")
        timeout = (
            self.config.request_timeout
            if deadline is None
            else min(self.config.request_timeout, deadline - self.clock())
        )
        if timeout <= 0:
            refuse("search_timeout wildcard deadline exhausted", "incomplete_source")
        return timeout

    def _remaining_request_budget(self, deadline, request_deadline, expired):
        self._check(deadline)
        remaining = request_deadline - self.clock()
        if expired.is_set() or remaining <= 0:
            raise TimeoutError
        return remaining

    def _read_response(
        self,
        operation,
        response,
        connected_socket,
        remaining_budget,
        sink,
        bounded_icon,
    ):
        body = _ResponseBody(self, operation, response, sink, bounded_icon)
        while True:
            remaining = remaining_budget()
            if response.isclosed():
                _verify_response_end(response)
                break
            connected_socket.settimeout(max(0.001, remaining))
            chunk = response.read1(body.read_limit())
            remaining_budget()
            if not chunk:
                _verify_response_end(response)
                break
            body.consume(chunk, remaining_budget)
        return body.finish(remaining_budget)

    def request(
        self,
        operation,
        path,
        subject_id=None,
        *,
        deadline=None,
        allow_tag_error=False,
        allow_missing_txt=False,
        allow_missing_image=False,
        sink=None,
        bounded_icon=False,
    ):
        timeout = self._request_timeout(deadline)
        address = urlsplit(self.config.api_url)
        factory = (
            http.client.HTTPSConnection
            if address.scheme == "https"
            else http.client.HTTPConnection
        )
        connection = factory(address.hostname, address.port, timeout=timeout)
        started = timestamp()
        timer = None
        response = None
        connected_socket = None
        expired = threading.Event()
        request_deadline = self.clock() + timeout

        remaining_budget = partial(
            self._remaining_request_budget, deadline, request_deadline, expired
        )

        try:
            connection.connect()
            connected_socket = connection.sock
            if not ipaddress.ip_address(connection.sock.getpeername()[0]).is_loopback:
                raise failure(
                    "api_origin_refused",
                    "The API connection did not resolve to a permitted local address",
                )
            remaining = remaining_budget()
            connection.sock.settimeout(remaining)
            timeout = remaining
            timer = threading.Timer(
                timeout, partial(_interrupt_response, connected_socket, expired)
            )
            timer.daemon = True
            timer.start()
            connection.request(
                "GET",
                address.path.rstrip("/") + path,
                headers={
                    "Authorization": "Bearer " + self._token,
                    "Accept-Encoding": "gzip",
                },
            )
            response = connection.getresponse()
            remaining_budget()
            missing_outcome = _response_outcome(
                response,
                operation,
                allow_tag_error,
                allow_missing_txt,
                allow_missing_image,
            )
            if missing_outcome is not None:
                # Classify the status without reading or retaining arbitrary
                # error bodies, headers or service-generated URLs.
                self.requests.append(
                    {
                        "sequence": len(self.requests) + 1,
                        "operation": operation,
                        "brain_id": self.brain_id,
                        "subject_id": subject_id,
                        "status": 404,
                        "outcome": missing_outcome,
                        "started_at": started,
                        "finished_at": timestamp(),
                        "actual_length": 0,
                    }
                )
                return 404, b""
            raw, total = self._read_response(
                operation,
                response,
                connected_socket,
                remaining_budget,
                sink,
                bounded_icon,
            )
            self._response_bytes += total
            entry = {
                "sequence": len(self.requests) + 1,
                "operation": operation,
                "brain_id": self.brain_id,
                "subject_id": subject_id,
                "status": response.status,
                "outcome": "success"
                if response.status == 200
                else "tag_inventory_zero_exception",
                "started_at": started,
                "finished_at": timestamp(),
                "actual_length": total,
            }
            self.requests.append(entry)
            return response.status, raw
        except TimeoutError:
            self._check(deadline)
            raise failure(
                "api_request_timeout", "A bounded local API request timed out"
            ) from None
        except OSError, http.client.HTTPException, zlib.error, ValueError:
            self._check(deadline)
            if expired.is_set() or self.clock() >= request_deadline:
                raise failure(
                    "api_request_timeout", "A bounded local API request timed out"
                ) from None
            raise failure(
                "api_transport_failed", "Local API transport could not complete safely"
            ) from None
        finally:
            if timer is not None:
                timer.cancel()
            if response is not None:
                response.close()
            connection.close()

    def decode_json(self, raw, *, deadline=None):
        def invalid(value):
            refuse("Local API JSON contains an invalid number")

        def integer(value):
            if value == "-0":
                return NegativeZeroInteger(0)
            return int(value)

        try:
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=pairs,
                parse_int=integer,
                parse_float=Decimal,
                parse_constant=invalid,
            )
        except UnicodeError, ValueError, RecursionError:
            refuse("A required local API response is malformed")
        self._check(deadline)
        return value

    def json(self, operation, path, subject_id=None, *, deadline=None):
        _, raw = self.request(operation, path, subject_id, deadline=deadline)
        return self.decode_json(raw, deadline=deadline)
