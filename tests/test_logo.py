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


# --- espn_fetch: an uploaded photo needs the cookies, a stranger must not get them


class FakeResponse:
    """Just enough of an http.client.HTTPResponse for _read."""

    def __init__(self):
        self.headers = type("H", (), {"get_content_type": lambda self: "image/svg+xml"})()

    def read(self):
        return b"<svg/>"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def capture_requests(monkeypatch):
    """Collect the urllib Requests logo would have sent, sending none."""
    sent = []

    def urlopen(request, timeout=None):
        sent.append(request)
        return FakeResponse()

    monkeypatch.setattr(logo.urllib.request, "urlopen", urlopen)
    return sent


def test_an_espn_upload_is_fetched_with_the_league_cookies(monkeypatch):
    """The whole point: mystique-api 401s anonymously, so a credentialed run
    must authenticate or every uploaded photo silently becomes a monogram."""
    sent = capture_requests(monkeypatch)

    logo.espn_fetch("S2VALUE", "{SWID-VALUE}")(
        "https://mystique-api.fantasy.espn.com/apis/v1/domains/lm/images/abc"
    )

    assert sent[0].get_header("Cookie") == "espn_s2=S2VALUE; SWID={SWID-VALUE}"


def test_a_third_party_photo_host_is_never_sent_the_espn_session(monkeypatch):
    """espn_s2 is a live credential and many team photos are self-hosted, so the
    cookie is scoped to espn.com rather than attached to every logo request."""
    sent = capture_requests(monkeypatch)
    fetch = logo.espn_fetch("S2VALUE", "{SWID-VALUE}")

    fetch("https://i.postimg.cc/vH6jBp6y/IMG-8279.jpg")
    fetch("https://espn.com.evil.test/logo.svg")

    assert sent[0].get_header("Cookie") is None
    assert sent[1].get_header("Cookie") is None, "a lookalike host is not espn.com"


def test_every_request_carries_a_browser_user_agent(monkeypatch):
    """Wikimedia 403s urllib's default agent, and a real team hosts its photo
    there -- so the header goes on every request, cookies or not."""
    sent = capture_requests(monkeypatch)

    logo._fetch("https://upload.wikimedia.org/x.jpg")
    logo.espn_fetch("S2", "{SW}")("https://upload.wikimedia.org/y.jpg")

    assert len(sent) == 2
    for request in sent:
        assert request.get_header("User-agent") == logo.USER_AGENT


def test_espn_subdomains_and_the_bare_domain_both_count():
    assert logo._is_espn("https://g.espncdn.com/x.svg") is False, "a different domain"
    assert logo._is_espn("https://mystique-api.fantasy.espn.com/x") is True
    assert logo._is_espn("https://espn.com/x") is True


def test_without_cookies_espn_fetch_is_the_plain_anonymous_one():
    """A public league passes None for both and must behave exactly as before."""
    assert logo.espn_fetch(None, None) is logo._fetch
    assert logo.espn_fetch("s2", None) is logo._fetch, "half a credential is none"
