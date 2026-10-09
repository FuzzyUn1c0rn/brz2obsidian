import base64
import json
from decimal import Decimal
from uuid import UUID
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_verified_coverage import add_attachment
from tests.support.notes import note_body


def rewrite(source, edit):
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    edit(parts)
    with ZipFile(source, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


def forget(parts, *numbers):
    records = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    for record in records:
        if record["Id"] in {identity(n) for n in numbers}:
            record["ForgottenDateTime"] = "2026-10-01T12:00:00.1234567+02:00"
    parts["thoughts.json"] = "\n".join(json.dumps(r) for r in records).encode()


def test_forgotten_owned_content_and_relationships_leave_no_destination_trace(tmp_path):
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private subject", 3: "Included"},
        [(1, 2, 1, 1, -1), (1, 3, 1, 1, -1)],
        notes={2: (b"secret owned prose", 4), 3: (b"included prose", 4)},
    )
    rewrite(source, lambda p: forget(p, 2))
    original = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean"
    assert inspected.counts.source_items == 2
    assert inspected.counts.source_relationships == 1
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "clean"
    output = b"\n".join(p.read_bytes() for p in vault.rglob("*") if p.is_file())
    for secret in (b"Private subject", b"secret owned prose", identity(2).encode()):
        assert secret not in output
        assert secret.decode() not in inspected.model_dump_json()
    assert b"included prose" in output
    assert source.read_bytes() == original


def test_excluded_link_phrase_disappears_and_unsafe_exact_copy_is_omitted(tmp_path):
    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    body = (
        f"α before\r\n[private **label**](brain://{compact}/private-title) after\rTail"
    )
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private"},
        notes={1: (body.encode(), 4)},
    )
    rewrite(source, lambda p: forget(p, 2))
    workflow = default_workflow()
    inspection = workflow.inspect(source)
    assert inspection.outcome == "clean"
    assert inspection.counts.source_references == 0
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "clean"
    assert note_body((vault / "Home — Home.md").read_bytes()).startswith(
        "# Home\n\nα before\r\n after\rTail".encode()
    )
    assert not any(p.name.endswith(".original") for p in vault.rglob("*"))
    output = b"\n".join(p.read_bytes() for p in vault.rglob("*") if p.is_file())
    for removed in (compact, "private-title", "private **label**", identity(2)):
        assert removed.encode() not in output
        assert removed not in inspection.model_dump_json()


def test_excluded_uri_in_inline_code_refuses_privately_without_publication(tmp_path):
    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    body = f"Safe prose `brain://{compact}/Private-title`"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private subject"},
        notes={1: (body.encode(), 4)},
    )
    rewrite(source, lambda p: forget(p, 2))
    original = source.read_bytes()
    destination = tmp_path / "vault"
    caller = tmp_path / "caller"
    caller.mkdir()
    (caller / "sentinel.bin").write_bytes(b"caller bytes")
    workflow = default_workflow()
    for result in (
        workflow.inspect(source),
        workflow.convert(source, destination),
        workflow.convert(source, caller),
    ):
        assert result.outcome == "refused"
        assert result.issues[0].code == "invalid_reference"
        for private in (compact, identity(2), "Private-title", "Private subject"):
            assert private not in result.model_dump_json()
    assert not destination.exists()
    assert {p.name: p.read_bytes() for p in caller.iterdir()} == {
        "sentinel.bin": b"caller bytes"
    }
    assert source.read_bytes() == original


def test_unicode_escaped_excluded_identity_in_note_refuses_privately(tmp_path):
    escaped = "".join(f"\\u{ord(char):04x}" for char in identity(2))
    body = '<!-- {"SourceId":"' + escaped + '","Label":"Private label"} -->'
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private subject"},
        notes={1: (body.encode(), 4)},
    )
    rewrite(source, lambda p: forget(p, 2))
    original = source.read_bytes()
    destination = tmp_path / "vault"
    workflow = default_workflow()
    for result in (workflow.inspect(source), workflow.convert(source, destination)):
        assert result.outcome == "refused"
        assert result.issues[0].code == "invalid_reference"
        for private in (escaped, identity(2), "Private label", "Private subject"):
            assert private not in result.model_dump_json()
    assert not destination.exists()
    assert source.read_bytes() == original


