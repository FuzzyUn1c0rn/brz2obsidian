import argparse
import io
import json
import subprocess
import sys
import tokenize
from collections import Counter
from pathlib import Path

from tools.check import Invalid, digest, git

BASELINE = Path("tools/comment-baseline.json")
PYTHON_SUFFIXES = {".py", ".pyi", ".pyw"}


def python_comments(root):
    names = git(
        root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"
    ).decode("utf-8")
    for name in sorted(set(names.split("\0")) - {""}):
        path = root / name
        if path.suffix not in PYTHON_SUFFIXES or not path.is_file():
            continue
        try:
            for token in tokenize.tokenize(io.BytesIO(path.read_bytes()).readline):
                if token.type == tokenize.COMMENT:
                    yield name, token
        except (SyntaxError, UnicodeError, tokenize.TokenError) as error:
            raise Invalid(
                f"{name}: cannot tokenize for comment lint: {error}"
            ) from error


def check_comments(root, *, prune=False):
    path = root / BASELINE
    remaining = {
        name: Counter(hashes)
        for name, hashes in json.loads(path.read_text(encoding="utf-8")).items()
    }
    retained = {}
    added = 0
    for name, token in python_comments(root):
        fingerprint = digest(token.string.rstrip().encode("utf-8"))
        if name in remaining and remaining[name][fingerprint]:
            remaining[name][fingerprint] -= 1
            retained.setdefault(name, []).append(fingerprint)
        else:
            line, column = token.start
            print(f"{name}:{line}:{column + 1}: new Python comment")
            added += 1
    if added:
        return False

    stale = sum(counts.total() for counts in remaining.values())
    if not stale:
        return True
    if not prune:
        print(
            f"Remove {stale} retired entries from {BASELINE.as_posix()} "
            "with python -m tools.check_lint --prune-comments"
        )
        return False

    records = [
        f"  {json.dumps(name)}: {json.dumps(sorted(hashes))}"
        for name, hashes in retained.items()
    ]
    temporary = path.with_suffix(".pending")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("{\n" + ",\n".join(records) + ("\n" if records else "") + "}\n")
    temporary.replace(path)
    print(f"Retired {stale} Python comment baseline entries")
    return True


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--cache-dir", type=Path)
    mode.add_argument("--prune-comments", action="store_true")
    args = parser.parse_args()
    try:
        comments_valid = check_comments(Path.cwd(), prune=args.prune_comments)
    except (Invalid, OSError, ValueError) as error:
        print(f"Comment lint: {error}", file=sys.stderr)
        comments_valid = False
    if args.prune_comments:
        return int(not comments_valid)
    ruff = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--cache-dir",
            str(args.cache_dir),
            ".",
        ],
        check=False,
    )
    return ruff.returncode or int(not comments_valid)


if __name__ == "__main__":
    raise SystemExit(main())
