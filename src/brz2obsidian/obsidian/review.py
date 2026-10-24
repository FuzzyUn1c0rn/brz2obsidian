"""In-memory explicit candidate safety, independent of automatic merge grammar."""

from hashlib import sha256

import yaml

from brz2obsidian.contracts import (
    ReviewedProperty,
    ReviewedTextCandidate,
    StructureSpan,
    TextCandidateDocument,
)

from .links import interpret_links


class _UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        keys = set()
        for key, _value in node.value:
            value = self.construct_object(key, deep=deep)
            try:
                if value in keys:
                    raise ValueError("duplicate_property")
                keys.add(value)
            except TypeError as error:
                raise ValueError("property_key_unsupported") from error
        return super().construct_mapping(node, deep=deep)


def inspect_text_candidate(
    content,
    *,
    identity,
    target,
    output_format,
    source_path,
    document_id,
    path_mode,
    link_targets,
    link_target_facts,
    link_inventory,
    membership_targets=(),
):
    """Validate explicit whole-file text without proposing edits or granting merge ownership."""
    raw = content.data
    properties = []
    body_start = 0
    appearance = None
    appearance_present = False
    status, issues = "safe", ()
    try:
        if output_format != 7:
            raise ValueError("candidate_format_unsupported")
        text = raw.decode("utf-8")
        if (
            raw.startswith(b"\xef\xbb\xbf")
            or any(c < 32 and c not in (9, 10, 13) for c in raw)
            or b"\r" in raw.replace(b"\r\n", b"")
        ):
            raise ValueError("candidate_encoding_uncertain")
        lines = text.splitlines(keepends=True)
        if lines and lines[0].rstrip("\r\n") == "---":
            closing = next(
                (
                    i
                    for i, line in enumerate(lines[1:], 1)
                    if line.rstrip("\r\n") in ("---", "...")
                ),
                None,
            )
            if closing is None:
                raise ValueError("frontmatter_unclosed")
            front = "".join(lines[1:closing])
            offset = len(lines[0].encode("utf-8"))
            body_start = len("".join(lines[: closing + 1]).encode("utf-8"))
            loader = _UniqueLoader(front)
            try:
                node = loader.get_single_node()
                if node is not None:
                    if not isinstance(node, yaml.MappingNode) or any(
                        k.tag != "tag:yaml.org,2002:str" for k, _ in node.value
                    ):
                        raise ValueError("property_key_unsupported")
                    values = loader.construct_document(node)
                    for key, value in node.value:
                        name = loader.construct_object(key)
                        parsed = values[name]
                        component = {
                            "source_collection_id": "collection",
                            "source_item_id": "item",
                        }.get(name)
                        if component and (not isinstance(parsed, str) or not parsed):
                            raise ValueError("candidate_identity_invalid")
                        kind = {"categories": "category", "tags": "tag"}.get(name)
                        representations, targets = (), ()
                        if kind:
                            if not isinstance(parsed, list) or any(
                                not isinstance(v, str) for v in parsed
                            ):
                                raise ValueError("candidate_membership_invalid")
                            representations = tuple(parsed)
                            selected = []
                            for representation in parsed:
                                matches = [
                                    t
                                    for t in membership_targets
                                    if t.kind == kind
                                    and representation in t.representations
                                ]
                                if len(matches) != 1:
                                    raise ValueError("candidate_target_unknown")
                                selected.append(matches[0])
                            targets = tuple(selected)
                        if name == "appearance_category":
                            appearance_present = True
                            if parsed is not None and not isinstance(parsed, str):
                                raise ValueError("candidate_appearance_invalid")
                            appearance = parsed
                        start = offset + len(
                            front[: key.start_mark.index].encode("utf-8")
                        )
                        end = offset + len(
                            front[: value.end_mark.index].encode("utf-8")
                        )
                        properties.append(
                            ReviewedProperty(
                                key=name,
                                span=StructureSpan(start=start, end=end),
                                raw=raw[start:end],
                                identity_component=component,
                                identity_value=parsed if component else None,
                                membership_kind=kind,
                                representations=representations,
                                targets=targets,
                            )
                        )
            finally:
                loader.dispose()
        elif raw.startswith(b"---"):
            raise ValueError("frontmatter_ambiguous")
    except (ValueError, yaml.YAMLError) as error:
        status, issues = "unsafe", (str(error),)
    document = TextCandidateDocument(
        schema_id="brz2obsidian.text-candidate-document",
        schema_version=1,
        output_format=output_format,
        content=content,
        status=status,
        issues=issues,
        properties=tuple(properties),
        body=StructureSpan(start=body_start, end=len(raw)),
        appearance=appearance,
        appearance_present=appearance_present,
    )
    return ReviewedTextCandidate(
        schema_id="brz2obsidian.reviewed-text-candidate",
        schema_version=1,
        content=content,
        document=document,
        links=interpret_links(
            content,
            document_id=document_id,
            source_path=source_path,
            path_mode=path_mode,
            targets=link_targets,
            target_facts=link_target_facts,
            inventory=link_inventory,
        ),
        link_targets=link_targets,
        link_target_facts=link_target_facts,
        identity=identity,
        target=target,
        status=status,
        validation_fingerprint="obsidian-candidate/v1:" + sha256(raw).hexdigest(),
    )
