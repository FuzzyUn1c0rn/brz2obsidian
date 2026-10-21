"""Combination of exact-bound source-neutral membership facts."""

from brz2obsidian.core.reference_targets import validate_targets


def validate_memberships(document, *, target_safety=True):
    fields = {f.key: f for f in document.fields}
    sets = {}
    for membership in document.memberships:
        if membership.field_key in sets or membership.field_key not in fields:
            raise ValueError("structure_unbound")
        field = fields[membership.field_key]
        if field.kind != "opaque":
            raise ValueError("structure_conflict")
        raw = membership.prefix + b"".join(e.raw for e in membership.entries)
        if document.content.data[field.span.start : field.span.end] != raw:
            raise ValueError("structure_unbound")
        if target_safety:
            validate_targets(tuple(e.target for e in membership.entries))
        for entry in membership.entries:
            if (
                entry.target.kind != membership.kind
                or entry.representation not in entry.target.representations
            ):
                raise ValueError("structure_conflict")
        sets[membership.field_key] = membership
    if (
        document.appearance_field is not None
        and document.appearance_field not in fields
    ):
        raise ValueError("structure_unbound")
    return sets


def appearance_issues(document):
    if document.appearance_field is None:
        return ()
    field = next(f for f in document.fields if f.key == document.appearance_field)
    if field.value in (None, ""):
        return ()
    if any(
        field.value in e.target.representations
        for m in document.memberships
        if m.kind == "category"
        for e in m.entries
    ):
        return ()
    return ("appearance_not_member",)


def used_mappings(comparison):
    """Keep only classification meanings actually referenced by this comparison."""

    def ordered(records):
        return tuple(
            sorted(records, key=lambda m: (m.classification_id, m.kind, m.target_id))
        )

    if any(
        d.status != "supported"
        for d in (comparison.original, comparison.current, comparison.incoming)
    ):
        # Unsupported syntax cannot prove a supplied mapping is unused.
        return ordered(comparison.prior_mappings), ordered(comparison.incoming_mappings)
    targets = {
        e.target_id
        for d in (comparison.original, comparison.current, comparison.incoming)
        for m in d.memberships
        for e in m.entries
    }
    targets.update(
        t.target_id
        for d in (comparison.original, comparison.current, comparison.incoming)
        for section in d.owned_sections
        for t in section.targets
    )
    records = comparison.prior_mappings + comparison.incoming_mappings
    ids = {m.classification_id for m in records if m.target_id in targets}
    return tuple(
        ordered(m for m in values if m.classification_id in ids)
        for values in (comparison.prior_mappings, comparison.incoming_mappings)
    )


def combine_memberships(documents, comparison):
    old_sets, local_sets, source_sets = (validate_memberships(d) for d in documents)
    if set(old_sets) != set(local_sets) or set(old_sets) != set(source_sets):
        raise ValueError("structure_conflict")
    maps = []
    for records in (comparison.prior_mappings, comparison.incoming_mappings):
        index = {m.classification_id: (m.kind, m.target_id) for m in records}
        if len(index) != len(records) or len(set(index.values())) != len(records):
            raise ValueError("structure_conflict")
        maps.append(index)
    prior, incoming = used_mappings(comparison)
    maps = [
        {m.classification_id: (m.kind, m.target_id) for m in records}
        for records in (prior, incoming)
    ]
    if any(maps[1].get(key) != value for key, value in maps[0].items()):
        raise ValueError("structure_conflict")
    replacements, results = {}, {}
    for key, source in source_sets.items():
        old, local = old_sets[key], local_sets[key]
        if old.kind != local.kind or old.kind != source.kind:
            raise ValueError("structure_conflict")
        old_ids, local_ids, source_ids = (
            {e.target_id for e in m.entries} for m in (old, local, source)
        )
        removed = old_ids - source_ids
        # Removals remain explicit review; additions alone cannot remove authored links.
        if removed:
            raise ValueError("structure_conflict")
        additions = tuple(
            e for e in source.entries if e.target_id not in old_ids | local_ids
        )
        prefix = source.prefix if additions and not local.entries else local.prefix
        result = local.model_copy(
            update={"entries": local.entries + additions, "prefix": prefix}
        )
        if additions:
            replacements[key] = result.prefix + b"".join(e.raw for e in result.entries)
        results[key] = result
    return replacements, results
