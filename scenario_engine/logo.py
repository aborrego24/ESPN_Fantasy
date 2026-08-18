"""Fetch team logos and inline them into the report as data URIs.

Used only by stage 1 under --logos, and only during a live pull -- the offline
engine never imports this. A member's uploaded photo is re-encoded down to a
small thumbnail so four full-size JPEGs don't bloat the one-file report; ESPN's
own logo-pack art is vector SVG and already tiny, so it goes in untouched. A
logo that can't be fetched or encoded is dropped, and the row falls back to its
monogram chip -- the report never depends on the network to render.
"""

import base64
import importlib.util
import sys
import urllib.request

THUMBNAIL_PX = 96  # the chip is displayed small; no reason to ship more pixels
JPEG_QUALITY = 80
FETCH_TIMEOUT = 12  # seconds -- one slow logo must not hang the whole pull


def _fetch(url):
    with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as response:
        return response.read(), response.headers.get_content_type()


def _is_svg(url, content_type):
    return content_type == "image/svg+xml" or url.lower().endswith(".svg")


def _data_uri(mime, raw):
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _shrink(raw):
    """Downscale a raster logo to a small JPEG. Requires Pillow."""
    from io import BytesIO

    from PIL import Image

    image = Image.open(BytesIO(raw)).convert("RGB")  # flatten alpha for JPEG
    image.thumbnail((THUMBNAIL_PX, THUMBNAIL_PX))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


def inline_logo(url, fetch=_fetch):
    """A data URI for one logo, or None if it can't be fetched/encoded.

    SVGs (ESPN's logo packs) are inlined verbatim; anything raster (a member's
    uploaded photo) is shrunk to a thumbnail first.
    """
    try:
        raw, content_type = fetch(url)
        if _is_svg(url, content_type):
            return _data_uri("image/svg+xml", raw)
        return _data_uri("image/jpeg", _shrink(raw))
    except Exception:
        return None  # a missing logo falls back to the monogram


def inline_all(url_by_name, fetch=_fetch):
    """{name: data_uri} for every logo that inlines; failures are dropped."""
    if url_by_name and importlib.util.find_spec("PIL") is None:
        # Without it, uploaded photos silently become monograms; say so once.
        print(
            "note: Pillow not installed -- uploaded-photo logos will fall back to "
            "monograms (vector SVG logos still inline). pip install Pillow",
            file=sys.stderr,
        )
    inlined = {}
    for name, url in url_by_name.items():
        uri = inline_logo(url, fetch=fetch)
        if uri:
            inlined[name] = uri
    return inlined
