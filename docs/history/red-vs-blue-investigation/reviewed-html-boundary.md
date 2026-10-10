# Reviewed HTML boundary and independent audit repair

Ticket [#146](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/146) closes the
literal-prose exclusion boundary introduced by #120. Active `content`, `shadow`
and `portal` tokens previously acquired literal escaping; they now refuse under
the existing unsupported-HTML diagnostic contract. Protected code, escaped
openers, comments and established bare `br` forms retain their meanings.

## Closed primary inventory, reviewed 2026-10-10

The review separately extracted the first element-index table and obsolete
element terms from frozen primary documents, then read the historical and
experimental definitions. It compared both implementations with these sources,
including equal omissions. The following 148 names are an exclusion policy,
not an HTML rendering capability or a browser compatibility registry.

### [WHATWG current HTML and foreign roots (115)](https://html.spec.whatwg.org/multipage/indices.html#elements-3)

113 conforming HTML names and the two foreign roots `math` and `svg`.

`a` `abbr` `address` `area` `article` `aside` `audio` `b` `base`
`bdi` `bdo` `blockquote` `body` `br` `button` `canvas` `caption` `cite`
`code` `col` `colgroup` `data` `datalist` `dd` `del` `details` `dfn`
`dialog` `div` `dl` `dt` `em` `embed` `fieldset` `figcaption` `figure`
`footer` `form` `h1` `h2` `h3` `h4` `h5` `h6` `head`
`header` `hgroup` `hr` `html` `i` `iframe` `img` `input` `ins`
`kbd` `label` `legend` `li` `link` `main` `map` `mark` `math`
`menu` `meta` `meter` `nav` `noscript` `object` `ol` `optgroup` `option`
`output` `p` `picture` `pre` `progress` `q` `rp` `rt` `ruby`
`s` `samp` `script` `search` `section` `select` `selectedcontent` `slot` `small`
`source` `span` `strong` `style` `sub` `summary` `sup` `svg` `table`
`tbody` `td` `template` `textarea` `tfoot` `th` `thead` `time` `title`
`tr` `track` `u` `ul` `var` `video` `wbr`

### [WHATWG obsolete elements (29)](https://html.spec.whatwg.org/multipage/obsolete.html#non-conforming-features)

Recognized obsolete names remain excluded.

`acronym` `applet` `basefont` `bgsound` `big` `blink` `center` `dir` `font`
`frame` `frameset` `isindex` `keygen` `listing` `marquee` `menuitem` `multicol` `nextid`
`nobr` `noembed` `noframes` `param` `plaintext` `rb` `rtc` `spacer` `strike`
`tt` `xmp`

### [Historical W3C Shadow DOM working draft (2)](https://www.w3.org/TR/2014/WD-shadow-dom-20140617/#the-content-element)

Sections 9.3–9.4 of the 2014-06-17 working draft define the historical insertion-point elements; these are not current conforming WHATWG names.

`content` `shadow`

### [WICG experimental proposal (1)](https://wicg.github.io/portals/#the-portal-element)

The portal proposal is explicitly not a W3C Standard. Its conservative exclusion is an explicit reviewed policy, not a claim of standardization.

`portal`

### Existing parser alias (1)

`image` retains its already reviewed exclusion. It is neither a conforming HTML
element nor a newly admitted experimental name. All 147 non-`br` names have
actual-ZIP Workflow and thin CLI refusal controls in lower/uppercase spellings;
separate controls preserve the existing bare `br` exception and protected names.
Neither production nor the raw oracle imports the other registry.

## Independent source expectations

The raw oracle recognizes candidate syntax from original characters under
[CommonMark 0.31.2 raw HTML](https://spec.commonmark.org/0.31.2/#raw-html), bounded
by active leaf ownership. Slash/dot angle words, invalid attribute sequences and
escaped punctuation remain ordinary authored text. Protection masks cannot
manufacture HTML whitespace or combine candidates across protected blocks.
Genuine attributes consume their complete quoted/unquoted text before Markdown
punctuation handling, including backticks and angle characters inside quotes;
they remain refused, rather than exposing a nested literal token. Link labels
remain active while complete destinations/titles are protected.

Independent review also found that the oracle required uppercase letters and
whitespace after a declaration opener. Section 6.6 instead requires `<!`, one
ASCII letter and zero or more non-`>` characters, then `>`; `<!A>`, `<!a>` and
`<!AB>` are genuine declarations. Their public Workflow/CLI refusal controls
and complete source/payload/original/document/manifest-rebound forged admissions
now exercise raw rejection across LF, CR and CRLF. For a line-start declaration,
[section 4.6 type 4](https://spec.commonmark.org/0.31.2/#html-blocks) owns the block
through a closer, its container boundary or EOF. The oracle rejects that active
block from the original opener, without borrowing inline delimiter requirements.
Existing code/comment ownership takes precedence; incomplete inline lookalikes,
escaped openers and invalid first characters remain authored prose.

Neighboring incomplete lowercase/indented declaration probes exposed a separate
runtime refusal defect. Their failed public controls and immutable receipts are
retained locally for [#147](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/147),
a separately scoped follow-up before actual acceptance.
This oracle repair does not claim that runtime defect is resolved. It changes
neither runtime admission nor any version beyond the version-8 meaning decision
already recorded here.

[CommonMark fenced-code ownership](https://spec.commonmark.org/0.31.2/#fenced-code-blocks)
also keeps quote/list-looking sample lines inside their existing protected leaf.
Only existing container prefixes and a real matching closer affect ownership.
Quoted/list-owned natural exits remain covered. Generated safety closures are
derived from the accumulated expected raw prefix, only when a later section
requires them; they never acquire authored spans, digests, reference credit or
adaptation counts. Full-note, exact-original, post-block literal/live-reference
and coherently rehashed missing/wrong/extra/moved-framing controls cover this seam.

For external Type2 files, absent/empty `Name` independently falls back to the
Windows basename of raw `Location` in both asset identity and Resources display.
Explicit nonempty names retain precedence. Unicode/URI-significant names and
identical basenames on distinct drives remain separate identities/destinations.
Existing drive-qualified path admission and UNC/relative/drive-relative/device/
alternate-stream refusals remain unchanged; inspection/conversion never probes,
reads or copies external targets. Rehashed wrong labels, identities, owners,
locations, URIs, roles, merged declarations and fake copies fail the raw audit.

## Versions and evidence limits

TheBrain module/profile move from 7 to 8 because the reviewed refusal meaning
changes. Source-neutral snapshot/policy/result, renderer and migration-record
shapes and meanings remain 6; BRZ format remains 5, Folio format/module/profile
remain independent, and the converter remains 0.3.0. Previous/future BRZ-profile
refusal controls and existing source-neutral version matrices remain explicit.

Five original preliminary public probes and the stopped actual run are retained
locally with hashes and immutable receipts. The historical run published thirteen
outputs, with twelve A–D raw audits passing and E held at the former raw-oracle
boundary; its repeat/reordered E variants were never completed. The current
version-8 checker intentionally refuses that historical version-7 output.
A separate read-only diagnosis copy changes only the two explicit version
expectations to their historical binding. Its byte-identical other modules,
exact counted substitutions, import origins, source/output fingerprints and
complete raw diagnosis result remain private evidence for independent review.
This qualified equivalent diagnosis does not establish a current-checker pass
or final acceptance. A new complete five-original/fifteen-output matrix belongs
to [#123](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/123); bounded native
comparison and the user's final verdict remain
[#124](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/124).

Required fresh full GUI/launcher pytest, lint, format and dependency receipts
bind the clean stable candidate, independent review and actual integration.
Structured handoffs retain criterion coverage, genuine RED/GREEN history and
separately qualified fixture/launch-authoring mistakes. No failed or partial
actual matrix substitutes for the refreshed gate.