@pytest.mark.parametrize("spelling", ["uppercase_uuid", "mixed_uuid", "percent_uri"])
def test_equivalent_excluded_identity_spellings_refuse_without_rewriting_literals(
    tmp_path, spelling
):
    private = int(UUID("a1b2c3d4-e5f6-4a78-9abc-def012345678"))
    compact = "1MOyofbleEqavN7wEjRWeA"
    target = {
        "uppercase_uuid": "A1B2C3D4-E5F6-4A78-9ABC-DEF012345678",
        "mixed_uuid": "a1B2c3D4-e5F6-4a78-9aBc-dEf012345678",
        "percent_uri": "brain://%31%4D%4F%79%6F%66%62%6C%65%45%71%61%76%4E%37%77%45%6A%52%57%65%41/Private-title",
    }[spelling]
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", private: "Private subject"},
        notes={1: (f"Literal `{target}`".encode(), 4)},
    )
    rewrite(source, lambda p: forget(p, private))
    original = source.read_bytes()
    destination = tmp_path / "vault"
    workflow = default_workflow()
    for result in (workflow.inspect(source), workflow.convert(source, destination)):
        assert result.outcome == "refused"
        assert result.issues[0].code == "invalid_reference"
        for secret in (identity(private), compact, target, "Private subject"):
            assert secret not in result.model_dump_json()
    assert not destination.exists()
    assert source.read_bytes() == original


@pytest.mark.parametrize("context", ["inline", "fenced", "comment", "plain"])
@pytest.mark.parametrize(
    "token",
    [
        "a1b2c3d4-e5f6-4a78-9abc-def012345678",
        "1MOyofbleEqavN7wEjRWeA",
        "A1B2C3D4-E5F6-4A78-9ABC-DEF012345678",
        "%31%4D%4F%79%6F%66%62%6C%65%45%71%61%76%4E%37%77%45%6A%52%57%65%41",
        "%61%31%62%32%63%33%64%34%2D%65%35%66%36%2D%34%61%37%38%2D%39%61%62%63%2D%64%65%66%30%31%32%33%34%35%36%37%38",
        r"\u0061\u0031\u0062\u0032\u0063\u0033\u0064\u0034\u002d\u0065\u0035\u0066\u0036\u002d\u0034\u0061\u0037\u0038\u002d\u0039\u0061\u0062\u0063\u002d\u0064\u0065\u0066\u0030\u0031\u0032\u0033\u0034\u0035\u0036\u0037\u0038",
        r"\u0031\u004d\u004f\u0079\u006f\u0066\u0062\u006c\u0065\u0045\u0071\u0061\u0076\u004e\u0037\u0077\u0045\u006a\u0052\u0057\u0065\u0041",
    ],
    ids=[
        "canonical",
        "compact",
        "uppercase",
        "url-compact",
        "url-uuid",
        "unicode-uuid",
        "unicode-compact",
    ],
)
def test_active_removal_cannot_publish_residual_excluded_literals(
    tmp_path, capsys, context, token
):
    from brz2obsidian.cli import main

    private = int(UUID("a1b2c3d4-e5f6-4a78-9abc-def012345678"))
    uri = f"brain://{token}/Private-title"
    literal = {
        "inline": f"`{uri}`",
        "fenced": f"```text\r\n{uri}\r\n```",
        "comment": f"<!-- {uri} -->",
        "plain": uri,
    }[context]
    body = f"α\r\n[Private label](brain://1MOyofbleEqavN7wEjRWeA/Private-title)\r{literal}\nTail"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", private: "Private subject"},
        notes={1: (body.encode(), 4)},
    )
    rewrite(source, lambda p: forget(p, private))
    before = source.read_bytes()
    destination = tmp_path / "vault"
    caller = tmp_path / "caller"
    caller.mkdir()
    (caller / "sentinel.bin").write_bytes(b"caller bytes")
    workflow = default_workflow()
    for result in (
        workflow.inspect(source),
        workflow.convert(source, destination),
        workflow.convert(source, caller),
    ):
        assert result.outcome == "refused"
        assert result.issues[0].code == "invalid_reference"
        for private_text in (
            identity(private),
            token,
            "1MOyofbleEqavN7wEjRWeA",
            "Private-title",
            "Private label",
            "Private subject",
        ):
            assert private_text not in result.model_dump_json()
    for args in (
        ["inspect", str(source)],
        ["inspect", str(source), "--json"],
        ["convert", str(source), str(destination)],
        ["convert", str(source), str(caller), "--json"],
    ):
        assert main(args) == 1
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert token not in output and "Private" not in output
        assert (
            identity(private) not in output and "1MOyofbleEqavN7wEjRWeA" not in output
        )
    assert source.read_bytes() == before
    assert not destination.exists()
    assert {p.name: p.read_bytes() for p in caller.iterdir()} == {
        "sentinel.bin": b"caller bytes"
    }


