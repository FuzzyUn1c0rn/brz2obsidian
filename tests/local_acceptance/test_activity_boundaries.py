"""Authored ZIP bytes establish independent code/comment and retained-state scope."""

CASES = [
    (
        "`<!--` <Value> <!-- harmless comment -->",
        "`<!--` \\<Value> <!-- harmless comment -->",
        ["<Value>"],
    ),
    ("<!-- unfinished comment <Hidden>", "<!-- unfinished comment <Hidden>", []),
    (
        "x <!-- ` --> <Value> ` <Tail>",
        "x <!-- ` --> \\<Value> ` \\<Tail>",
        ["<Value>", "<Tail>"],
    ),
    (
        "`<!--` <Value> <!-- ` --> <Tail> `<!--`",
        "`<!--` \\<Value> <!-- ` --> \\<Tail> `<!--`",
        ["<Value>", "<Tail>"],
    ),
    (
        "<!-- <Hidden> -->\n<Value>",
        "<!-- <Hidden> -->\n\\<Value>",
        ["<Value>"],
    ),
    ("x <!-- <Hidden> --> <Value>", "x <!-- <Hidden> --> \\<Value>", ["<Value>"]),
    ("x <!-- <Hidden> -->", "x <!-- <Hidden> -->", []),
    (
        "x <!-- <!-- <Hidden> --> <Value>",
        "x <!-- <!-- <Hidden> --> \\<Value>",
        ["<Value>"],
    ),
    ("x <!-- unfinished <Value>", "x <!-- unfinished \\<Value>", ["<Value>"]),
    ("> <!-- unfinished\n> <Hidden>", "> <!-- unfinished\n> <Hidden>", []),
    ("- <!-- unfinished\n  <Hidden>", "- <!-- unfinished\n  <Hidden>", []),
    ("> <!-- unfinished\n\n<Value>", "> <!-- unfinished\n\n\\<Value>", ["<Value>"]),
    (
        "x <!-- `\n```md\n<Hidden>\n-->\n<Value>",
        "x <!-- `\n```md\n<Hidden>\n-->\n<Value>",
        [],
    ),
    (
        "<!-- `\n```\n<Hidden>\n-->\n<Value>",
        "<!-- `\n```\n<Hidden>\n-->\n\\<Value>",
        ["<Value>"],
    ),
    (
        "```md\n<!-- <Hidden>\n```\n<Value>",
        "```md\n<!-- <Hidden>\n```\n\\<Value>",
        ["<Value>"],
    ),
    (
        "~~~\n<!-- <Hidden>\n~~\n<Hidden2>\n~~~\n<Value>",
        "~~~\n<!-- <Hidden>\n~~\n<Hidden2>\n~~~\n\\<Value>",
        ["<Value>"],
    ),
    ("    <!-- <Hidden>\n\n<Value>", "    <!-- <Hidden>\n\n\\<Value>", ["<Value>"]),
    (
        "x\n    <!-- <Hidden> --> <Value>",
        "x\n    <!-- <Hidden> --> \\<Value>",
        ["<Value>"],
    ),
    (r"x \<!-- <Value> -->", r"x \<!-- \<Value> -->", ["<Value>"]),
    (r"x \\<!-- <Hidden> --> <Value>", r"x \\<!-- <Hidden> --> \<Value>", ["<Value>"]),
    (
        r"x \` <!-- <Hidden> --> <Value> `",
        r"x \` <!-- <Hidden> --> \<Value> `",
        ["<Value>"],
    ),
    (r"`a\` <Value>", r"`a\` \<Value>", ["<Value>"]),
    ("x &lt;!-- <Value>", "x &lt;!-- \\<Value>", ["<Value>"]),
    ("``<!-- ` <Hidden>`` <Value>", "``<!-- ` <Hidden>`` \\<Value>", ["<Value>"]),
    ("`<Value> ``", "`\\<Value> ``", ["<Value>"]),
    ("`<!--\n<Hidden>` <Value>", "`<!--\n<Hidden>` \\<Value>", ["<Value>"]),
    ("`x\n\n<Value> `", "`x\n\n\\<Value> `", ["<Value>"]),
    (
        "`x\n~~~\n<Hidden>\n~~~\n<Value> `",
        "`x\n~~~\n<Hidden>\n~~~\n\\<Value> `",
        ["<Value>"],
    ),
    ("α\u2028`<!--` <Value>", "α\u2028`<!--` \\<Value>", ["<Value>"]),
    ("> ```\n> <Hidden>\n\n<Value>", "> ```\n> <Hidden>\n\n\\<Value>", ["<Value>"]),
    ("- ```\n  <Hidden>\n\n<Value>", "- ```\n  <Hidden>\n\n\\<Value>", ["<Value>"]),
    (
        "`<Hidden>\nheading\n---\n<Value> `",
        "`\\<Hidden>\nheading\n---\n\\<Value> `",
        ["<Hidden>", "<Value>"],
    ),
    (
        "`<Hidden>\n***\n<Value> `",
        "`\\<Hidden>\n***\n\\<Value> `",
        ["<Hidden>", "<Value>"],
    ),
]
