"""Independent byte/pixel/native qualification, distinct from product admission."""

import hashlib
import json
import struct
import time
from pathlib import Path

import pytest

from tests.local_acceptance.api_icon_inputs import (
    FIXTURES,
    LITERAL_BGRA,
    LITERAL_BMP_RGBA,
    LITERAL_MASK,
    LITERAL_RGBA,
    bmp,
    bmp_mutations,
    ico,
    ico_mutations,
    legacy_zero_alpha_control,
    patch,
    positive_cases,
    profile5_capture_vector,
    public_facts,
)
from tests.local_acceptance.api_image_proofs import ico_proof


def test_literal_source_bytes_and_frozen_preencoding_facts():
    facts = json.loads((FIXTURES / "source-facts.json").read_bytes())
    assert LITERAL_RGBA.hex() == "f00a14ff075009800b1621000102c840"
    assert LITERAL_BGRA.hex() == "21160b00c8020140140af0ff09500780"
    literal = ico()
    assert literal["raw"][62:78] == LITERAL_BGRA
    assert literal["raw"][78:86] == LITERAL_MASK
    assert bmp(2, 2)["frames"][0]["rgba"] == LITERAL_BMP_RGBA
    bitmap = bmp()
    assert len(bitmap["raw"]) == 78
    assert (
        bitmap["frames"][0]["offset"],
        bitmap["frames"][0]["body_length"],
        bitmap["frames"][0]["pixel_offset"],
        bitmap["frames"][0]["rgba_length"],
    ) == (14, 64, 54, 24)
    assert {name: public_facts(value) for name, value in positive_cases()} == facts[
        "cases"
    ]
    assert sum(case["length"] for case in facts["cases"].values()) < 128 * 1024


def test_new_icon_proofs_match_preencoding_pixels_and_original_extents(tmp_path):
    from tests.local_acceptance.api_image_proofs import icon_proof

    evidence = []
    for name, fixture in positive_cases():
        proof = icon_proof(fixture["raw"])
        assert proof["source_sha256"] == fixture["sha256"], name
        assert proof["status"] == "complete-independent-icon-pixels", name
        assert len(proof["frames"]) == len(fixture["frames"]), name
        for expected, actual in zip(fixture["frames"], proof["frames"], strict=True):
            for field in (
                "index",
                "width",
                "height",
                "offset",
                "body_length",
                "body_sha256",
                "rgba_sha256",
                "pixel_offset",
                "dib_header",
            ):
                assert actual[field] == expected[field], (name, field)
            assert actual["comparison"]["canonical_equal"], name
            assert actual["offset"] + actual["body_length"] <= fixture["length"]
            if "mask_sha256" in expected:
                assert actual["mask_sha256"] == expected["mask_sha256"]
            assert actual["decoded_bytes"] == expected["rgba_length"]
            assert actual["comparison"]["alpha_mismatches"] == 0
            assert actual["comparison"]["visible_rgb_mismatches"] == 0
        print(
            json.dumps(
                {
                    "case": name,
                    "source_sha256": proof["source_sha256"],
                    "frames": len(proof["frames"]),
                    "codec": proof["frames"][0]["native"]["codec"],
                }
            )
        )
        evidence.append({"case": name, "proof": proof})
    (tmp_path / "native-icon-proofs.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf8"
    )


def test_exact_and_alpha0_comparison_are_distinct_and_adversarial():
    from tests.local_acceptance.api_image_proofs import (
        canonical_icon_pixels,
        compare_icon_pixels,
    )

    expected = LITERAL_RGBA
    assert canonical_icon_pixels(expected) == bytes.fromhex(
        "f0 0a 14 ff 07 50 09 80 00 00 00 00 01 02 c8 40"
    )
    hidden = bytearray(expected)
    hidden[8:11] = b"\x99\x88\x77"
    result = compare_icon_pixels(expected, bytes(hidden))
    assert result["raw_equal"] is False and result["canonical_equal"] is True
    assert result["hidden_rgb_mismatches"] == 3
    for index in (0, 3, 4, 7, 11, 15):
        changed = bytearray(expected)
        changed[index] ^= 1
        with pytest.raises(AssertionError, match="visible/alpha"):
            compare_icon_pixels(expected, bytes(changed))
    with pytest.raises(AssertionError, match="visible/alpha"):
        compare_icon_pixels(bytes((7, 80, 9, 1)), bytes((0, 0, 0, 1)))
    for changed in (
        expected[8:] + expected[:8],
        b"".join(
            expected[i : i + 4][2::-1] + expected[i + 3 : i + 4]
            for i in range(0, 16, 4)
        ),
        expected[:4] + bytes((4, 40, 5, 128)) + expected[8:],
    ):
        with pytest.raises(AssertionError, match="visible/alpha"):
            compare_icon_pixels(expected, changed)
    with pytest.raises(AssertionError, match="length"):
        compare_icon_pixels(expected, expected[:-1])