def test_included_literal_only_body_and_exact_original_survive_scope_guard(tmp_path):
    private = int(UUID("a1b2c3d4-e5f6-4a78-9abc-def012345678"))
    included = private + 1
    body = (
        b"Private subject is also an included title\r\n"
        b"`brain://1MOyofbleEqavN7wEjRWeQ/included`\r"
        b"```text\nA1B2C3D4-E5F6-4A78-9ABC-DEF012345679\r\n```\n"
        b"<!-- brain://1MOyofbleEqavN7wEjRWeQ/included -->\r\n"
        b"brain://1MOyofbleEqavN7wEjRWeQ/included\n"
        b"Case-sensitive unrelated compact identity 1moyofbleeqavn7wejrwea\r\n"
        b"Encoded included %61%31b2c3d4-e5f6-4a78-9abc-def012345679\n"
        b'{"SourceId":"\\u00611b2c3d4-e5f6-4a78-9abc-def012345679"}\r'
    )
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", private: "Private subject", included: "Private subject"},
        notes={1: (body, 4)},
    )
    rewrite(source, lambda p: forget(p, private))
    before = source.read_bytes()
    workflow = default_workflow()
    assert workflow.inspect(source).outcome == "clean"
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "clean"
    assert note_body((vault / "Home — Home.md").read_bytes()) == (
        b"# Home\n\n"
        + body
        + b"\n## Categories\n\n[[Categories.md|Browse categories]]\n"
    )
    originals = [p.read_bytes() for p in vault.rglob("*.original")]
    assert originals == [body]
    assert source.read_bytes() == before


