"""Finite icon-chain oracle, independent of source/renderer implementations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class IconResult:
    asset: str | None
    chain: tuple[str, ...]
    status: str


def resolve_icon(start, owned, providers, memberships, categories, *, limit=None):
    """Own icon wins; otherwise follow only explicitly selected memberships.

    Source snapshots have no depth limit. A native lookup validates the next
    provider before declaring depth, but never reads its out-of-budget icon.
    The inputs contain valid owned icon facts, never borrowed declarations.
    """
    chain = [start]
    while True:
        node = chain[-1]
        if owned.get(node):
            return IconResult(owned[node], tuple(chain), "icon")
        provider = providers.get(node)
        if provider is None:
            return IconResult(None, tuple(chain), "blank")
        if provider not in categories or provider not in memberships.get(node, ()):
            return IconResult(None, (*chain, provider), "invalid")
        if provider in chain:
            return IconResult(None, (*chain, provider), "cycle")
        if limit is not None and len(chain) - 1 >= limit:
            return IconResult(None, (*chain, provider), "depth")
        chain.append(provider)


def source_icon(start, owned, providers, categories):
    return resolve_icon(
        start,
        owned,
        providers,
        {key: {value} for key, value in providers.items()},
        categories,
    )


def check_depth_warnings(record, created, owned, providers, categories, evidence):
    """Check migration warnings from the full independently calculated chain."""
    expected = []
    for key in sorted(created):
        result = source_icon(key, owned, providers, categories)
        if len(result.chain) <= 9:
            continue
        provenance = list(
            dict.fromkeys(
                pointer for item in result.chain[:-1] for pointer in evidence[item]
            )
        )
        expected.append(
            {
                "code": "icon_lookup_depth",
                "severity": "warning",
                "phase": "planning",
                "message": "Icon lookup exceeds 8 links.",
                "affected": list(result.chain),
                "evidence": provenance,
                "rule_id": None,
                "guidance": "Native dashboards check up to eight selected appearance-category links. Assign a nearer valid icon or change a selected provider, then close and reopen affected category dashboards and Categories overview. Migration-time body snapshots use the full finite chain.",
                "leftover_path": None,
            }
        )
    assert [
        row for row in record["issues"] if row["code"] == "icon_lookup_depth"
    ] == expected, "independent native depth warning chains/provenance"
    return expected
