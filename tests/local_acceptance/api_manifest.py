"""Source-bound API acceptance inputs. Standard library only; no converter imports."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


def read_json(data, *, parse_float=float):
    def unique(pairs):
        result = dict(pairs)
        assert len(result) == len(pairs), "duplicate evidence JSON keys"
        return result

    return json.loads(
        data.decode("utf-8"), object_pairs_hook=unique, parse_float=parse_float
    )


def safe_path(root, name):
    path = PurePosixPath(name)
    assert name and str(path) == name and not path.is_absolute(), "unsafe audit path"
    assert not {".", ".."}.intersection(name.split("/")), "unsafe audit path"
    assert not any(c in name for c in "\\:"), "unsafe audit path"
    result = root / name
    assert result.resolve().is_relative_to(root.resolve()), "unsafe audit path"
    return result


@dataclass(frozen=True)
class ApiBaseline:
    manifest_path: Path
    fingerprint: str
    data: dict

    def verify(self):
        raw = self.manifest_path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == self.fingerprint, (
            "baseline manifest changed; independent requalification required"
        )
        assert read_json(raw) == self.data, "baseline manifest changed in memory"
        for name, expected in self.data["files"].items():
            path = safe_path(self.manifest_path.parent, name)
            assert path.is_file(), "baseline evidence changed"
            payload = path.read_bytes()
            assert (
                len(payload) == expected["length"]
                and hashlib.sha256(payload).hexdigest() == expected["sha256"]
            ), "baseline evidence changed; independent requalification required"

    def bytes(self, name):
        assert name in self.data["files"], "unbound baseline input"
        return safe_path(self.manifest_path.parent, name).read_bytes()

    def json(self, name):
        return read_json(self.bytes(name))


def load_baseline(manifest_path, expected_sha256):
    path = Path(manifest_path)
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected_sha256, (
        "baseline manifest changed; independent requalification required"
    )
    data = read_json(raw)
    assert data["schema"] in {
        "brz2obsidian.api-acceptance/1",
        "brz2obsidian.api-acceptance/2",
    }, "baseline schema"
    if data["schema"] == "brz2obsidian.api-acceptance/1":
        assert "scope_inputs" not in data, "version1 does not grant scope inputs"
    else:
        required = {
            "schema",
            "files",
            "brain",
            "scope",
            "graphs",
            "types",
            "tags",
            "statistics",
            "link_attachments",
            "link_attachment_outcomes",
            "relationship_metadata",
            "no_notes",
            "payloads",
            "attachment_inventories",
            "attachment_metadata",
            "scope_inputs",
            "qualification",
            "archive_matches",
            "one_way_controls",
        }
        assert (
            required
            <= data.keys()
            <= required | {"source_packet_ledger", "http_responses"}
        ), "closed version2 baseline fields"
    baseline = ApiBaseline(path, expected_sha256, data)
    baseline.verify()
    return baseline
