"""Bounded local HTTP reads, with no redirects or retained transport secrets."""

import http.client
import ipaddress
import json
import socket
import threading
import zlib
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlsplit

from .capture import pairs
from .errors import failure, refuse


def timestamp():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class LocalHttp:
    def __init__(self, config, token, brain_id, clock):
        self.config, self._token, self.brain_id, self.clock = (
            config,
            token,
            brain_id,
            clock,
        )
        self.requests = []
        self._response_bytes = 0
        self.started_at = timestamp()

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
        if deadline is not None and self.clock() >= deadline:
            refuse("search_timeout wildcard deadline exhausted", "incomplete_source")

    def request(
        self, operation, path, subject_id=None, *, deadline=None, allow_tag_error=False
    ):
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

        def remaining_budget():
            self._check(deadline)
            remaining = request_deadline - self.clock()
            if expired.is_set() or remaining <= 0:
                raise TimeoutError
            return remaining

        def interrupt():
            expired.set()
            try:
                if connected_socket is not None:
                    connected_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

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
            timer = threading.Timer(timeout, interrupt)
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
            if 300 <= response.status < 400:
                raise failure(
                    "api_redirect_refused", "Local API redirects are not followed"
                )
            if response.status in {401, 403}:
                raise failure(
                    "api_authentication_failed", "The local API denied access"
                )
            if response.status != 200 and not (
                allow_tag_error and operation == "tags" and response.status == 400
            ):
                raise failure(
                    "api_request_failed", "A required local API request failed"
                )
            cap = (
                self.config.search_max_response_bytes
                if operation == "search"
                else self.config.max_response_bytes
            )
            setting = (
                "search_max_response_bytes"
                if operation == "search"
                else "max_response_bytes"
            )
            encoding = response.getheader("Content-Encoding", "").lower().strip()
            if encoding not in {"", "identity", "gzip"}:
                refuse("The local API used an unsupported content encoding")
            decoder = (
                zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
            )
            chunks = []
            total = compressed = 0
            while True:
                remaining = remaining_budget()
                if response.isclosed():
                    if response.length not in {None, 0}:
                        refuse(
                            "A required local API response ended before its declared length"
                        )
                    break
                connected_socket.settimeout(max(0.001, remaining))
                chunk = response.read1(min(65536, cap + 1))
                remaining_budget()
                if not chunk:
                    if response.length not in {None, 0}:
                        refuse(
                            "A required local API response ended before its declared length"
                        )
                    break
                compressed += len(chunk)
                if compressed > 2 * cap + 65536:
                    refuse(
                        setting + " compressed transport bound exhausted",
                        "incomplete_source",
                    )
                while True:
                    decoded = (
                        decoder.decompress(chunk, cap - total + 1) if decoder else chunk
                    )
                    total += len(decoded)
                    if (
                        self._response_bytes + total
                        > self.config.max_total_capture_bytes
                    ):
                        refuse(
                            "max_total_capture_bytes aggregate response bound exhausted",
                            "incomplete_source",
                        )
                    if total > cap:
                        refuse(
                            setting + " response bound exhausted", "incomplete_source"
                        )
                    chunks.append(decoded)
                    if decoder and decoder.unconsumed_tail:
                        chunk = decoder.unconsumed_tail
                    else:
                        break
            if decoder and (not decoder.eof or decoder.unused_data):
                refuse("Compressed local API response is incomplete or unsupported")
            remaining_budget()
            raw = b"".join(chunks)
            self._response_bytes += len(raw)
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
                "actual_length": len(raw),
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

        try:
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=pairs,
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