@pytest.mark.parametrize("encoding", ["nested", "serialized", "unicode_escaped"])
def test_uppercase_uuid_ownership_omits_entire_record_and_transitive_dependents(
    tmp_path, encoding
):
    private = int(UUID("a1b2c3d4-e5f6-4a78-9abc-def012345678"))
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home", private: "Private subject"}
    )
    safe = (
        '{"ThoughtId":"'
        + identity(1)
        + '","Precise":0.123456789012345678901234567890,"SafeNull":null}'
    )

    def edit(parts):
        forget(parts, private)
        owned = {"ThoughtId": "A1B2C3D4-E5F6-4A78-9ABC-DEF012345678"}
        if encoding == "serialized":
            owned = json.dumps(owned)
        elif encoding == "unicode_escaped":
            owned = (
                '{"ThoughtId":"'
                + "".join(
                    f"\\u{ord(char):04x}"
                    for char in "A1B2C3D4-E5F6-4A78-9ABC-DEF012345678"
                )
                + '"}'
            )
        for record in (
            {
                "Id": identity(8100),
                "Nested": [{"Envelope": owned}],
                "Value": "Private sibling",
            },
            {
                "Id": identity(8101),
                "ThoughtId": identity(8100),
                "Value": "Private dependent",
            },
            {"Id": identity(8102), "Nested": safe, "SafeNull": None},
        ):
            parts["settings.json"] += b"\n" + json.dumps(record).encode()

    rewrite(source, edit)
    before = source.read_bytes()
    workflow = default_workflow()
    assert workflow.inspect(source).outcome == "clean"
    vault = tmp_path / "vault"
    assert workflow.convert(source, vault).outcome == "clean"
    output = b"\n".join(p.read_bytes() for p in vault.rglob("*") if p.is_file())
    for secret in (
        identity(private),
        "A1B2C3D4-E5F6-4A78-9ABC-DEF012345678",
        identity(8100),
        identity(8101),
        "Private sibling",
        "Private dependent",
    ):
        assert secret.encode() not in output
    record = json.loads((vault / "migration-record.json").read_bytes())
    settings = next(
        e["records"] for e in record["original_evidence"] if e["key"] == "settings.json"
    )
    retained = next(r for r in settings if r["Id"] == identity(8102))
    assert retained == {"Id": identity(8102), "Nested": safe, "SafeNull": None}
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "encoded",
    [
        "A1B2C3D4-E5F6-4A78-9ABC-DEF012345678",
        "brain://%31%4D%4F%79%6F%66%62%6C%65%45%71%61%76%4E%37%77%45%6A%52%57%65%41/Private-title",
        r'{"Id":"\u00611b2c3d4-e5f6-4a78-9abc-def012345678"}',
    ],
    ids=["uppercase", "url-compact", "serialized-unicode"],
)
def test_encoded_omitted_identity_cannot_reappear_in_retained_opaque_evidence(
    tmp_path, encoded
):
    private = int(UUID("a1b2c3d4-e5f6-4a78-9abc-def012345678"))
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home", private: "Private subject"}
    )

    def edit(parts):
        forget(parts, private)
        parts["brainusers.json"] = json.dumps(
            {"Id": identity(8102), "OpaquePrivate": encoded, "SafeNull": None}
        ).encode()

    rewrite(source, edit)
    original = source.read_bytes()
    workflow = default_workflow()
    assert workflow.inspect(source).outcome == "clean"
    vault = tmp_path / "vault"
    assert workflow.convert(source, vault).outcome == "clean"
    record = json.loads((vault / "migration-record.json").read_bytes())
    retained = next(
        e["records"]
        for e in record["original_evidence"]
        if e["key"] == "brainusers.json"
    )
    assert retained == [{"Id": identity(8102), "SafeNull": None}]
    assert source.read_bytes() == original


def test_associated_record_identity_in_included_body_refuses_privately(tmp_path):
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private subject"},
        notes={1: (b"<!-- 00000000-0000-0000-0000-000000001fa4 -->", 4)},
    )

    def edit(parts):
        forget(parts, 2)
        parts["settings.json"] += (
            b"\n"
            + json.dumps(
                {
                    "Id": identity(8100),
                    "ThoughtId": identity(2),
                    "Value": "Private sibling",
                }
            ).encode()
        )

    rewrite(source, edit)
    original = source.read_bytes()
    workflow = default_workflow()
    vault = tmp_path / "vault"
    for result in (workflow.inspect(source), workflow.convert(source, vault)):
        assert (
            result.outcome == "refused" and result.issues[0].code == "invalid_reference"
        )
        for private in (
            identity(2),
            identity(8100),
            "Private sibling",
            "Private subject",
        ):
            assert private not in result.model_dump_json()
    assert not vault.exists() and source.read_bytes() == original


