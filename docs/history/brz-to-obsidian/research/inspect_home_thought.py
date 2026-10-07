"""Read-only, private-safe evidence probe for the inspected format-5 exports.

This is a throwaway investigation aid, not a converter or general BRZ validator.
It reads the two exact real input paths and optional controlled synthetic export.
Real thought names, IDs, note text, and assigned filenames never enter stdout.
Python 3.11+ standard library; no extraction, mutation, or network access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid
import zipfile


REAL_INPUTS = (
    ("A", "D&D_ The Rise of Anzoras 2026-10-03.brz",
     "84405276897f27f188a9f33453aac94cfdac6a4dfaaeecf8f0bd5a46454b7be4"),
    ("B", "Dungeons & Dragons 2026-10-03.brz",
     "20b6085239b82ba7c4a6951d07a53243c3d7ddd00fcd3d6b91115cd7170c26b0"),
)
BASELINE_SHA256 = "53fd9fd22249a59875d3525774e1bb27c8b66830b3d84430b4ababdf0675ae6a"
CONTROLLED_HOME_SHA256 = "aa29d7aa0afb687f8b4ffdd490220c3c2e198c729681083fe5065b3bb55dfbf0"
UUID_TEXT = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")


def canonical_uuid(value):
    if isinstance(value, str) and UUID_TEXT.fullmatch(value):
        return str(uuid.UUID(value))
    return None


def load(path, expected_sha=None):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if expected_sha is not None and digest != expected_sha:
        raise ValueError("Unexpected archive fingerprint")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive CRC failure")
        records = {
            member: [json.loads(line) for line in
                     archive.read(member).decode("utf-8-sig").splitlines()
                     if line.strip()]
            for member in ("meta.json", "thoughts.json", "settings.json", "links.json")
        }
    if records["meta.json"][0]["ExchangeFormatVersion"] != 5:
        raise ValueError("Unexpected exchange format")
    return digest, records


def home_reference(records):
    brain_id = uuid.UUID(records["meta.json"][0]["BrainId"])
    setting_id = str(uuid.uuid5(brain_id, "20"))
    settings = [row for row in records["settings.json"]
                if canonical_uuid(row["Id"]) == setting_id]
    if not settings:
        return "absent", None, None
    if len(settings) != 1:
        return "duplicate_setting", None, None
    thought_id = canonical_uuid(settings[0]["Value"])
    if thought_id is None:
        return "invalid_uuid_value", None, settings[0]
    thoughts = [row for row in records["thoughts.json"]
                if canonical_uuid(row["Id"]) == thought_id]
    if not thoughts:
        return "nonlive_reference", thought_id, settings[0]
    if len(thoughts) != 1:
        return "duplicate_thought", thought_id, settings[0]
    return "resolved", thought_id, settings[0]


def summarize(label, path, records, digest, vault_record=None):
    state, thought_id, _ = home_reference(records)
    brain_id = uuid.UUID(records["meta.json"][0]["BrainId"])
    thought_ids = {canonical_uuid(t["Id"]) for t in records["thoughts.json"]}
    numeric_keys = {str(uuid.uuid5(brain_id, str(index))) for index in range(1000)}
    thought = next((t for t in records["thoughts.json"]
                    if canonical_uuid(t["Id"]) == thought_id), None)
    result = {
        "archive": label,
        "bytes": path.stat().st_size,
        "sha256": digest,
        "exchange_format": 5,
        "settings": len(records["settings.json"]),
        "settings_matching_uuid5_brain_numeric_text_0_to_999": sum(
            canonical_uuid(s["Id"]) in numeric_keys for s in records["settings.json"]),
        "settings_with_exact_live_thought_uuid_values": sum(
            canonical_uuid(s.get("Value")) in thought_ids for s in records["settings.json"]),
        "key_derivation": "UUIDv5(namespace=meta.BrainId, name='20')",
        "reference_state": state,
        "target_kind": thought["Kind"] if thought else None,
        "target_ordinary_parent_count": sum(
            link["Meaning"] == 1 and link["Relation"] == 1
            and canonical_uuid(link["ThoughtIdB"]) == thought_id
            for link in records["links.json"]),
    }
    if vault_record is not None and thought_id is not None:
        assigned = [row for row in vault_record["all_reserved_real_targets"]
                    if row["archive"] == label
                    and canonical_uuid(row["source_thought_id"]) == thought_id]
        selected = [row for row in vault_record["thoughts"]
                    if row["archive"] == label
                    and canonical_uuid(row["source"]["Id"]) == thought_id]
        result["trial_reserved_target_matches"] = len(assigned)
        result["trial_selected_record_matches"] = len(selected)
        result["trial_home_created"] = len(selected) == 1 and selected[0]["created"]
    return result


def controlled_comparison(before, after):
    before_state, before_id, _ = home_reference(before)
    after_state, after_id, _ = home_reference(after)
    if before_state != "resolved" or after_state != "resolved":
        raise ValueError("Controlled home reference not resolved")
    expected_names = {"PARENT", "CHILD", "PEER", "ARROW", "REVERSE_ARROW",
                      "ONE_WAY_FORWARD", "ONE_WAY_REVERSE"}
    actual_names = {t["Name"] for t in after["thoughts.json"] if t["Kind"] == 1}
    if actual_names != expected_names:
        raise ValueError("Not the expected synthetic Brain")
    by_id = {canonical_uuid(t["Id"]): t for t in after["thoughts.json"]}
    if before["meta.json"][0]["BrainId"] != after["meta.json"][0]["BrainId"]:
        raise ValueError("Controlled exports belong to different Brains")
    if by_id[before_id]["Name"] != "PARENT" or by_id[after_id]["Name"] != "CHILD":
        raise ValueError("Controlled PARENT to CHILD home change not found")
    active = [t for t in after["thoughts.json"] if t.get("ActivationDateTime")]
    latest = max(t["ActivationDateTime"] for t in active)
    most_recent = sorted(t["Name"] for t in active if t["ActivationDateTime"] == latest)
    if most_recent != ["PEER"]:
        raise ValueError("Controlled most recent activation does not match PEER")
    namespace = uuid.UUID(after["meta.json"][0]["BrainId"])
    numeric_names = {str(uuid.uuid5(namespace, str(index))): index for index in range(1000)}
    old_values = {s["Id"]: s["Value"] for s in before["settings.json"]}
    new_values = {s["Id"]: s["Value"] for s in after["settings.json"]}
    changed = {key for key in old_values.keys() & new_values.keys()
               if old_values[key] != new_values[key]}
    return {
        "same_brain": True,
        "same_derived_setting_id": True,
        "setting_value_changed": before_id != after_id,
        "before_synthetic_home": "PARENT",
        "after_synthetic_home": "CHILD",
        "most_recent_activated_synthetic_thoughts": most_recent,
        "changed_numeric_setting_values": sorted(numeric_names[key] for key in changed if key in numeric_names),
        "changed_setting_values_without_numeric_match": len(changed - numeric_names.keys()),
        "home_has_ordinary_parent": any(
            link["Meaning"] == 1 and link["Relation"] == 1
            and canonical_uuid(link["ThoughtIdB"]) == after_id
            for link in after["links.json"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--controlled-after", type=Path)
    parser.add_argument("--vault-record", type=Path)
    args = parser.parse_args()
    vault_record = json.loads(args.vault_record.read_text(encoding="utf-8-sig")) if args.vault_record else None
    output = {"real_archives": []}
    for label, filename, expected in REAL_INPUTS:
        path = args.source_root / "brz" / filename
        digest, records = load(path, expected)
        output["real_archives"].append(summarize(label, path, records, digest, vault_record))
    path = args.source_root / "brz" / "relationship-fixture.brz"
    digest, before = load(path, BASELINE_SHA256)
    output["original_controlled_export"] = summarize("controlled_original", path, before, digest)
    if args.controlled_after:
        digest, after = load(args.controlled_after, CONTROLLED_HOME_SHA256)
        output["changed_controlled_export"] = summarize("controlled_changed", args.controlled_after, after, digest)
        output["controlled_comparison"] = controlled_comparison(before, after)
    # Exercise evidence detection only; these are not imported into TheBrain.
    key = str(uuid.uuid5(uuid.UUID(before["meta.json"][0]["BrainId"]), "20"))
    row = next(s for s in before["settings.json"] if s["Id"] == key)
    omitted = {**before, "settings.json": [s for s in before["settings.json"] if s["Id"] != key]}
    invalid = {**before, "settings.json": [({**s, "Value": ""} if s is row else s) for s in before["settings.json"]]}
    nonlive = {**before, "settings.json": [({**s, "Value": str(uuid.UUID(int=0))} if s is row else s) for s in before["settings.json"]]}
    output["in_memory_detection_only"] = {
        "omitted_setting": home_reference(omitted)[0],
        "empty_value": home_reference(invalid)[0],
        "nonlive_uuid_value": home_reference(nonlive)[0],
        "does_not_establish_thebrain_fallback_behavior": True,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"inspection_failed": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
