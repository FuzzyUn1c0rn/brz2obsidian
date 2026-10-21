"""Source-neutral target meaning shared by membership and section consumers."""

import unicodedata


def validate_targets(targets):
    ids, meanings, paths = set(), set(), set()
    reserved = {"con", "prn", "aux", "nul"} | {
        f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)
    }
    for record in targets:
        if record.status != "safe" or not record.representations:
            raise ValueError("structure_conflict")
        if record.kind == "tag":
            if (
                record.identity is not None
                or record.canonical_path is not None
                or record.target is not None
            ):
                raise ValueError("structure_conflict")
            meaning = ("tag", record.target_id)
        else:
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
                    or part.split(".", 1)[0].casefold() in reserved
                    or any(ord(c) < 32 or c in '<>:"\\|?*' for c in part)
                    for part in path.split("/")
                )
                or target.normalized_path
                != unicodedata.normalize(
                    "NFC", unicodedata.normalize("NFC", path).casefold()
                )
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
            if record.kind in ("category", "relationship") or (
                record.kind == "note" and record.identity is not None
            ):
                if record.identity is None:
                    raise ValueError("structure_conflict")
                identity = record.identity
                meaning = (identity.collection_id, identity.module_id, identity.item_id)
            else:
                if record.identity is not None:
                    raise ValueError("structure_conflict")
                meaning = (record.kind, record.target_id)
        if record.target_id in ids or meaning in meanings:
            raise ValueError("structure_conflict")
        ids.add(record.target_id)
        meanings.add(meaning)
