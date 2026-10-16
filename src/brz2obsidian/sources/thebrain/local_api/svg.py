"""The finite static SVG drawing grammar for local API profile3 only."""

import re
from pathlib import Path
from xml.parsers import expat

from .errors import refuse

NAMESPACE = "http://www.w3.org/2000/svg"
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
COLOUR = re.compile(r"(?:#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}|none)")
SPACE = " \t\r\n"


def number(text, *, positive=False, bound=1000000):
    if len(text) > 64 or NUMBER.fullmatch(text) is None:
        raise ValueError
    negative = text.startswith("-")
    mantissa, _, exponent = text.lstrip("+-").lower().partition("e")
    integer, _, fraction = mantissa.partition(".")
    coefficient = int(integer + fraction)
    if not coefficient:
        if positive:
            raise ValueError
        return
    if positive and negative:
        raise ValueError
    power = (int(exponent) if exponent else 0) - len(fraction)
    digits = len(str(coefficient)) + power
    if digits <= 0:
        return
    if digits > len(str(bound)):
        raise ValueError
    # Here the magnitude bound also bounds the exponent, avoiding expansion of
    # arbitrarily large exponent lexemes while retaining every tiny positive.
    if (
        coefficient * 10**power > bound
        if power >= 0
        else coefficient > bound * 10 ** (-power)
    ):
        raise ValueError


def attributes(name, values):
    if name == "svg":
        if values.keys() != {"width", "height", "viewBox"}:
            raise ValueError
        for key in ("width", "height"):
            number(values[key], positive=True, bound=32768)
        terms = re.split(
            r"[ \t\r\n]*,[ \t\r\n]*|[ \t\r\n]+", values["viewBox"].strip(SPACE)
        )
        if len(terms) != 4:
            raise ValueError
        for index, term in enumerate(terms):
            number(term, positive=index >= 2)
        return
    required = (
        {"width", "height"} if name == "rect" else {"x1", "y1", "x2", "y2", "stroke"}
    )
    optional = (
        {"x", "y", "fill", "stroke", "stroke-width"}
        if name == "rect"
        else {"stroke-width", "stroke-linecap"}
    )
    if not required <= values.keys() <= required | optional:
        raise ValueError
    for key, value in values.items():
        if key in {"fill", "stroke"}:
            if COLOUR.fullmatch(value) is None:
                raise ValueError
        elif key == "stroke-linecap":
            if value not in {"butt", "round", "square"}:
                raise ValueError
        else:
            number(value, positive=key in {"width", "height", "stroke-width"})


def validate_svg(raw):
    """Validate all source bytes without rewriting or resolving dependencies."""
    if isinstance(raw, Path):
        with raw.open("rb") as stream:
            data = stream.read(1048577)
    else:
        data = raw
    try:
        if len(data) > 1048576 or data.startswith(b"\xef\xbb\xbf"):
            raise ValueError
        text = data.decode("utf-8", errors="strict")
        if "&" in text or "\x00" in text:
            raise ValueError
        parser = expat.ParserCreate(namespace_separator="|")
        depth = count = 0

        def prohibited(*args):
            raise ValueError

        def namespace(prefix, uri):
            if prefix is not None or uri != NAMESPACE:
                raise ValueError

        def declaration(version, encoding, standalone):
            if (
                version != "1.0"
                or encoding is not None
                and encoding.lower() != "utf-8"
                or standalone != -1
            ):
                raise ValueError

        def start(expanded, values):
            nonlocal depth, count
            depth += 1
            count += 1
            local = expanded.removeprefix(NAMESPACE + "|")
            if (
                count > 4096
                or expanded != NAMESPACE + "|" + local
                or (depth == 1 and local != "svg")
                or (depth == 2 and local not in {"rect", "line"})
                or depth > 2
            ):
                raise ValueError
            attributes(local, values)

        def end(name):
            nonlocal depth
            depth -= 1

        def characters(value):
            if value.strip(SPACE):
                raise ValueError

        parser.StartNamespaceDeclHandler = namespace
        parser.XmlDeclHandler = declaration
        parser.StartElementHandler = start
        parser.EndElementHandler = end
        parser.CharacterDataHandler = characters
        parser.CommentHandler = prohibited
        parser.ProcessingInstructionHandler = prohibited
        parser.StartDoctypeDeclHandler = prohibited
        parser.EntityDeclHandler = prohibited
        parser.ExternalEntityRefHandler = prohibited
        parser.Parse(text, True)
        if count == 0 or depth:
            raise ValueError
    except UnicodeError, ValueError, expat.ExpatError:
        refuse("Required image bytes do not match the finite SVG qualification")
