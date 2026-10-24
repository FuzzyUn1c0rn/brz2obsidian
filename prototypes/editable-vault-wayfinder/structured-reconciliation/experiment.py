"""Bounded manual design experiment for #251; no production update implementation."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.dont_write_bytecode = True

from brz2obsidian.contracts import (Asset, ClassificationAssignment, Document, Item, OriginalEvidence,
    Relationship, RunMetadata, SourceAccounting, SourceIdentity, SourcePolicy, SourceSnapshot)
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import render

HERE = Path(__file__).parent
IDENTITY = ("structured-synthetic", "topic")
HEADINGS = ("Resources", "Parents", "Children", "Related")
LOCAL_BINARY = b"Local binary\x00revision\n"
INCOMING_BINARY = b"Incoming binary\x00revision\n"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def put(root, path, data):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data.encode() if isinstance(data, str) else data)


def generated():
    """Actual public renderer from synthetic source-neutral contracts, no private input."""
    text = "Original first paragraph.\n\nOriginal second paragraph.\n"
    digest = sha(text.encode())
    names = {"entry": "Entry", "topic": "Topic", "parent": "Parent", "other": "Other parent",
        "peer": "Peer", "local": "Local peer", "projects": "Projects", "topics": "Topics", "manual": "Manual"}
    items = tuple(Item(key=k, original_identity=k, naming_seed=f"{n+16:08x}", title=v,
        role="definition" if k in {"projects", "topics", "manual"} else "ordinary",
        document_ids=("doc",) if k == "topic" else ("doc-" + k,),
        resource_ids=("binary",) if k == "topic" else ()) for n, (k, v) in enumerate(names.items()))
    facts = SourceSnapshot(identity=SourceIdentity(source_id=IDENTITY[0], module_id="synthetic",
        module_version="1", format_version="1", source_sha256="a"*64, snapshot_digest="b"*64),
        collection_title="Structured reconciliation", entry_key="entry", items=items,
        documents=(Document(key="doc", owner="topic", text=text, text_digest=digest,
            original_asset_id=None, original_copy_omitted=True),) + tuple(Document(key="doc-"+k,
            owner=k, text="Synthetic target control.\n", text_digest=sha(b"Synthetic target control.\n"),
            original_asset_id=None, original_copy_omitted=True) for k in names if k != "topic"),
        assets=(Asset(asset_id="binary", owner="topic", naming_seed="a1", original_name="report.txt",
            role="file", availability="present", actual_length=len(LOCAL_BINARY), actual_sha256=sha(LOCAL_BINARY)),),
        relationships=(Relationship(key="p", kind="hierarchy", item_a="parent", item_b="topic"),
            Relationship(key="r", kind="related", item_a="topic", item_b="peer"),
            Relationship(key="c", kind="classification", item_a="projects", item_b="topic")),
        classification_assignments=(ClassificationAssignment(relationship_key="c", definition_key="projects", item_key="topic", evidence=("synthetic-classification",)),),
        original_evidence=(OriginalEvidence(key="synthetic-classification", kind="records", original_json='{"definition":"projects","member":"topic"}'),),
        accounting=SourceAccounting(entries=()))
    policy = SourcePolicy(profile_id="synthetic", profile_version="1", module_id="synthetic", module_version="1", format_version="1")
    planned = plan(analyze(facts, policy))
    artifacts = render(planned, RunMetadata(converter_version="prototype", renderer_version="7",
        run_id="fixed", run_time="2026-10-21T00:00:00Z", obsidian_version="1.14.4", bookmark_time=0))
    files = {f.relative_path: f.content for f in artifacts.generated_files}
    files.update({t.relative_path: LOCAL_BINARY for t in planned.asset_targets if t.asset_id == "binary"})
    paths = {t.item_key: t.relative_path for t in planned.item_targets}
    return files, paths, facts.model_dump(mode="json")


def parse(data):
    """Only canonical v7 scalar/list YAML and plain body paragraphs/list sections."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("unsupported encoding") from None
    if not text.startswith("---\n") or "\r" in text:
        raise ValueError("unsupported frontmatter")
    front, body = text[4:].split("---\n\n", 1)
    values, raws, key = {}, {}, None
    for line in front.splitlines(keepends=True):
        if line.startswith("  - ") and key:
            try:
                value = json.loads(line[4:])
                if not isinstance(values[key], list) or not isinstance(value, str):
                    raise ValueError()
                values[key].append(value)
                raws[key] += line
            except (ValueError, TypeError):
                raise ValueError("unsupported frontmatter") from None
            continue
        match = re.fullmatch(r"([a-z_]+):(?: (.*))?\n", line)
        if not match or match[1] in values:
            raise ValueError("unsupported frontmatter")
        key, scalar = match.groups()
        try:
            value = None if scalar is None else json.loads(scalar)
        except ValueError:
            if scalar and re.fullmatch(r"\d{4}-\d{2}-\d{2}", scalar):
                value = scalar
            else:
                raise ValueError("unsupported frontmatter") from None
        if value is None and key in {"categories", "tags", "aliases"}:
            value = []
        if isinstance(value, dict):
            raise ValueError("unsupported frontmatter")
        values[key], raws[key] = value, line
    starts = list(re.finditer(r"^## (.+)\n\n", body, re.M))
    labels = [m[1] for m in starts]
    if any(label not in HEADINGS for label in labels) or len(set(labels)) != len(labels):
        raise ValueError("ambiguous body structure")
    prefix = body[: starts[0].start()] if starts else body
    # No claim to parse arbitrary Markdown, fenced examples or headings in source prose.
    if re.search(r"(?m)^(?:```|~~~|##|\||>|- )", prefix):
        raise ValueError("ambiguous body structure")
    blocks = {m[1]: body[m.end(): starts[i+1].start() if i+1 < len(starts) else len(body)]
        for i, m in enumerate(starts)}
    for label, block in blocks.items():
        if label == "Resources":
            valid = r"- \[\[[^\]\n]+\|[^\]\n]+\]\]\n"
        else:
            valid = r"- \[\[[^\]\n]+\|[^\]\n]+\]\]\n"
        if not re.fullmatch("(?:" + valid + ")+\\n*", block):
            raise ValueError("ambiguous body structure")
    return values, raws, prefix, blocks


