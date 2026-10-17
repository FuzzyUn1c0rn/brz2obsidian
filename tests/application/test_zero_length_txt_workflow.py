"""Reviewed zero-length declarations through real inspect/convert boundaries."""

from tests.application.test_verified_coverage import (
    PDF,
    TXT,
    add_attachment,
    source_parts,
)

PDF_BYTES = b"%PDF-1.4 zero-length rule control\r\n%%EOF\r\n"
RULE = "thebrain-format5/zero-length-absent-txt/v1"
TXT_NAME = PDF + ".txt"
OTHER = "88888888-8888-4888-8888-888888888888"


def zero_parts(tmp_path):
    parts = source_parts(tmp_path)
    add_attachment(parts, PDF, 1, "manual.pdf", PDF_BYTES)
    add_attachment(parts, TXT, 15, TXT_NAME, declared=0, state=2)
    return parts
