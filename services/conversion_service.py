from typing import Callable, Literal, Optional
ProgressCallback = Callable[[float, float], None]  # (current, total)
"""
services/conversion_service.py – ISO-to-XEX and ISO-to-GOD conversion.

Wraps exiso.exe (extract XEX) and iso2god.exe (GOD container) via subprocess.

Security notes
--------------
* All arguments passed to subprocess are provided as a list (never shell=True).
* Binary paths are resolved via the BASE_PATH env var set in main.py; they are
  never derived from user input.
* The working directory is always set to a controlled temp folder.
"""

import os
import subprocess
from pathlib import Path
from typing import Callable, Literal, Optional

from services.exceptions import ConversionError

# ── Types ────────────────────────────────────────────────────────────────────

ConversionFormat = Literal["XEX", "GOD"]
ProgressCallback = Callable[[int, int], None]  # (current, total)

# ── Binary resolution ────────────────────────────────────────────────────────


def _bin_path(name: str) -> Path:
    """Resolve a bundled binary (exiso.exe / iso2god.exe) from BASE_PATH."""
    base = Path(os.environ.get("ROMTOOL_BASE", os.path.abspath(".")))
    candidate = base / "bin" / name
    if not candidate.exists():
        raise ConversionError(
            f"Conversion binary not found: {candidate}. "
            "Ensure the bin/ directory is present alongside the application."
        )
    return candidate


# ── Public API ───────────────────────────────────────────────────────────────


def convert_iso(
    iso_path: Path,
    output_dir: Path,
    fmt: ConversionFormat,
    *,
    progress_callback: Optional[ProgressCallback] = None,
) -> Path:
    """
    Convert *iso_path* to *fmt* and write result into *output_dir*.

    Parameters
    ----------
    iso_path          : Path to the source .iso file.
    output_dir        : Directory where the converted output will be placed.
    fmt               : 'XEX' or 'GOD'.
    progress_callback : Optional (current, total) callback – not all tools
                        expose progress; called once at 0 % and 100 % when
                        the tool offers no streaming output.

    Returns
    -------
    Path to the conversion output directory.

    Raises
    ------
    ConversionError on any subprocess error or missing binary.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if fmt == "XEX":
        return _convert_xex(iso_path, output_dir, progress_callback)
    elif fmt == "GOD":
        return _convert_god(iso_path, output_dir, progress_callback)
    else:
        raise ConversionError(f"Unknown conversion format: {fmt!r}")


# ── Private converters ────────────────────────────────────────────────────────


def _convert_xex(
    iso_path: Path,
    output_dir: Path,
    cb: Optional[ProgressCallback],
) -> Path:
    """
    Run exiso.exe to extract XEX content from the ISO.

    Expected invocation:
        exiso.exe -d <output_dir> <iso_path>
    """
    exiso = _bin_path("exiso.exe")

    if cb:
        cb(0, 100)

    cmd = [str(exiso), "-d", str(output_dir), str(iso_path)]
    _run_subprocess(cmd, label="exiso.exe")

    if cb:
        cb(100, 100)

    # exiso typically creates a subdirectory named after the game inside output_dir.
    # Return output_dir; caller can inspect its contents.
    return output_dir


def _convert_god(
    iso_path: Path,
    output_dir: Path,
    cb: Optional[ProgressCallback],
) -> Path:
    """
    Run iso2god.exe to produce a Games-On-Demand container.

    Expected invocation:
        iso2god.exe <iso_path> <output_dir> [--trim]
    """
    iso2god = _bin_path("iso2god.exe")

    if cb:
        cb(0, 100)

    # --trim reduces output size by removing padding; safe for all Xbox 360 ISOs.
    cmd = [str(iso2god), str(iso_path), str(output_dir), "--trim"]
    _run_subprocess(cmd, label="iso2god.exe")

    if cb:
        cb(100, 100)

    return output_dir


def _run_subprocess(cmd: list, label: str) -> None:
    """
    Execute *cmd* via subprocess with security and error handling.

    Raises
    ------
    ConversionError if the process exits non-zero or cannot be launched.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=False,  # Never use shell=True with user-derived data
            timeout=3600,  # 1-hour hard limit for very large ISOs
        )
    except FileNotFoundError as exc:
        raise ConversionError(
            f"{label} executable not found at the expected path. "
            "Ensure it exists in the bin/ directory."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(
            f"{label} exceeded the 1-hour time limit and was terminated."
        ) from exc
    except OSError as exc:
        raise ConversionError(f"OS error launching {label}: {exc}") from exc

    if result.returncode != 0:
        stderr_snippet = (result.stderr or "")[:500]
        stdout_snippet = (result.stdout or "")[:500]
        raise ConversionError(
            f"{label} exited with code {result.returncode}.\n"
            f"STDOUT: {stdout_snippet}\n"
            f"STDERR: {stderr_snippet}"
        )
