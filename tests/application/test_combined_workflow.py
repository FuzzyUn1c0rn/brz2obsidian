"""Combined features cross the real Workflow and CLI with authored expectations."""

HOME_BODY = (
    "# Opening\n\nα \\<Enter> / \\<type>\r\n"
    '[[Notes/First.md|\\<Value>]] ![\\<Alt>](Attachments/00000000000000000000000000000001/picture.png "Caption")\r'
    "`<Code> </Enter>` \\<Escaped> <https://example.invalid>\n"
    "```md\n<Enter></Enter> ![fake](.data/md-images/missing.png)\n```\n\n\n"
    "## Resources\n\n"
    "- [[Attachments/00000000000000000000000000000001/manual.bin|manual.bin]]\n"
    "- [C:\\\\unavailable\\\\directory](<file:///C:/unavailable/directory>)\n\n"
    "## Children\n\n- [[Categories/Concept.md|Concept]]\n\n"
    "## Related\n\n- [[Notes/Different marker.md|Different marker]]\n\n"
    "## Categories\n\n[[Categories.md|Browse categories]]\n"
).encode()