@pytest.mark.parametrize("collection", ["settings.json", "brainusers.json"])
@pytest.mark.parametrize(
    "encoding", ["nested", "serialized", "unicode_escaped", "duplicate_keys"]
)
def test_nested_excluded_ownership_omits_the_associated_record_and_its_transitive_dependents(
    tmp_path, encoding, collection
):
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private"},
        notes={1: (b"safe prose", 4)},
    )
    safe_serialized = (
        '{"SourceId":"'
        + identity(1)
        + '","Precise":0.123456789012345678901234567890,"SafeNull":null}'
    )

    def edit(parts):
        forget(parts, 2)
        owned = {"SourceId": identity(2), "Value": "INNER_EXCLUDED_CONTENT"}
        if encoding == "serialized":
            owned = json.dumps(owned)
        elif encoding == "unicode_escaped":
            escaped = "".join(f"\\u{ord(char):04x}" for char in identity(2))
            owned = '{"SourceId":"' + escaped + '","Value":"INNER_EXCLUDED_CONTENT"}'
        elif encoding == "duplicate_keys":
            owned = (
                '{"SourceId":"'
                + identity(2)
                + '","SourceId":"'
                + identity(1)
                + '","Value":"INNER_EXCLUDED_CONTENT"}'
            )
        for record in (
            {
                "Id": identity(8100),
                "Nested": [{"Envelope": owned}],
                "Value": "OUTER_EXCLUDED_CONTENT",
            },
            {
                "Id": identity(8101),
                "Nested": {"AttachmentId": identity(8100)},
                "Value": "TRANSITIVE_EXCLUDED_CONTENT",
            },
            {
                "Id": identity(8102),
                "Nested": safe_serialized,
                "Value": "safe retained string",
            },
        ):
            parts[collection] += b"\n" + json.dumps(record).encode()

    rewrite(source, edit)
    original = source.read_bytes()
    workflow = default_workflow()
    assert workflow.inspect(source).outcome == "clean"
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "clean"
    output = b"\n".join(p.read_bytes() for p in vault.rglob("*") if p.is_file())
    for secret in (
        identity(2),
        identity(8100),
        identity(8101),
        "INNER_EXCLUDED_CONTENT",
        "OUTER_EXCLUDED_CONTENT",
        "TRANSITIVE_EXCLUDED_CONTENT",
    ):
        assert secret.encode() not in output
    record = json.loads((vault / "migration-record.json").read_bytes())
    settings = next(
        e["records"] for e in record["original_evidence"] if e["key"] == collection
    )
    safe = next(r for r in settings if r["Id"] == identity(8102))
    assert safe["Nested"] == safe_serialized and safe["Value"] == "safe retained string"
    assert source.read_bytes() == original


def test_current_public_envelopes_reserve_empty_gap_and_presentation_facts(tmp_path):
    source = graph_archive(tmp_path / "source.brz", {1: "Home"})
    result = default_workflow().inspect(source)
    assert result.schema_version == 4
    assert result.converter_version == "0.3.0"
    assert result.profile_version == result.source_identity.module_version == "4"
    assert result.inspection.source_gaps == ()
    assert result.inspection.generated_presentations == ()
    vault = tmp_path / "vault"
    converted = default_workflow().convert(source, vault)
    assert converted.outcome == "clean"
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert record["schema_version"] == 4 and record["renderer_version"] == "4"
    assert record["source_gaps"] == record["generated_presentations"] == []


def test_excluded_thought_embed_is_removed_without_rewriting_code_or_other_text(
    tmp_path,
):
    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    body = f"before\r\n![private](brain://{compact}/private)\rafter\n`![literal](https://example.invalid/x)`"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private"},
        notes={1: (body.encode(), 4)},
    )
    rewrite(source, lambda p: forget(p, 2))
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean"
    assert note_body((vault / "Home — Home.md").read_bytes()).startswith(
        b"# Home\n\nbefore\r\n\rafter\n`![literal](https://example.invalid/x)`"
    )


