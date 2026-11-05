"""Selected appearance-chain safety over bound normalized file identities."""


def _chain_problems(states):
    providers, invalid = {}, {}
    for state in states:
        document = state.structure
        if document is None or document.appearance_field is None:
            continue
        field = next(f for f in document.fields if f.key == document.appearance_field)
        if field.value in (None, ""):
            continue
        matches = {
            entry.target_id
            for membership in document.memberships
            if membership.kind == "category"
            for entry in membership.entries
            if field.value in entry.target.representations
        }
        if len(matches) == 1:
            providers[state.target_id] = matches.pop()
        else:
            invalid[state.target_id] = (field.kind, field.scalar_type, field.value)
    problems = {}
    for state in states:
        chain = [state.target_id]
        while chain[-1] in providers:
            provider = providers[chain[-1]]
            if provider in chain:
                problems[state.target_id] = (
                    "selected_provider_cycle",
                    (*chain, provider),
                )
                break
            chain.append(provider)
        if chain[-1] in invalid:
            problems[state.target_id] = (
                "selected_provider_invalid",
                tuple(chain),
                invalid[chain[-1]],
            )
    return problems


def provider_chain_blockers(current_states, selected_states):
    """Preserve unchanged baseline problems while refusing newly harmful chains.

    This independent check traverses the full finite chain even if a nearer
    owned icon already supplies the visible image. Native lookup depth is not
    a safety boundary.
    """
    previous = _chain_problems(current_states)
    return tuple(
        dict.fromkeys(
            problem[0]
            for start, problem in _chain_problems(selected_states).items()
            if previous.get(start) != problem
        )
    )
