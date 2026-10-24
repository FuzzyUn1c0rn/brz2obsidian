"""Validation of closed named dependency relationships; no fact interpretation."""

from collections import deque


def validate_dependencies(nodes):
    children = {key: [] for key in nodes}
    pending = {}
    for key, node in nodes.items():
        if (
            not node.key
            or len(node.fingerprint) != 64
            or any(c not in "0123456789abcdef" for c in node.fingerprint)
            or len(set(node.depends_on)) != len(node.depends_on)
        ):
            raise ValueError("Invalid dependency provenance")
        pending[key] = len(node.depends_on)
        for parent in node.depends_on:
            if parent not in nodes:
                raise ValueError("Missing dependency provenance")
            children[parent].append(key)
    ready = deque(key for key, count in pending.items() if count == 0)
    visited = 0
    while ready:
        visited += 1
        for child in children[ready.popleft()]:
            pending[child] -= 1
            if pending[child] == 0:
                ready.append(child)
    if visited != len(nodes):
        raise ValueError("Cyclic dependency provenance")
