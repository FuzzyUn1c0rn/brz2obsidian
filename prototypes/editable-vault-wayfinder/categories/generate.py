"""Disposable synthetic category/link design evidence; never a converter or updater."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUTPUT_ROOT = ROOT / "tmp" / "merge-wayfinding" / "categories"
ATLAS = "Imports/Atlas/"
PROJECTS = "Categories/Projects.md"
TOPICS = ATLAS + "Categories/Topics — Atlas.md"
PEOPLE = "Categories/People.md"
WORK = "Categories/Work.md"
TOPIC = ATLAS + "Notes/Topic — Atlas.md"
FUTURE = ATLAS + "Notes/FutureIdea — Atlas.md"
MOVED = "Reading/Atlas topic moved.md"
SOURCE = "synthetic-atlas"


def note(title, body, *, categories=(), tags=(), item=None, aliases=()):
    lines = ["---", "categories:"]
    lines += ["  - " + json.dumps("[[" + target + "]]", ensure_ascii=False) for target in categories]
    if not categories:
        lines[-1] = "categories: []"
    lines += ["tags: " + json.dumps(list(tags)), "aliases: " + json.dumps(list(aliases))]
    if item:
        lines += [f"source_collection_id: {SOURCE}", f"source_item_id: {item}"]
    return "\n".join(lines) + f"\n---\n# {title}\n\n{body}\n"


def base(target="this"):
    # Uses the current linked-membership expression, deliberately no custom plugin.
    return 'filters:\n  and:\n    - file.ext == "md"\n    - \'!file.inFolder("Templates")\'\n    - \'!file.inFolder("Attachments")\'\n    - list(categories).contains(' + target + ')\nviews:\n  - type: table\n    name: Members\n    order:\n      - file.name\n      - note.categories\n    sort:\n      - property: file.name\n        direction: ASC\n'


def dashboard(title, body):
    return note(title, body + '\n\n## Members\n\n![[Templates/Bases/Linked members.base#Members]]', tags=("categories",))


def existing():
    return {
        "Home.md": "# Existing vault\n\n[[Categories.md|My categories]]\n\n[[Existing/Link probes.md|Existing link meanings]]\n",
        "Categories.md": "# My categories\n\n- [[Categories/Projects.md]]\n- [[Categories/Topics.md]]\n- [[Categories/People.md]]\n- [[Categories/Work.md]]\n",
        PROJECTS: dashboard("Projects", "User-authored project guidance. Keep this prose and its attachment.\n\n[[Attachments/existing-project.txt]]"),
        "Categories/Topics.md": dashboard("Topics", "The user's existing topic category."),
        WORK: dashboard("Work", "Another user category, initially unrelated to Atlas."),
        "Categories/Manual favorites.md": dashboard("Manual favorites", "Manually curated memberships."),
        PEOPLE: note("People", "User-authored person guidance.\n\n## Custom dashboard\n\n```dataview\nLIST FROM #people\n```\n\nThis custom-query example is incompatible with linked categories. No community plugin is installed in this fixture.", tags=("categories",)),
        "Existing/Topic.md": note("Topic", "## Details\n\nExisting topic body. ^topic-block", categories=("Categories/Topics.md",), aliases=("Old topic",)),
        "Existing/Local project.md": note("Local project", "Existing project; must remain on the shared dashboard.", categories=(PROJECTS,), tags=("research", "reviewed")),
        "Existing/Ada.md": note("Ada", "Existing person uses both conventions for a positive linked-membership control.", categories=(PEOPLE,), tags=("people",)),
        "Existing/Work note.md": note("Work note", "Existing work member.", categories=(WORK,)),
        "Existing/Link probes.md": "# Existing link meanings\n\nShort: [[Topic]]\nQualified: [[Existing/Topic.md]]\nAlias display: [[Existing/Topic.md|Old topic]]\nHeading: [[Existing/Topic.md#Details]]\nBlock: [[Existing/Topic.md#^topic-block]]\nMarkdown: [Topic details](Topic.md#Details)\nUncreated short: [[FutureIdea]]\nUncreated qualified: [[Plans/FutureIdea.md]]\n\nDo not click either uncreated link during the preservation observation.\n",
        "Attachments/existing-project.txt": "Synthetic existing project attachment, bytes must survive.\n",
        "Templates/Project.md": note("New project", "User-authored template scaffold.", categories=(PROJECTS,), tags=("reviewed",)),
        "Templates/Bases/Linked members.base": base(),
        ".obsidian/core-plugins.json": json.dumps(["file-explorer", "global-search", "backlink", "outgoing-link", "properties", "page-preview", "templates", "bases"]),
        ".obsidian/community-plugins.json": "[]\n",
        ".obsidian/app.json": json.dumps({"alwaysUpdateLinks": True, "newLinkFormat": "shortest", "showInlineTitle": True}),
        ".obsidian/appearance.json": json.dumps({"theme": "obsidian"}),
        ".obsidian/templates.json": json.dumps({"folder": "Templates"}),
    }


def mappings(category_id, title, destination):
    return {
        "prototype_only": True,
        "source_collection_id": SOURCE,
        "categories": {category_id: {"last_source_title": title, "target": destination}, "type-topic": {"last_source_title": "Topics", "target": TOPICS}},
        "tags": {"tag-research": "atlas/research", "tag-reviewed": "reviewed"},
        "warning": "Illustrative identity/mapping shape, not an accepted persistent format.",
    }


def common_import():
    return {
        TOPICS: dashboard("Topics — Atlas", "Separate category chosen explicitly; the user's existing Topics remains distinct.\n\nSynthetic source topic prose."),
        TOPIC: note("Topic", "Incoming ordinary note remains distinct.\n\n[[" + FUTURE + "|FutureIdea]]", categories=(PROJECTS, TOPICS), tags=("atlas/research", "reviewed"), item="item-topic"),
        FUTURE: note("FutureIdea", "An incoming note with the name of an intentionally uncreated target uses a distinct filename.\n\nRelated source note: [[" + TOPIC + "|Topic]]", categories=(PROJECTS,), tags=("atlas/research",), item="item-future"),
        ATLAS + "References/Projects — source reference.md": note("Projects — source reference", "Synthetic source category prose: Keep experiments small.\n\nShared category: [[Categories/Projects.md|Projects]]\n\nSource attachment: [[Imports/Atlas/Attachments/projects-guide.txt]]", item="type-project"),
        ATLAS + "Attachments/projects-guide.txt": "Synthetic source attachment: an Atlas project checklist.\n",
        ATLAS + "Categories.md": "# Atlas categories\n\nCategories used by this import:\n\n- [[Categories/Projects.md|Projects (shared)]]\n- [[Imports/Atlas/Categories/Topics — Atlas.md|Topics (separate)]]\n\n[[Imports/Atlas/References/Projects — source reference.md|Original Projects content]]\n",
    }


def scenarios():
    before = existing()
    first = before | common_import()
    case1 = (before, first, mappings("type-project", "Projects", PROJECTS), {})
    person = ATLAS + "Notes/Ada — Atlas.md"
    view = ATLAS + "Views/People — linked members.md"
    case2_after = before | {
        person: note("Ada", "Synthetic imported person.", categories=(PEOPLE,), tags=("atlas/research",), item="item-ada"),
        ATLAS + "References/People — source reference.md": note("People — source reference", "Synthetic source People guidance.\n\nShared category: [[Categories/People.md]]\n\n[[Imports/Atlas/Attachments/people-guide.txt]]", item="type-people"),
        ATLAS + "Attachments/people-guide.txt": "Synthetic People attachment.\n",
        ATLAS + "Categories.md": "# Atlas categories\n\n- [[Categories/People.md|People (shared)]]\n\nExisting custom dashboard needs review. [[Imports/Atlas/Views/People — linked members.md|Proposed compatible view]]\n",
        view: "# People — linked members (proposed)\n\nCategory: [[Categories/People.md]]\n\nThis separate compatible view includes all linked members. The custom People dashboard is unchanged.\n\n![[Imports/Atlas/Views/People — linked members.base#Members]]\n",
        ATLAS + "Views/People — linked members.base": base('link("Categories/People.md")'),
    }
    people_mapping = mappings("type-people", "People", PEOPLE)
    people_mapping["categories"].pop("type-topic")
    people_mapping["tags"].pop("tag-reviewed")
    case2 = (before, case2_after, people_mapping, {"compatible_view": {"status": "pending-human-review", "path": view, "existing_dashboard": PEOPLE}})
    remap_before = dict(first)
    remap_before[MOVED] = remap_before.pop(TOPIC).replace('  - "[[Categories/Projects.md]]"', '  - "[[Categories/Projects.md]]"\n  - "[[Categories/Manual favorites.md]]"') + "\nManual prose added after import.\n"
    # A hand-authored preimage, not a claim that Obsidian performed this move.
    remap_before[FUTURE] = remap_before[FUTURE].replace(TOPIC, MOVED)
    remap_after = dict(remap_before)
    remap_after[FUTURE] = remap_after[FUTURE].replace(PROJECTS, WORK)
    remap_after[ATLAS + "Categories.md"] = "# Atlas categories\n\n- [[Categories/Work.md|Initiatives (shared Work, proposed remap)]]\n- [[Imports/Atlas/Categories/Topics — Atlas.md|Topics (separate)]]\n\n[[Imports/Atlas/References/Projects — source reference.md|Source category content]]\n\nMapping change is pending; one manually edited membership requires a verdict.\n"
    ref = ATLAS + "References/Projects — source reference.md"
    remap_after[ref] = remap_after[ref].replace("# Projects — source reference", "# Initiatives — source reference").replace("[[Categories/Projects.md|Projects]]", "[[Categories/Work.md|Work (proposed)]]")
    remap = mappings("type-project", "Initiatives", WORK)
    remap["item_paths"] = {"item-topic": MOVED, "item-future": FUTURE}
    case3 = (remap_before, remap_after, remap, {
        "status": "proposal-only-not-applied",
        "category_source_identity": [SOURCE, "type-project"],
        "prior_mapping": PROJECTS,
        "new_mapping": WORK,
        "source_title_before": "Projects",
        "source_title_now": "Initiatives",
        "identity_followed_to": MOVED,
        "membership_conflicts": [{"path": MOVED, "reason": "Membership changed manually after import; keep bytes and require explicit resolution", "baseline": [PROJECTS, TOPICS], "current": [PROJECTS, "Categories/Manual favorites.md", TOPICS], "incoming_proposal": [WORK, TOPICS], "verdict": None}],
        "compatible_membership_changes": [FUTURE],
        "apply_allowed": False,
    })
    return [case1, case2, case3]


def put_tree(destination, files):
    destination.mkdir(parents=True, exist_ok=False)
    for name, content in sorted(files.items()):
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))


def inventory(directory):
    return [{"path": path.relative_to(directory).as_posix(), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(directory.rglob("*")) if path.is_file()]


def frontmatter_values(text, key):
    """Parse just this fixture's limited JSON-in-YAML list shape; not a vault parser."""
    front = text.split("---", 2)[1] if text.startswith("---\n") else ""
    match = re.search(r"^" + re.escape(key) + r": (\[.*\])$", front, re.M)
    if match:
        return json.loads(match[1])
    match = re.search(r"^" + re.escape(key) + r":\n((?:  - .*\n)+)", front, re.M)
    return [json.loads(line[4:]) for line in match[1].splitlines()] if match else []


