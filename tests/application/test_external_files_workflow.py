"""External files are archive-only references through the public workflow."""

import json

OWNER = "bbbbbbbb-0000-4000-8000-000000000001"


def association(identity, form):
    if form == "direct":
        return {"AttachmentId": identity}
    if form == "nested":
        return {"Metadata": {"Rows": [{"AttachmentId": identity.upper()}]}}
    if form == "serialized":
        return {"Metadata": json.dumps({"ObjectId": identity})}
    return {
        "Metadata": '{"AttachmentId":"public","AttachmentId":'
        + json.dumps(identity)
        + "}"
    }
