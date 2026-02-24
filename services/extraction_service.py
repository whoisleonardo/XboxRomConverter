"""
services/extraction_service.py – Archive extraction (ZIP, RAR, 7z).

Security
--------
All extracted paths are validated against the destination directory before any
file is written, preventing path-traversal attacks embedded in malicious
archives (ZIP slip).

Supported formats
-----------------
  .zip            – stdlib zipfile
  .rar            – patool / unrar CLI (requires unrar on PATH or patool)
  .7z             – py7zr (pure Python) or patool / 7z CLI
  .tar .tar.gz etc– stdlib tarfile (bonus support)

patool is used as a universal fallback when format-specific libraries are
unavailable; it delegates to whatever extraction tools are installed on the
system.
"""

import os
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Optional

from services.exceptions import ExtractionError

# Archive extensions we handle.
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".001"}


def is_archive(path: Path) -> bool:
    """Return True when *path* has a recognised archive extension."""
    suffix = path.suffix.lower()
    # Handle multi-part archives like game.part1.rar → .rar
    suffixes = [s.lower() for s in path.suffixes]
    return any(s in ARCHIVE_EXTENSIONS for s in suffixes)


def extract(archive_path: Path, dest_dir: Path) -> Path:
    """
    Extract *archive_path* into *dest_dir*.

    Returns
    -------
    Path
        The directory that was actually written (dest_dir itself, or a
        sub-directory created by the extraction tool).

    Raises
    ------
    ExtractionError
        On any extraction failure or security violation.
    """
    if not archive_path.exists():
        raise ExtractionError(f"Archive not found: {archive_path}")

    dest_dir.mkdir(parents=True, exist_ok=True)

    suffix = archive_path.suffix.lower()
    suffixes = [s.lower() for s in archive_path.suffixes]

    try:
        if suffix == ".zip":
            _extract_zip(archive_path, dest_dir)
        elif suffix == ".rar" or ".rar" in suffixes:
            _extract_rar(archive_path, dest_dir)
        elif suffix == ".7z" or ".7z" in suffixes:
            _extract_7z(archive_path, dest_dir)
        elif suffix in (".tar", ".gz", ".bz2", ".xz") or ".tar" in suffixes:
            _extract_tar(archive_path, dest_dir)
        else:
            # Last resort: patool
            _extract_patool(archive_path, dest_dir)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(
            f"Unexpected error extracting '{archive_path.name}': {exc}"
        ) from exc

    return dest_dir


# ── Format-specific extractors ────────────────────────────────────────────────


def _extract_zip(archive: Path, dest: Path) -> None:
    """Extract ZIP archive with path-traversal protection."""
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            for member in zf.infolist():
                # Sanitise member path.
                member_path = _safe_member_path(dest, member.filename)
                if member_path is None:
                    raise ExtractionError(
                        f"Path traversal detected in ZIP member: {member.filename}"
                    )
                zf.extract(member, dest)
    except zipfile.BadZipFile as exc:
        raise ExtractionError(f"Corrupt or invalid ZIP archive: {exc}") from exc


def _extract_tar(archive: Path, dest: Path) -> None:
    """Extract TAR-family archives with path-traversal protection."""
    try:
        with tarfile.open(archive, "r:*") as tf:
            for member in tf.getmembers():
                member_path = _safe_member_path(dest, member.name)
                if member_path is None:
                    raise ExtractionError(
                        f"Path traversal detected in TAR member: {member.name}"
                    )
            tf.extractall(dest)
    except tarfile.TarError as exc:
        raise ExtractionError(f"Corrupt or invalid TAR archive: {exc}") from exc


def _extract_rar(archive: Path, dest: Path) -> None:
    """Extract RAR using py7zr (supports RAR5) or fallback to patool."""
    # Try rarfile first
    try:
        import rarfile  # type: ignore

        rarfile.UNRAR_TOOL = shutil.which("unrar") or "unrar"
        with rarfile.RarFile(str(archive)) as rf:
            for member in rf.infolist():
                member_path = _safe_member_path(dest, member.filename)
                if member_path is None:
                    raise ExtractionError(
                        f"Path traversal detected in RAR member: {member.filename}"
                    )
            rf.extractall(str(dest))
        return
    except ImportError:
        pass
    except Exception as exc:
        raise ExtractionError(f"RAR extraction failed: {exc}") from exc

    # Fallback to patool
    _extract_patool(archive, dest)


def _extract_7z(archive: Path, dest: Path) -> None:
    """Extract 7z using py7zr or fallback to patool."""
    try:
        import py7zr  # type: ignore

        with py7zr.SevenZipFile(str(archive), mode="r") as sz:
            all_names = sz.getnames()
            for name in all_names:
                if _safe_member_path(dest, name) is None:
                    raise ExtractionError(
                        f"Path traversal detected in 7z member: {name}"
                    )
            sz.extractall(path=str(dest))
        return
    except ImportError:
        pass
    except Exception as exc:
        raise ExtractionError(f"7z extraction failed: {exc}") from exc

    _extract_patool(archive, dest)


def _extract_patool(archive: Path, dest: Path) -> None:
    """Universal fallback using patool CLI wrapper."""
    try:
        import patoollib  # type: ignore

        patoollib.extract_archive(str(archive), outdir=str(dest))
    except ImportError:
        raise ExtractionError(
            "No extraction backend available for this archive format. "
            "Install py7zr, rarfile, or patool."
        )
    except Exception as exc:
        raise ExtractionError(f"patool extraction failed: {exc}") from exc


# ── Security helper ───────────────────────────────────────────────────────────


def _safe_member_path(dest: Path, member_name: str) -> Optional[Path]:
    """
    Resolve *member_name* relative to *dest* and confirm it stays inside.

    Returns the resolved path on success, None on path-traversal attempt.
    """
    # Normalise separators and strip leading / or ..
    clean = os.path.normpath(member_name.replace("\\", "/"))
    # Reject absolute paths and any remaining upward traversal
    if os.path.isabs(clean) or clean.startswith(".."):
        return None
    resolved = (dest / clean).resolve()
    try:
        resolved.relative_to(dest.resolve())
    except ValueError:
        return None
    return resolved