def tri(base, local, incoming, label):
    if incoming == base or local == incoming:
        return local
    if local == base:
        return incoming
    raise ValueError("conflicting " + label)


def identity_inventory(files):
    """Read canonical identity scalars only; unrelated malformed notes supply no match."""
    found = {}
    for path, data in files.items():
        if not path.endswith(".md"):
            continue
        text = data.decode("utf-8", errors="replace")
        front = text.split("---", 2)[1] if text.startswith("---\n") else ""
        pairs = [re.findall(r"(?m)^" + key + r': "([^"\n]+)"$', front)
            for key in ("source_collection_id", "source_item_id")]
        if all(len(v) == 1 for v in pairs):
            found.setdefault(tuple(v[0] for v in pairs), []).append(path)
    return found


def recheck_review(reviewed_sha, current):
    if reviewed_sha != sha(current):
        return {"status": "stale-review", "reason": "affected bytes changed"}
    return {"status": "review-current"}


def reconcile(base, local, incoming, path, identity_paths, *, current_paths=None):
    """Pure bounded decision; unchanged incoming never requires parsing authored bytes."""
    result = {"path": path, "bytes": local, "status": "unresolved"}
    if incoming is None:
        return result | {"status": "source-absent-preserved"}
    if local is None:
        return result | {"status": "keep-deleted" if incoming == base else "restoration-review"}
    matches = identity_paths.get(IDENTITY, [])
    if len(matches) != 1:
        return result | {"status": "identity-resolution", "reason": "missing affected identity" if not matches else "duplicate affected identity"}
    result["path"] = matches[0]
    if base is None:
        return result | {"status": "onboarding-review", "reason": "unknown original bytes"}
    if incoming == base:
        return result | {"status": "no-op" if local == base else "preserve-vault"}
    try:
        b, l, n = parse(base), parse(local), parse(incoming)
        if any(tuple(x[0]) != tuple(b[0]) for x in (l, n)):
            raise ValueError("unsupported frontmatter")
        if any(tuple(x[0].get(k) for k in ("source_collection_id", "source_item_id")) != IDENTITY for x in (b, l, n)):
            raise ValueError("changed identity")
        raw = []
        for key in b[0]:
            if key == "categories" and b[0][key] != l[0][key] and b[0][key] != n[0][key] and l[0][key] != n[0][key]:
                before, left, right = (x[0][key] for x in (b, l, n))
                if not all(isinstance(v, list) and len(set(v)) == len(v) for v in (before, left, right)):
                    raise ValueError("unsupported memberships")
                if not set(before) <= set(left) or not set(before) <= set(right):
                    raise ValueError("membership removal overlaps local change")
                combined = left + [v for v in right if v not in left]
                raw.append("categories:\n" + "".join("  - " + json.dumps(v) + "\n" for v in combined))
            else:
                chosen = tri(b[0][key], l[0][key], n[0][key], "property " + key)
                raw.append(l[1][key] if chosen == l[0][key] else n[1][key])
        bp, lp, np = [x[2].split("\n\n") for x in (b, l, n)]
        if len(bp) != len(lp) or len(bp) != len(np):
            raise ValueError("ambiguous body structure")
        prose = "\n\n".join(tri(x, y, z, "prose") for x, y, z in zip(bp, lp, np))
        sections = []
        for heading in HEADINGS:
            block = tri(*(x[3].get(heading, "") for x in (b, l, n)), "section " + heading)
            if not block:
                continue
            # Rewrite only verified generated relationship slots, using unique identity/path mapping.
            if heading != "Resources":
                for old_path, new_path in (current_paths or {}).items():
                    block = block.replace("[[" + old_path + "|", "[[" + new_path + "|")
            sections.append("## " + heading + "\n\n" + block)
        data = ("---\n" + "".join(raw) + "---\n\n" + prose + "".join(sections)).encode()
        parse(data)
        return result | {"status": "proposed-compatible", "bytes": data}
    except ValueError as error:
        return result | {"reason": str(error)}


