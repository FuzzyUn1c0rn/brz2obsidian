"""Strict JSON decoding without silent duplicate-key or nonfinite loss."""

import json
import re

ROOT_FILES = (
    "meta.json",
    "thoughts.json",
    "links.json",
    "attachments.json",
    "settings.json",
    "modificationlogs.json",
    "brainusers.json",
    "syncpoints.json",
    "tombstones.json",
    "calendarevents.json",
    "access.json",
    "fielddefinitions.json",
    "fieldinstances.json",
)


def decode_records(name: str, raw: bytes) -> tuple[tuple[dict, ...], str]:
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError(f"Duplicate JSON key {key!r}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"Nonfinite JSON value {value}")

    text = raw.decode("utf-8-sig")
    values = (
        [text]
        if name == "meta.json"
        else [line for line in re.split(r"\r\n|\r|\n", text) if line.strip(" \t")]
    )
    decoded = tuple(
        json.loads(value, object_pairs_hook=pairs, parse_constant=nonfinite)
        for value in values
    )
    if any(type(record) is not dict for record in decoded):
        raise ValueError("Root records must be JSON objects")
    return decoded, "[" + ",".join(values) + "]"
