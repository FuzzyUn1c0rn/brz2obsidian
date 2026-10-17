"""Combined actual-output acceptance at public workflow/command/checker seams."""

import yaml


def properties(data):
    return yaml.safe_load(data.decode().split("---", 2)[1])
