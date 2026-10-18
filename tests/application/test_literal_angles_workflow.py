"""Literal prose is preserved through actual BRZ Workflow and CLI routes."""

import json

from tests.application.test_forgotten_workflow import rewrite
from tests.application.test_resources_workflow import HOME, resource_archive


def literal_archive(path, body, *, resources=(), thoughts=()):
    source = resource_archive(path, resources, thoughts=thoughts)

    def note(parts):
        rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
        rows[0]["DataLength"] = len(body)
        parts["attachments.json"] = "\n".join(json.dumps(row) for row in rows).encode()
        parts[HOME + "/Notes.md"] = body

    rewrite(source, note)
    return source
