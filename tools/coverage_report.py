"""Report exact file contexts once, without duplicate full-file maps in regions."""

import argparse
import json
from pathlib import Path

from coverage import Coverage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rcfile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    coverage = Coverage(config_file=str(args.rcfile))
    coverage.load()
    coverage.json_report(outfile=str(args.output), show_contexts=False)
    report = json.loads(args.output.read_text(encoding="utf-8"))
    data = coverage.get_data()
    measured = {}
    for name in data.measured_files():
        path = Path(name).resolve()
        if path in measured:
            raise ValueError("Ambiguous canonical coverage source path")
        measured[path] = name
    for filename, details in report["files"].items():
        source = measured.get(Path(filename).resolve())
        if source is None and details["executed_lines"]:
            raise ValueError("Executed coverage source has no bound context data")
        details["contexts"] = {} if source is None else data.contexts_by_lineno(source)
    report["meta"]["show_contexts"] = True
    report["meta"]["context_scope"] = "file"
    args.output.write_text(json.dumps(report) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
