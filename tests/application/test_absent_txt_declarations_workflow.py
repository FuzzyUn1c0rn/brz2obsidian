"""Repeated absent TXT declarations retain separate facts at public boundaries."""

from tests.application.test_verified_coverage import (
    PDF,
    TXT,
    add_attachment,
    source_parts,
)

THIRD = "88888888-8888-4888-8888-888888888888"
INTACT_PDF = "99999999-9999-4999-8999-999999999999"
PDF_BYTES = b"%PDF-1.4 preserved same-owner resource"
RULE = "thebrain-format5/absent-txt/v1"


def repeated_parts(tmp_path, count=2):
    parts = source_parts(tmp_path)
    for key, length in zip((TXT, PDF, THIRD)[:count], (17, 29, 41)):
        add_attachment(parts, key, 15, "shared.txt", declared=length, state=2)
    add_attachment(parts, INTACT_PDF, 1, "manual.pdf", PDF_BYTES)
    return parts
