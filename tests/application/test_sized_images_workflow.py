"""Legacy image presentation is audited through actual ZIP Workflow and CLI."""

from io import BytesIO

from PIL import Image


def images():
    result = []
    for color, size in (("red", (4, 2)), ("blue", (3, 5))):
        stream = BytesIO()
        Image.new("RGB", size, color).save(stream, format="PNG")
        result.append(stream.getvalue())
    return result
