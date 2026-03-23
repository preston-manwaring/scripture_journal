"""Fetch Open Graph metadata and thumbnail from a URL."""

import io
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 10


def _meta(soup: BeautifulSoup, *attrs: dict) -> str | None:
    for attr in attrs:
        tag = soup.find("meta", attrs=attr)
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def fetch_og(url: str) -> dict:
    """
    Returns a dict with keys:
      og_title, og_description, og_image (bytes|None), og_image_mime (str|None)
    Raises requests.RequestException on network failure.
    """
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.content, "html.parser")

    title = (
        _meta(soup, {"property": "og:title"})
        or _meta(soup, {"name": "twitter:title"})
        or (soup.title.string.strip() if soup.title else None)
    )
    description = (
        _meta(soup, {"property": "og:description"})
        or _meta(soup, {"name": "twitter:description"})
        or _meta(soup, {"name": "description"})
    )
    image_url = (
        _meta(soup, {"property": "og:image"})
        or _meta(soup, {"name": "twitter:image"})
    )

    og_image: bytes | None = None
    og_image_mime: str | None = None

    if image_url:
        try:
            # Make image_url absolute if relative
            if image_url.startswith("//"):
                image_url = "https:" + image_url
            elif image_url.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                image_url = f"{parsed.scheme}://{parsed.netloc}{image_url}"

            img_resp = requests.get(image_url, headers=HEADERS, timeout=TIMEOUT, stream=True)
            img_resp.raise_for_status()
            og_image = img_resp.content
            og_image_mime = img_resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        except Exception:
            pass  # Thumbnail is optional — don't fail the whole fetch

    return {
        "og_title": title,
        "og_description": description,
        "og_image": og_image,
        "og_image_mime": og_image_mime,
    }
