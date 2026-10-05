"""Safe YAML scalars and lists for imported properties and native templates."""

import json
from datetime import date


def frontmatter(properties):
    lines = ["---"]
    for name, value in properties.items():
        if isinstance(value, list) and value:
            lines.append(name + ":")
            lines.extend("  - " + json.dumps(v, ensure_ascii=False) for v in value)
        elif isinstance(value, date):
            lines.append(name + ": " + value.isoformat())
        elif value is None:
            lines.append(name + ":")
        else:
            lines.append(name + ": " + json.dumps(value, ensure_ascii=False))
    return "\n".join(lines) + "\n---\n\n"
