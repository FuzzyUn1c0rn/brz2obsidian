"""Complete bounded discovery and qualified source/payload acquisition."""

from urllib.parse import urlencode

from brz2obsidian.contracts import (
    AccountingEntry,
    CalendarDates,
    DeclaredAppearance,
    Item,
    OriginalEvidence,
    SourceAccounting,
    SourceIdentity,
    SourceSnapshot,
)

from .capture import canonical, identifiers
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
from .errors import refuse, unsupported_shape
from .graph import link_identity, normalize_relationships
from .notes import bind_documents
from .resources import capture_owner
from .session import LocalApiSession
from .transport import timestamp

ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def _same_observation(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _same_observation(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _same_observation(a, b) for a, b in zip(left, right)
        )
    return left == right


def _candidate_shape(hit, brain_id):
    required = {
        "brainId",
        "isFromOtherBrain",
        "sourceThought",
        "sourceLink",
        "searchResultType",
        "entityType",
        "sourceType",
        "attachmentId",
    }
    if not required <= hit.keys() or not hit.keys() <= required | {"name", "brainName"}:
        return None
    owner = hit["sourceThought"]
    if (
        not isinstance(owner, dict)
        or owner.get("brainId") != brain_id
        or hit["sourceLink"] is not None
        or any(
            hit.get(field) is not None and not isinstance(hit[field], str)
            for field in ("name", "brainName")
        )
    ):
        return None
    values = tuple(
        hit[field] for field in ("searchResultType", "entityType", "sourceType")
    )
    if not all(type(value) is int for value in values):
        return None
    if values == (1, 2, 0) and hit["attachmentId"] == ZERO_UUID:
        return "thought"
    if values in ((3, 4, 2), (4, 4, 2)):
        uuid(hit["attachmentId"])
        return "attachment"
    return None


class Acquisition:
    def __init__(
        self,
        client,
        config,
        brain_id,
        clock,
        profile_version="1",
        capture_directory=None,
    ):
        self.client, self.config, self.brain_id, self.clock = (
            client,
            config,
            brain_id,
            clock,
        )
        self.ids, self.link_ids = set(), set()
        self.observations, self.thoughts, self.graphs = {}, {}, {}
        self.links = {}
        self.profile_version = profile_version
        self.capture_directory = capture_directory

    def get(self, operation, path, subject=None, deadline=None):
        return self.client.json(operation, path, subject, deadline=deadline)

    def statistics(self):
        value = self.get("statistics", "/brains/" + self.brain_id + "/statistics")
        if not isinstance(value, dict) or value.get("brainId") != self.brain_id:
            refuse("Source statistics have missing or foreign Brain ownership")
        return counters(value)

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

    def observe_link(self, value, expected_id=None):
        key = link_identity(value, self.brain_id, expected_id)
        if key in self.links and not _same_observation(self.links[key], value):
            refuse("Repeated authoritative relationship observations disagree")
        self.links[key] = value
        self.link_ids.add(key)
        self.seed(value["thoughtIdA"])
        self.seed(value["thoughtIdB"])
        return key

    def candidates(self, hit):
        if (
            not isinstance(hit, dict)
            or hit.get("brainId") not in (self.brain_id, ZERO_UUID)
            or hit.get("isFromOtherBrain") is not False
        ):
            refuse("A wildcard candidate has foreign or invalid ownership")
        if self.profile_version == "3" and any(
            node is not None
            and (not isinstance(node, dict) or node.get("brainId") != self.brain_id)
            for node in (hit.get("sourceThought"), hit.get("sourceLink"))
        ):
            refuse("A wildcard candidate has foreign or invalid ownership")
        shape = (
            _candidate_shape(hit, self.brain_id)
            if hit["brainId"] == ZERO_UUID or hit.get("attachmentId") == ZERO_UUID
            else None
        )
        if hit["brainId"] == ZERO_UUID and shape is None:
            unsupported_shape(
                self.profile_version,
                "search",
                "A wildcard candidate envelope is not qualified",
            )
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
            if hit["attachmentId"] == ZERO_UUID:
                if shape != "thought":
                    unsupported_shape(
                        self.profile_version,
                        "search",
                        "A wildcard attachment identity is not qualified",
                    )
            else:
                uuid(hit["attachmentId"])
        if not found:
            unsupported_shape(
                self.profile_version,
                "search",
                "A wildcard hit has no resolvable authoritative owner",
            )

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
        start = self.statistics()
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
                self.observe_link(link, link_id)
                resolved_links.add(link_id)
                continue
            key = min(self.ids - self.thoughts.keys())
            value = thought(
                self.get("thought", "/thoughts/" + b + "/" + key, key), b, key
            )
            self.observe(value)
            self.thoughts[key] = value
            if tag400 and value["kind"] == 4:
                refuse(
                    "Authoritative tag metadata contradicts the reviewed zero-tag rule"
                )
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
            incident_links = set()
            for link in links:
                if not isinstance(link, dict) or link.get("thoughtIdA") == link.get(
                    "thoughtIdB"
                ):
                    refuse("A graph carries a malformed relationship candidate")
                incident = key in (link.get("thoughtIdA"), link.get("thoughtIdB"))
                # Discovery is Brain-wide; only complete authoritative endpoint
                # graphs can qualify a candidate's relationship meaning.
                observed = self.observe_link(link)
                if incident:
                    incident_links.add(observed)
            projected["link_ids"] = sorted(incident_links)
            attachments = graph["attachments"]
            if attachments is not None and not isinstance(attachments, list):
                refuse("A graph attachment declaration is malformed")
            projected["attachment_ids"] = []
            self.graphs[key] = projected, attachments
        excluded = {
            key
            for key, value in self.thoughts.items()
            if value["kind"] == 5 or value["forgottenDateTime"] is not None
        }
        active_links = {
            key: value
            for key, value in self.links.items()
            if not {value["thoughtIdA"], value["thoughtIdB"]} & excluded
        }
        relationships, assignments = normalize_relationships(
            active_links,
            self.graphs,
            {key: value for key, value in self.thoughts.items() if key not in excluded},
            excluded,
            profile_version=self.profile_version,
        )
        # These retained inventories are scoped facts, not raw graph wrappers.
        # Keep removed identities only in minimal exclusion/scope evidence.
        for graph, _ in self.graphs.values():
            for name in (*NEIGHBORS.values(), "type_ids"):
                graph[name] = [key for key in graph[name] if key not in excluded]
            graph["link_ids"] = [
                key for key in graph["link_ids"] if key in active_links
            ]
        for relationship in relationships:
            if array(
                self.get(
                    "attachments",
                    "/links/" + b + "/" + relationship.key + "/attachments",
                    relationship.key,
                )
            ):
                refuse("Link-owned content is outside reviewed coverage")
        records, decisions, items = [], [], []

        def record(domain, key, owner, value):
            records.append(
                {"key": key, "domain": domain, "owner_id": owner, "value": value}
            )

        record("brain", "brain:" + b, b, brain)
        for key, value in sorted(self.links.items()):
            if key in active_links:
                record("link", "link:" + key, b, value)
            else:
                minimal = {
                    name: value[name]
                    for name in ("id", "brainId", "thoughtIdA", "thoughtIdB")
                }
                record("link", "link:" + key, b, minimal)
                endpoints = {value["thoughtIdA"], value["thoughtIdB"]}
                removed = endpoints & excluded
                system = any(self.thoughts[node]["kind"] == 5 for node in removed)
                decisions.append(
                    {
                        "key": "scope:association:" + key,
                        "rule_id": "local-api.system.v1"
                        if system
                        else "local-api.forgotten.v1",
                        "outcome": "excluded_association",
                        "subjects": ["link:" + key]
                        + ["thought:" + node for node in sorted(endpoints)],
                        "evidence": ["link:" + key]
                        + ["exclusion:" + node for node in sorted(removed)],
                    }
                )
        assets, documents, payloads = [], [], {}
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
            graph, attachments = self.graphs[key]
            owned = array(
                self.get(
                    "attachments", "/thoughts/" + b + "/" + key + "/attachments", key
                )
            )
            owner_assets, owner_documents, owner_payloads = capture_owner(
                self.client,
                self.config,
                b,
                key,
                owned,
                attachments,
                record,
                self.profile_version,
                {k: self.thoughts[k] for k in excluded},
                decisions,
                self.capture_directory,
            )
            assets.extend(owner_assets)
            documents.extend(owner_documents)
            payloads.update(owner_payloads)
            graph["attachment_ids"] = sorted(
                [a.asset_id for a in owner_assets]
                + [d.key for d in owner_documents if d.original_copy_omitted]
            )
            note = (
                self.get("note", "/notes/" + b + "/" + key, key)
                if not owner_documents
                else None
            )
            expected = {
                "brainId": b,
                "sourceId": key,
                "sourceType": 2,
                "modificationDateTime": "0001-01-01T00:00:00",
                "markdown": "",
                "html": None,
                "text": None,
            }
            if not owner_documents and (
                note != expected
                or not isinstance(note, dict)
                or type(note.get("sourceType")) is not int
            ):
                refuse(
                    "Authored note absence is not established by the qualified empty state"
                )
            record("thought", "thought:" + key, b, value)
            record("graph", "graph:" + key, key, graph)
            if not owner_documents:
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
                    document_ids=tuple(d.key for d in owner_documents),
                    resource_ids=tuple(
                        a.asset_id for a in owner_assets if a.role != "note_original"
                    ),
                    role={1: "ordinary", 2: "definition", 4: "tag"}[value["kind"]],
                    title=value["name"],
                    label=value.get("label"),
                    declared_appearance=DeclaredAppearance(
                        foreground_color=value["foregroundColor"],
                        background_color=value["backgroundColor"],
                        icon_asset_id=next(
                            (a.asset_id for a in owner_assets if a.role == "icon"), None
                        ),
                    )
                    if value["foregroundColor"] is not None
                    or value["backgroundColor"] is not None
                    or any(a.role == "icon" for a in owner_assets)
                    else None,
                    calendar_dates=CalendarDates(
                        created=source_date(value["creationDateTime"]),
                        updated=source_date(value["modificationDateTime"]),
                    ),
                    evidence=("thought:" + key,),
                )
            )
        if brain["homeThoughtId"] not in included[1]:
            refuse("Home must be an included ordinary live thought")
        end = self.statistics()
        if (
            start != end
            or end
            != {
                "thoughts": len(included[1]),
                "thoughtTypes": len(included[2]),
                "tags": len(included[4]),
                "forgottenThoughts": end["forgottenThoughts"],
                # This is a narrow observed ordinary-link family, not a total.
                # Excluded population/tuples supply no qualified count equation.
                "links": end["links"]
                if active_links.keys() != self.links.keys()
                or end["forgottenThoughts"] > 0
                else sum(v["meaning"] == 1 for v in active_links.values()),
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
        documents, findings = bind_documents(
            documents,
            assets,
            set().union(*map(set, included.values())),
            with_findings=True,
        )
        from .gaps import gap_projections

        gap_findings, gap_decisions = gap_projections(
            assets,
            {
                r["value"]["id"]: r["value"]
                for r in records
                if r["domain"] == "attachment"
            },
        )
        findings.extend(gap_findings)
        decisions.extend(gap_decisions)
        source = {
            "identifiers": identifiers(self.profile_version),
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
            "payloads": [
                {
                    "asset_id": a.asset_id,
                    "owner_id": a.owner,
                    "availability": a.availability,
                    "actual_length": a.actual_length,
                    "actual_sha256": a.actual_sha256,
                    "external_uri": a.external_uri,
                }
                for a in assets
            ],
        }
        normalized_records = {
            **{"thought:" + item.key: (item.key,) for item in items},
            **{"link:" + r.key: (r.key,) for r in relationships},
            **{"attachment:" + a.asset_id: (a.asset_id,) for a in assets},
            **{"note_text:" + d.owner: (d.key,) for d in documents},
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
            documents=tuple(documents),
            assets=tuple(assets),
            findings=tuple(findings),
            relationships=relationships,
            classification_assignments=assignments,
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
                        if r["key"] in normalized_records
                        else "retained_only",
                        references=normalized_records.get(r["key"], (r["key"],)),
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
        self.capture_directory.verify()
        return LocalApiSession(
            source=source,
            snapshot=snapshot,
            audit=audit,
            payloads=payloads,
            profile_version=self.profile_version,
        )
