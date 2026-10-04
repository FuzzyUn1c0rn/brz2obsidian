"""The reviewed URL/metadata forms, interpreted as facts without executing HTML."""

import re
from urllib.parse import parse_qs, urlsplit

from brz2obsidian.contracts import VideoPresentation

_VIDEO_ID = r"[A-Za-z0-9_-]{11}"
_REVIEWED_HTML = re.compile(
    r"<iframe width='100%' height='100%' "
    r"src='https://www\.youtube\.com/embed/(?P<video_id>"
    + _VIDEO_ID
    + r")\?start=0' frameborder='0'></iframe>"
)


def reviewed_video(record, refuse):
    html = record.get("VideoHtml")
    if html is None or html == "":
        return None
    affected = (record["Id"],)
    if type(html) is not str:
        refuse("invalid_source", "Video metadata must be text or null", affected)
    if (record["SourceType"], record["Type"], record["NoteType"]) != (2, 3, 0):
        refuse(
            "unsupported_feature", "Video metadata requires an external URL", affected
        )
    metadata = _REVIEWED_HTML.fullmatch(html)
    uri = urlsplit(record["Location"])
    query = parse_qs(uri.query, keep_blank_values=True)
    if (
        metadata is None
        or record["DataLength"] != 0
        or uri.scheme != "https"
        or uri.netloc != "www.youtube.com"
        or uri.path != "/watch"
        or uri.fragment
        or set(query) not in ({"v"}, {"v", "t"})
        or len(query.get("v", [])) != 1
        or not re.fullmatch(_VIDEO_ID, query["v"][0])
    ):
        refuse(
            "unsupported_feature", "Video provider or metadata is unreviewed", affected
        )
    video_id = query["v"][0]
    if metadata["video_id"] != video_id:
        refuse("invalid_source", "Video URL and metadata identities conflict", affected)
    start = 0
    if "t" in query:
        if len(query["t"]) != 1 or not re.fullmatch(r"[0-9]+s", query["t"][0]):
            refuse("unsupported_feature", "Video timing syntax is unreviewed", affected)
        start = int(query["t"][0][:-1])
    return VideoPresentation(
        provider="youtube",
        embed_uri=f"https://www.youtube.com/embed/{video_id}?start={start}",
        start_seconds=start,
    )
