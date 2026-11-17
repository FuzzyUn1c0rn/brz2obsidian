"""Find a concrete directed cycle without recursion or path-length limits."""


def directed_cycle(edges):
    adjacency = {}
    for left, right in edges:
        adjacency.setdefault(left, []).append(right)
    finished = set()
    for start in sorted(adjacency):
        if start in finished:
            continue
        path, positions = [start], {start: 0}
        stack = [iter(sorted(adjacency.get(start, ())))]
        while stack:
            target = next(stack[-1], None)
            if target is None:
                finished.add(path[-1])
                positions.pop(path.pop())
                stack.pop()
            elif target in positions:
                return tuple(path[positions[target] :] + [target])
            elif target not in finished:
                positions[target] = len(path)
                path.append(target)
                stack.append(iter(sorted(adjacency.get(target, ()))))
    return ()
