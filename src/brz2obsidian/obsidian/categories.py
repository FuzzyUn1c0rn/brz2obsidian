"""Native linked membership, separate from graph navigation and source tags."""


def classification_records(plan):
    targets = {t.item_key: t for t in plan.item_targets}
    return [
        dict(
            **a.model_dump(),
            definition_target=targets[a.definition_key].relative_path,
            item_target=targets[a.item_key].relative_path,
        )
        for a in plan.analysis.snapshot.classification_assignments
    ]
