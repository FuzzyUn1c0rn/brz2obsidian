"""Complete raw audits reject coherently forged active declaration admission."""

FORGED_DECLARATIONS = [
    "<!a",
    " <!z",
    "  <!Z",
    "   <!A",
    "Prose\n<!a\n\ncontinued",
    "> <!a\n> continued",
    "- <!a\n  continued",
    "> - <!a\n>   continued",
    "- > <!a\n  > continued",
    "   <!a>\ncontinued",
    "<!a\n\ncontinued\nend >",
    "> <!a\n\noutside container",
    "- <!a\n\noutside container",
    "-\t<!a",
    "- \t<!a",
    "-\t <!a",
    "1.\t<!a",
    "123.\t<!a",
    "> -\t<!a",
    "- ordinary\n\n\t <!a",
    "Paragraph\n> 10. <!a",
    "> Paragraph\n> > 10. <!a",
    "- Paragraph\n  > 10. <!a",
    "Paragraph\n\n10. <!a",
    # Independently authored conservative reviewed owner limit, not token output
    # from the runtime parser: missing old quote/list prefixes cannot grant
    # supported-source admission to these ordered declaration routes.
    "> Paragraph\n10. <!a",
    "- Paragraph\n10. <!a",
]
