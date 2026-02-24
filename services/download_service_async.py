"""
services/download_service_async.py – Async file download with progress callbacks.

Uses httpx.AsyncClient for parallel downloads. Progress callback (bytes_downloaded, total_bytes) is called periodically.
"""

import os
from pathlib import Path
from typing import Callable, Optional
import asyncio
import httpx

from services.exceptions import DownloadError

CHUNK_SIZE: int = 1024 * 1024  # 1 MiB
CONNECT_TIMEOUT: float = 30.0
MAX_RETRIES: int = 3

ProgressCallback = Callable[[int, int], None]

async def download_file_async(
    url: str,
    dest_dir: Path,
    *,
    progress_callback: Optional[ProgressCallback] = None,
    filename_override: Optional[str] = None,
) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await _attempt_download_async(
                url, dest_dir, progress_callback, filename_override
            )
        except DownloadError as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                await _cleanup_partial_async(dest_dir, filename_override or _filename_from_url(url))
            continue
    raise DownloadError(
        f"Download failed after {MAX_RETRIES} attempts. Last error: {last_error}"
    ) from last_error

async def _attempt_download_async(
    url: str,
    dest_dir: Path,
    progress_callback: Optional[ProgressCallback],
    filename_override: Optional[str],
) -> Path:
    timeout = httpx.Timeout(connect=CONNECT_TIMEOUT, read=None, write=None, pool=None)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            resp = await client.get(url, stream=True)
            resp.raise_for_status()
            filename = (
                filename_override
                or _filename_from_headers(resp.headers)
                or _filename_from_url(url)
                or "download.bin"
            )
            filename = Path(filename).name
            dest_path = dest_dir / filename
            total_bytes = int(resp.headers.get("content-length", -1))
            downloaded = 0
            with open(dest_path, "wb") as fh:
                async for chunk in resp.aiter_bytes(chunk_size=CHUNK_SIZE):
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

def _filename_from_headers(headers: httpx.Headers) -> Optional[str]:
    cd = headers.get("content-disposition", "")
    if not cd:
        return None
    for part in cd.split(";"):
        part = part.strip()
        if part.lower().startswith("filename="):
            name = part[len("filename="):].strip().strip('"').strip("'")
            return name or None
    return None

def _filename_from_url(url: str) -> str:
    from urllib.parse import urlparse, unquote
    parsed = urlparse(url)
    name = unquote(parsed.path.split("/")[-1])
    return name if name else "download.bin"

async def _cleanup_partial_async(dest_dir: Path, filename: str) -> None:
    partial = dest_dir / filename
    try:
        if partial.exists():
            partial.unlink()
    except OSError:
        pass