def inspect_case(before, after, expected, review):
    """Static fixture evidence only; deliberately no native link resolver claim."""
    checks = []
    def record(name, observed, wanted):
        checks.append({"check": name, "status": "pass" if observed == wanted else "fail", "observed": observed, "expected": wanted})
    for target, members in expected["expected_members"].items():
        observed = sorted(path for path, text in after.items() if path.endswith(".md") and not path.startswith("Templates/") and "[[" + target + "]]" in frontmatter_values(text, "categories"))
        record("explicit linked membership: " + target, observed, sorted(members))
    overview = after[ATLAS + "Categories.md"]
    overview_targets = [link for link in re.findall(r"\[\[([^]|]+)(?:\|[^]]*)?\]\]", overview) if link in after and "categories" in frontmatter_values(after[link], "tags")]
    record("import-scoped overview category links", sorted(overview_targets), sorted(expected["expected_overview"]))
    for path in expected["expected_absent"]:
        record("target remains absent: " + path, path in after, False)
    for path, tags in expected["expected_tags"].items():
        record("tag choices: " + path, frontmatter_values(after[path], "tags"), tags)
    unchanged = [path for path in before if path.startswith(("Existing/", "Categories/", "Templates/", "Attachments/", ".obsidian/")) or path in ("Categories.md", "Home.md")]
    record("every existing authored/support file preserved byte-for-byte", [path for path in unchanged if after.get(path) != before[path]], [])
    probes = before["Existing/Link probes.md"]
    record("existing basename Topic stays unique", sorted(path for path in after if Path(path).name.casefold() == "topic.md"), ["Existing/Topic.md"])
    record("intentional FutureIdea basename remains absent", sorted(path for path in after if Path(path).name.casefold() == "futureidea.md"), [])
    record("existing link probe bytes", after["Existing/Link probes.md"], probes)
    ref = expected["source_reference"]
    text = after[ref["path"]]
    record("separate source reference preserves prose", ref["prose"] in text, True)
    record("separate source reference retains source identity", f"source_collection_id: {SOURCE}\nsource_item_id: {ref['item_id']}\n" in text, True)
    record("source reference links shared category", "[[" + ref["category"] in text, True)
    record("source reference links attachment", "[[" + ref["attachment"] + "]]" in text, True)
    record("source attachment bytes", after[ref["attachment"]], ref["attachment_text"])
    if expected.get("pending_conflict"):
        path = expected["pending_conflict"]
        record("manual membership and prose protected until verdict", after[path], before[path])
        record("whole operation blocked", review["apply_allowed"], False)
        record("moved source identity not duplicated", [path for path, text in after.items() if "source_item_id: item-topic\n" in text], [MOVED])
        record("incoming relationship follows moved note", "[[" + MOVED + "|Topic]]" in after[FUTURE], True)
    return {"evidence_kind": "static-synthetic-fixture-inspection", "native_observations": "unverified", "checks": checks, "passed": all(row["status"] == "pass" for row in checks)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Fresh destination inside tmp/merge-wayfinding/categories; existing paths refused")
    args = parser.parse_args()
    output = (args.output or OUTPUT_ROOT / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])).resolve()
    if not output.is_relative_to(OUTPUT_ROOT.resolve()) or output == OUTPUT_ROOT.resolve():
        parser.error("Output must be a fresh child of tmp/merge-wayfinding/categories")
    output.mkdir(parents=True, exist_ok=False)
    source = json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))
    results = []
    for expected, (before, after, mapping, review) in zip(source["cases"], scenarios(), strict=True):
        directory = output / expected["id"]
        put_tree(directory / "before-vault", before)
        put_tree(directory / "proposal-vault", after)
        # Review copies absorb native workspace/cache changes; evidence originals stay untouched.
        shutil.copytree(directory / "before-vault", directory / "native-before")
        shutil.copytree(directory / "proposal-vault", directory / "native-proposal")
        def save(name, value):
            (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        save("before-inventory.json", inventory(directory / "before-vault"))
        save("proposal-inventory.json", inventory(directory / "proposal-vault"))
        save("prior-mappings.json", mappings("type-project", "Projects", PROJECTS) if review.get("prior_mapping") else {})
        save("proposed-mappings.json", mapping)
        save("review.json", review)
        save("independent-expectations.json", expected)
        report = inspect_case(before, after, expected, review)
        save("static-observations.json", report)
        results.append({"case": expected["id"], "static_passed": report["passed"], "checks": len(report["checks"]), "native": "unverified", "human_verdict": None})
    (output / "summary.json").write_text(json.dumps({"prototype_only": True, "output": str(output), "cases": results}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "cases": results}, indent=2))
    if not all(row["static_passed"] for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
