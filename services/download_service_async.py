
"""
services/download_service_async.py – Download assíncrono otimizado, multipart, racing, resume, telemetria e perfis.

Pipeline de alta performance:
* HTTP/2+ (httpx)
* Download multipart (quando suportado)
* Mirror racing
* Resume real
* Escrita concorrente
* Perfis configuráveis
* Telemetria avançada
"""


import os
import math
import json
import aiofiles
from pathlib import Path
from typing import Callable, Optional, List, Dict, Any
import asyncio
import httpx

from services.exceptions import DownloadError
from services.download_profiles import get_profile

# Tipos
ProgressCallback = Callable[[int, int, Dict[str, Any]], None]  # bytes, total, telemetria

# Estado de partes para resume
class PartState:
    def __init__(self, idx: int, start: int, end: int, done: bool = False, downloaded: int = 0):
        self.idx = idx
        self.start = start
        self.end = end
        self.done = done
        self.downloaded = downloaded

class DownloadTelemetry:
    def __init__(self):
        self.instant_speed = 0.0
        self.avg_speed = 0.0
        self.peak_speed = 0.0
        self.eta = -1
        self.active_conns = 0
        self.mode = "single-stream"

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

# --- Função principal (esqueleto inicial) ---


async def download_file_optimized(
    url: str,
    dest_dir: Path,
    *,
    mirrors: Optional[List[str]] = None,
    profile: str = "aggressive",
    progress_callback: Optional[ProgressCallback] = None,
    filename_override: Optional[str] = None,
    resume: bool = True,
    verify_ssl: bool = True,
) -> Path:
    """
    Download otimizado com pipeline de alta performance, incluindo mirror racing.
    """
    cfg = get_profile(profile)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # --- Mirror racing ---
    probe_size = 2 * 1024 * 1024  # 2 MiB para probe
    probe_timeout = cfg["probe_timeout"]
    candidate_urls = [url] if not mirrors else mirrors

    async def probe_mirror(murl):
        try:
            async with httpx.AsyncClient(http2=True, timeout=probe_timeout, follow_redirects=True, verify=verify_ssl) as client:
                start = asyncio.get_event_loop().time()
                resp = await client.get(murl, headers={"Range": f"bytes=0-{probe_size-1}"}, stream=True)
                resp.raise_for_status()
                n = 0
                async for chunk in resp.aiter_bytes(1024 * 256):
                    n += len(chunk)
                    if n >= probe_size:
                        break
                elapsed = asyncio.get_event_loop().time() - start
                speed = n / elapsed if elapsed > 0 else 0
                return {"url": murl, "latency": elapsed, "speed": speed}
        except Exception:
            return {"url": murl, "latency": float("inf"), "speed": 0}

    # Probe paralelo
    probe_results = await asyncio.gather(*[probe_mirror(u) for u in candidate_urls])
    # Score: prioriza maior throughput, depois menor latência
    probe_results.sort(key=lambda r: (-r["speed"], r["latency"]))
    best_url = probe_results[0]["url"]

    # --- Download pipeline (igual antes, mas usando best_url) ---
    async with httpx.AsyncClient(http2=True, timeout=cfg["probe_timeout"], follow_redirects=True, verify=verify_ssl) as client:
        # Usar GET com Range: bytes=0-0 para máxima compatibilidade
        head = await client.get(best_url, headers={"Range": "bytes=0-0"})
        head.raise_for_status()
        accept_ranges = head.headers.get("accept-ranges", "none").lower() == "bytes"
        total_bytes = int(head.headers.get("content-range", head.headers.get("content-length", -1)).split("/")[-1]) if "content-range" in head.headers else int(head.headers.get("content-length", -1))
        filename = (
            filename_override
            or _filename_from_headers(head.headers)
            or _filename_from_url(best_url)
            or "download.bin"
        )
        filename = Path(filename).name
        dest_path = dest_dir / filename

        state_path = dest_dir / (filename + ".state.json")
        part_states = []
        if accept_ranges and total_bytes > 0:
            num_parts = min(cfg["max_parts"], max(1, total_bytes // cfg["chunk_size"]))
            part_size = math.ceil(total_bytes / num_parts)
            for i in range(num_parts):
                start = i * part_size
                end = min(start + part_size, total_bytes) - 1
                part_states.append({"idx": i, "start": start, "end": end, "done": False, "downloaded": 0})
            if resume and state_path.exists():
                try:
                    with open(state_path, "r") as f:
                        saved = json.load(f)
                        for s, p in zip(saved, part_states):
                            p["done"] = s.get("done", False)
                            p["downloaded"] = s.get("downloaded", 0)
                except Exception:
                    pass
        else:
            part_states = [{"idx": 0, "start": 0, "end": total_bytes-1 if total_bytes>0 else None, "done": False, "downloaded": 0}]

        async def download_part(part, telem_state):
            headers = {"Range": f"bytes={part['start']}-{part['end']}"} if accept_ranges and part["end"] is not None else {}
            retries = 0
            chunk_size = cfg["chunk_size"]
            while retries < cfg["retry_policy"] and not part["done"]:
                try:
                    async with client.stream("GET", best_url, headers=headers) as resp:
                        resp.raise_for_status()
                        offset = part["start"]
                        async with aiofiles.open(dest_path, "rb+" if dest_path.exists() else "wb") as f:
                            await f.seek(offset)
                            last_time = asyncio.get_event_loop().time()
                            last_bytes = part["downloaded"]
                            speeds = []
                            async for chunk in resp.aiter_bytes(chunk_size):
                                if not chunk:
                                    continue
                                await f.write(chunk)
                                part["downloaded"] += len(chunk)
                                now = asyncio.get_event_loop().time()
                                dt = now - last_time
                                if dt > 0.2:
                                    inst_speed = (part["downloaded"] - last_bytes) / dt
                                    speeds.append(inst_speed)
                                    last_time = now
                                    last_bytes = part["downloaded"]
                                    # Chunk size autotuning (simples)
                                    if len(speeds) > 4:
                                        avg = sum(speeds[-4:]) / 4
                                        if avg > 20 * 1024 * 1024 and chunk_size < 16 * 1024 * 1024:
                                            chunk_size *= 2
                                        elif avg < 2 * 1024 * 1024 and chunk_size > 512 * 1024:
                                            chunk_size //= 2
                                if progress_callback:
                                    # Telemetria avançada
                                    total_downloaded = sum(p["downloaded"] for p in part_states)
                                    elapsed = now - telem_state["start_time"]
                                    inst_speed = (total_downloaded - telem_state["last_bytes"]) / (now - telem_state["last_time"]) if now > telem_state["last_time"] else 0
                                    telem_state["last_time"] = now
                                    telem_state["last_bytes"] = total_downloaded
                                    telem_state["inst_speed"] = inst_speed
                                    telem_state["avg_speed"] = total_downloaded / elapsed if elapsed > 0 else 0
                                    telem_state["peak_speed"] = max(telem_state.get("peak_speed", 0), inst_speed)
                                    remaining = total_bytes - total_downloaded
                                    eta = remaining / telem_state["avg_speed"] if telem_state["avg_speed"] > 0 else -1
                                    telem = {
                                        "part": part["idx"],
                                        "mode": "multipart" if accept_ranges else "single-stream",
                                        "inst_speed": telem_state["inst_speed"],
                                        "avg_speed": telem_state["avg_speed"],
                                        "peak_speed": telem_state["peak_speed"],
                                        "eta": eta,
                                        "active_conns": telem_state["active_conns"],
                                    }
                                    progress_callback(total_downloaded, total_bytes, telem)
                        part["done"] = True
                        with open(state_path, "w") as sf:
                            json.dump(part_states, sf)
                except Exception:
                    retries += 1
                    await asyncio.sleep(0.5 * (2 ** retries))

        if not dest_path.exists() or os.path.getsize(dest_path) != total_bytes:
            with open(dest_path, "wb") as f:
                if total_bytes > 0:
                    f.truncate(total_bytes)


        # Telemetria global
        telem_state = {
            "start_time": asyncio.get_event_loop().time(),
            "last_time": asyncio.get_event_loop().time(),
            "last_bytes": 0,
            "inst_speed": 0.0,
            "avg_speed": 0.0,
            "peak_speed": 0.0,
            "active_conns": 0,
        }

        async def part_wrapper(part):
            telem_state["active_conns"] += 1
            try:
                await download_part(part, telem_state)
            finally:
                telem_state["active_conns"] -= 1

        await asyncio.gather(*[part_wrapper(p) for p in part_states if not p["done"]])

        if all(p["done"] for p in part_states):
            if state_path.exists():
                os.remove(state_path)
        return dest_path

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
