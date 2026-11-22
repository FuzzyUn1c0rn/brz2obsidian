"""Source-backed scoped updates and explicit classification remapping."""

from pathlib import Path

from brz2obsidian.contracts import (
    ImportCategoryChoice,
    MigrationRefused,
    SourceIdentity,
)
from brz2obsidian.obsidian.import_classification import (
    classification_review,
    refuse_classification,
    reobserve_category_choices,
    require_classification_choices,
)
from brz2obsidian.publication.collection_placement import (
    collection_connection_choices,
    observe_classification_inventory,
    recorded_classification_choices,
    remembered_tag_mappings,
)
from brz2obsidian.publication.vault_history import collection_baselines

from .collection_import import _baseline, _refused, prepare_collection_import
from .update_facts import CollectionImportConflict, record


def _retained_source(operations, history, record_path):
    checkpoint = history.checkpoint
    if history.status != "intact" or checkpoint is None:
        raise CollectionImportConflict("collection_not_active")
    matches = tuple(
        manifest
        for value in collection_baselines(checkpoint).values()
        if value is not None
        for _, manifest in (value,)
        if manifest.collection_record_path == record_path
    )
    if len(matches) != 1 or matches[0].observed_source is None:
        raise CollectionImportConflict("collection_not_active")
    observed = matches[0].observed_source
    source, _, _ = _baseline(operations, history, observed, record_path)
    return record(source, record_path)


def _select_category_updates(review, original, offered, remap):
    retained, _ = recorded_classification_choices(original)
    retained = reobserve_category_choices(retained, review.vault_categories)
    allowed = {key for key, _ in review.source_categories}
    selected = {
        row.source_identity: row for row in retained if row.source_identity in allowed
    }
    for row in offered:
        previous = selected.get(row.source_identity)
        if not remap and previous is not None and row != previous:
            refuse_classification("classification_remap_required")
        selected[row.source_identity] = row
    return require_classification_choices(review, tuple(selected.values()))


def _update_placement(
    snapshot, original, review, categories, tag_reuse, remap, separate_tags=()
):
    before = SourceIdentity.model_validate(original["source_identity"])
    actual = snapshot.identity
    if (actual.module_id, actual.source_id) != (before.module_id, before.source_id):
        refuse_classification("association_mismatch")
    if remap and actual.snapshot_digest != before.snapshot_digest:
        refuse_classification("classification_remap_source_changed")
    remembered = remembered_tag_mappings(original)
    prior_tags = {key: (token, mode) for key, token, mode in remembered}
    reset = _separate_tag_choices(separate_tags, prior_tags, review, tag_reuse)
    if not remap and any(
        source in prior_tags and prior_tags[source] != (token, "reuse")
        for source, token in tag_reuse
    ):
        refuse_classification("classification_remap_required")
    return {
        "import_location": original["collection_location"],
        "reserved_names": tuple(original.get("import_reserved_names", ())),
        "import_link_connections": collection_connection_choices(original),
        "category_choices": _select_category_updates(
            review, original, categories, remap
        ),
        "existing_vault_tags": review.vault_tags,
        "remembered_tags": tuple(row for row in remembered if row[0] not in reset),
        "remembered_item_paths": tuple(
            (row["original_identity"], row["relative_path"])
            for row in original["item_targets"]
        ),
        "tag_reuse": tag_reuse,
    }


def _separate_tag_choices(separate_tags, prior, review, reuse):
    reset = set(separate_tags)
    retained_reuse = {key for key, (_, mode) in prior.items() if mode == "reuse"}
    live = {key for key, _ in review.source_tags}
    if reset - (retained_reuse & live) or reset.intersection(dict(reuse)):
        refuse_classification("import_tag_mapping_invalid")
    return reset


def prepare_scoped_classification_update(
    operations,
    workflow,
    vault,
    source,
    *,
    staging,
    record_path,
    category_choices=(),
    tag_reuse=(),
    remap=False,
    separate_tags=(),
):
    kind = "source_update"
    try:
        root, staging = Path(vault).resolve(), Path(staging).resolve()
        if root == staging or root in staging.parents or staging in root.parents:
            return _refused("distinct_source_required", kind=kind)
        history = operations.inspect_history(root)
        original = _retained_source(operations, history, record_path)
        vault_categories, vault_tags = observe_classification_inventory(
            history.admission, history.checkpoint
        )
        categories = tuple(
            ImportCategoryChoice.model_validate(row) for row in category_choices
        )
        reused = tuple(tuple(row) for row in tag_reuse)
        observed_review = None

        def placement(snapshot):
            nonlocal observed_review
            observed_review = classification_review(
                snapshot, vault_categories, vault_tags
            )
            return _update_placement(
                snapshot,
                original,
                observed_review,
                categories,
                reused,
                remap,
                separate_tags=separate_tags,
            )

        result = workflow.convert_collection(source, staging, placement=placement)
        if result.receipt is None:
            codes = tuple(issue.code for issue in result.issues)
            return _refused(
                codes[0] if codes else "collection_render_unavailable", kind=kind
            ).model_copy(
                update={"classification_review": observed_review, "findings": codes}
            )
        offered = prepare_collection_import(
            operations,
            root,
            staging,
            record_path=record_path,
            rendered=result.receipt,
            update=True,
            remap=remap,
        )
        return offered.model_copy(update={"classification_review": observed_review})
    except CollectionImportConflict as error:
        return _refused(str(error), kind=kind)
    except MigrationRefused as error:
        return _refused(error.issues[0].code, kind=kind)
    except OSError, ValueError, TypeError, KeyError:
        return _refused("collection_classification_unavailable", kind=kind)
