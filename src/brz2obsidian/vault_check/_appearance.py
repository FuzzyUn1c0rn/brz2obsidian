"""Finite provider-graph diagnostics from already resolved vault identities."""

from .contracts import VaultCheckIssue


def appearance_issues(notes, providers, owned_icons, invalid_providers):
    issues = []
    for start in sorted(notes):
        if start.split("/")[0] in {"Templates", "Attachments"}:
            continue
        chain = [start]
        while chain[-1] in providers and providers[chain[-1]] not in chain:
            chain.append(providers[chain[-1]])
        if chain[-1] in providers:
            issues.append(
                VaultCheckIssue(
                    code="provider_cycle",
                    artifact=start,
                    property="appearance_category",
                    reference=" -> ".join(
                        "[[" + key + "]]" for key in (*chain, providers[chain[-1]])
                    ),
                    message="Appearance-category chain contains a cycle.",
                    guidance="Review the selected category chain and remove the repeated provider. An owned icon can still display, but it does not repair the independent cycle.",
                )
            )
        if len(chain) > 1 and chain[-1] in invalid_providers:
            issues.append(
                VaultCheckIssue(
                    code="invalid_provider",
                    artifact=start,
                    property="appearance_category",
                    reference=" -> ".join("[[" + key + "]]" for key in chain),
                    message="Appearance-category chain reaches an invalid provider declaration.",
                    guidance="Review the chain and correct the final note's selected provider. A nearer owned icon does not repair the independent declaration.",
                )
            )
        nearest = next((i for i, key in enumerate(chain) if key in owned_icons), None)
        if len(chain) > 9 and (nearest is None or nearest > 8):
            issues.append(
                VaultCheckIssue(
                    code="icon_lookup_depth",
                    artifact=start,
                    property="appearance_category",
                    reference=" -> ".join("[[" + key + "]]" for key in chain),
                    message="Icon lookup exceeds 8 links.",
                    guidance="Assign a valid icon to a nearer category or change a selected appearance category, then close and reopen affected category dashboards and Categories overview. This warning does not prevent checking or import.",
                )
            )
    return issues
