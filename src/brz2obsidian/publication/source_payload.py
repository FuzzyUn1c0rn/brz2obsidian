"""Physical complete converted-source observation outside S1 reconciliation."""

import os
import stat
from pathlib import Path

from brz2obsidian.application.source_payload_contracts import (
    ReviewedSourceBinding,
    SourcePayloadFile,
)
from brz2obsidian.publication.vault_admission import _safe_relative, _walk
from brz2obsidian.publication.vault_native import observe_file, verify_directory


def observe_reviewed_source(source, review):
    """Bind current physical payload to a prepared review before user choices."""
    root = Path(source).absolute()
    anchor = verify_directory(root)
    paths = []
    for parent, names, files in _walk(root):
        for name in (*names, *files):
            relative = (Path(parent) / name).relative_to(root).as_posix()
            if not _safe_relative(relative):
                raise OSError("Converted source has unsafe path")
        paths.extend(
            (Path(parent) / name).relative_to(root).as_posix() for name in files
        )
    inventory = []
    for path in sorted(paths):
        info, digest, _, _ = observe_file(root, root / path, prefix_limit=0)
        mode = "100755" if os.name != "nt" and info.st_mode & stat.S_IXUSR else "100644"
        inventory.append(
            SourcePayloadFile(
                path=path,
                mode=mode,
                size=info.st_size,
                sha256=digest,
            )
        )
    rows = tuple(inventory)
    return ReviewedSourceBinding(
        schema_id="brz2obsidian.reviewed-source-binding",
        schema_version=1,
        proposal_id=review.proposal.proposal_id,
        generation=review.proposal.generation,
        incoming_identity=review.facts.incoming_identity,
        target_source_version=review.facts.format_operation.target_source_version,
        source_anchor=anchor,
        files=rows,
        fingerprint=ReviewedSourceBinding.digest(rows),
    )
