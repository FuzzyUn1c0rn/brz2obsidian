"""Bounded lexical legacy decoding into the single current content family.

The caller's original buffer is retained by reference. Payload string tokens
are unescaped and decoded in bounded blocks directly into owned transactions;
they are never assembled into a second complete base64 scalar.
"""

import base64
import codecs
import json
from functools import lru_cache
from typing import Annotated, get_args, get_origin

from pydantic import BaseModel

from .content_fingerprints import _resolved_annotation, resolved_contract_fields
from .contracts import (
    ImmutableContentReference,
    InlineExactContent,
    OpaqueContent,
    SavedReview,
)


def _alternatives(annotation):
    if type(annotation) is tuple:
        for child in annotation:
            yield from _alternatives(child)
        return
    _resolved_annotation(annotation)
    if get_origin(annotation) is Annotated:
        yield from _alternatives(get_args(annotation)[0])
    elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
        yield annotation
    else:
        for child in get_args(annotation):
            if child is not Ellipsis:
                yield from _alternatives(child)


@lru_cache(maxsize=2048)
def _field(annotation, key):
    fields = tuple(
        resolved_contract_fields(model)[key].annotation
        for model in _models(annotation)
        if key in resolved_contract_fields(model)
    )
    if not fields:
        raise ValueError("Unknown legacy schema field")
    return fields[0] if len(fields) == 1 else fields


@lru_cache(maxsize=256)
def _models(annotation):
    if type(annotation) is tuple:
        return tuple(model for child in annotation for model in _alternatives(child))
    return tuple(_alternatives(annotation))


@lru_cache(maxsize=256)
def _array_item(annotation):
    if type(annotation) is tuple:
        return tuple(_array_item(child) for child in annotation)
    _resolved_annotation(annotation)
    if get_origin(annotation) is Annotated:
        return _array_item(get_args(annotation)[0])
    args = get_args(annotation)
    if get_origin(annotation) in (tuple, list) and args:
        return args[0]
    if args:
        return tuple(_array_item(child) for child in args if child is not type(None))
    raise ValueError("Legacy array lacks a declared element schema")


class _Characters:
    def __init__(self, raw, ledger):
        if type(raw) not in (bytes, str):
            raise ValueError("Legacy input requires bytes or text")
        self.raw, self.ledger = raw, ledger
        self.position = self.index = 0
        self.block = ""
        self.decoder = (
            codecs.getincrementaldecoder("utf-8")() if type(raw) is bytes else None
        )
        self.finished = False

    def peek(self):
        while self.index == len(self.block) and not self.finished:
            self.ledger.check()
            self.ledger.take("step", 1)
            end = min(len(self.raw), self.position + 4096)
            block = self.raw[self.position : end]
            self.position = end
            self.finished = end == len(self.raw)
            self.block = (
                self.decoder.decode(block, final=self.finished)
                if self.decoder
                else block
            )
            self.index = 0
        return self.block[self.index] if self.index < len(self.block) else ""

    def take(self):
        char = self.peek()
        if not char:
            raise ValueError("Truncated JSON")
        self.index += 1
        return char

    def whitespace(self):
        while self.peek() and self.peek() in " \t\r\n":
            self.take()


