"""The public operation owns filesystem checks and diagnostic translation."""

from pathlib import Path

import yaml

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
    categories = imported = 0
    read_markdown = read_bases = 0
    all_notes_read = complete
    notes = {}
    identities = {}
    for path in markdown:
        artifact = path.relative_to(root).as_posix()
        try:
            text = read_text(path, root)
        except OSError, UnicodeError:
            issues.append(read_failure(artifact))
            all_notes_read = False
            continue
        except UnsafePath:
            issues.append(unsafe_issue(artifact))
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
    for path in bases:
        artifact = path.relative_to(root).as_posix()
        try:
            text = read_text(path, root)
        except OSError, UnicodeError:
            issues.append(read_failure(artifact))
            continue
        except UnsafePath:
            issues.append(unsafe_issue(artifact))
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
    for artifact, (properties, body) in notes.items():
        memberships = set()
        unavailable_memberships = set()
        values = properties.get("categories", [])
        for value in values if isinstance(values, list) else []:
            if not wikilink(value):
                continue
            target, issue = resolve(
                root, names, value, artifact, "category", "categories"
            )
            if issue:
                issues.append(issue)
            elif target not in notes:
                # Its own parse/read diagnostic already explains the unavailable role.
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
        icon = properties.get("icon")
        if not blank(icon) and wikilink(icon):
            target, issue = resolve(root, names, icon, artifact, "image", "icon")
            if issue:
                issues.append(issue)
        for reference, kind, relative in required_references(body):
            target, issue = resolve(
                root, names, reference, artifact, kind, relative=relative
            )
            if issue:
                issues.append(issue)
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
            category_notes=categories if all_notes_read else None,
            imported_notes=imported if all_notes_read else None,
        ),
        issues=ordered,
    )
