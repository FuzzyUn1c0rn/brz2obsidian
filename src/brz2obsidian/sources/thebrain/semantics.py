"""Guard semantic fields separately from uninterpreted original metadata."""


def validate_semantic_fields(record, refuse, known_flags=(), known_type_fields=()):
    for name, value in record.items():
        if name.startswith("Is") and name not in known_flags:
            if type(value) is not bool:
                refuse(
                    "invalid_source",
                    "Semantic flags must be booleans",
                    (record.get("Id", ""),),
                )
            if value:
                refuse(
                    "unsupported_feature",
                    "Unverified semantic role flag: " + name,
                    (record.get("Id", ""),),
                )
    for name in ("ThoughtTypeId", "LinkTypeId", "TypeId"):
        if name in record and record[name] is not None:
            if type(record[name]) is not str:
                refuse(
                    "invalid_source",
                    "Custom type identifiers must be text or null",
                    (record.get("Id", ""),),
                )
            if record[name] and name not in known_type_fields:
                refuse(
                    "unsupported_feature",
                    "Custom types are outside reviewed coverage",
                    (record.get("Id", ""),),
                )
