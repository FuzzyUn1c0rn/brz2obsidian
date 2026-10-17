"""Reviewed HTML exclusions and non-tag prose cross actual ZIP/CLI boundaries."""

import json

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from tests.application.test_literal_angles_workflow import literal_archive
from tests.application.test_resources_workflow import HOME, resource_archive
from tests.local_acceptance.checker import check_run_result, check_vault

# Independently extracted/reviewed primary inventory, 2026-10-10.
# This expected list is not imported from either implementation registry.
CURRENT_AND_FOREIGN = [
    "a",
    "abbr",
    "address",
    "area",
    "article",
    "aside",
    "audio",
    "b",
    "base",
    "bdi",
    "bdo",
    "blockquote",
    "body",
    "br",
    "button",
    "canvas",
    "caption",
    "cite",
    "code",
    "col",
    "colgroup",
    "data",
    "datalist",
    "dd",
    "del",
    "details",
    "dfn",
    "dialog",
    "div",
    "dl",
    "dt",
    "em",
    "embed",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "head",
    "header",
    "hgroup",
    "hr",
    "html",
    "i",
    "iframe",
    "img",
    "input",
    "ins",
    "kbd",
    "label",
    "legend",
    "li",
    "link",
    "main",
    "map",
    "mark",
    "math",
    "menu",
    "meta",
    "meter",
    "nav",
    "noscript",
    "object",
    "ol",
    "optgroup",
    "option",
    "output",
    "p",
    "picture",
    "pre",
    "progress",
    "q",
    "rp",
    "rt",
    "ruby",
    "s",
    "samp",
    "script",
    "search",
    "section",
    "select",
    "selectedcontent",
    "slot",
    "small",
    "source",
    "span",
    "strong",
    "style",
    "sub",
    "summary",
    "sup",
    "svg",
    "table",
    "tbody",
    "td",
    "template",
    "textarea",
    "tfoot",
    "th",
    "thead",
    "time",
    "title",
    "tr",
    "track",
    "u",
    "ul",
    "var",
    "video",
    "wbr",
]
OBSOLETE = [
    "acronym",
    "applet",
    "basefont",
    "bgsound",
    "big",
    "blink",
    "center",
    "dir",
    "font",
    "frame",
    "frameset",
    "isindex",
    "keygen",
    "listing",
    "marquee",
    "menuitem",
    "multicol",
    "nextid",
    "nobr",
    "noembed",
    "noframes",
    "param",
    "plaintext",
    "rb",
    "rtc",
    "spacer",
    "strike",
    "tt",
    "xmp",
]
HISTORICAL = ["content", "shadow"]
EXPERIMENTAL_CONSERVATIVE = ["portal"]
LEGACY_ALIAS = ["image"]

RECOGNIZED = (
    CURRENT_AND_FOREIGN
    + OBSOLETE
    + HISTORICAL
    + EXPERIMENTAL_CONSERVATIVE
    + LEGACY_ALIAS
)


@pytest.mark.parametrize("name", [name for name in RECOGNIZED if name != "br"])
@pytest.mark.parametrize("uppercase", [False, True])
def test_recognized_historical_and_experimental_names_refuse(
    tmp_path, capsys, name, uppercase
):
    spelling = name.upper() if uppercase else name
    source = literal_archive(tmp_path / "source.brz", f"Use <{spelling}>".encode())
    before = source.read_bytes()
    operation = default_workflow()
    for result in (
        operation.inspect(source),
        operation.convert(source, tmp_path / "library-vault"),
    ):
        assert result.outcome == "refused", result.model_dump_json()
        assert result.receipt is None
        issue = result.issues[0]
        assert issue.code == "unsupported_feature"
        assert HOME in issue.affected
        assert "33333333-3333-4333-8333-333333333333" in issue.affected
        assert "attachments.json:0" in issue.evidence
        assert "Markdown" in issue.guidance and "Home" not in issue.guidance
    for arguments in (
        ["inspect", str(source), "--json"],
        ["convert", str(source), str(tmp_path / "cli-vault"), "--json"],
    ):
        assert main(arguments) == 1
        cli = json.loads(capsys.readouterr().out)
        assert cli["outcome"] == "refused" and cli["receipt"] is None
        assert cli["issues"][0]["code"] == "unsupported_feature"
    assert not (tmp_path / "library-vault").exists()
    assert not (tmp_path / "cli-vault").exists()
    assert source.read_bytes() == before