@pytest.mark.parametrize("marker", ["2020-01-01", "2026-10-01T12:00:00Z"])
def test_valid_populated_scope_marker_excludes_the_designated_home_without_disclosure(
    tmp_path, marker
):
    source = graph_archive(tmp_path / "source.brz", {1: "Private home"})

    def edit(parts):
        record = json.loads(parts["thoughts.json"])
        record["ForgottenDateTime"] = marker
        parts["thoughts.json"] = json.dumps(record).encode()

    rewrite(source, edit)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "refused" and result.issues[0].code == "invalid_entry"
    assert (
        identity(1) not in result.model_dump_json()
        and "Private home" not in result.model_dump_json()
    )
    assert not (tmp_path / "vault").exists()


def test_included_controls_survive_provider_and_owned_asset_exclusion_with_safe_raw_evidence(
    tmp_path,
):
    source = graph_archive(
        tmp_path / "source.brz",
        {
            1: "Home",
            2: "Same title",
            3: "Same title",
            4: "Private provider",
            5: "Member",
            6: "Private tag",
        },
        [(4, 5, 1, 2, -1), (6, 5, 1, 5, -1), (2, 3, 1, 1, -1)],
        kinds={4: 2, 6: 4},
        notes={
            2: (b"private prose", 4),
            3: (b"included prose", 4),
            5: (b"member prose", 4),
        },
    )

    def edit(parts):
        forget(parts, 2, 4, 6)
        records = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
        member = next(r for r in records if r["Id"] == identity(5))
        member["TypeId"] = identity(4)
        member["SafeNull"] = None
        member["Unsafe_" + identity(2)] = "associated hidden metadata"
        member["Nested"] = {identity(2): "associated hidden metadata"}
        parts["thoughts.json"] = "\n".join(json.dumps(r) for r in records).encode()
        for owner, asset, kind, name in (
            (2, 3002, 12, "same.png"),
            (3, 3003, 12, "same.png"),
            (4, 3004, 5, "icon.png"),
        ):
            add_attachment(
                parts,
                identity(asset),
                kind,
                name,
                b"same pixels",
                owner=identity(owner),
            )
        add_attachment(
            parts,
            identity(3005),
            3,
            "https://private.invalid/resource",
            owner=identity(2),
            state=None,
        )
        parts["modificationlogs.json"] = json.dumps(
            {"Id": identity(7000), "Content": "unscopable private prose"}
        ).encode()
        parts["tombstones.json"] = json.dumps(
            {"Id": identity(7001), "SourceId": identity(2)}
        ).encode()
        parts["settings.json"] += (
            b"\n"
            + json.dumps(
                {
                    "Id": identity(7002),
                    "SourceId": identity(2),
                    "Value": "private associated settings content",
                }
            ).encode()
        )

    rewrite(source, edit)
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean"
    assert inspected.counts.source_items == 3
    assert inspected.counts.source_definitions == inspected.counts.source_tags == 0
    assert (
        inspected.counts.classification_assignments
        == inspected.counts.source_relationships
        == 0
    )
    targets = {t.item_key: t for t in inspected.inspection.item_targets}
    assert targets[identity(3)].relative_path == "Notes/Same title.md"
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "clean"
    output = b"\n".join(p.read_bytes() for p in vault.rglob("*") if p.is_file())
    for n in (2, 4, 6, 3002, 3004, 3005, 7000, 7001, 7002):
        assert identity(n).encode() not in output
    for secret in (b"private prose", b"private.invalid", b"associated hidden metadata"):
        assert secret not in output
    assert b"included prose" in output and b"same pixels" in output
    assert not (vault / "Categories/Private provider.md").exists()
    record = json.loads((vault / "migration-record.json").read_bytes())
    raw_thoughts = next(
        e["records"] for e in record["original_evidence"] if e["key"] == "thoughts.json"
    )
    retained = next(r for r in raw_thoughts if r["Id"] == identity(5))
    assert retained["SafeNull"] is None and "MissingField" not in retained
    assert "TypeId" not in retained
    assert [
        e["records"]
        for e in record["original_evidence"]
        if e["key"] in {"modificationlogs.json", "tombstones.json"}
    ] == [[], []]


