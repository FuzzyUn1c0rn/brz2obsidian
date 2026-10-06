"""Opt-in driver. Run as python -m tests.local_acceptance.run --help."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from .checker import (
    ROOTS,
    check_run_result,
    check_vault,
    compare_vaults,
    read_source,
    semantic,
)

INPUTS = {
    "A": (45016149, "84405276897f27f188a9f33453aac94cfdac6a4dfaaeecf8f0bd5a46454b7be4"),
    "B": (
        153693431,
        "20b6085239b82ba7c4a6951d07a53243c3d7ddd00fcd3d6b91115cd7170c26b0",
    ),
    "C": (62008262, "7c533a30439e281b1d51d6617c9f1f3cad9c2c1d67e5a1e056f280bf37709764"),
    "D": (
        320594486,
        "2b24c1d21b4090f3b0ed3ec0227f269b8c7a4e5b6832ada0e244a1dcfc941ced",
    ),
}
SOURCE_D_GATES = {
    "source_items": 570,
    "ordinary_items": 521,
    "definition_items": 47,
    "tag_items": 1,
    "system_items": 1,
    "source_relationships": 730,
    "ordinary_category_hierarchy": 54,
    "typed_members": 330,
    "attachment_records": 1557,
    "raw_local_payloads": 1017,
    "url_attachments": 454,
    "marked_documents": 328,
    "canonical_documents": 31,
    "present_note_images": 499,
    "present_generic_files": 106,
    "present_icons": 53,
    "absent_ordinary_owners": 63,
    "generated_embeds": 63,
    "absent_definition_notes": 2,
    "absent_icon_providers": 8,
    "neutral_affected_members": 45,
    "txt_gaps": 13,
    "present_icon_discrepancies": 7,
}


def fingerprint(source):
    with source.open("rb") as stream:
        return source.stat().st_size, hashlib.file_digest(stream, "sha256").hexdigest()


def check_input(source, expected):
    assert fingerprint(source) == expected, "accepted source changed"


def check_reordering(source, reordered):
    """Independent multiset/physical byte proof before using reordered inputs."""
    with ZipFile(source) as first, ZipFile(reordered) as second:
        assert first.testzip() is None and second.testzip() is None, "reorder CRC"
        assert len(set(first.namelist())) == len(first.namelist()) and len(
            set(second.namelist())
        ) == len(second.namelist()), "reorder unique ZIP identities"
        assert set(first.namelist()) == set(second.namelist()), "reorder ZIP identities"
        a, b = read_source(first), read_source(second)
        for name in ROOTS:
            assert sorted(map(semantic, a[name]), key=repr) == sorted(
                map(semantic, b[name]), key=repr
            ), "reorder root record multiset"
        for name in first.namelist():
            if name not in ROOTS:
                assert first.read(name) == second.read(name), (
                    "reorder physical payload bytes"
                )


def reordered_archive(source, destination):
    """Reverse record streams and ZIP order; leave all payload bytes intact."""
    with (
        ZipFile(source) as archive,
        ZipFile(destination, "w", compression=ZIP_DEFLATED) as output,
    ):
        for name in reversed(archive.namelist()):
            data = archive.read(name)
            if name in ROOTS and name != "meta.json":
                text = data.decode("utf-8-sig")
                lines = [line for line in re.split(r"\r\n|\r|\n", text) if line.strip()]
                data = b"\xef\xbb\xbf" + "\n".join(reversed(lines)).encode("utf-8")
            output.writestr(name, data)
    check_reordering(source, destination)


def convert(source, destination):
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "brz2obsidian",
            "convert",
            str(source),
            str(destination),
            "--json",
        ],
        capture_output=True,
        env=environment,
        check=False,
    )
    result = json.loads(completed.stdout)
    (destination.parent / (destination.name + "-result.json")).write_bytes(
        completed.stdout
    )
    assert (
        completed.returncode == (2 if result["outcome"] == "warnings" else 0)
        and result["outcome"] in {"clean", "warnings"}
        and result["receipt"]["verified"]
    ), "CLI outcome/receipt"
    assert not completed.stderr, "CLI stderr"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-a",
        type=Path,
        required=True,
        help="Exact original A: D&D, The Rise of Anzoras",
    )
    parser.add_argument(
        "--source-b",
        type=Path,
        required=True,
        help="Exact original B: Dungeons & Dragons",
    )
    parser.add_argument(
        "--source-c",
        type=Path,
        required=True,
        help="Exact original C: Software Engineering",
    )
    parser.add_argument(
        "--source-d",
        type=Path,
        required=True,
        help="Exact original Management & Leadership export; no recovery/re-export substitute",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New ignored short directory; never your normal vault",
    )
    args = parser.parse_args()
    source_paths = {
        "A": args.source_a,
        "B": args.source_b,
        "C": args.source_c,
        "D": args.source_d,
    }
    run_acceptance(source_paths, args.output)


def run_acceptance(source_paths, output, pins=None):
    """Audit twelve complete outputs; explicit pins support synthetic examples.

    The CLI always requires the accepted original pins. This callable permits
    independently fingerprinted synthetic inputs for reusable public proof.
    """
    assert set(source_paths) == set("ABCD"), "four mandatory original inputs"
    pins = INPUTS if pins is None else pins
    assert set(pins) == set("ABCD"), "four mandatory fingerprint pins"
    for key, source in source_paths.items():
        check_input(source, pins[key])
    # Explicit per-process source selection also flows into the CLI subprocess.
    expected_src = Path(__file__).resolve().parents[2] / "src"
    assert os.environ.get("PYTHONPATH") and expected_src.resolve() in {
        Path(p).resolve() for p in os.environ["PYTHONPATH"].split(os.pathsep)
    }, "worktree PYTHONPATH required"
    loaded = subprocess.run(
        [
            sys.executable,
            "-c",
            "import brz2obsidian; print(brz2obsidian.__file__); print(brz2obsidian.__version__)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    location, version = loaded.stdout.strip().splitlines()
    assert (
        Path(location).resolve()
        == (expected_src / "brz2obsidian/__init__.py").resolve()
        and version == "0.3.0"
    ), "worktree converter import/version"
    output.mkdir(parents=True, exist_ok=False)
    summaries = {}
    operations = []
    for key, source in source_paths.items():
        check_input(source, pins[key])
        destination = output / key
        result = convert(source, destination)
        summaries[key] = check_vault(source, destination)
        if key == "D" and pins[key] == INPUTS["D"]:
            assert all(
                summaries[key][field] == value
                for field, value in SOURCE_D_GATES.items()
            ), (
                "agreed D scoped inventory gates (additional to complete raw-source proof)"
            )
        check_run_result(result, destination, summaries[key])
        check_input(source, pins[key])
        operations.append(
            {
                "source": key,
                "variant": "exact",
                "source_fingerprint": pins[key],
                "summary": summaries[key],
            }
        )
        print(f"{key} exact independently accepted", flush=True)
        repeat = output / (key + "-repeat")
        check_input(source, pins[key])
        result = convert(source, repeat)
        assert check_vault(source, repeat) == summaries[key], (
            "repeat independent acceptance"
        )
        check_run_result(result, repeat, summaries[key])
        compare_vaults(destination, repeat)
        check_input(source, pins[key])
        operations.append(
            {
                "source": key,
                "variant": "repeat",
                "source_fingerprint": pins[key],
                "summary": summaries[key],
            }
        )
        print(f"{key} repeat independently accepted", flush=True)
        reordered = output / (key + "-reordered.brz")
        check_input(source, pins[key])
        reordered_archive(source, reordered)
        check_input(source, pins[key])
        shuffled_fingerprint = fingerprint(reordered)
        shuffled_vault = output / (key + "-reordered")
        check_input(reordered, shuffled_fingerprint)
        result = convert(reordered, shuffled_vault)
        assert check_vault(reordered, shuffled_vault) == summaries[key], (
            "reordered independent acceptance"
        )
        check_run_result(result, shuffled_vault, summaries[key])
        compare_vaults(destination, shuffled_vault)
        check_input(reordered, shuffled_fingerprint)
        check_input(source, pins[key])
        check_reordering(source, reordered)
        operations.append(
            {
                "source": key,
                "variant": "reordered",
                "source_fingerprint": shuffled_fingerprint,
                "summary": summaries[key],
            }
        )
        print(f"{key} reordered independently accepted", flush=True)
    for key, source in source_paths.items():
        check_input(source, pins[key])
    (output / "operations.json").write_text(
        json.dumps(operations, indent=2) + "\n", encoding="utf-8"
    )
    (output / "aggregate.json").write_text(
        json.dumps(summaries, indent=2) + "\n", encoding="utf-8"
    )
    for key, source in source_paths.items():
        check_input(source, pins[key])
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
