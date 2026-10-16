"""Independent finite S7 source proof. No execution, decoding or converter imports."""

import hashlib
import re
from io import StringIO
from xml.etree import ElementTree as XML

NS = "http://www.w3.org/2000/svg"
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
COLOUR = re.compile(r"(?:none|#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6})\Z")
SPACE = " \t\r\n"


def number(value, *, positive=False, maximum=1000000):
    assert len(value) <= 64 and NUMBER.fullmatch(value), "SVG decimal spelling"
    # Exponent integers are bounded lexically, not by Decimal/float capacity.
    # Keep scale symbolic so arbitrary tiny positives never underflow to zero.
    mantissa, _, exponent = value.lower().partition("e")
    negative = mantissa.startswith("-")
    mantissa = mantissa.lstrip("+-")
    whole, _, fraction = mantissa.partition(".")
    digits = (whole + fraction).lstrip("0")
    assert not positive or digits and not negative, "SVG positive dimension"
    if not digits:
        return
    scale = int(exponent or "0") - len(fraction)
    order = len(digits) + scale
    bound = str(maximum)
    assert order <= len(bound), "SVG numeric magnitude"
    if order == len(bound):
        prefix = digits[: len(bound)].ljust(len(bound), "0")
        assert (
            prefix < bound
            or prefix == bound
            and not any(c != "0" for c in digits[len(bound) :])
        ), "SVG numeric magnitude"


def qualify_svg(payload):
    assert 0 < len(payload) <= 1048576, "SVG byte bound"
    assert not payload.startswith(b"\xef\xbb\xbf"), "SVG UTF8 BOM"
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise AssertionError("SVG strict UTF8") from exc
    # Reject references lexically, including predefined/numeric whitespace forms.
    assert "&" not in text, "SVG entity reference"
    assert not any(token in text for token in ("<!DOCTYPE", "<!ENTITY", "<!--")), (
        "SVG forbidden declaration"
    )
    if text.startswith("<?xml"):
        declaration = re.match(
            r"<\?xml[ \t\r\n]+version[ \t\r\n]*=[ \t\r\n]*(['\"])1\.0\1(?:[ \t\r\n]+encoding[ \t\r\n]*=[ \t\r\n]*(['\"])(?i:UTF-8)\2)?[ \t\r\n]*\?>",
            text,
        )
        assert declaration, "SVG XML declaration"
        rest = text[declaration.end() :]
    else:
        rest = text
    assert "<?" not in rest, "SVG processing instruction"
    try:
        events = list(
            XML.iterparse(StringIO(text), events=("start-ns", "start", "end"))
        )
    except (XML.ParseError, ValueError) as exc:
        raise AssertionError("SVG well formed XML") from exc
    stack, count = [], 0
    for event, value in events:
        if event == "start-ns":
            assert value == ("", NS), "SVG namespace declaration"
            continue
        if event == "end":
            assert (value.text or "").strip(SPACE) == "" and (value.tail or "").strip(
                SPACE
            ) == "", "SVG whitespace character data"
            stack.pop()
            continue
        count += 1
        assert count <= 4096, "SVG element bound"
        stack.append(value.tag)
        assert len(stack) <= 2, "SVG direct shape depth"
        attrs = value.attrib
        if len(stack) == 1:
            assert value.tag == "{" + NS + "}svg", "SVG root namespace/name"
            assert set(attrs) == {"width", "height", "viewBox"}, "SVG root attributes"
            number(attrs["width"], positive=True, maximum=32768)
            number(attrs["height"], positive=True, maximum=32768)
            view = attrs["viewBox"].strip(SPACE)
            assert not re.search(r"(?:^,|,$|,[ \t\r\n]*,)", view), (
                "SVG viewBox empty term"
            )
            terms = re.split(r"[ \t\r\n,]+", view)
            assert len(terms) == 4, "SVG viewBox arity"
            for i, term in enumerate(terms):
                number(term, positive=i >= 2)
        else:
            if value.tag == "{" + NS + "}rect":
                required = {"width", "height"}
                allowed = required | {"x", "y", "fill", "stroke", "stroke-width"}
            else:
                assert value.tag == "{" + NS + "}line", "SVG shape name/namespace"
                required = {"x1", "y1", "x2", "y2", "stroke"}
                allowed = required | {"stroke-width", "stroke-linecap"}
            assert required <= set(attrs) <= allowed, "SVG shape attributes"
            for key, item in attrs.items():
                if key in {"fill", "stroke"}:
                    assert COLOUR.fullmatch(item), "SVG paint"
                elif key == "stroke-linecap":
                    assert item in {"butt", "round", "square"}, "SVG cap"
                else:
                    number(item, positive=key in {"width", "height", "stroke-width"})
    return {
        "format": "SVG",
        "status": "static-grammar-valid",
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "elements": count,
    }
