"""Complete bounded discovery, followed by this stage's metadata-only gate."""

from urllib.parse import urlencode

from brz2obsidian.contracts import (
    AccountingEntry,
    CalendarDates,
    Item,
    OriginalEvidence,
    SourceAccounting,
    SourceIdentity,
    SourceSnapshot,
)

from .capture import IDENTIFIERS, canonical
from .declarations import (
    GRAPH_FIELDS,
    NEIGHBORS,
    array,
    collection,
    counters,
    source_date,
    thought,
    uuid,
)
from .errors import refuse
from .session import LocalApiSession
from .transport import timestamp


class Acquisition:
    def __init__(self, client, config, brain_id, clock):
        self.client, self.config, self.brain_id, self.clock = (
            client,
            config,
            brain_id,
            clock,
        )
        self.ids, self.link_ids = set(), set()
        self.observations, self.thoughts, self.graphs = {}, {}, {}

    def get(self, operation, path, subject=None, deadline=None):
        return self.client.json(operation, path, subject, deadline=deadline)

    def seed(self, key):
        self.ids.add(uuid(key))
        if len(self.ids) + len(self.link_ids) > self.config.max_traversal_items:
            refuse(
                "max_traversal_items acquisition limit exhausted", "incomplete_source"
            )

    def observe(self, value):
        value = thought(value, self.brain_id)
        key = value["id"]
        if key in self.observations and self.observations[key] != value:
            refuse("Repeated authoritative thought observations disagree")
        self.observations[key] = value
        self.seed(key)
        return key

    def candidates(self, hit):
        if (
            not isinstance(hit, dict)
            or hit.get("brainId") != self.brain_id
            or hit.get("isFromOtherBrain") is not False
        ):
            refuse("A wildcard candidate has foreign or invalid ownership")
        found = False
        node = hit.get("sourceThought")
        if node is not None:
            if not isinstance(node, dict) or node.get("brainId") != self.brain_id:
                refuse("A wildcard owner has foreign or invalid ownership")
            self.seed(node.get("id"))
            found = True
        link = hit.get("sourceLink")
        if link is not None:
            if not isinstance(link, dict) or link.get("brainId") != self.brain_id:
                refuse("A wildcard link has foreign or invalid ownership")
            self.link_ids.add(uuid(link.get("id")))
            self.seed(link.get("thoughtIdA"))
            self.seed(link.get("thoughtIdB"))
            found = True
        if hit.get("attachmentId") is not None:
            uuid(hit["attachmentId"])
        if not found:
            refuse("A wildcard hit has no resolvable authoritative owner")

    def acquire(self):
        b = self.brain_id
        brain = collection(self.get("brain", "/brains/" + b, b), b)
        accessible = array(self.get("brain", "/brains"))
        matches = [
            value
            for value in accessible
            if isinstance(value, dict) and value.get("id") == b
        ]
        if not matches or any(collection(value, b) != brain for value in matches):
            refuse("The requested Brain does not agree with accessible Brain inventory")
        start = counters(self.get("statistics", "/brains/" + b + "/statistics"))
        definitions = {}
        for role, operation in ((2, "types"), (4, "tags")):
            status, raw = self.client.request(
                operation,
                "/thoughts/" + b + "/" + operation,
                allow_tag_error=operation == "tags",
            )
            if status == 400:
                try:
                    text = raw.decode("utf-8")
                except UnicodeError:
                    refuse("The failed tag inventory is not qualified UTF-8")
                if (
                    text.strip() != "Could not retrieve list of Tags for brain " + b
                    or start["tags"] != 0
                ):
                    refuse(
                        "The failed tag inventory does not meet the reviewed zero-tag rule"
                    )
                entries = []
            else:
                entries = array(self.client.decode_json(raw))
            keys = set()
            for value in entries:
                key = self.observe(value)
                if value["kind"] != role:
                    refuse("A definition inventory has contradictory roles")
                keys.add(key)
            definitions[role] = keys
            if operation == "tags":
                tag400 = status == 400
        self.seed(brain["homeThoughtId"])
        if self.config.include_pins:
            for value in array(self.get("thought", "/thoughts/" + b + "/pins")):
                self.observe(value)
        limit = min(
            self.config.search_initial_results,
            self.config.search_max_results or 2147483647,
        )
        deadline = self.clock() + self.config.search_timeout
        while True:
            found = array(
                self.get(
                    "search",
                    "/search/"
                    + b
                    + "?"
                    + urlencode(
                        {
                            "queryText": "*",
                            "maxResults": limit,
                            "onlySearchThoughtNames": "false",
                        }
                    ),
                    deadline=deadline,
                )
            )
            raw_count = len(found)
            for hit in found:
                self.candidates(hit)
            if self.clock() >= deadline:
                refuse("Wildcard search deadline exhausted", "incomplete_source")
            if raw_count < limit:
                break
            ceiling = self.config.search_max_results or 2147483647
            if limit >= ceiling:
                refuse(
                    "Wildcard search remains saturated at its result ceiling",
                    "incomplete_source",
                )
            limit = min(limit * 2, ceiling)
        resolved_links = set()
        while self.ids - self.thoughts.keys() or self.link_ids - resolved_links:
            if self.link_ids - resolved_links:
                link_id = min(self.link_ids - resolved_links)
                link = self.get("link", "/links/" + b + "/" + link_id, link_id)
                if (
                    not isinstance(link, dict)
                    or link.get("id") != link_id
                    or link.get("brainId") != b
                ):
                    refuse("An authoritative link has foreign or conflicting ownership")
                self.seed(link.get("thoughtIdA"))
                self.seed(link.get("thoughtIdB"))
                resolved_links.add(link_id)
                continue
            key = min(self.ids - self.thoughts.keys())
            value = thought(
                self.get("thought", "/thoughts/" + b + "/" + key, key), b, key
            )
            self.observe(value)
            self.thoughts[key] = value
            if value["kind"] == 5 or value["forgottenDateTime"] is not None:
                continue
            if value["kind"] in {2, 4} and key not in definitions[value["kind"]]:
                refuse(
                    "An included definition is absent from its authoritative inventory"
                )
            graph = self.get(
                "graph",
                "/thoughts/" + b + "/" + key + "/graph?includeSiblings=true",
                key,
            )
            if not isinstance(graph, dict) or graph.keys() != GRAPH_FIELDS:
                refuse("A thought graph has an unsupported declaration")
            if self.observe(graph["activeThought"]) != key:
                refuse("An acquired graph has a foreign active owner")
            projected = {}
            for name, target in NEIGHBORS.items():
                values = array(graph[name])
                neighbors = [self.observe(node) for node in values]
                projected[target] = sorted(set(neighbors))
            projected["type_ids"] = (
                [self.observe(graph["type"])] if graph["type"] is not None else []
            )
            links = array(graph["links"])
            projected["link_ids"] = [
                uuid(link.get("id")) for link in links if isinstance(link, dict)
            ]
            if len(projected["link_ids"]) != len(links):
                refuse("A graph link is malformed")
            self.link_ids.update(projected["link_ids"])
            attachments = graph["attachments"]
            if attachments is not None and not isinstance(attachments, list):
                refuse("A graph attachment declaration is malformed")
            projected["attachment_ids"] = []
            self.graphs[key] = projected, attachments
        # Included relationship normalization belongs to the next stage. Authoritative
        # endpoint acquisition still happens before this refusal.
        if self.link_ids or any(
            any(
                graph[name]
                for name in (
                    "parents_ids",
                    "children_ids",
                    "jump_ids",
                    "tag_ids",
                    "type_ids",
                )
            )
            for graph, _ in self.graphs.values()
        ):
            refuse(
                "Relationship or classification content is not implemented in this stage"
            )
        records, decisions, items = [], [], []

        def record(domain, key, owner, value):
            records.append(
                {"key": key, "domain": domain, "owner_id": owner, "value": value}
            )

        record("brain", "brain:" + b, b, brain)
        included = {1: [], 2: [], 4: []}
        observed_forgotten = 0
        for key, value in sorted(self.thoughts.items()):
            if value["kind"] == 5 or value["forgottenDateTime"] is not None:
                system = value["kind"] == 5
                if not system and value["kind"] == 1:
                    observed_forgotten += 1
                minimal = {
                    name: value[name]
                    for name in ("id", "brainId", "kind", "acType", "forgottenDateTime")
                }
                record("exclusion", "exclusion:" + key, b, minimal)
                decisions.append(
                    {
                        "key": "scope:excluded:" + key,
                        "rule_id": "local-api.system.v1"
                        if system
                        else "local-api.forgotten.v1",
                        "outcome": "excluded_system"
                        if system
                        else "excluded_forgotten",
                        "subjects": ["thought:" + key],
                        "evidence": ["exclusion:" + key],
                    }
                )
                continue
            included[value["kind"]].append(key)
            if (
                value["typeId"] is not None
                or value["foregroundColor"] is not None
                or value["backgroundColor"] is not None
            ):
                refuse(
                    "Classification or appearance content is not implemented in this stage"
                )
            graph, attachments = self.graphs[key]
            owned = array(
                self.get(
                    "attachments", "/thoughts/" + b + "/" + key + "/attachments", key
                )
            )
            if owned or attachments:
                refuse("Resource content is not implemented in this stage")
            note = self.get("note", "/notes/" + b + "/" + key, key)
            expected = {
                "brainId": b,
                "sourceId": key,
                "sourceType": 2,
                "modificationDateTime": "0001-01-01T00:00:00",
                "markdown": "",
                "html": None,
                "text": None,
            }
            if (
                note != expected
                or not isinstance(note, dict)
                or type(note.get("sourceType")) is not int
            ):
                refuse("Authored note content is not implemented in this stage")
            record("thought", "thought:" + key, b, value)
            record("graph", "graph:" + key, key, graph)
            record("no_note", "no_note:" + key, key, expected)
            rule = "local-api.roles-access.v1"
            decisions.append(
                {
                    "key": "scope:included:" + key,
                    "rule_id": rule,
                    "outcome": "included",
                    "subjects": ["thought:" + key],
                    "evidence": ["thought:" + key],
                }
            )
            items.append(
                Item(
                    key=key,
                    original_identity=key,
                    naming_seed=key.replace("-", ""),
                    role={1: "ordinary", 2: "definition", 4: "tag"}[value["kind"]],
                    title=value["name"],
                    label=value.get("label"),
                    calendar_dates=CalendarDates(
                        created=source_date(value["creationDateTime"]),
                        updated=source_date(value["modificationDateTime"]),
                    ),
                    evidence=("thought:" + key,),
                )
            )
        if brain["homeThoughtId"] not in included[1]:
            refuse("Home must be an included ordinary live thought")
        end = counters(self.get("statistics", "/brains/" + b + "/statistics"))
        if (
            start != end
            or end
            != {
                "thoughts": len(included[1]),
                "thoughtTypes": len(included[2]),
                "tags": len(included[4]),
                "forgottenThoughts": end["forgottenThoughts"],
                "links": 0,
            }
            or observed_forgotten > end["forgottenThoughts"]
        ):
            refuse("Required source inventory counts do not reconcile")
        record("statistics", "statistics:start", b, start)
        record("statistics", "statistics:end", b, end)
        if tag400:
            decisions.append(
                {
                    "key": "scope:tag400-zero:" + b,
                    "rule_id": "local-api.tag400.v1",
                    "outcome": "tag400_zero",
                    "subjects": ["brain:" + b],
                    "evidence": [
                        "inventory:tag_ids",
                        "statistics:end",
                        "statistics:start",
                    ],
                }
            )
        source = {
            "identifiers": IDENTIFIERS,
            "brain": brain,
            "records": records,
            "inventories": {
                "ordinary_ids": included[1],
                "type_ids": included[2],
                "tag_ids": included[4],
            },
            "scope": {
                "policy": "public-live-ordinary-type-tag-v1",
                "decisions": decisions,
            },
            "payloads": [],
        }
        snapshot = SourceSnapshot(
            identity=SourceIdentity(
                source_id=b,
                module_id="thebrain-local-api",
                module_version="1",
                format_version="1",
                source_sha256="",
                snapshot_digest="",
            ),
            collection_title=brain["name"],
            entry_key=brain["homeThoughtId"],
            items=tuple(items),
            original_evidence=tuple(
                OriginalEvidence(
                    key=r["key"],
                    kind="records",
                    original_json=canonical(r["value"]).decode("utf-8"),
                )
                for r in records
            )
            + tuple(
                OriginalEvidence(
                    key=d["key"],
                    kind="records",
                    original_json=canonical(d).decode("utf-8"),
                )
                for d in decisions
            ),
            accounting=SourceAccounting(
                entries=tuple(
                    AccountingEntry(
                        identity=r["key"],
                        disposition="normalized"
                        if r["domain"] == "thought"
                        else "retained_only",
                        references=(r["value"]["id"],)
                        if r["domain"] == "thought"
                        else (r["key"],),
                    )
                    for r in records
                )
                + tuple(
                    AccountingEntry(
                        identity=d["key"],
                        disposition="retained_only",
                        references=(d["key"],),
                    )
                    for d in decisions
                )
            ),
        )
        audit = {
            "atomic": False,
            "method": "bounded-read-only-local-api",
            "started_at": self.client.started_at,
            "finished_at": timestamp(),
            "limits": self.config.audit_limits(),
            "requests": self.client.requests,
            "consistency_limits": [
                "non-atomic-multi-request",
                "captured-copy-integrity-only",
                "empirical-discovery-no-completeness-guarantee",
            ],
        }
        self.client.ensure_safe(source)
        self.client.ensure_safe(snapshot.model_dump(mode="json"))
        return LocalApiSession(source=source, snapshot=snapshot, audit=audit)
