"""Resolve source-neutral normalized queries, never Markdown or wiki syntax."""

import unicodedata
from hashlib import sha256

from brz2obsidian.contracts import LinkMeaning

from .identity import _paths_collide, _target_safe


def _key(value):
    return unicodedata.normalize("NFC", value).casefold()


def resolve_link_meaning(query, display, fragment, targets, target_facts, inventory):
    def result(status, target=None, state=None, matches=()):
        return LinkMeaning(status=status, target_id=None if target is None else target.target_id,
            target_identity=None if target is None else target.identity, path=None if target is None else target.canonical_path,
            target_version=None if state is None or state.content is None else sha256(state.content.data).hexdigest(),
            display_text=display, fragment=fragment, candidates=tuple(sorted(t.target_id for t in matches)))

    if query is None:
        return result("unsupported")
    if inventory != "complete":
        return result("inventory_uncertain")
    matches = []
    for target in targets:
        if target.canonical_path is None:
            continue
        path = _key(target.canonical_path)
        paths = {path}
        if target.kind != "resource" and path.endswith(".md"):
            paths.add(path[:-3])
        aliases = {_key(name) for name in target.representations}
        value = _key(query.value)
        if value in paths or value in aliases or (query.mode == "shortened" and any(p.endswith("/" + value) for p in paths)):
            matches.append(target)
    if not matches:
        return result("missing")
    if len(matches) != 1:
        return result("ambiguous", matches=matches)
    target, = matches
    collisions = tuple(t for t in targets if t.target_id != target.target_id and t.canonical_path is not None and _paths_collide(t.canonical_path, target.canonical_path))
    if target.status != "safe" or target.target is None or not _target_safe(target.canonical_path, target.target, collisions):
        return result("unsafe", target)
    states = tuple(s for s in target_facts if s.target_id == target.target_id)
    if len(states) != 1:
        return result("unknown", target)
    state, = states
    if state.existence != "present":
        return result(state.existence, target, state)
    if fragment is not None:
        count = state.fragments.count(fragment)
        if state.interpretation != "supported":
            return result("unknown", target, state)
        if count != 1:
            return result("fragment_missing" if count == 0 else "fragment_ambiguous", target, state)
    return result("resolved", target, state)
