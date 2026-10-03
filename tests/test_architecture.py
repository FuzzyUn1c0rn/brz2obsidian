import json
import subprocess
import sys


def test_generic_imports_do_not_load_source_cli_or_publication_implementations():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys,json; import brz2obsidian.core,brz2obsidian.obsidian,brz2obsidian.application; print(json.dumps(sorted(sys.modules)))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    modules = json.loads(result.stdout)
    assert "brz2obsidian.sources.thebrain" not in modules
    assert "brz2obsidian.publication.filesystem" not in modules
    assert "brz2obsidian.cli" not in modules
    assert "brz2obsidian.application.wiring" not in modules