@pytest.mark.parametrize("name", [None, ""])
def test_external_missing_or_empty_name_has_windows_display_and_resource_fallback(
    tmp_path, capsys, name
):
    external = {"Type": 2, "Location": r"C:\Unavailable\lesson.pdf"}
    if name is not None:
        external["Name"] = name
    source = resource_archive(tmp_path / "source.brz", [(external, None)])
    before = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "clean"
    asset = next(a for a in inspected.inspection.assets if a.availability == "external")
    assert asset.display_name == "lesson.pdf" and asset.role == "file"
    assert asset.external_uri == "file:///C:/Unavailable/lesson.pdf"
    assert asset.actual_sha256 is None and asset.actual_length is None
    assert main(["inspect", str(source), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["receipt"] is None
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert "- [lesson.pdf](<file:///C:/Unavailable/lesson.pdf>)" in (
        vault / "Home — Entry thought.md"
    ).read_text(encoding="utf-8")
    assert not list(vault.rglob("*.pdf"))
    check_run_result(result, vault, check_vault(source, vault))
    assert source.read_bytes() == before


def _distinct_html_body_cases():
    bodies = [
        r'Text <Unknown x="a\_b">',
        r"Text <Unknown x=path\_part>",
        'Text <Unknown x="`<Inner>`">',
        'Text <Unknown x="<Inner>">',
        "Text <Unknown x='a\\>b'>",
        "Text <Unknown\n x='a'>",
        "Text </Unknown>",
        "Text <Unknown>pair</Unknown>",
        "Text <!A>",
        "Text <!a>",
        "Text <!AB>",
        "Text <!a0/punctuation>",
        "Text <!a\nmore>",
        "Text <?xml?>",
        "Text <!-- protected --> <!a>",
        "Text `<!Hidden>` <!a>",
        "<!A>",
        "<!a>",
        "<!A",
    ]
    cases = []
    seen = set()
    for body in bodies:
        for newline in ("\n", "\r", "\r\n"):
            payload = body.replace("\n", newline).encode()
            if payload in seen:
                continue
            seen.add(payload)
            # Existing decorator order gives newline-body node IDs.
            cases.append(pytest.param(body, newline, id=f"{newline}-{body}"))
    return cases


@pytest.mark.parametrize("body,newline", _distinct_html_body_cases())
def test_genuine_html_attributes_and_closers_refuse_without_inner_edits(
    tmp_path, capsys, body, newline
):
    from tests.local_acceptance.text import literal_edits

    body = body.replace("\n", newline)
    source = literal_archive(tmp_path / "source.brz", body.encode())
    before = source.read_bytes()
    for result in (
        default_workflow().inspect(source),
        default_workflow().convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused" and result.receipt is None
        assert result.issues[0].code == "unsupported_feature"
    assert main(["inspect", str(source), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["receipt"] is None
    assert main(["convert", str(source), str(tmp_path / "cli-vault"), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["receipt"] is None
    with pytest.raises(AssertionError, match="active HTML"):
        literal_edits(body)
    assert not (tmp_path / "vault").exists() and not (tmp_path / "cli-vault").exists()
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "body,expected",
    [
        (r"`<content>` \<shadow> <br> <Value>", r"`<content>` \<shadow> <br> \<Value>"),
        ("<!-- <portal> -->\n<Value>", "<!-- <portal> -->\n\\<Value>"),
        ("~~~\n<content>\n~~~\n<Value>", "~~~\n<content>\n~~~\n\\<Value>"),
        ("```\n<shadow>\n```\n<Value>", "```\n<shadow>\n```\n\\<Value>"),
        ("Text <Type-2>", "Text \\<Type-2>"),
    ],
)
def test_recognized_protected_names_and_supported_br_keep_authored_bytes(
    tmp_path, capsys, body, expected
):
    from tests.support.notes import note_body

    source = literal_archive(tmp_path / "source.brz", body.encode())
    before = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "clean" and inspected.counts.text_adaptations == 1
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert (
        note_body((vault / "Home — Entry thought.md").read_bytes())
        == (
            "# Entry thought\n\n"
            + expected
            + "\n\n## Categories\n\n[[Categories.md|Browse categories]]\n"
        ).encode()
    )
    check_run_result(result, vault, check_vault(source, vault))
    assert source.read_bytes() == before


def test_external_fallback_unicode_and_duplicate_basenames_remain_distinct(
    tmp_path, capsys
):
    source = resource_archive(
        tmp_path / "source.brz",
        [
            ({"Type": 2, "Location": r"C:\Unavailable\Résumé #1 %.pdf"}, None),
            (
                {"Type": 2, "Name": "", "Location": r"D:\Elsewhere\Résumé #1 %.pdf"},
                None,
            ),
            (
                {
                    "Type": 2,
                    "Name": "Authored_名",
                    "Location": r"Z:\Offline\actual.pdf",
                },
                None,
            ),
        ],
    )
    before = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "clean"
    assets = [a for a in inspected.inspection.assets if a.availability == "external"]
    assert [a.display_name for a in assets] == [
        "Résumé #1 %.pdf",
        "Résumé #1 %.pdf",
        "Authored_名",
    ]
    assert len({a.asset_id for a in assets}) == 3
    assert [a.external_uri for a in assets] == [
        "file:///C:/Unavailable/R%C3%A9sum%C3%A9%20%231%20%25.pdf",
        "file:///D:/Elsewhere/R%C3%A9sum%C3%A9%20%231%20%25.pdf",
        "file:///Z:/Offline/actual.pdf",
    ]
    vault = tmp_path / "vault"
    assert main(["inspect", str(source), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["present_assets"] == 1
    assert main(["convert", str(source), str(vault), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    text = (vault / "Home — Entry thought.md").read_text(encoding="utf-8")
    assert (
        "- [Résumé #1 %.pdf](<file:///C:/Unavailable/R%C3%A9sum%C3%A9%20%231%20%25.pdf>)"
        in text
    )
    assert (
        "- [Résumé #1 %.pdf](<file:///D:/Elsewhere/R%C3%A9sum%C3%A9%20%231%20%25.pdf>)"
        in text
    )
    assert "- [Authored\\_名](<file:///Z:/Offline/actual.pdf>)" in text
    assert not list(vault.rglob("*.pdf"))
    check_run_result(result, vault, check_vault(source, vault))
    assert source.read_bytes() == before
