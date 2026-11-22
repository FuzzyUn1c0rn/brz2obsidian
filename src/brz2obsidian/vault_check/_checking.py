"""The public operation owns filesystem checks and diagnostic translation."""

from pathlib import Path

import yaml

from ._appearance import appearance_issues
from ._filesystem import (
    UnsafePath,
    guard,
    inventory,
    read_failure,
    read_text,
    unsafe_issue,
)
from ._frontmatter import blank, category, frontmatter, mapping, validate, wikilink
from ._markdown import required_references
from ._references import resolve
from .contracts import (
    VaultCheckCounts,
    VaultCheckIdentity,
    VaultCheckIssue,
    VaultCheckResult,
)


def _read_artifact(path, root, artifact, issues):
    try:
        return read_text(path, root)
    except OSError, UnicodeError:
        issues.append(read_failure(artifact))
    except UnsafePath:
        issues.append(unsafe_issue(artifact))
    return None


def _read_markdown(root, markdown, issues):
    categories = imported = 0
    read_markdown = 0
    all_notes_read = True
    notes = {}
    identities = {}
    for path in markdown:
        artifact = path.relative_to(root).as_posix()
        text = _read_artifact(path, root, artifact, issues)
        if text is None:
            all_notes_read = False
            continue
        read_markdown += 1
        try:
            properties, body = frontmatter(text)
        except yaml.YAMLError, ValueError:
            all_notes_read = False
            issues.append(
                VaultCheckIssue(
                    code="invalid_frontmatter",
                    artifact=artifact,
                    message="Frontmatter must be valid data-only YAML with unique keys.",
                    guidance="Correct the YAML mapping, duplicate keys or unsupported tags.",
                )
            )
            continue
        issues.extend(validate(properties, artifact))
        notes[artifact] = (properties, body)
        categories += category(properties, artifact)
        source_pair = tuple(
            properties.get(name) for name in ("source_collection_id", "source_item_id")
        )
        if all(isinstance(value, str) and value.strip() for value in source_pair):
            imported += 1
            identities.setdefault(source_pair, []).append(artifact)
    return notes, identities, read_markdown, categories, imported, all_notes_read


def _read_bases(root, bases, issues):
    read_bases = 0
    for path in bases:
        artifact = path.relative_to(root).as_posix()
        text = _read_artifact(path, root, artifact, issues)
        if text is None:
            continue
        read_bases += 1
        try:
            mapping(text)
        except yaml.YAMLError, ValueError:
            issues.append(
                VaultCheckIssue(
                    code="invalid_base",
                    artifact=artifact,
                    message="Base must be valid data-only YAML with a mapping and unique keys.",
                    guidance="Correct the Base YAML; formulas are never evaluated by this checker.",
                )
            )
    return read_bases


def _category_memberships(root, names, notes, artifact, properties, issues):
    memberships = set()
    unavailable_memberships = set()
    values = properties.get("categories", [])
    for value in values if isinstance(values, list) else []:
        if not wikilink(value):
            continue
        target, issue = resolve(root, names, value, artifact, "category", "categories")
        if issue:
            issues.append(issue)
        elif target not in notes:
            unavailable_memberships.add(target)
        elif not category(notes[target][0], target):
            issues.append(
                VaultCheckIssue(
                    code="invalid_category",
                    artifact=artifact,
                    property="categories",
                    reference=value,
                    message="Membership target does not have the category folder and native tag role.",
                    guidance="Link to a Categories note with the categories tag.",
                )
            )
        else:
            memberships.add(target)
    return memberships, unavailable_memberships


def _check_note_references(root, names, notes, issues):
    providers, owned_icons = {}, set()
    for artifact, (properties, body) in notes.items():
        memberships, unavailable_memberships = _category_memberships(
            root, names, notes, artifact, properties, issues
        )
        provider = properties.get("appearance_category")
        if not blank(provider) and wikilink(provider):
            target, issue = resolve(
                root, names, provider, artifact, "provider", "appearance_category"
            )
            if issue:
                issues.append(issue)
            elif target not in memberships | unavailable_memberships:
                issues.append(
                    VaultCheckIssue(
                        code="invalid_provider",
                        artifact=artifact,
                        property="appearance_category",
                        reference=provider,
                        message="Appearance provider is not a valid category in this note's memberships.",
                        guidance="Choose a category in categories, or leave the provider blank to opt out.",
                    )
                )
            elif target in memberships:
                providers[artifact] = target
        icon = properties.get("icon")
        if not blank(icon) and wikilink(icon):
            target, issue = resolve(root, names, icon, artifact, "image", "icon")
            if issue:
                issues.append(issue)
            else:
                owned_icons.add(artifact)
        for reference, kind, relative in required_references(body):
            target, issue = resolve(
                root, names, reference, artifact, kind, relative=relative
            )
            if issue:
                issues.append(issue)
    invalid_providers = {
        issue.artifact
        for issue in issues
        if issue.property == "appearance_category" and issue.code != "read_failure"
    }
    issues.extend(appearance_issues(notes, providers, owned_icons, invalid_providers))


def _check_duplicate_identities(identities, issues):
    for artifacts in identities.values():
        if len(artifacts) > 1:
            for artifact in artifacts:
                issues.append(
                    VaultCheckIssue(
                        code="duplicate_source_identity",
                        artifact=artifact,
                        candidates=tuple(sorted(artifacts)),
                        message="The same imported source identity pair appears on multiple notes.",
                        guidance="Review the copies using both opaque identities; titles do not establish identity.",
                    )
                )


def check_vault(vault: str | Path) -> VaultCheckResult:
    root = Path(vault).absolute()
    identity = VaultCheckIdentity(location=str(root), name=root.name)
    try:
        guard(root)
        if not root.is_dir():
            raise OSError("Vault must be an existing directory")
    except (OSError, UnsafePath) as error:
        return VaultCheckResult(
            outcome="failed",
            vault=identity,
            counts=VaultCheckCounts(),
            issues=(
                unsafe_issue() if isinstance(error, UnsafePath) else read_failure(),
            ),
        )
    files, names, issues, complete = inventory(root)
    markdown = [path for path in files if path.suffix.lower() == ".md"]
    bases = [path for path in files if path.suffix.lower() == ".base"]
    notes, identities, read_markdown, categories, imported, all_notes_read = (
        _read_markdown(root, markdown, issues)
    )
    read_bases = _read_bases(root, bases, issues)
    _check_note_references(root, names, notes, issues)
    _check_duplicate_identities(identities, issues)
    ordered = tuple(
        sorted(
            issues,
            key=lambda i: (
                i.artifact or "",
                i.code,
                i.property or "",
                i.reference or "",
                i.candidates,
            ),
        )
    )
    return VaultCheckResult(
        outcome="failed"
        if any(i.code == "read_failure" for i in issues)
        else "issues"
        if issues
        else "clean",
        vault=identity,
        counts=VaultCheckCounts(
            inventory_files=len(files) if complete else None,
            markdown_files=len(markdown) if complete else None,
            base_files=len(bases) if complete else None,
            read_markdown_files=read_markdown,
            read_base_files=read_bases,
            category_notes=categories if complete and all_notes_read else None,
            imported_notes=imported if complete and all_notes_read else None,
        ),
        issues=ordered,
    )
