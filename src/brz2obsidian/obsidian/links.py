"""Bounded in-memory Obsidian link interpretation; never reads vault files."""

import re
from urllib.parse import unquote_to_bytes

from brz2obsidian.contracts import (
    LinkDocument, LinkFragment, LinkOccurrence, LinkQuery, LinkTargetFacts, StructureSpan,
)
from brz2obsidian.core.link_meanings import resolve_link_meaning


def _code_ranges(text):
    ranges, issues, fence, start, offset = [], [], None, 0, 0
    for line in text.splitlines(keepends=True):
        marker = re.match(r" {0,3}(`{3,}|~{3,})", line)
        if fence is None and marker:
            fence, start = marker[1], offset
        elif fence is not None and re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*", line):
            ranges.append((start, offset + len(line)))
            fence = None
        offset += len(line)
    if fence is not None:
        ranges.append((start, len(text)))
        issues.append("code_unclosed")
    cursor = 0
    for run in re.finditer(r"`+", text):
        if run.start() < cursor or any(a <= run.start() < b for a, b in ranges):
            continue
        closing = next((m for m in re.finditer(r"`+", text[run.end():]) if len(m[0]) == len(run[0])), None)
        if closing is None:
            issues.append("code_unclosed")
            ranges.append((run.start(), len(text)))
            break
        cursor = run.end() + closing.end()
        ranges.append((run.start(), cursor))
    return ranges, issues


def _query(value, source_path, path_mode):
    if any(ord(c) < 32 or c in '\\<>:"|^[]#' for c in value):
        return None
    if not value:
        return LinkQuery(value=source_path, mode="exact")
    parts = source_path.split("/")[:-1] if path_mode == "relative" else []
    for part in value.split("/"):
        if part == "." and path_mode == "relative":
            continue
        if part == ".." and path_mode == "relative" and parts:
            parts.pop()
        elif part in ("", ".", ".."):
            return None
        else:
            parts.append(part)
    return LinkQuery(value="/".join(parts), mode="shortened" if path_mode == "shortened" else "exact")


def _decode(value):
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        raise ValueError("Invalid percent encoding")
    return unquote_to_bytes(value).decode("utf-8")


def interpret_link_target(content, *, target_id, existence, memberships):
    fragments, status = [], "unknown" if content is None else "supported"
    if content is not None:
        try:
            text = content.data.decode("utf-8")
        except UnicodeDecodeError:
            status = "unsupported"
        else:
            headings = []
            for line in text.splitlines():
                heading = re.fullmatch(r"(#{1,6}) (.+)", line)
                block = re.search(r"(?:^| )\^([A-Za-z0-9-]+)$", line)
                if heading:
                    while headings and headings[-1][0] >= len(heading[1]):
                        headings.pop()
                    headings.append((len(heading[1]), heading[2]))
                    fragments.append(LinkFragment(kind="heading", value=heading[2]))
                    if len(headings) > 1:
                        fragments.append(LinkFragment(kind="heading", value="#".join(value for _, value in headings)))
                if block:
                    fragments.append(LinkFragment(kind="block", value=block[1]))
    return LinkTargetFacts(schema_id="brz2obsidian.link-target-facts", schema_version=1,
        target_id=target_id, existence=existence, content=content, fragments=tuple(fragments), memberships=memberships, interpretation=status)


def interpret_links(content, *, document_id, source_path, path_mode, targets, target_facts, inventory):
    occurrences, issues, consumed = [], [], []
    try:
        text = content.data.decode("utf-8")
    except UnicodeDecodeError:
        text = ""
        issues.append("encoding_unsupported")
    masked, code_issues = _code_ranges(text)
    issues.extend(code_issues)
    pattern = r"!?\[\[(?P<w>[^\r\n]*?)\]\]|!?\[(?P<label>[^\[\]\r\n]*)\]\((?P<m>[^()\r\n]*)\)"
    for match in re.finditer(pattern, text):
        escaped = len(text[:match.start()]) - len(text[:match.start()].rstrip("\\"))
        if escaped % 2 or any(a <= match.start() < b for a, b in masked):
            consumed.append((match.start(), match.end()))
            continue
        consumed.append((match.start(), match.end()))
        wiki = match["w"] is not None
        syntax = "wiki" if wiki else "markdown"
        raw_destination, _, alias = match["w"].partition("|") if wiki else (match["m"], "", match["label"])
        display = alias if alias or not wiki else raw_destination
        try:
            angled = not wiki and raw_destination.startswith("<") and raw_destination.endswith(">")
            if (wiki and (match["w"].count("|") > 1 or ("|" in match["w"] and not alias))) or (not wiki and not angled and any(c.isspace() for c in raw_destination)):
                raise ValueError("Unsupported destination")
            semantic_destination = raw_destination[1:-1] if angled else raw_destination
            target_text, marker, fragment_text = semantic_destination.partition("#")
            if not wiki:
                target_text, fragment_text = _decode(target_text), _decode(fragment_text)
            if marker and (not fragment_text or (fragment_text.startswith("^") and not re.fullmatch(r"\^[A-Za-z0-9-]+", fragment_text)) or any(not part or any(c in "[]|^" for c in part) for part in fragment_text.removeprefix("^").split("#"))):
                raise ValueError("Unsupported fragment")
            fragment = None if not fragment_text else LinkFragment(kind="block" if fragment_text.startswith("^") else "heading", value=fragment_text.removeprefix("^"))
            external = not wiki and re.match(r"(?i)^(https?://|mailto:)", target_text)
            query = None if external else _query(target_text, source_path, path_mode)
        except (ValueError, UnicodeDecodeError):
            query, fragment, external = None, None, False
        if query is None and not external:
            issues.append("path_unsupported")
        meaning = resolve_link_meaning(query, display, None if external else fragment, targets, target_facts, inventory)
        if external:
            meaning = meaning.model_copy(update={"status": "external"})
        start, end = len(text[:match.start()].encode()), len(text[:match.end()].encode())
        destination_start = len(text[:match.start("w" if wiki else "m")].encode())
        occurrences.append(LinkOccurrence(occurrence_id=f"{document_id}:link:{len(occurrences)}", syntax=syntax,
            embedded=match[0].startswith("!"), span=StructureSpan(start=start, end=end),
            destination_span=StructureSpan(start=destination_start, end=destination_start + len(raw_destination.encode())),
            raw=content.data[start:end], query=query, meaning=meaning))
    residue = list(text)
    for start, end in masked + consumed:
        residue[start:end] = " " * (end - start)
    residue = "".join(residue)
    if "[[" in residue or "](" in residue or re.search(r"!?\[[^\[\]\n]+\]\s*\[[^\[\]\n]*\]|<a\b", residue, re.I):
        issues.append("link_syntax_unsupported")
    return LinkDocument(schema_id="brz2obsidian.link-document", schema_version=1, document_id=document_id,
        source_path=source_path, content=content, path_mode=path_mode, inventory=inventory,
        status="unsupported" if issues else "supported", issues=tuple(issues), occurrences=tuple(occurrences))
