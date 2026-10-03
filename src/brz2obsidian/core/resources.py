"""Source-neutral resource eligibility and stable preservation assignments."""

import re
import unicodedata
from pathlib import PurePosixPath

from brz2obsidian.contracts import AssetTarget, Issue, MigrationRefused


def resource_owners(snapshot):
    return {
        asset.owner
        for asset in snapshot.assets
        if (asset.availability == "external" and asset.role in {"url", "directory"})
        or (
            asset.availability == "present"
            and asset.role in {"file", "image"}
            and asset.actual_length > 0
        )
    }


def _refuse(message):
    raise MigrationRefused(
        (
            Issue(
                code="invalid_source",
                phase="planning",
                message=message,
                guidance="Supply distinct stable hexadecimal naming seeds.",
            ),
        )
    )


def _tokens(values):
    lengths = {key: 8 for key in values}
    while True:
        result = {key: seed[: lengths[key]] for key, seed in values.items()}
        duplicate = {
            token for token in result.values() if list(result.values()).count(token) > 1
        }
        if not duplicate:
            return result
        changed = False
        for key in values:
            if result[key] in duplicate and lengths[key] < len(values[key]):
                lengths[key] += 4
                changed = True
        if not changed:
            _refuse("Owner naming seeds cannot uniquely identify resource folders")


def _name(original):
    value = unicodedata.normalize("NFC", PurePosixPath(original).name)
    value = value.replace(":", " - ").replace("[", "(").replace("]", ")")
    value = re.sub(r'[<>"/\\|?*#^%\x00-\x1f]', " ", value)
    value = " ".join(value.split()).strip(" .") or "Untitled"
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", value, re.IGNORECASE):
        value = "Note - " + value
    return value


def assign_asset_targets(snapshot):
    owners = _tokens({item.key: item.naming_seed for item in snapshot.items})
    locals_ = [a for a in snapshot.assets if a.availability == "present"]
    bases = {a.asset_id: _name(a.original_name) for a in locals_}
    suffix_lengths = {a.asset_id: 0 for a in locals_}
    inline_images = {
        (document.owner, reference.target)
        for document in snapshot.documents
        for reference in document.references
        if reference.kind == "image"
    }

    def filename(asset):
        base = bases[asset.asset_id]
        extension = PurePosixPath(base).suffix
        stem = base[: -len(extension)] if extension else base
        marker = (
            " — " + asset.naming_seed[: suffix_lengths[asset.asset_id]]
            if suffix_lengths[asset.asset_id]
            else ""
        )
        ending = extension + (".original" if asset.role == "note_original" else "")
        while len((stem + marker + ending).encode("utf-16-le")) // 2 > 120 and stem:
            stem = stem[:-1]
        if not stem:
            _refuse("Resource extension/identity exceeds the safe filename bound")
        return stem.rstrip(" .") + marker + ending

    while True:
        paths = {
            a.asset_id: f"Attachments/{owners[a.owner]}/{filename(a)}" for a in locals_
        }
        groups = {}
        for key, path in paths.items():
            groups.setdefault(path.casefold(), []).append(key)
        collisions = [keys for keys in groups.values() if len(keys) > 1]
        if not collisions:
            break
        for keys in collisions:
            changed = False
            for key in keys:
                asset = next(a for a in locals_ if a.asset_id == key)
                if suffix_lengths[key] < len(asset.naming_seed):
                    suffix_lengths[key] = (
                        8 if not suffix_lengths[key] else suffix_lengths[key] + 4
                    )
                    changed = True
            if not changed:
                _refuse("Resource naming seeds cannot resolve colliding filenames")
    return tuple(
        AssetTarget(
            asset_id=a.asset_id,
            relative_path=paths.get(a.asset_id),
            resource_link=paths[a.asset_id]
            if a.availability == "present"
            and (
                a.role == "file"
                or (a.role == "image" and (a.owner, a.asset_id) not in inline_images)
            )
            else (a.external_uri if a.availability == "external" else None),
        )
        for a in sorted(snapshot.assets, key=lambda a: a.asset_id)
    )
