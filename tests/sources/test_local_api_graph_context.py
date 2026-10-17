from tests.support.local_api import ALONE, BRAIN, HOME, thought
from tests.support.local_api_graph import HIERARCHY, GraphApi, link

SIBLING = "44444444-4444-4444-8444-444444444444"
OTHER_LINK = "55555555-5555-4555-8555-555555555555"


class SiblingGraphApi(GraphApi):
    def __init__(self):
        super().__init__()
        self.thoughts[SIBLING] = thought(SIBLING, "Sibling")
        self.links[OTHER_LINK] = link(OTHER_LINK, HOME, SIBLING, direction=1)

    def response(self, path, query):
        if path in self.overrides:
            return super().response(path, query)
        status, value = super().response(path, query)
        if path == f"/api/thoughts/{BRAIN}/{ALONE}/graph" and status == 200:
            value["siblings"] = [self.thoughts[SIBLING]]
            value["links"].append(self.links[OTHER_LINK])
        if path == f"/api/thoughts/{BRAIN}/{SIBLING}/graph" and status == 200:
            value["siblings"] = [self.thoughts[ALONE]]
            if HIERARCHY in self.links:
                value["links"].append(self.links[HIERARCHY])
        return status, value
