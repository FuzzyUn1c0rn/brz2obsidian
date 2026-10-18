from tests.support.local_api import BRAIN

ZERO = "00000000-0000-0000-0000-000000000000"


def thought_match(owner):
    return {
        "brainId": ZERO,
        "isFromOtherBrain": False,
        "sourceThought": {"id": owner, "brainId": BRAIN, "kind": 0},
        "sourceLink": None,
        "searchResultType": 1,
        "entityType": 2,
        "sourceType": 0,
        "attachmentId": ZERO,
        "name": "Search display hint",
        "brainName": None,
    }


REQUIRED = (
    "brainId",
    "isFromOtherBrain",
    "sourceThought",
    "sourceLink",
    "searchResultType",
    "entityType",
    "sourceType",
    "attachmentId",
)
