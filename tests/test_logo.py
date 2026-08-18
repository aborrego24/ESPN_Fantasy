"""Fetching and inlining team logos.

Every test injects a fake fetch, so nothing here touches the network. Pillow is
a real dependency of the raster path and is exercised with an in-memory image.
"""

import base64
from io import BytesIO

import pytest

import logo


def fetch_returning(raw, content_type):
    return lambda url: (raw, content_type)


def decode(data_uri):
    """The (mime, bytes) a data URI carries back."""
    head, b64 = data_uri.split(",", 1)
    assert head.startswith("data:") and head.endswith(";base64")
    return head[len("data:"): -len(";base64")], base64.b64decode(b64)


# --- SVG: inlined verbatim -----------------------------------------------------


def test_an_svg_is_inlined_untouched():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="5"/></svg>'
    uri = logo.inline_logo("http://x/logo.svg", fetch=fetch_returning(svg, "image/svg+xml"))

    mime, raw = decode(uri)
    assert mime == "image/svg+xml"
    assert raw == svg, "vector art must not be re-encoded"


def test_the_svg_suffix_alone_is_enough_even_without_a_content_type():
    svg = b"<svg/>"
    uri = logo.inline_logo(
        "http://x/thing.SVG", fetch=fetch_returning(svg, "application/octet-stream")
    )

    assert decode(uri)[0] == "image/svg+xml"


# --- raster: fetched, shrunk, re-encoded as JPEG -------------------------------


def a_png(width, height):
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (width, height), (10, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_a_raster_logo_is_thumbnailed_and_becomes_jpeg():
    big = a_png(400, 300)
    uri = logo.inline_logo("http://x/photo.png", fetch=fetch_returning(big, "image/png"))

    mime, raw = decode(uri)
    assert mime == "image/jpeg", "rasters are re-encoded to JPEG for size"

    from PIL import Image

    thumb = Image.open(BytesIO(raw))
    assert max(thumb.size) <= logo.THUMBNAIL_PX, "downscaled to the thumbnail box"
    assert thumb.width == 96 and thumb.height == 72, "aspect ratio is kept"


def test_a_photo_shrinks_rather_than_grows():
    big = a_png(800, 800)
    _, raw = decode(
        logo.inline_logo("http://x/p.jpg", fetch=fetch_returning(big, "image/jpeg"))
    )

    assert len(raw) < len(big)


# --- failure falls back to nothing (the caller draws a monogram) ---------------


def test_a_fetch_that_raises_yields_none():
    def boom(url):
        raise OSError("network down")

    assert logo.inline_logo("http://x/y.svg", fetch=boom) is None


def test_undecodable_bytes_yield_none():
    uri = logo.inline_logo(
        "http://x/broken.png", fetch=fetch_returning(b"not an image", "image/png")
    )
    assert uri is None


# --- inline_all: keep what works, drop what does not ---------------------------


def test_inline_all_drops_only_the_failures():
    svg = b"<svg/>"
    urls = {"Good": "http://x/g.svg", "Bad": "http://x/b.svg"}

    def fetch(url):
        if url.endswith("b.svg"):
            raise OSError
        return svg, "image/svg+xml"

    out = logo.inline_all(urls, fetch=fetch)

    assert set(out) == {"Good"}, "a team whose logo fails is simply absent"
    assert out["Good"].startswith("data:image/svg+xml;base64,")
