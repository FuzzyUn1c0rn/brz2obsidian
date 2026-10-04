"""Source timestamp interpretation, independent of retained original strings."""

import re
from datetime import date, datetime

from brz2obsidian.contracts import CalendarDates, DeclaredAppearance


def declared_appearance(record, assets, refuse):
    icons = [a for a in assets if a.owner == record["Id"] and a.role == "icon"]
    if len(icons) > 1:
        refuse(
            "invalid_source",
            "Thought has ambiguous owned icon declarations",
            (record["Id"],),
        )
    values = {"icon_asset_id": icons[0].asset_id if icons else None}
    for property_name, field in (
        ("foreground_color", "ForegroundColor"),
        ("background_color", "BackgroundColor"),
    ):
        value = record.get(field)
        if value is None:
            continue
        if type(value) is not int:
            refuse(
                "invalid_source",
                "Declared source colour must be an integer: " + field,
                (record["Id"],),
            )
        if not -16777216 <= value <= -1:
            refuse(
                "unsupported_feature",
                "Declared source colour is outside reviewed opaque ARGB: " + field,
                (record["Id"],),
            )
        values[property_name] = f"#{value & 0xFFFFFF:06X}"
    return DeclaredAppearance(**values)


def calendar_dates(record, refuse):
    values = {}
    for property_name, field in (
        ("created", "CreationDateTime"),
        ("updated", "ModificationDateTime"),
    ):
        value = record.get(field)
        if value is None or value == "":
            values[property_name] = None
            continue
        try:
            if type(value) is not str or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?",
                value,
            ):
                raise ValueError("Unrecognized source date spelling")
            if len(value) > 10:
                datetime.fromisoformat(value)
            values[property_name] = date.fromisoformat(value[:10])
        except ValueError:
            refuse(
                "invalid_source",
                "Populated thought timestamp lacks a valid calendar date: " + field,
                (record["Id"],),
            )
    return CalendarDates(**values)
