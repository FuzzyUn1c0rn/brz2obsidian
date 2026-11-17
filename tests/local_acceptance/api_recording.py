"""Bounded test-only loopback recorder; never an expected-fact projection."""

import gzip
import hashlib
import http.client
import ipaddress
import json
import re
import socket
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4


class RecordingError(ValueError):
    """A safe failure that contains neither source content nor credentials."""


def write_json(path, value):
    raw = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


class ApiRecording:
    """Record one acquisition through a local proxy, then explicitly seal it.

    Every attempt has a new directory. Closing first joins all handlers and
    binds the occurrence ledger. Failed attempts keep safe evidence, never a
    complete manifest. Neither credentials nor authentication headers persist.
    """

    def __init__(
        self,
        directory,
        upstream,
        *,
        brain_id,
        credential,
        max_requests=100000,
        max_body_bytes=256000000,
        max_total_bytes=1000000000,
        timeout=30,
        purpose="capture",
    ):
        parts = urlsplit(upstream)
        try:
            local = ipaddress.ip_address(parts.hostname).is_loopback
        except ValueError:
            local = parts.hostname == "localhost"
        if not (
            parts.scheme == "http"
            and local
            and parts.path in {"/api", "/api/"}
            and parts.username is None
            and parts.password is None
            and not parts.query
            and not parts.fragment
            and parts.port
            and str(UUID(brain_id)) == brain_id
            and UUID(brain_id).int
            and isinstance(credential, str)
            and credential
            and purpose in {"capture", "inspect", "convert"}
            and all(
                type(n) is int and 0 < n <= 2**63 - 1
                for n in (max_requests, max_body_bytes, max_total_bytes)
            )
            and max_total_bytes >= 4096
            and type(timeout) in {int, float}
            and 0 < timeout <= 86400
        ):
            raise RecordingError("Invalid bounded loopback recording configuration")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self._upstream = parts
        self._upstream_api_url = parts.geturl().rstrip("/")
        self._upstream_origin = parts.scheme + "://" + parts.netloc
        self._effective_upstream = {
            "address": "127.0.0.1" if parts.hostname == "localhost" else parts.hostname,
            "port": parts.port,
        }
        self._credential = credential
        self._token = credential.encode()
        self.brain_id = brain_id
        self.max_requests = max_requests
        self.max_body_bytes = max_body_bytes
        self.max_total_bytes = max_total_bytes
        self.timeout = timeout
        self._total = 0
        self._occurrences = []
        self._requests = 0
        self._failures = []
        self._lock = threading.Lock()
        self._closed = False
        self._started = False
        self._phase = "source-acquisition"
        self._purpose = purpose
        self._acquisition_id = str(uuid4())
        self._ledger_bytes = len(
            (json.dumps(self._ledger([]), indent=2, ensure_ascii=False) + "\n").encode()
        )
        identity = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
        namespace = re.escape(brain_id)
        self._routes = re.compile(
            rf"/api/(?:v1/docs\.json|brains(?:/{namespace}(?:/statistics)?)?"
            rf"|search/{namespace}"
            rf"|thoughts/{namespace}/(?:types|tags|pins|{identity}(?:/graph|/attachments)?)"
            rf"|links/{namespace}/{identity}(?:/attachments)?"
            rf"|attachments/{namespace}/{identity}/(?:metadata|file-content)"
            rf"|notes/{namespace}/{identity})"
        )

    def __enter__(self):
        if self._started:
            raise RecordingError("A recording cannot be reused")
        self._started = True
        recording = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(recording.timeout)

            def do_GET(self):
                recording._handle(self)

            def do_POST(self):
                recording._fail("Only read-only GET acquisition is supported")
                self.send_error(405)

            def log_message(self, *args):
                pass

        # One bounded writer also bounds worker memory and makes shutdown wait
        # for the in-flight response before the immutable ledger is published.
        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self._thread.start()
        self.api_url = f"http://127.0.0.1:{self._server.server_port}/api"
        return self

    def _fail(self, reason):
        with self._lock:
            if not self._failures:
                self._failures.append(reason)

    def _safe(self, raw):
        if self._token in raw:
            raise RecordingError("Credential reflection refused")
        try:
            parsed = json.loads(raw, object_pairs_hook=lambda pairs: pairs)
        except UnicodeError, ValueError:
            return
        except RecursionError:
            raise RecordingError("Unqualified response nesting") from None
        pending = [parsed]
        while pending:
            value = pending.pop()
            if isinstance(value, str) and self._credential in value:
                raise RecordingError("Credential reflection refused")
            if isinstance(value, (list, tuple)):
                pending.extend(value)

    def _handle(self, handler):
        # Serial forwarding makes the occurrence order and byte budget explicit.
        # The caller still owns whether the recorded source is non-atomic.
        with self._lock:
            if self._failures:
                handler.send_error(502, "Recording refused")
                return
            self._requests += 1
            ordinal = self._requests
            started = time.monotonic()
            try:
                target = handler.path
                self._safe(target.encode())
                url = urlsplit(target)
                if (
                    len(target) > 16384
                    or url.scheme
                    or url.netloc
                    or not url.path.startswith("/api/")
                    or not self._routes.fullmatch(url.path)
                    or url.fragment
                    or any(ord(c) < 33 or ord(c) > 126 for c in target)
                    or ordinal > self.max_requests
                    or handler.headers.get("Authorization")
                    != "Bearer " + self._credential
                ):
                    raise RecordingError("Invalid or over-budget recording request")
                host = self._upstream.hostname
                # localhost is pinned to a loopback address, never re-resolved.
                connection = http.client.HTTPConnection(
                    "127.0.0.1" if host == "localhost" else host,
                    self._upstream.port,
                    timeout=self.timeout,
                )
                expired = threading.Event()
                connected_socket = None
                response = None

                def interrupt():
                    expired.set()
                    if connected_socket is not None:
                        try:
                            connected_socket.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass

                remaining = self.timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise RecordingError("Total recording request deadline exhausted")
                connection.timeout = remaining
                timer = threading.Timer(remaining, interrupt)
                timer.daemon = True
                timer.start()
                try:
                    connection.connect()
                    connected_socket = connection.sock
                    peer = connected_socket.getpeername()
                    if (
                        not ipaddress.ip_address(peer[0]).is_loopback
                        or peer[1] != self._upstream.port
                    ):
                        raise RecordingError(
                            "Upstream endpoint differs from approved loopback origin"
                        )
                    if expired.is_set():
                        raise RecordingError(
                            "Total recording request deadline exhausted"
                        )
                    connection.request(
                        "GET",
                        target,
                        headers={
                            "Authorization": "Bearer " + self._credential,
                            "Accept-Encoding": handler.headers.get(
                                "Accept-Encoding", "identity"
                            ),
                            "Connection": "close",
                            "Host": self._upstream.netloc,
                        },
                    )
                    response = connection.getresponse()
                    headers = response.getheaders()
                    self._safe(repr(headers).encode())
                    if 300 <= response.status < 400:
                        raise RecordingError("Redirect refused")
                    chunks, length = [], 0
                    while chunk := response.read1(
                        min(65536, self.max_body_bytes + 1 - length)
                    ):
                        chunks.append(chunk)
                        length += len(chunk)
                        if (
                            length > self.max_body_bytes
                            or time.monotonic() - started > self.timeout
                        ):
                            raise RecordingError("Response body bound exhausted")
                    raw = b"".join(chunks)
                    if len(raw) > self.max_body_bytes:
                        raise RecordingError("Response body bound exhausted")
                    if response.length not in {None, 0}:
                        raise RecordingError("Incomplete response body")
                    self._safe(raw)
                    encoding = response.getheader(
                        "Content-Encoding", "identity"
                    ).casefold()
                    if encoding == "gzip":
                        with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:
                            decoded = stream.read(self.max_body_bytes + 1)
                        if len(decoded) > self.max_body_bytes:
                            raise RecordingError(
                                "Decoded response body bound exhausted"
                            )
                    elif encoding == "identity":
                        decoded = raw
                    else:
                        raise RecordingError("Unqualified response content encoding")
                    self._safe(decoded)
                    size = len(raw) + (len(decoded) if encoding != "identity" else 0)
                    prefix = f"response-{ordinal:08d}"
                    body = prefix + ".bin"
                    decoded_path = (
                        prefix + "-decoded.bin" if encoding != "identity" else body
                    )
                    occurrence = {
                        "ordinal": ordinal,
                        "phase": self._phase,
                        "upstream_peer": {"address": peer[0], "port": peer[1]},
                        "method": "GET",
                        "target": target,
                        "status": response.status,
                        "content_type": response.getheader("Content-Type"),
                        "content_encoding": encoding,
                        "transfer_encoding": response.getheader("Transfer-Encoding"),
                        "body": body,
                        "decoded_body": decoded_path,
                        "length": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "decoded_length": len(decoded),
                        "decoded_sha256": hashlib.sha256(decoded).hexdigest(),
                        "utc": datetime.now(UTC).isoformat(),
                        "elapsed_seconds": time.monotonic() - started,
                    }
                    row = json.dumps(occurrence, indent=2, ensure_ascii=False)
                    # Embedding this row in the indented ledger adds four
                    # spaces per line, plus list separators. Reserve a small
                    # fixed failure record; do not repeatedly serialize the
                    # whole growing transcript just to measure its size.
                    added = (
                        len(row.encode())
                        + 4 * (row.count("\n") + 1)
                        + (4 if not self._occurrences else 2)
                    )
                    if (
                        self._total + size + self._ledger_bytes + added + 512
                        > self.max_total_bytes
                    ):
                        raise RecordingError(
                            "Aggregate retained-evidence bound exhausted"
                        )
                    if expired.is_set() or time.monotonic() - started > self.timeout:
                        raise RecordingError(
                            "Total recording request deadline exhausted"
                        )
                    with (self.directory / body).open("xb") as stream:
                        stream.write(raw)
                    if encoding != "identity":
                        with (self.directory / decoded_path).open("xb") as stream:
                            stream.write(decoded)
                    self._total += size
                    self._ledger_bytes += added
                    self._occurrences.append(occurrence)
                    handler.send_response(response.status)
                    if occurrence["content_type"]:
                        handler.send_header("Content-Type", occurrence["content_type"])
                    if encoding != "identity":
                        handler.send_header("Content-Encoding", encoding)
                    handler.send_header("Content-Length", str(len(raw)))
                    handler.end_headers()
                    handler.wfile.write(raw)
                finally:
                    timer.cancel()
                    if response is not None:
                        response.close()
                    connection.close()
            except Exception as error:  # noqa: BLE001 - never expose source/transport text
                reason = (
                    str(error)
                    if isinstance(error, RecordingError)
                    else "Recording transport failed"
                )
                self._failures.append(reason)
                try:
                    handler.send_error(502, "Recording refused")
                except OSError:
                    pass

    def _ledger(self, occurrences=None):
        return {
            "schema": "brz2obsidian.api-http-recording/1",
            "brain_id": self.brain_id,
            "acquisition_id": self._acquisition_id,
            "purpose": self._purpose,
            "upstream_api_url": self._upstream_api_url,
            "upstream_origin": self._upstream_origin,
            "effective_upstream_endpoint": self._effective_upstream,
            "complete": not self._failures,
            "atomic": False,
            "discovery_limit": "empirical discovery; no universal completeness guarantee",
            "representation": "HTTP entity bytes after transfer decoding",
            "limits": {
                "max_requests": self.max_requests,
                "max_body_bytes": self.max_body_bytes,
                "max_total_bytes": self.max_total_bytes,
                "timeout": self.timeout,
            },
            "occurrences": self._occurrences if occurrences is None else occurrences,
            "failures": self._failures,
        }

    def __exit__(self, kind, value, traceback):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=self.timeout)
        self._closed = True
        if kind is not None:
            self._failures.append("Acquisition did not complete")
        ledger = self._ledger()
        self.fingerprint = write_json(self.directory / "recording.json", ledger)

    def seal(self, *, qualification):
        from .api_baseline import build_baseline

        if not self._closed:
            raise RecordingError("Close recording before sealing")
        return build_baseline(
            self.directory, self.fingerprint, qualification=qualification
        )

    def complete(self):
        """Acquire independently required coverage while this attempt is open.

        Missing evidence is never synthesized from the production snapshot.
        These supplemental GETs share the same explicit non-atomic attempt.
        """
        from .api_baseline import coverage

        if not self._started or self._closed:
            raise RecordingError("Coverage acquisition requires an open recording")
        self._phase = "supplemental-audit"
        while True:
            missing, *_ = coverage(
                self.directory,
                {
                    "brain_id": self.brain_id,
                    "occurrences": self._occurrences,
                    "limits": {"max_body_bytes": self.max_body_bytes},
                },
                allow_missing=True,
            )
            if not missing:
                final = "/api/brains/" + self.brain_id + "/statistics"
                if self._occurrences[-1]["target"] == final:
                    return
                missing = [final]
            for target in dict.fromkeys(missing):
                proxy = urlsplit(self.api_url)
                connection = http.client.HTTPConnection(
                    proxy.hostname, proxy.port, timeout=self.timeout
                )
                try:
                    connection.request(
                        "GET",
                        target,
                        headers={"Authorization": "Bearer " + self._credential},
                    )
                    response = connection.getresponse()
                    response.read(self.max_body_bytes + 1)
                    if self._failures:
                        raise RecordingError("Required coverage acquisition failed")
                finally:
                    connection.close()
