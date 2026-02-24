
import re
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup, Tag

from models.game_entry import GameEntry
from services.exceptions import SearchError

# ── Configuration ────────────────────────────────────────────────────────────

# Master catalogue page URL – replace with the real endpoint before packaging.
CATALOGUE_URL: str = "https://myrient.erista.me/files/Redump/Microsoft%20-%20Xbox%20360/"

# CSS selector for rows / items that contain a game link.
# Adjust to match the real site (e.g. "table#gamelist tr", "ul.games li", …).
ROW_SELECTOR: str = "tr"

# Within each row, the anchor whose text is the title and href is detail URL.
TITLE_ANCHOR_SELECTOR: str = "a"

# Optional: index of <td> that holds the region string (None = skip).
REGION_TD_INDEX: Optional[int] = 1

# Optional: index of <td> that holds the size string (None = skip).
SIZE_TD_INDEX: Optional[int] = 2

# Fallback: href pattern for plain link harvesting.
LINK_PATTERN: re.Pattern = re.compile(r"/(xbox|games?)/", re.IGNORECASE)

# HTTP timeout (seconds)
HTTP_TIMEOUT: float = 30.0

# ── Public API ───────────────────────────────────────────────────────────────


def fetch_catalogue() -> List[GameEntry]:
    """
    Download and parse the master game list.

    Returns
    -------
    List[GameEntry]
        Parsed entries; never empty on success.

    Raises
    ------
    SearchError
        On any network or parse failure.
    """
    try:
        response = httpx.get(CATALOGUE_URL, timeout=HTTP_TIMEOUT, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SearchError(
            f"Catalogue server returned HTTP {exc.response.status_code}."
        ) from exc
    except httpx.RequestError as exc:
        raise SearchError(f"Network error while fetching catalogue: {exc}") from exc

    html = response.text
    entries = _parse_catalogue(html, base_url=str(response.url))

    if not entries:
        raise SearchError(
            "Catalogue page was retrieved but no game entries could be parsed. "
            "The site structure may have changed – update the CSS selectors in "
            "services/search_service.py."
        )

    return entries


def search(entries: List[GameEntry], query: str) -> List[GameEntry]:
    """
    Case-insensitive in-memory filter.

    Parameters
    ----------
    entries : Full catalogue list returned by fetch_catalogue().
    query   : User-supplied search string.

    Returns
    -------
    Filtered list; returns all entries when query is empty/whitespace.
    """
    q = query.strip().lower()
    if not q:
        return entries
    return [e for e in entries if q in e.title.lower()]


def fetch_mirrors(game: GameEntry) -> List["MirrorLink"]:  # noqa: F821
    """
    Fetch the game's detail page and extract all mirror download links.

    Returns
    -------
    List[MirrorLink]
        At least one mirror on success.

    Raises
    ------
    SearchError
        On network failure or when no mirrors are found.
    """
    from models.game_entry import MirrorLink  # local import to avoid circular

    try:
        response = httpx.get(
            game.detail_url, timeout=HTTP_TIMEOUT, follow_redirects=True
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SearchError(
            f"Game detail page returned HTTP {exc.response.status_code}."
        ) from exc
    except httpx.RequestError as exc:
        raise SearchError(f"Network error fetching mirror list: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    mirrors: List[MirrorLink] = []

    # Strategy 1 – links explicitly labelled as mirrors / downloads.
    for anchor in soup.find_all("a", href=True):
        href: str = anchor["href"].strip()
        text: str = anchor.get_text(strip=True) or href

        # Accept direct archive / ISO links and anything with "mirror" / "download"
        if _is_download_link(href, text):
            absolute = _make_absolute(href, str(response.url))
            mirrors.append(MirrorLink(label=text, url=absolute))

    if not mirrors:
        raise SearchError(
            f"No download mirrors found on the detail page for '{game.title}'. "
            "The page structure may have changed."
        )

    # De-duplicate by URL while preserving order.
    seen: set = set()
    unique: List[MirrorLink] = []
    for m in mirrors:
        if m.url not in seen:
            seen.add(m.url)
            unique.append(m)

    return unique


# ── Private helpers ───────────────────────────────────────────────────────────


def _parse_catalogue(html: str, base_url: str) -> List[GameEntry]:
    """Try structured parse first; fall back to plain link harvesting."""
    soup = BeautifulSoup(html, "html.parser")
    entries = _structured_parse(soup, base_url)
    if not entries:
        entries = _fallback_parse(soup, base_url)
    return entries


def _structured_parse(soup: BeautifulSoup, base_url: str) -> List[GameEntry]:
    entries: List[GameEntry] = []
    for row in soup.select(ROW_SELECTOR):
        anchor = row.select_one(TITLE_ANCHOR_SELECTOR)
        if not anchor or not anchor.get("href"):
            continue
        title = anchor.get_text(strip=True)
        href = anchor["href"].strip()
        if not title or not href:
            continue

        cells = row.find_all("td")
        region = _safe_cell_text(cells, REGION_TD_INDEX)
        size = _safe_cell_text(cells, SIZE_TD_INDEX)

        entries.append(
            GameEntry(
                title=title,
                detail_url=_make_absolute(href, base_url),
                region=region,
                size_hint=size,
            )
        )
    return entries


def _fallback_parse(soup: BeautifulSoup, base_url: str) -> List[GameEntry]:
    entries: List[GameEntry] = []
    for anchor in soup.find_all("a", href=True):
        href: str = anchor["href"].strip()
        if not LINK_PATTERN.search(href):
            continue
        title = anchor.get_text(strip=True)
        if not title:
            continue
        entries.append(
            GameEntry(title=title, detail_url=_make_absolute(href, base_url))
        )
    return entries


def _safe_cell_text(cells: list, index: Optional[int]) -> str:
    if index is None or index >= len(cells):
        return ""
    return cells[index].get_text(strip=True)


def _make_absolute(href: str, base_url: str) -> str:
    """Resolve a potentially-relative URL against the page base URL."""
    if href.startswith(("http://", "https://")):
        return href
    from urllib.parse import urljoin

    return urljoin(base_url, href)


def _is_download_link(href: str, text: str) -> bool:
    """Heuristic: is this anchor pointing to a downloadable file?"""
    download_extensions = (
        ".iso", ".zip", ".rar", ".7z", ".part1.rar", ".001"
    )
    download_keywords = ("mirror", "download", "direct", "link", "get")

    href_lower = href.lower()
    text_lower = text.lower()

    return any(href_lower.endswith(ext) for ext in download_extensions) or any(
        kw in text_lower for kw in download_keywords
    )
