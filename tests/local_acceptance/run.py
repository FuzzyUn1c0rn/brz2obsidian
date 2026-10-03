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

from .checker import ROOTS, check_run_result, check_vault, compare_vaults

INPUTS = {
    "A": (45016149, "84405276897f27f188a9f33453aac94cfdac6a4dfaaeecf8f0bd5a46454b7be4"),
    "B": (
        153693431,
        "20b6085239b82ba7c4a6951d07a53243c3d7ddd00fcd3d6b91115cd7170c26b0",
    ),
}
EXPECTED = {
    "A": {
        "notes": 49,
        "hierarchy_only": 5,
        "payloads": 60,
        "backups": 43,
        "warnings": 2,
        "warning_owners": 2,
    },
    "B": {
        "notes": 42,
        "hierarchy_only": 2,
        "payloads": 50,
        "backups": 34,
        "warnings": 9,
        "warning_owners": 7,
    },
}


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
        completed.returncode == 2
        and result["outcome"] == "warnings"
        and result["receipt"]["verified"]
    ), "CLI outcome/receipt"
    assert not completed.stderr, "CLI stderr"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-a", type=Path, required=True)
    parser.add_argument("--source-b", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New ignored short directory; never your normal vault",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    summaries = {}
    for key, source in [("A", args.source_a), ("B", args.source_b)]:
        size, digest = INPUTS[key]
        assert source.stat().st_size == size, "acceptance input size"
        with source.open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == digest, (
                "acceptance input fingerprint"
            )
        destination = args.output / key
        result = convert(source, destination)
        summaries[key] = check_vault(source, destination)
        check_run_result(result, destination, summaries[key])
        assert all(
            summaries[key][field] == value for field, value in EXPECTED[key].items()
        ), "agreed baseline"
        repeat = args.output / (key + "-repeat")
        result = convert(source, repeat)
        assert check_vault(source, repeat) == summaries[key], (
            "repeat independent acceptance"
        )
        check_run_result(result, repeat, summaries[key])
        compare_vaults(destination, repeat)
        reordered = args.output / (key + "-reordered.brz")
        reordered_archive(source, reordered)
        shuffled_vault = args.output / (key + "-reordered")
        result = convert(reordered, shuffled_vault)
        assert check_vault(reordered, shuffled_vault) == summaries[key], (
            "reordered independent acceptance"
        )
        check_run_result(result, shuffled_vault, summaries[key])
        compare_vaults(destination, shuffled_vault)
    (args.output / "aggregate.json").write_text(
        json.dumps(summaries, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