def test_complete_structural_mutation_catalogue_refuses_before_native():
    from tests.local_acceptance.api_image_proofs import icon_proof

    for name, raw in (*ico_mutations(), *bmp_mutations()):
        with pytest.raises(AssertionError, match="ICO|BMP|icon"):
            icon_proof(raw, native=False)
        # The names are retained so every meaningful mutation is visible in logs.
        print("structural refusal:", name)


def test_masks_hidden_rgb_and_valid_changed_artwork_keep_their_meaning():
    from tests.local_acceptance.api_image_proofs import icon_proof

    original = ico()["raw"]
    mask_changed = original[:-8] + b"\xff" * 8
    a, b = icon_proof(original), icon_proof(mask_changed)
    assert a["source_sha256"] != b["source_sha256"]
    assert a["frames"][0]["rgba_sha256"] == b["frames"][0]["rgba_sha256"]
    assert a["frames"][0]["mask_sha256"] != b["frames"][0]["mask_sha256"]
    changed = patch(original, 62, "<B", 34)  # bottom-left hidden blue33->34
    c = icon_proof(changed)
    assert c["frames"][0]["rgba_sha256"] != a["frames"][0]["rgba_sha256"]
    assert (
        c["frames"][0]["canonical_rgba_sha256"]
        == a["frames"][0]["canonical_rgba_sha256"]
    )
    visible = icon_proof(patch(original, 70, "<B", 21))
    assert (
        visible["frames"][0]["canonical_rgba_sha256"]
        != a["frames"][0]["canonical_rgba_sha256"]
    )
    bmps = [icon_proof(bmp(x=x)["raw"]) for x in ("zero", "255", "mixed")]
    assert len({p["source_sha256"] for p in bmps}) == 3
    assert len({p["frames"][0]["rgba_sha256"] for p in bmps}) == 1


