"""Reviewed external video resources through real workflow and CLI boundaries."""

from tests.application.test_verified_coverage import (
    add_attachment,
    change_record,
    source_parts,
)

VIDEO = "88888888-8888-4888-8888-888888888888"
VIDEO_ID = "SYNTHVID001"
URL = "https://www.youtube.com/watch?v=SYNTHVID001&t=18s"
HTML = (
    "<iframe width='100%' height='100%' "
    "src='https://www.youtube.com/embed/SYNTHVID001?start=0' "
    "frameborder='0'></iframe>"
)
EMBED = "https://www.youtube.com/embed/SYNTHVID001?start=18"


def video_parts(tmp_path, url=URL, html=HTML):
    parts = source_parts(tmp_path)
    add_attachment(parts, VIDEO, 3, url, state=None)
    change_record(parts, VIDEO, Name="Reviewed video", VideoHtml=html)
    return parts
