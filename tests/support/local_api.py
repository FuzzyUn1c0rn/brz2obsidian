"""Independent synthetic source facts served at the external HTTP boundary."""

import copy
import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

BRAIN = "11111111-1111-4111-8111-111111111111"
HOME = "22222222-2222-4222-8222-222222222222"
ALONE = "33333333-3333-4333-8333-333333333333"
KEY = "API_KEY_CANARY"


def thought(key, name):
    return {
        "id": key,
        "brainId": BRAIN,
        "name": name,
        "kind": 1,
        "acType": 0,
        "typeId": None,
        "label": None,
        "aliases": [],
        "foregroundColor": None,
        "backgroundColor": None,
        "forgottenDateTime": None,
        "creationDateTime": "2026-10-14T10:00:00",
        "modificationDateTime": "2026-10-14T10:00:00",
    }


class MetadataApi:
    def __init__(self):
        self.thoughts = {HOME: thought(HOME, "Entry"), ALONE: thought(ALONE, "Alone")}
        self.search = [
            {
                "brainId": BRAIN,
                "isFromOtherBrain": False,
                "sourceThought": {"id": key, "brainId": BRAIN, "kind": 0},
                "sourceLink": None,
            }
            for key in self.thoughts
        ]
        self.types = []
        self.tags = []
        self.pins = []
        self.requests = []
        self.overrides = {}
        self.response_chunks = {}

    def response(self, path, query):
        if path in self.overrides:
            value = self.overrides[path]
            return value(query) if callable(value) else value
        if path == f"/api/brains/{BRAIN}":
            return 200, {
                "id": BRAIN,
                "name": "Synthetic collection",
                "homeThoughtId": HOME,
            }
        if path == "/api/brains":
            return 200, [
                {"id": BRAIN, "name": "Synthetic collection", "homeThoughtId": HOME}
            ]
        if path == f"/api/brains/{BRAIN}/statistics":
            return 200, {
                "brainId": BRAIN,
                "thoughts": sum(
                    t["kind"] == 1 and t["forgottenDateTime"] is None
                    for t in self.thoughts.values()
                ),
                "thoughtTypes": len(self.types),
                "tags": len(self.tags),
                "forgottenThoughts": sum(
                    t["forgottenDateTime"] is not None for t in self.thoughts.values()
                ),
                "links": 0,
            }
        if path == f"/api/search/{BRAIN}":
            return 200, self.search
        if path == f"/api/thoughts/{BRAIN}/types":
            return 200, self.types
        if path == f"/api/thoughts/{BRAIN}/tags":
            return 200, self.tags
        if path == f"/api/thoughts/{BRAIN}/pins":
            return 200, self.pins
        for key, value in self.thoughts.items():
            if path == f"/api/thoughts/{BRAIN}/{key}":
                return 200, value
            if path == f"/api/thoughts/{BRAIN}/{key}/graph":
                return 200, {
                    "activeThought": value,
                    "parents": [],
                    "children": [],
                    "jumps": [],
                    "siblings": [],
                    "tags": [],
                    "type": None,
                    "links": [],
                    "attachments": [],
                }
            if path == f"/api/thoughts/{BRAIN}/{key}/attachments":
                return 200, []
            if path == f"/api/notes/{BRAIN}/{key}":
                return 200, {
                    "brainId": BRAIN,
                    "sourceId": key,
                    "sourceType": 2,
                    "modificationDateTime": "0001-01-01T00:00:00",
                    "markdown": "",
                    "html": None,
                    "text": None,
                }
        return 404, b"not found"


@contextmanager
def api_server(api=None):
    api = api or MetadataApi()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            api.requests.append((url.path, query, self.headers.get("Authorization")))
            result = api.response(url.path, query)
            status, value = result[:2]
            headers = result[2] if len(result) > 2 else {}
            body = (
                value
                if isinstance(value, bytes)
                else json.dumps(copy.deepcopy(value)).encode()
            )
            self.send_response(status)
            if not any(name.lower() == "content-length" for name in headers):
                self.send_header("Content-Length", str(len(body)))
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            try:
                size, pause = api.response_chunks.get(url.path, (max(1, len(body)), 0))
                for offset in range(0, len(body), size):
                    self.wfile.write(body[offset : offset + size])
                    self.wfile.flush()
                    if pause:
                        time.sleep(pause)
            except BrokenPipeError, ConnectionResetError, ConnectionAbortedError:
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield api, f"http://127.0.0.1:{server.server_port}/api"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
