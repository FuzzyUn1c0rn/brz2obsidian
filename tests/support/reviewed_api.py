"""HTTP-only review equivalence controls, independent of capture encoders."""

import copy

from tests.support.local_api_payloads import RichPayloadApi


class ReorderedReviewApi(RichPayloadApi):
    def response(self, path, query):
        status, value = super().response(path, query)
        value = copy.deepcopy(value)
        if status == 200 and isinstance(value, list):
            value.reverse()
        if status == 200 and isinstance(value, dict) and path.endswith("/graph"):
            for field in (
                "parents",
                "children",
                "jumps",
                "siblings",
                "tags",
                "links",
                "attachments",
            ):
                if isinstance(value.get(field), list):
                    value[field].reverse()
        if status == 200 and path.endswith("/statistics"):
            value["dateGenerated"] = "2031-01-02T03:04:05Z"
        return status, value
