"""Fetch team logos and inline them into the report as data URIs.

Used only by stage 1 under --logos, and only during a live pull -- the offline
engine never imports this. A member's uploaded photo is re-encoded down to a
small thumbnail so four full-size JPEGs don't bloat the one-file report; ESPN's
own logo-pack art is vector SVG and already tiny, so it goes in untouched. A
logo that can't be fetched or encoded is dropped, and the row falls back to its
monogram chip -- the report never depends on the network to render.

Fetching an uploaded photo **needs the league cookies**; see `espn_fetch`.
"""

import base64
import importlib.util
import sys
import urllib.parse
import urllib.request

THUMBNAIL_PX = 96  # the chip is displayed small; no reason to ship more pixels
JPEG_QUALITY = 80
FETCH_TIMEOUT = 12  # seconds -- one slow logo must not hang the whole pull
# A manager may point their logo at any host, and some refuse urllib's default
# `Python-urllib/3.x`: Wikimedia answers it with 403 Forbidden and the same URL
# with 200 for an ordinary browser string. Measured on a real team whose photo
# lives on upload.wikimedia.org.
USER_AGENT = "Mozilla/5.0 (compatible; fantasy-report/1.0)"


def _fetch(url):
    return _read(urllib.request.Request(url))


def _read(request):
    request.add_header("User-Agent", USER_AGENT)
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
        return response.read(), response.headers.get_content_type()


def _is_espn(url):
    """Whether `url` points at ESPN, and so may be sent ESPN's cookies.

    `espn_s2` is a live session credential, so it goes to espn.com and nowhere
    else. Team photos are frequently self-hosted -- two teams in one real league
    point at `i.postimg.cc` -- and attaching the cookie to those requests would
    hand a third-party image host the user's ESPN session.
    """
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return host == "espn.com" or host.endswith(".espn.com")


def espn_fetch(espn_s2=None, swid=None):
    """A `fetch` that authenticates to ESPN, or the anonymous one without cookies.

    **An uploaded team photo is not public.** It is served from
    `mystique-api.fantasy.espn.com`, which answers an anonymous GET with 401
    `Unauthorized: Credentials are missing` -- measured on a real league, six of
    its ten teams. Only ESPN's own logo-pack SVGs on `g.espncdn.com` and photos a
    manager self-hosted elsewhere fetch without cookies, so before this a fully
    credentialed run still drew a monogram for every manager who had uploaded a
    picture, which looked like the feature being broken rather than a 401.

    Cookies do not resurrect a *deleted* upload: ESPN keeps the image id in an
    old season's payload after the file is gone, and those URLs return 404
    `Image not found` even when authenticated. That is a genuine absence and
    still falls back to the monogram.
    """
    if not (espn_s2 and swid):
        return _fetch
    cookie = f"espn_s2={espn_s2}; SWID={swid}"

    def fetch(url):
        headers = {"Cookie": cookie} if _is_espn(url) else {}
        return _read(urllib.request.Request(url, headers=headers))

    return fetch


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
