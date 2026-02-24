"""
services/storage_service.py – Disk space validation and final file installation.

Responsibilities
----------------
1. Check that the destination drive has enough free space.
2. Move the converted output from the temp working directory to the user-chosen
   install directory.
3. Clean up the temporary working directory on success (or leave it on failure
   so the user can recover data).
"""

import shutil
from pathlib import Path

from services.exceptions import InsufficientDiskSpaceError, StorageError

# Safety buffer: require at least this many extra bytes beyond the estimated
# file size to account for filesystem overhead, GOD container overhead, etc.
DISK_SAFETY_BUFFER_BYTES: int = 512 * 1024 * 1024  # 512 MiB


def check_disk_space(path: Path, required_bytes: int) -> None:
    """
    Verify *path* (or its nearest existing ancestor) has enough free space.

    Parameters
    ----------
    path           : Destination directory (need not exist yet).
    required_bytes : Minimum bytes needed for the download + conversion.

    Raises
    ------
    InsufficientDiskSpaceError if free space < required_bytes + safety buffer.
    StorageError on any filesystem error.
    """
    # Walk up until we find an existing directory to stat.
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent

    try:
        usage = shutil.disk_usage(probe)
    except OSError as exc:
        raise StorageError(f"Cannot check disk space on '{probe}': {exc}") from exc

    needed = required_bytes + DISK_SAFETY_BUFFER_BYTES
    if usage.free < needed:
        raise InsufficientDiskSpaceError(
            required_bytes=needed, available_bytes=usage.free
        )


def install(source_dir: Path, dest_dir: Path) -> Path:
    """
    Move the contents of *source_dir* into *dest_dir*.

    If a single sub-directory was produced (common with GOD containers and
    exiso output), that sub-directory is moved directly so the install
    directory doesn't gain an extra nesting level.

    Parameters
    ----------
    source_dir : Temporary conversion output directory.
    dest_dir   : User-chosen install directory.

    Returns
    -------
    Path to the installed directory / file.

    Raises
    ------
    StorageError on any filesystem error.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    children = list(source_dir.iterdir())
    if not children:
        raise StorageError(
            f"Conversion produced no output in '{source_dir}'. "
            "The conversion tool may have failed silently."
        )

    try:
        if len(children) == 1 and children[0].is_dir():
            # Move the single sub-directory directly.
            game_folder = children[0]
            target = dest_dir / game_folder.name
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(game_folder), str(target))
            return target
        else:
            # Multiple items – move all into a new named folder.
            # Use the source_dir name as the folder name.
            target = dest_dir / source_dir.name
            target.mkdir(exist_ok=True)
            for item in children:
                dst = target / item.name
                if dst.exists():
                    if dst.is_dir():
                        shutil.rmtree(dst)
                    else:
                        dst.unlink()
                shutil.move(str(item), str(dst))
            return target
    except OSError as exc:
        raise StorageError(
            f"Failed to move converted files to '{dest_dir}': {exc}"
        ) from exc


def cleanup_temp(temp_dir: Path) -> None:
    """
    Remove the temporary working directory and all its contents.

    Silently logs (but does not raise) if removal fails, since cleanup
    failure should not mask a successful install.
    """
    try:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
    except OSError as exc:
        # Non-fatal – leave a warning in the log but don't raise.
        import logging

        logging.getLogger(__name__).warning(
            "Could not remove temp directory '%s': %s", temp_dir, exc
        )