class LegacyDecoder:
    def __init__(self, raw, owner):
        self.owner = owner
        self.ledger = owner._ledger
        self.ledger.check()
        resolved_contract_fields(SavedReview)
        self.ledger.check()
        # Fixed lexical buffers plus a tuple path for every allowed recursion
        # level. These are named structural workspace units, not a heap claim.
        self.workspace = 4096 * (80 + 16 + 4 + 4) + sum(
            64 + 16 * level for level in range(self.ledger.budget.depth_limit + 1)
        )
        self.ledger.retain_metadata(self.workspace)
        self.chars = _Characters(raw, self.ledger)

    def _hex_code_unit(self):
        digits = "".join(self.chars.take() for _ in range(4))
        if any(c not in "0123456789abcdefABCDEF" for c in digits):
            raise ValueError("Invalid Unicode escape")
        return int(digits, 16)

    def _escaped_character(self):
        escape = self.chars.take()
        if escape == "u":
            ordinal = self._hex_code_unit()
            if 0xD800 <= ordinal <= 0xDBFF:
                if self.chars.take() != "\\" or self.chars.take() != "u":
                    raise ValueError("Unpaired Unicode surrogate")
                low = self._hex_code_unit()
                if not 0xDC00 <= low <= 0xDFFF:
                    raise ValueError("Unpaired Unicode surrogate")
                ordinal = 0x10000 + ((ordinal - 0xD800) << 10) + low - 0xDC00
            elif 0xDC00 <= ordinal <= 0xDFFF:
                raise ValueError("Unpaired Unicode surrogate")
            return chr(ordinal)
        translations = {
            '"': '"',
            "\\": "\\",
            "/": "/",
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
        }
        if escape not in translations:
            raise ValueError("Invalid JSON escape")
        return translations[escape]

    def _string_blocks(self):
        if self.chars.take() != '"':
            raise ValueError("Expected JSON string")
        block = []
        while True:
            char = self.chars.take()
            if char == '"':
                if block:
                    yield "".join(block)
                return
            if char == "\\":
                char = self._escaped_character()
            elif ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF:
                raise ValueError("Invalid JSON string character")
            block.append(char)
            if len(block) == 4096:
                yield "".join(block)
                block.clear()

    def _string(self):
        blocks = []
        self.ledger.retain_metadata(64)
        parts_charge, length = 64, 0
        for block in self._string_blocks():
            self.ledger.retain_metadata(4 * len(block) + 16)
            parts_charge += 4 * len(block) + 16
            length += len(block)
            blocks.append(block)
        self.ledger.retain_metadata(64 + 4 * length)
        result = "".join(blocks)
        self.ledger.release_metadata(parts_charge)
        return result

    def _data(self, transaction=None):
        residual, ended = "", False
        result = bytearray() if transaction is None else None
        for text in self._string_blocks():
            if ended and text:
                raise ValueError("Base64 data after padding")
            text.encode("ascii")
            joined = residual + text
            end = len(joined) - len(joined) % 4
            chunk, residual = joined[:end], joined[end:]
            if chunk:
                raw = base64.b64decode(chunk, altchars=b"-_", validate=True)
                ended = "=" in chunk
                if transaction is None:
                    self.ledger.take("decoded", len(raw))
                    result.extend(raw)
                else:
                    transaction.write(raw)
        if residual:
            if ended or len(residual) == 1:
                raise ValueError("Invalid base64 tail")
            raw = base64.b64decode(
                residual + "=" * (4 - len(residual)), altchars=b"-_", validate=True
            )
            if transaction is None:
                self.ledger.take("decoded", len(raw))
                result.extend(raw)
            else:
                transaction.write(raw)
        return bytes(result) if result is not None else None

    def _scalar(self):
        token = []
        while self.chars.peek() and self.chars.peek() not in " \t\r\n,]}":
            self.ledger.retain_metadata(4)
            token.append(self.chars.take())
        if not token:
            raise ValueError("Missing JSON value")
        value = json.loads("".join(token))
        if value is not None and type(value) not in (bool, int):
            raise ValueError("Invalid legacy scalar")
        return value

    def value(self, annotation, path=(), depth=1):
        self.ledger.node(depth)
        self.chars.whitespace()
        char = self.chars.peek()
        if char == "{":
            return self._object(annotation, path, depth)
        if char == "[":
            self.chars.take()
            self.ledger.retain_metadata(64)
            children = []
            self.chars.whitespace()
            if self.chars.peek() != "]":
                while True:
                    self.ledger.retain_metadata(16)
                    children.append(
                        self.value(
                            _array_item(annotation), path + (len(children),), depth + 1
                        )
                    )
                    self.chars.whitespace()
                    if self.chars.peek() != ",":
                        break
                    self.chars.take()
            if self.chars.take() != "]":
                raise ValueError("Invalid JSON array")
            return tuple(children)
        if char == '"':
            return self._data() if annotation is bytes else self._string()
        return self._scalar()

    def _member_name(self, values):
        key = self._string()
        if key in values:
            raise ValueError("Duplicate JSON member")
        self.ledger.retain_metadata(64)
        self.chars.whitespace()
        if self.chars.take() != ":":
            raise ValueError("Missing JSON colon")
        self.chars.whitespace()
        return key

    def _finish_content(self, values, transaction, *, inline):
        if set(values) - {"data", "reference"} or transaction is None:
            raise ValueError("Invalid legacy content fields")
        historical = values.get("reference")
        if historical is not None:
            historical = ImmutableContentReference.model_validate(historical)
        return self.owner._finish_input(transaction, historical, inline=inline)

    def _object(self, annotation, path, depth):
        models = _models(annotation)
        content = InlineExactContent in models or OpaqueContent in models
        inline = content and OpaqueContent not in models
        self.chars.take()
        self.ledger.retain_metadata(256)
        values, transaction = {}, None
        try:
            self.chars.whitespace()
            if self.chars.peek() != "}":
                while True:
                    key = self._member_name(values)
                    if content and key == "data":
                        transaction = self.owner._begin_input(path)
                        self._data(transaction)
                        values[key] = True
                    else:
                        values[key] = self.value(
                            _field(annotation, key), path + (key,), depth + 1
                        )
                    self.chars.whitespace()
                    if self.chars.peek() != ",":
                        break
                    self.chars.take()
                    self.chars.whitespace()
            if self.chars.take() != "}":
                raise ValueError("Invalid JSON object")
            if content:
                return self._finish_content(values, transaction, inline=inline)
            return self.owner._semantic_input(models, values)
        except BaseException:
            if transaction is not None:
                transaction.abort()
            raise

    def decode(self):
        try:
            value = self.value(SavedReview)
            self.chars.whitespace()
            if self.chars.peek():
                raise ValueError("Trailing JSON data")
            return value
        finally:
            self.ledger.release_metadata(self.workspace)


