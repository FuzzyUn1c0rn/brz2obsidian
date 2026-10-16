"""Exact independently authored HTTP body delivery; no source interpretation."""

import hashlib
import json


class RawPacketApi:
    def __init__(self, packet):
        self.files = packet["files"]
        ledger = json.loads(packet["ledger"])
        self.routes = {row["route"]: row for row in ledger["routes"]}
        self.pair = ledger["consistency_pair"]
        self.requests = []
        self.response_chunks = {}
        self.response_counts = {}
        self.served = []
        self.unexpected_requests = []

    def response(self, path, query):
        if path not in self.routes:
            self.unexpected_requests.append(path)
            return 404, b""
        row = self.routes[path]
        body_path = row["body_path"]
        if path == self.pair["route"]:
            count = self.response_counts.get(path, 0)
            self.response_counts[path] = count + 1
            body_path = (
                self.pair["starting_body"]
                if count % 2 == 0
                else self.pair["ending_body"]
            )
        raw = self.files[body_path]
        assert isinstance(raw, bytes), "the transport requires exact source bytes"
        self.served.append(
            {
                "path": path,
                "query": query,
                "status": row["status"],
                "body_path": body_path,
                "length": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        return row["status"], raw