def test_scoped_safe_raw_values_keep_exact_precision_omission_and_null(tmp_path):
    source = graph_archive(tmp_path / "source.brz", {1: "Home", 2: "Private"})

    def edit(parts):
        forget(parts, 2)
        raw = parts["thoughts.json"].decode()
        raw = raw.replace(
            '"Name": "Home"',
            '"Name": "Home", "Precise": 0.123456789012345678901234567890, "SafeNull": null',
        )
        parts["thoughts.json"] = raw.encode()

    rewrite(source, edit)
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "clean"
    record = json.loads(
        (vault / "migration-record.json").read_bytes(), parse_float=Decimal
    )
    raw = next(
        e["records"][0]
        for e in record["original_evidence"]
        if e["key"] == "thoughts.json"
    )
    assert raw["Precise"] == Decimal("0.123456789012345678901234567890")
    assert raw["SafeNull"] is None and "Unspecified" not in raw


@pytest.mark.parametrize("case", ["marker", "owner", "path", "unknown", "parse"])
def test_scope_and_unknown_reference_failures_are_private_and_leave_caller_files_unchanged(
    tmp_path, case, capsys
):
    from brz2obsidian.cli import main

    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private subject"},
        notes={2: (b"private prose", 4)},
    )

    def edit(parts):
        forget(parts, 2)
        if case == "marker":
            raw = (
                parts["thoughts.json"]
                .decode()
                .replace("2026-10-01T12:00:00.1234567+02:00", "Private invalid marker")
            )
            parts["thoughts.json"] = raw.encode()
        elif case in {"owner", "path"}:
            raw = json.loads(parts["attachments.json"])
            raw["SourceId" if case == "owner" else "Location"] = (
                identity(99) if case == "owner" else "../Private path"
            )
            parts["attachments.json"] = json.dumps(raw).encode()
        elif case == "unknown":
            parts["links.json"] = json.dumps(
                {
                    "Id": identity(5000),
                    "BrainId": "11111111-1111-4111-8111-111111111111",
                    "ThoughtIdA": identity(1),
                    "ThoughtIdB": identity(99),
                    "Kind": 1,
                    "Relation": 1,
                    "Meaning": 1,
                    "Direction": -1,
                }
            ).encode()
        else:
            parts["thoughts.json"] = (
                b'{"Private parse payload": 1, "Private parse payload": 2}'
            )

    rewrite(source, edit)
    before = source.read_bytes()
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "caller.bin").write_bytes(b"caller bytes")
    for argv in (
        ["inspect", str(source), "--json"],
        ["convert", str(source), str(vault), "--json"],
        ["inspect", str(source)],
    ):
        assert main(argv) == 1
        output = capsys.readouterr().out
        for private in (
            identity(2),
            "Private subject",
            "Private invalid marker",
            "Private path",
            "Private parse payload",
            "private prose",
        ):
            assert private not in output
    assert source.read_bytes() == before
    assert {p.name: p.read_bytes() for p in vault.iterdir()} == {
        "caller.bin": b"caller bytes"
    }


@pytest.mark.parametrize(
    "destination",
    (
        "brain://{compact}=/Private-title",
        "brain://{compact}==/Private-title",
        "brain://{compact}==/Private-title?query=1",
        "brain://{compact}==",
        "brain://{compact}==/Private-title#fragment",
    ),
    ids=("one-padding", "two-padding", "query", "no-path", "fragment"),
)
def test_padded_excluded_reference_refuses_privately_without_publication(
    tmp_path, destination
):
    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    target = destination.format(compact=compact)
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private"},
        notes={1: (f"before [Private label]({target}) after".encode(), 4)},
    )
    rewrite(source, lambda p: forget(p, 2))
    original = source.read_bytes()
    vault = tmp_path / "vault"
    workflow = default_workflow()
    for result in (workflow.inspect(source), workflow.convert(source, vault)):
        assert result.outcome == "refused"
        assert result.issues[0].code == "invalid_reference"
        assert result.receipt is None
        for secret in (compact, target, "Private", identity(2)):
            assert secret not in result.model_dump_json()
    assert not vault.exists()
    assert source.read_bytes() == original


