"""Active declaration blocks refuse at actual ZIP Workflow and CLI boundaries."""

import pytest

# CommonMark 0.31.2 section 4.6 type 4: <! + ASCII letter at the
# owning container's content start. EOF cases contain no accidental later >.
DECLARATIONS = [
    " " * spaces + "<!" + letter
    for spaces in range(4)
    for letter in ("A", "a", "Z", "z")
] + [
    "<!a>",
    "   <!A> trailing",
    "<!a\n\ncontinued\nend >\n<Value>",
    "<!A\n<Value>",  # later literal-looking text closes the owned block
    "Prose\n<!a\ncontinued",
    "Prose\n   <!a\ncontinued",
    "> <!a\n> continued",
    ">   <!A\n>\n> continued",
    "> <!a\n\noutside container",
    "- <!a\n  continued",
    "1. <!z\n   continued",
    "-   <!A\n\n    continued",
    "- <!a\n\noutside container",
    "> - <!a\n>   continued",
    "- > <!a\n  > continued",
    "[label](https://example.invalid)\n<!a",
    "-\t<!a",
    "- \t<!a",
    "-\t <!a",
    "1.\t<!A",
    "1.\t  <!a",
    "10.\t<!a",
    "123.\t<!a",
    "- ordinary\n\n     <!a",
    "1.    ordinary\n\n         <!a",
    "- ordinary\n\n\t <!a",
    "> -\t<!a",
    "Paragraph\n1. <!a",
    "- > paragraph\n  <!a",
    "> - paragraph\n>\n>     <!a",
    "Paragraph\n> 10. <!a",
    "> Paragraph\n> > 10. <!a",
    "- Paragraph\n  > 10. <!a",
    "Paragraph\n\n10. <!a",
    # Conservative reviewed route: a missing old owner prefix starts a new
    # ordered container in the pinned source parser. No general lazy admission.
    "> Paragraph\n10. <!a",
    "- Paragraph\n10. <!a",
]


def _distinct_declaration_cases():
    cases = []
    seen = set()
    for authored in DECLARATIONS:
        for newline in ("\n", "\r", "\r\n"):
            payload = authored.replace("\n", newline).encode()
            if payload in seen:
                continue
            seen.add(payload)
            # This reproduces the existing authored-newline pytest ID.
            cases.append(pytest.param(authored, newline, id=f"{authored}-{newline}"))
    return cases
