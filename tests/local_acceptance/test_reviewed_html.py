"""Raw grammatical non-tags survive complete ZIP/CLI/original audits."""

NON_TAGS = [
    "Text <sys/header.h> <Value>",
    "Text <sys/other.h> <Value>",
    'Text <I", example\\_value\n\n## Next\n\n`<Hidden>`\n\nend > <Value>',
    r"Text <SESSION\_KEY> <Value>",
    "Text <!a\n\n<Value>",
    "Text <!_> <!1> <!é> <Value>",
    r"Text \<!a> <Value>",
    "`<!a>` <Value>",
    "<!-- <!a> -->\n<Value>",
    "```\n<!a\n> > prompt\n```\n<Value>",
    "~~~\n<!a>\n~~~\n<Value>",
    "    <!a\n\n<Value>",
]
