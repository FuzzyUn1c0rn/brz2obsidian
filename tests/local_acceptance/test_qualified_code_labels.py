"""Code ownership controls through public source and independent audit seams."""

from contextlib import nullcontext
from uuid import UUID

import pytest

from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain import BrzSourceModule
from tests.application.test_forgotten_workflow import forget, rewrite
from tests.application.test_graph_workflow import graph_archive
from tests.local_acceptance.api_scope import scope_note
from tests.local_acceptance.checker import source_references
from tests.local_acceptance.test_qualified_label_audit import CURRENT, FOREIGN, TOKEN
from tests.support.local_api import ALONE, BRAIN, HOME


@pytest.mark.parametrize(
    "opening,closing,refused",
    [
        ("`", "`", False),
        (r"\`", "`", True),
        ("`", "``", True),
        ("``", "``", False),
        (r"\\`", "`", False),
        ("`", r"\`", False),
        (r"\\\`", "`", True),
        (r"\\\\`", "`", False),
        ("``", "`", True),
        (r"\``", "`", False),
        (r"\``", "``", True),
        ("``a`", "``", False),
    ],
)
def test_public_source_and_both_oracles_agree_on_code_owned_private_label(
    tmp_path, opening, closing, refused
):
    label = opening + "&#X4D;" + TOKEN[1:] + closing
    phrase = f"[{label}]({FOREIGN})"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", int(UUID(ALONE)): "Private"},
        notes={1: (phrase.encode(), 4)},
    )
    rewrite(source, lambda parts: forget(parts, int(UUID(ALONE))))
    with (
        pytest.raises(MigrationRefused) if refused else nullcontext(),
        BrzSourceModule().open(source) as session,
    ):
        document = session.snapshot.documents[0]
        assert document.text == phrase and document.references == ()
        with session.open_payload(document.original_asset_id) as stream:
            assert stream.read() == phrase.encode()
    outcomes = {}
    for name, call in (
        (
            "brz",
            lambda: source_references(phrase, HOME, {}, {ALONE}, qualified_brain=BRAIN),
        ),
        ("api", lambda: scope_note(phrase, {ALONE}, qualified_brain=BRAIN)),
    ):
        try:
            call()
        except AssertionError as error:
            assert "excluded" in str(error)
            outcomes[name] = True
        else:
            outcomes[name] = False
    assert outcomes == {"brz": refused, "api": refused}


@pytest.mark.parametrize(
    "authored,visible",
    [
        (r"\`A&copy;`", "`A©`"),
        ("`A&copy;``", "`A©``"),
        ("`A&copy;`", "A&copy;"),
        (r"\\`A&copy;`", "\\A&copy;"),
        (r"\\\`A&copy;`", "\\`A\u00a9`"),
        (r"\\\\`A&copy;`", "\\\\A&copy;"),
        ("``A&copy;`", "``A\u00a9`"),
        ("``A&copy;``", "A&copy;"),
        ("``a`A&copy;``", "a`A&copy;"),
        (r"\``A&copy;`", "`A&copy;"),
        (r"\``A&copy;``", "``A\u00a9``"),
        (r"`A&copy;\`", "A&copy;\\"),
        (r"`A\&copy;`", "A\\&copy;"),
        (r"\`A&copy;\`", "`A\u00a9`"),
        ("` A&copy; `", "A&copy;"),
        ("`  `", "  "),
        ("`A\n&copy;`", "A &copy;"),
        ("`A`&copy;`B`", "A\u00a9B"),
    ],
)
def test_public_reference_and_independent_label_follow_code_delimiter_ownership(
    tmp_path, authored, visible
):
    phrase = f"[{authored}]({CURRENT})"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", int(UUID(ALONE)): "Target"},
        notes={1: (phrase.encode(), 4)},
    )
    with BrzSourceModule().open(source) as session:
        reference = session.snapshot.documents[0].references[0]
        assert (
            reference.display_text == visible and reference.expected_original == phrase
        )
    references = source_references(phrase, HOME, {}, qualified_brain=BRAIN)
    assert len(references) == 1 and references[0]["label"] == visible