def test_malformed_reference_to_excluded_subject_refuses_without_echoing_its_target(
    tmp_path,
):
    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private"},
        notes={
            1: (f"[Private label](brain://{compact}/Private-title?query=1)".encode(), 4)
        },
    )
    rewrite(source, lambda p: forget(p, 2))
    result = default_workflow().inspect(source)
    assert result.outcome == "refused" and result.issues[0].code == "invalid_reference"
    assert (
        compact not in result.model_dump_json()
        and "Private" not in result.model_dump_json()
    )


def test_malformed_authority_refusals_do_not_echo_excluded_uri_or_label_and_preserve_caller_files(
    tmp_path, capsys
):
    from brz2obsidian.cli import main

    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private"},
        notes={
            1: (f"[Private label](brain://{compact}extra/Private-title)".encode(), 4)
        },
    )
    rewrite(source, lambda p: forget(p, 2))
    original = source.read_bytes()
    caller = tmp_path / "caller"
    caller.mkdir()
    (caller / "sentinel.bin").write_bytes(b"caller bytes")
    workflow = default_workflow()
    for result in (workflow.inspect(source), workflow.convert(source, caller)):
        assert (
            result.outcome == "refused" and result.issues[0].code == "invalid_reference"
        )
        for private in (compact, "Private-title", "Private label", identity(2)):
            assert private not in result.model_dump_json()
    for args in (
        ["inspect", str(source)],
        ["inspect", str(source), "--json"],
        ["convert", str(source), str(caller), "--json"],
    ):
        assert main(args) == 1
        output = capsys.readouterr().out
        assert compact not in output and "Private" not in output
    assert source.read_bytes() == original
    assert {p.name: p.read_bytes() for p in caller.iterdir()} == {
        "sentinel.bin": b"caller bytes"
    }


def test_image_wrapped_excluded_link_removes_the_whole_phrase_and_keeps_the_included_image(
    tmp_path,
):
    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private"},
        notes={
            1: (
                f"before [![owned](.data/md-images/safe.png)](brain://{compact}/private) after".encode(),
                4,
            )
        },
    )

    def edit(parts):
        forget(parts, 2)
        add_attachment(
            parts,
            identity(3001),
            12,
            "safe.png",
            b"included image pixels",
            owner=identity(1),
        )

    rewrite(source, edit)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean"
    assert note_body((vault / "Home — Home.md").read_bytes()).startswith(
        b"# Home\n\nbefore  after"
    )
    assert any(
        p.read_bytes() == b"included image pixels"
        for p in vault.rglob("*")
        if p.is_file()
    )
    assert not any(p.name.endswith(".original") for p in vault.rglob("*"))


def test_required_collection_metadata_with_excluded_ownership_refuses_privately(
    tmp_path,
):
    source = graph_archive(tmp_path / "source.brz", {1: "Home", 2: "Private"})

    def edit(parts):
        forget(parts, 2)
        meta = json.loads(parts["meta.json"])
        meta["Nested"] = {"SourceId": identity(2)}
        meta["Value"] = "PRIVATE_METADATA_CONTENT"
        parts["meta.json"] = json.dumps(meta).encode()

    rewrite(source, edit)
    original = source.read_bytes()
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "refused" and result.issues[0].code == "invalid_source"
    assert "PRIVATE_METADATA_CONTENT" not in result.model_dump_json()
    assert identity(2) not in result.model_dump_json()
    assert source.read_bytes() == original and not vault.exists()
