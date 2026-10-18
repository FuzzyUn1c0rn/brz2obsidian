"""The narrowly reviewed active NoteType-0 note, through real BRZ workflows."""

from tests.application.test_links_workflow import TARGET
from tests.application.test_resources_workflow import resource_archive, thought

OWNER = "cccccccc-0000-4000-8000-000000000003"
NOTE = "aaaaaaaa-0000-4000-8000-000000000001"
IMAGE = "aaaaaaaa-0000-4000-8000-000000000002"


def exceptional_archive(path, body, *, resources=(), reverse=False):
    return resource_archive(
        path,
        [
            ({"SourceId": OWNER, "Location": "Notes.md"}, body),
            *resources,
        ],
        thoughts=[thought(OWNER, "Different marker"), thought(TARGET, "Topic.v2")],
        reverse=reverse,
    )
