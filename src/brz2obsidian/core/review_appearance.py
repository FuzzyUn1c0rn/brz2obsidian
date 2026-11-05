"""Selected appearance-chain safety over bound normalized file identities."""

from .link_meanings import resolve_link_meaning


def _icon_problem(state, targets, states):
    owner = next((row for row in targets if row.target_id == state.target_id), None)
    if owner is None or owner.canonical_path != state.file_roles.path:
        return ("icon_unbound",)
    declaration = state.file_roles.owned_icon
    if declaration.status in ("absent", "blank"):
        return None
    if declaration.status != "valid":
        return ("icon_declaration", declaration.status)
    meaning = resolve_link_meaning(
        declaration.query, "", None, targets, states, "complete"
    )
    target = next((row for row in targets if row.target_id == meaning.target_id), None)
    asset = next((row for row in states if row.target_id == meaning.target_id), None)
    if (
        meaning.status != "resolved"
        or target is None
        or target.kind != "resource"
        or asset is None
        or asset.file_roles is None
        or asset.file_roles.path != target.canonical_path
        or not asset.file_roles.image_path
        or asset.existence != "present"
        or asset.content is None
        or not asset.content.data
    ):
        return (
            "icon_target",
            meaning.status,
            meaning.target_id,
            meaning.target_version,
        )
    return None


def _category_reference(query, targets, states):
    meaning = resolve_link_meaning(query, "", None, targets, states, "complete")
    target = next((row for row in targets if row.target_id == meaning.target_id), None)
    state = next((row for row in states if row.target_id == meaning.target_id), None)
    if (
        meaning.status == "resolved"
        and target is not None
        and target.kind in ("category", "note")
        and state is not None
        and state.file_roles is not None
        and state.file_roles.path == target.canonical_path
        and state.file_roles.category
    ):
        return meaning.target_id
    return None


def _chain_problems(states, targets):
    providers, invalid = {}, {}
    for state in states:
        roles = state.file_roles
        if roles is not None:
            memberships = tuple(
                _category_reference(query, targets, states)
                for query in roles.category_memberships.queries
            )
            if roles.category_memberships.status == "invalid" or any(
                member is None for member in memberships
            ):
                invalid[(state.target_id, "categories")] = (
                    "category_declaration",
                    roles.category_memberships.status,
                    memberships,
                )
            provider = roles.provider
            if provider.status == "invalid":
                invalid[(state.target_id, "provider")] = (
                    "provider_declaration",
                    provider.status,
                )
            elif provider.status == "valid":
                selected = _category_reference(provider.query, targets, states)
                if selected is None or selected not in memberships:
                    invalid[(state.target_id, "provider")] = (
                        "provider_member",
                        selected,
                    )
                else:
                    providers[state.target_id] = selected
            problem = _icon_problem(state, targets, states)
            if problem is not None:
                invalid[(state.target_id, "icon")] = problem
            continue
        document = state.structure
        if document is None:
            continue
        if document.appearance_field is None:
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
            provider = matches.pop()
            providers[state.target_id] = provider
        else:
            invalid[(state.target_id, "provider")] = (
                field.kind,
                field.scalar_type,
                field.value,
            )
    problems = {}
    for state in states:
        chain = [state.target_id]
        while chain[-1] in providers:
            provider = providers[chain[-1]]
            if provider in chain:
                problems[(state.target_id, "cycle")] = (
                    "selected_provider_cycle",
                    (*chain, provider),
                )
                break
            chain.append(provider)
        # Each declaration remains independent of cycles and other defects.
        for (failed, declaration), detail in invalid.items():
            if failed in chain:
                problems[(state.target_id, failed, declaration)] = (
                    "selected_provider_invalid",
                    tuple(chain),
                    detail,
                )
    return problems


def provider_chain_blockers(
    current_states,
    selected_states,
    *,
    current_targets=(),
    selected_targets=(),
):
    """Preserve unchanged baseline problems while refusing newly harmful chains.

    This independent check traverses the full finite chain even if a nearer
    owned icon already supplies the visible image. Native lookup depth is not
    a safety boundary.
    """
    previous = _chain_problems(current_states, current_targets)
    return tuple(
        dict.fromkeys(
            problem[0]
            for start, problem in _chain_problems(
                selected_states, selected_targets
            ).items()
            if previous.get(start) != problem
        )
    )