def test_legacy_forms_keep_old_pixel_masks_and_exact_tails():
    from tests.local_acceptance.api_image_proofs import icon_proof

    root = Path(__file__).parents[1] / "fixtures/local_api_images_v3"
    facts = json.loads((root / "source-facts.json").read_bytes())["payloads"]
    for fact in facts:
        raw = (root / fact["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == fact["sha256"]
        old = ico_proof(raw)
        union = icon_proof(raw)
        assert union["alternative"] == "unchanged-historical"
        assert union["legacy_proof"] == old
        for frame, expected in zip(old["frames"], fact["directory_order"], strict=True):
            assert frame["rgba_sha256"] == expected["rgba_sha256"]
        assert len(union["native_details"]) == len(old["frames"])
        assert all(
            row["codec"]["clsid"] and row["codec"]["version"]
            for row in union["native_details"]
        )
        tail = next(
            (v for v in fact["directory_order"] if v["extra_zero_tail_length"]), None
        )
        if tail:
            index = tail["offset"] + tail["body_length"] - 1
            with pytest.raises(AssertionError):
                icon_proof(patch(raw, index, "<B", 1))


def test_separate_historical_zero_alpha_mask_control(tmp_path):
    from tests.local_acceptance.api_image_proofs import (
        compare_icon_pixels,
        decode_ico_variant,
        icon_proof,
    )

    fixture = legacy_zero_alpha_control()
    frozen = json.loads((FIXTURES / "source-facts.json").read_bytes())[
        "legacy_zero_alpha"
    ]
    assert public_facts(fixture) == frozen
    raw = fixture["raw"]
    proof = icon_proof(raw)
    assert proof["alternative"] == "unchanged-historical"
    observed = []
    for frame in fixture["frames"]:
        size, offset, length = frame["width"], frame["offset"], frame["body_length"]
        assert not any(raw[offset + 43 : offset + 40 + 4 * size * size : 4])
        wrapper = (
            struct.pack("<HHHBBBBHHII", 0, 1, 1, size, size, 0, 0, 1, 32, length, 22)
            + raw[offset : offset + length]
        )
        native = decode_ico_variant(wrapper, include_pixels=True)
        comparison = compare_icon_pixels(frame["rgba"], native.pop("rgba"))
        assert frame["rgba"][3] == 0 and set(frame["rgba"][7::4]) == {255}
        observed.append({"size": size, "comparison": comparison, "native": native})
    with pytest.raises(AssertionError):
        icon_proof(raw[:-1])
    (tmp_path / "historical-zero-alpha-mask-proof.json").write_text(
        json.dumps(observed, indent=2), encoding="utf8"
    )


def test_profile5_capture_vector_is_independently_canonical_and_frozen():
    from tests.local_acceptance.api_icon_inputs import capture_digest, capture_json

    path = (
        Path(__file__).parents[1]
        / "fixtures/local_api_capture/profile5-capture-vector.json"
    )
    frozen = json.loads(path.read_bytes())
    assert profile5_capture_vector() == frozen
    assert (
        capture_json({"b": [False, 1], "a": "x\nΩ"})
        == b'{"a":"x\\u000a\xce\xa9","b":[false,1]}'
    )
    files = {
        r["storage_key"]: bytes.fromhex(r["hex"]) for r in frozen["retained_files"]
    }
    source = json.loads(files["source.json"])
    assert source["identifiers"]["profile_version"] == "5"
    assert capture_digest("source", source) == frozen["expected_source_sha256"]
    changed = json.loads(files["source.json"])
    changed["identifiers"]["profile_version"] = "4"
    assert capture_digest("source", changed) != frozen["expected_source_sha256"]
    manifest = json.loads(files["manifest.json"])
    for row in manifest["files"]:
        assert row["actual_length"] == len(files[row["storage_key"]])
        assert (
            row["actual_sha256"]
            == hashlib.sha256(files[row["storage_key"]]).hexdigest()
        )
    assert (
        len(
            [
                r
                for r in manifest["payload_bindings"]
                if r["asset_id"].endswith("000005")
            ]
        )
        == 1
    )


def test_every_admitted_size_and_independent_storage_order(tmp_path):
    from tests.local_acceptance.api_image_proofs import icon_proof

    started = time.perf_counter()
    frozen = json.loads((FIXTURES / "source-facts.json").read_bytes())[
        "dimension_sweep"
    ]
    observed = []
    for size in range(1, 257):
        fixture = ico((size,), size_images=(4 * size * size,), opaque=True)
        assert public_facts(fixture) == frozen[str(size)]
        frame = icon_proof(fixture["raw"])["frames"][0]
        assert (frame["width"], frame["rgba_sha256"]) == (
            size,
            fixture["frames"][0]["rgba_sha256"],
        )
        observed.append(
            {
                "dimension": size,
                "container_sha256": fixture["sha256"],
                "rgba_sha256": frame["rgba_sha256"],
                "native_canonical_match": frame["comparison"]["canonical_equal"],
            }
        )
        del fixture, frame
    for physical in ((0, 1, 2), (2, 1, 0), (1, 2, 0)):
        fixture = ico((33, 31, 32), physical=physical, size_images=(4356, 0, 4096))
        proof = icon_proof(fixture["raw"])
        assert [p["rgba_sha256"] for p in proof["frames"]] == [
            p["rgba_sha256"] for p in fixture["frames"]
        ]
    elapsed = time.perf_counter() - started
    assert elapsed < 60, "bounded native qualification sweep"
    print(
        json.dumps(
            {
                "swept_dimensions": 256,
                "directory_physical_orders": 3,
                "elapsed_seconds": elapsed,
            }
        )
    )
    (tmp_path / "dimension-sweep.json").write_text(
        json.dumps({"cases": observed, "elapsed_seconds": elapsed}, indent=2),
        encoding="utf8",
    )


def test_genuine_maxima_and_dominated_operational_caps_are_measured(tmp_path):
    from tests.local_acceptance.api_image_proofs import icon_process_memory, icon_proof

    before = icon_process_memory()
    observations = []
    frozen = json.loads((FIXTURES / "source-facts.json").read_bytes())["maxima"]
    for name, build in (
        (
            "ico-16-distinct",
            lambda: ico(
                tuple(range(241, 257)),
                physical=tuple(range(15, -1, -1)),
                opaque=True,
                retain_pixels=False,
            ),
        ),
        ("bmp-1024-square", lambda: bmp(1024, 1024, retain_pixels=False)),
    ):
        fixture = build()
        start = time.perf_counter()
        assert public_facts(fixture) == frozen[name]
        proof = icon_proof(fixture["raw"])
        assert [f["rgba_sha256"] for f in proof["frames"]] == [
            f["rgba_sha256"] for f in fixture["frames"]
        ]
        expected = (988376, 4081638) if name.startswith("ico") else (1048576, 4194358)
        assert (
            sum(f["width"] * f["height"] for f in proof["frames"]),
            len(fixture["raw"]),
        ) == expected
        elapsed = time.perf_counter() - start
        assert elapsed < 30, "worst-bound diagnostic deadline"
        observations.append(
            {
                "case": name,
                "pixels": expected[0],
                "encoded_bytes": expected[1],
                "elapsed_seconds": elapsed,
                "process_memory": icon_process_memory(),
            }
        )
        del fixture, proof
    for build in (
        lambda: b"\0\0\1\0" + bytes(8 * 1024 * 1024 - 3),
        lambda: b"BM" + bytes(4194357),
        lambda: patch(ico()["raw"], 4, "<H", 17),
        lambda: patch(bmp()["raw"], 18, "<i", 1025),
    ):
        raw = build()
        with pytest.raises(AssertionError):
            icon_proof(raw, native=False)
        del raw
    evidence = {
        "baseline_process_memory": before,
        "maxima": observations,
        "memory_meaning": "absolute process lifetime peak and current working set/private commit; not a production decoder guarantee",
    }
    print(json.dumps(evidence))
    (tmp_path / "worst-bound-observations.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf8"
    )