class _RetainedDecoder:
    """Adapt the unchanged refs envelope to actual owned Git registrations."""

    def __init__(self, record, registrations, owner):
        self.record, self.registrations, self.owner = record, registrations, owner
        self.ledger = owner._ledger

    def _content(self, marker, historical, path, *, inline):
        if (
            type(marker) is not dict
            or set(marker) != {"__brz2obsidian_review_blob__"}
            or type(marker["__brz2obsidian_review_blob__"]) is not str
        ):
            raise ValueError("Invalid saved-review byte reference")
        registration = self.registrations.get(marker["__brz2obsidian_review_blob__"])
        if registration is None:
            raise ValueError("Saved review bytes are outside the owned role closure")
        historical = (
            None
            if historical is None
            else ImmutableContentReference.model_validate(historical)
        )
        return self.owner._retained_value(registration, historical, path, inline=inline)

    def value(self, value, annotation, path=(), depth=1):
        self.ledger.check()
        self.ledger.node(depth)
        if type(value) is dict:
            self.ledger.retain_metadata(256 + 64 * len(value))
            models = _models(annotation)
            if InlineExactContent in models or OpaqueContent in models:
                if set(value) - {"data", "reference"} or "data" not in value:
                    raise ValueError("Invalid legacy content fields")
                return self._content(
                    value["data"],
                    value.get("reference"),
                    path,
                    inline=OpaqueContent not in models,
                )
            if set(value) == {"__brz2obsidian_review_blob__"}:
                # Non-content byte fields are semantic evidence in the old
                # contract; they retain actual bytes rather than a descriptor.
                return self._content(value, None, path, inline=True).data
            fields = {
                key: self.value(
                    child, _field(annotation, key), path + (key,), depth + 1
                )
                for key, child in value.items()
            }
            return self.owner._semantic_input(models, fields)
        if type(value) is list:
            self.ledger.retain_metadata(64 + 16 * len(value))
            return tuple(
                self.value(child, _array_item(annotation), path + (index,), depth + 1)
                for index, child in enumerate(value)
            )
        if type(value) is str:
            self.ledger.retain_metadata(64 + 4 * len(value))
        elif value is not None and type(value) not in (bool, int, float):
            raise ValueError("Invalid saved-review scalar")
        return value

    def decode(self):
        return self.value(self.record, SavedReview)
