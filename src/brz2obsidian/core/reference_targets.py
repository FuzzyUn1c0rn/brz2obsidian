"""Source-neutral target meaning shared by membership and section consumers."""

import unicodedata

_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)
}


def _register_target_path(record, paths):
    path, target = record.canonical_path, record.target
    if (
        path is None
        or target is None
        or target.status != "safe"
        or target.containment != "contained"
        or any(c in path for c in "\\:\x00")
        or any(p in ("", ".", "..") for p in path.split("/"))
        or any(
            part.endswith((".", " "))
            or part.split(".", 1)[0].casefold() in _RESERVED
            or any(ord(c) < 32 or c in '<>:"\\|?*' for c in part)
            for part in path.split("/")
        )
        or target.normalized_path
        != unicodedata.normalize("NFC", unicodedata.normalize("NFC", path).casefold())
    ):
        raise ValueError("structure_conflict")
    if any(
        target.normalized_path == other
        or target.normalized_path.startswith(other + "/")
        or other.startswith(target.normalized_path + "/")
        for other in paths
    ):
        raise ValueError("structure_conflict")
    paths.add(target.normalized_path)


def _target_meaning(record, paths):
    if record.kind == "tag":
        if (
            record.category_anchor is not None
            or record.identity is not None
            or record.canonical_path is not None
            or record.target is not None
        ):
            raise ValueError("structure_conflict")
        return "tag", record.target_id
    _register_target_path(record, paths)
    identity = record.identity
    if record.category_anchor == "observed_path":
        if record.kind != "category" or identity is not None:
            raise ValueError("structure_conflict")
        return "vault_category", record.target.normalized_path
    if record.category_anchor == "scoped_identity" and (
        record.kind != "category" or identity is None
    ):
        raise ValueError("structure_conflict")
    if record.kind in ("category", "relationship") or (
        record.kind == "note" and identity is not None
    ):
        if identity is None:
            raise ValueError("structure_conflict")
        return identity.collection_id, identity.module_id, identity.item_id
    if identity is not None:
        raise ValueError("structure_conflict")
    return record.kind, record.target_id


def validate_targets(targets):
    ids, meanings, paths = set(), set(), set()
    for record in targets:
        if record.status != "safe" or not record.representations:
            raise ValueError("structure_conflict")
        meaning = _target_meaning(record, paths)
        if record.target_id in ids or meaning in meanings:
            raise ValueError("structure_conflict")
        ids.add(record.target_id)
        meanings.add(meaning)