def semantic_audit(data):
    """Independent observations: regex extraction + literal expectations, not merge parser."""
    if data is None:
        return {}
    text = data.decode("utf-8", errors="replace")
    front = text.split("---", 2)[1] if text.startswith("---") else ""
    categories = re.search(r"(?m)^categories:\n((?:  - .*\n)*)", front)
    facts = {"categories": re.findall(r'\[\[([^\]]+)\]\]', categories[1]) if categories else []}
    for heading, key in (("Resources", "resources"), ("Parents", "parents"), ("Related", "related")):
        part = re.search(r"(?ms)^## " + heading + r"\n\n(.*?)(?=^## |\Z)", text)
        facts[key] = re.findall(r"\[\[([^|\]]+)(?:\|[^\]]*)?\]\]", part[1]) if part else []
    return facts


def main():
    start = time.perf_counter()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "tmp/merge-wayfinding/followups/structured" / stamp
    out.mkdir(parents=True, exist_ok=False)
    # Read the independently authored oracle before generating or running anything.
    expected_bytes = (HERE / "expected.json").read_bytes()
    expected = json.loads(expected_bytes)
    put(out, "expected-before-run.json", expected_bytes)
    files, paths, facts = generated()
    for path, data in files.items():
        put(out / "generated", path, data)
    put(out, "source-contracts.json", json.dumps(facts, indent=2))
    base = files[paths["topic"]]
    path = paths["topic"]
    ident = identity_inventory(files)
    def edit(data, old, new):
        if data.count(old.encode()) != 1:
            raise RuntimeError(f"fixture edit requires unique literal: {old}")
        return data.replace(old.encode(), new.encode())
    inc = edit(base, "Original first paragraph.", "Incoming first paragraph.")
    local = edit(base, "Original second paragraph.", "Local second paragraph.")
    alias = edit(base, "aliases: []", 'aliases:\n  - "Local alias"')
    values = {}
    def run(key, left=base, right=inc, original=base, identities=ident, at=path, **kw):
        folder = out / "cases" / key
        for version, data in (("base", original), ("vault", left), ("incoming", right)):
            if data is not None:
                put(folder, version + ".md", data)
        result = reconcile(original, left, right, at, identities, **kw)
        if result["bytes"] is not None:
            put(folder, "result.md", result["bytes"])
        put(folder, "identity-inventory.json", json.dumps({"/".join(k):v for k,v in identities.items()}, indent=2))
        values[key] = result
    run("S01", alias)
    run("S02", local)
    run("S03", edit(base, "Original first paragraph.", "Local first paragraph."))
    run("S04", alias, edit(base, "updated:", "updated: 2026-10-21"))
    run("S05", alias, edit(base, "aliases: []", 'aliases:\n  - "Incoming alias"'))
    member = '  - "[[Categories/Projects.md]]"'
    run("S06", edit(base, member, member + '\n  - "[[Categories/Manual.md]]"'),
        edit(base, member, member + '\n  - "[[Categories/Topics.md]]"'))
    run("S07", edit(base, member, member + '\n  - "[[Categories/Manual.md]]"'), edit(base, member, '  - "[[Categories/Topics.md]]"'))
    run("S08", edit(base, "- [[Notes/Peer.md|Peer]]", "- [[Notes/Peer.md|Peer]]\n- [[Notes/Local peer.md|Local peer]]"),
        edit(base, "- [[Notes/Parent.md|Parent]]", "- [[Notes/Parent.md|Parent]]\n- [[Notes/Other parent.md|Other parent]]"))
    run("S09", edit(base, "- [[Notes/Peer.md|Peer]]", "- [[Notes/Peer.md|Peer]]\n- [[Notes/Local peer.md|Local peer]]"),
        edit(base, "- [[Notes/Peer.md|Peer]]", "- [[Notes/Other parent.md|Other parent]]"))
    old_resource = "Attachments/00000011/report.txt"
    # Asset ownership uses the item's seed; this exact expected path is checked separately.
    if old_resource not in base.decode():
        raise RuntimeError("Unexpected actual renderer resource shape")
    resource_inc = edit(base, old_resource, "Attachments/a1/report-incoming.txt")
    run("S10", local, resource_inc)
    unsupported = edit(base, "aliases: []", "aliases: &local []")
    run("S11", unsupported)
    run("S12", base + b"\n## Related\n\nAuthored section with the same heading.\n")
    moved = {k:v for k,v in files.items() if k != path} | {"Reading/Topic moved.md": alias}
    run("S13", alias, identities=identity_inventory(moved))
    missing = edit(base, 'source_item_id: "topic"\n', "")
    run("S14", missing, identities=identity_inventory(files | {path: missing}))
    duplicate = files | {"Other/Topic.md": base}
    run("S15", identities=identity_inventory(duplicate))
    put(out / "identity-fixtures", "missing/Notes/Topic.md", missing)
    put(out / "identity-fixtures", "duplicate/Notes/Topic.md", base)
    put(out / "identity-fixtures", "duplicate/Other/Topic.md", base)
    put(out / "identity-fixtures", "moved/Reading/Topic moved.md", alias)
    run("S16", alias, original=None)
    run("S18", unsupported, base)
    run("S19", b"\xff\xfeL\x00o\x00c\x00a\x00l\x00")
    run("S20", right=None)
    run("S21", left=None, right=base)
    run("S22", left=None)
    run("S23", right=base)
    # A saved-review recheck is separate from semantic merge.
    values["S24"] = recheck_review(sha(base), local) | {"bytes": local,
        "reviewed_sha256": sha(base), "current_sha256": sha(local)}
    run("S25", right=inc, current_paths={"Notes/Peer.md": "Reading/Peer moved.md"})
    # This fixture removes the old peer through source change only, then retargets it in the known generated slot.
    run("S26", edit(base, old_resource, "Attachments/a1/report-local.txt"), resource_inc)
    # Both additions are textually mergeable but create duplicated scalar keys.
    yaml_base = base
    yaml_left = edit(base, "created:\n", 'created:\npriority: "local"\n')
    yaml_right = edit(base, "aliases: []\n", 'aliases: []\npriority: "incoming"\n')
    folder = out / "git-clean-duplicate-key"
    for name, data in (("base.md", yaml_base), ("vault.md", yaml_left), ("incoming.md", yaml_right)):
        put(folder, name, data)
    merge = subprocess.run(["git", "merge-file", "-p", str(folder / "vault.md"), str(folder / "base.md"), str(folder / "incoming.md")], capture_output=True)
    put(folder, "git-result.md", merge.stdout)
    # Parse the actual clean merged bytes; success at the Git layer cannot authorise publication.
    try:
        parse(merge.stdout)
        reason = "unexpected accepted duplicate key"
    except ValueError as error:
        reason = str(error)
    values["S27"] = {"status": "unresolved", "reason": reason, "bytes": yaml_left,
        "git_exit": merge.returncode, "duplicate_key_count": merge.stdout.count(b"priority:")}
    # Keep-both is deliberately an explicit reviewed choice; no automatic binary merge.
    keep = out / "keep-both"
    kept_path = old_resource
    incoming_path = "Attachments/a1/report-incoming.txt"
    put(keep, kept_path, LOCAL_BINARY)
    put(keep, incoming_path, INCOMING_BINARY)
    keep_note = edit(base, old_resource, incoming_path)
    put(keep, path, keep_note)
    values["S17"] = {"status": "explicit-keep-both", "bytes": keep_note, "path": kept_path,
        "incoming_path": incoming_path, "vault_bytes": (keep / kept_path).read_bytes().decode(),
        "incoming_bytes": (keep / incoming_path).read_bytes().decode(),
        "reference_change": {"from": old_resource, "to": incoming_path, "requires_explicit_review": True}}
    # Native sample is a copy of actual output plus reviewed synthetic move/reference adjustments.
    native = out / "native-copy"
    for target, data in files.items():
        put(native, target, data)
    (native / path).unlink()
    (native / "Notes/Peer.md").unlink()
    put(native, "Reading/Topic moved.md", values["S13"]["bytes"])
    put(native, "Reading/Peer moved.md", files["Notes/Peer.md"])
    native_topic = edit(values["S13"]["bytes"], "Notes/Peer.md|Peer", "Reading/Peer moved.md|Peer")
    native_topic = edit(native_topic, old_resource, incoming_path)
    put(native, "Reading/Topic moved.md", native_topic)
    put(native, kept_path, b"Retained native control.\n")
    put(native, incoming_path, b"Incoming native control: this is the distinct reviewed target.\n")
    put(native, "START.md", "# Structured reconciliation native sample\n\n[[Reading/Topic moved.md|Moved Topic]]\n\n[[Categories/Projects.md|Projects category]]\n")
    observed = []
    for expect in expected["cases"]:
        actual = values[expect["id"]]
        body = actual["bytes"].decode("utf-8", errors="replace") if actual["bytes"] else ""
        facts = semantic_audit(actual["bytes"])
        checks = {"status": actual["status"] == expect["status"]}
        for key in ("path", "incoming_path", "reason", "vault_bytes", "incoming_bytes"):
            if key in expect:
                checks[key] = actual.get(key) == expect[key]
        for key in ("categories", "parents", "related", "resources"):
            if key in expect:
                checks[key] = sorted(facts.get(key, [])) == sorted(expect[key])
        checks["contains"] = all(v in body for v in expect.get("contains", []))
        checks["absent"] = all(v not in body for v in expect.get("absent", []))
        if actual["status"] in {"unresolved", "identity-resolution", "onboarding-review"}:
            # Exact untouched local bytes are required for unresolved fallbacks.
            fixture = out / "cases" / expect["id"] / "vault.md"
            if fixture.exists():
                checks["local_bytes_preserved"] = actual["bytes"] == fixture.read_bytes()
        if expect["id"] == "S27":
            checks["git_clean_but_duplicate"] = actual["git_exit"] == 0 and actual["duplicate_key_count"] == 2
        observed.append({"expected": expect, "actual": {k:v for k,v in actual.items() if k != "bytes"},
            "semantic_observations": facts, "result_sha256": sha(actual["bytes"]) if actual["bytes"] else None,
            "checks": checks, "pass": all(checks.values())})
    binding = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in [HERE / "experiment.py", HERE / "expected.json",
        ROOT / "src/brz2obsidian/obsidian/rendering.py", ROOT / "src/brz2obsidian/obsidian/properties.py",
        ROOT / "src/brz2obsidian/obsidian/relationships.py", ROOT / "src/brz2obsidian/obsidian/resources.py"]}
    payload = {"purpose": "manual prototype observations, no production guarantee", "source_hashes": binding,
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python": sys.executable, "elapsed_seconds": time.perf_counter()-start,
        "generated_inventory": {k: {"sha256": sha(v), "bytes": len(v)} for k,v in files.items()},
        "cases": observed, "all_pass": all(v["pass"] for v in observed)}
    put(out, "results.json", json.dumps(payload, indent=2, ensure_ascii=False))
    report = ["# Structured reconciliation observations", "", f"Run: {out}",
        f"All literal expectations matched: {payload['all_pass']}. Elapsed {payload['elapsed_seconds']:.3f}s.", "",
        "| Case | Scenario | Outcome | Expectation |", "|---|---|---|---|"]
    report += [f"| {v['expected']['id']} | {v['expected']['scenario']} | {v['actual']['status']} | {'PASS' if v['pass'] else 'FAIL'} |" for v in observed]
    put(out, "REPORT.md", "\n".join(report) + "\n")
    print(out)
    print(json.dumps({"all_pass": payload["all_pass"], "failed": [v["expected"]["id"] for v in observed if not v["pass"]]}))


if __name__ == "__main__":
    main()
