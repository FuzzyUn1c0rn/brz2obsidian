"""Ordinary resource links backed by the one planned asset assignment."""

import re
from pathlib import PurePosixPath


def resource_section(plan, owner):
    targets = {target.asset_id: target for target in plan.asset_targets}
    lines = []
    for asset in sorted(plan.analysis.snapshot.assets, key=lambda a: a.asset_id):
        target = targets[asset.asset_id]
        if asset.owner != owner or target.resource_link is None:
            continue
        label = asset.display_name or PurePosixPath(asset.original_name).name
        label = re.sub(r"[\[\]|\r\n]", " ", label).strip() or "Resource"
        if asset.availability == "external":
            label = re.sub(r"([\\`*_{}<>])", r"\\\1", label)
            lines.append(f"- [{label}](<{target.resource_link}>)")
        else:
            lines.append(f"- [[{target.resource_link}|{label}]]")
    return "## Resources\n\n" + "\n".join(lines) + "\n" if lines else ""
