def _attempt_download(
    url: str,
    dest_dir: Path,
    progress_callback: Optional[ProgressCallback],
    filename_override: Optional[str],
    cancel_event: Optional[object],
) -> Path:
    timeout = httpx.Timeout(connect=CONNECT_TIMEOUT, read=None, write=None, pool=None)

    try:
        with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as resp:
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise DownloadError(
                    f"Server returned HTTP {exc.response.status_code} for URL: {url}"
                ) from exc

            filename = (
                filename_override
                or _filename_from_headers(resp.headers)
                or _filename_from_url(url)
                or "download.bin"
            )
            # Sanitise filename – strip path components.
            filename = Path(filename).name

            dest_path = dest_dir / filename

            total_bytes = int(resp.headers.get("content-length", -1))
            downloaded = 0

            with open(dest_path, "wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=CHUNK_SIZE):
                    if cancel_event and cancel_event.is_set():
                        raise DownloadError("Download cancelled by user.")
                    if not chunk:
                        continue
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total_bytes)

    except httpx.RequestError as exc:
        raise DownloadError(f"Network error during download: {exc}") from exc
    except OSError as exc:
        raise DownloadError(f"I/O error writing download to disk: {exc}") from exc

    return dest_path
# ── Public API ───────────────────────────────────────────────────────────────
def download_file(
    url: str,
    dest_dir: Path,
    *,
    progress_callback: Optional[ProgressCallback] = None,
    filename_override: Optional[str] = None,
    cancel_event: Optional[object] = None,
) -> Path:
    """
    Stream-download *url* into *dest_dir*.

    Parameters
    ----------
    url               : Direct download URL.
    dest_dir          : Directory where the file will be written.
    progress_callback : Optional callable receiving (downloaded, total).
    filename_override : Force a specific filename; otherwise derived from URL /
                        Content-Disposition header.
    cancel_event      : Optional event to cancel the download.

    Returns
    -------
    Path to the downloaded file.

    Raises
        if progress_callback:
            progress_callback(0, -1)
    ------
    DownloadError on any network or I/O failure.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return _attempt_download(
                url, dest_dir, progress_callback, filename_override, cancel_event
            )
        except DownloadError as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                # Clean up any partial file before retrying.
                _cleanup_partial(dest_dir, filename_override or _filename_from_url(url))
            continue

    raise DownloadError(
        f"Download failed after {MAX_RETRIES} attempts. Last error: {last_error}"
    ) from last_error
"""
services/download_service.py – Streaming file download with progress callbacks.

Uses httpx in streaming mode so large ISO files are never loaded fully into
memory.  A progress callback (bytes_downloaded, total_bytes_or_-1) is called
periodically so the UI can update its progress bar.
"""

import os
from pathlib import Path
from typing import Callable, Optional

import httpx

from services.exceptions import DownloadError

# ── Configuration ────────────────────────────────────────────────────────────
CHUNK_SIZE: int = 1024 * 1024  # 1 MiB
CONNECT_TIMEOUT: float = 30.0
MAX_RETRIES: int = 3

# ── Types ────────────────────────────────────────────────────────────────────
ProgressCallback = Callable[[int, int], None]

def _filename_from_headers(headers: httpx.Headers) -> Optional[str]:
    """Extract filename from Content-Disposition header if present."""
    cd = headers.get("content-disposition", "")
    if not cd:
        return None
    # e.g.  attachment; filename="game.iso"
    for part in cd.split(";"):
        part = part.strip()
        if part.lower().startswith("filename="):
            name = part[len("filename="):].strip().strip('"').strip("'")
            return name or None
    return None

def _filename_from_url(url: str) -> str:
    """Derive a filename from the last path segment of the URL."""
    from urllib.parse import urlparse, unquote
    parsed = urlparse(url)
    name = unquote(parsed.path.split("/")[-1])
    return name if name else "download.bin"


def _cleanup_partial(dest_dir: Path, filename: str) -> None:
    partial = dest_dir / filename
    try:
        if partial.exists():
            partial.unlink()
    except OSError:
        pass
