"""
workers/install_worker.py – Background QThread worker that orchestrates the
full download → extract → convert → install pipeline.

Signal contract
---------------
  progress(int, int)   : (bytes_done, bytes_total)  — for the progress bar
  status(str)          : Human-readable status message — for the log area
  finished(str)        : Install path on success
  error(str)           : User-friendly error message on failure

The worker intentionally keeps all service calls inside try/except blocks so
that a single failure emits error() rather than crashing the entire thread.
Temp files are preserved on failure for manual recovery.
"""

import tempfile
import uuid
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal

from models.game_entry import MirrorLink
from services import (
    download_service,
    extraction_service,
    conversion_service,
    storage_service,
)
from services.conversion_service import ConversionFormat
from services.exceptions import (
    DownloadError,
    ExtractionError,
    ConversionError,
    StorageError,
    InsufficientDiskSpaceError,
    ROMToolError,
)

# Estimated bytes needed when Content-Length is absent (used for disk check).
# Default to 9 GiB (maximum single-layer DVD9 ISO + conversion overhead).
FALLBACK_SIZE_ESTIMATE: int = 9 * 1024 ** 3


class InstallWorker(QThread):
    """
    Runs the full install pipeline on a background thread.

    Instantiate, connect signals, then call start().
    """

    # ── Signals ───────────────────────────────────────────────────────────────
    progress = Signal(float, float)    # (downloaded_bytes, total_bytes)
    status   = Signal(str)         # status log message
    finished = Signal(str)         # absolute install path
    error    = Signal(str)         # user-facing error message

    def __init__(
        self,
        mirror: MirrorLink,
        install_dir: Path,
        fmt: ConversionFormat,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._mirror      = mirror
        self._install_dir = install_dir
        self._fmt         = fmt
        self._temp_dir: Optional[Path] = None

    # ── QThread entry point ───────────────────────────────────────────────────

    def run(self) -> None:
        """Main pipeline executed on the worker thread."""
        try:
            self._run_pipeline()
        except InsufficientDiskSpaceError as exc:
            self.error.emit(
                f"Not enough disk space.\n"
                f"Required: {exc.required_bytes / 1024**3:.1f} GiB  |  "
                f"Available: {exc.available_bytes / 1024**3:.1f} GiB"
            )
        except DownloadError as exc:
            self.error.emit(f"Download failed:\n{exc}")
        except ExtractionError as exc:
            self.error.emit(f"Extraction failed:\n{exc}")
        except ConversionError as exc:
            self.error.emit(f"Conversion failed:\n{exc}")
        except StorageError as exc:
            self.error.emit(f"Storage error:\n{exc}")
        except ROMToolError as exc:
            self.error.emit(f"Error:\n{exc}")
        except Exception as exc:  # noqa: BLE001
            # Catch-all so the worker thread never silently dies.
            self.error.emit(f"Unexpected error:\n{type(exc).__name__}: {exc}")

    # ── Pipeline steps ────────────────────────────────────────────────────────

    def _run_pipeline(self) -> None:
        # ── 1. Create isolated temp directory ─────────────────────────────
        self._temp_dir = Path(tempfile.gettempdir()) / f"romtool_{uuid.uuid4().hex}"
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self.status.emit(f"Working directory: {self._temp_dir}")

        # ── 2. Validate disk space ─────────────────────────────────────────
        self.status.emit("Checking available disk space…")
        storage_service.check_disk_space(
            self._install_dir,
            required_bytes=FALLBACK_SIZE_ESTIMATE,
        )
        self.status.emit("Disk space OK.")

        # ── 3. Download ────────────────────────────────────────────────────
        self.status.emit(f"Downloading from: {self._mirror.url}")
        download_path = download_service.download_file(
            url=self._mirror.url,
            dest_dir=self._temp_dir,
            progress_callback=self._on_download_progress,
        )
        self.status.emit(f"Download complete: {download_path.name}")

        # ── 4. Extract archive if necessary ───────────────────────────────
        iso_path = download_path
        if extraction_service.is_archive(download_path):
            self.status.emit(f"Extracting archive: {download_path.name}")
            extract_dir = self._temp_dir / "extracted"
            extraction_service.extract(download_path, extract_dir)
            # Find the .iso inside the extraction output.
            iso_path = _find_iso(extract_dir)
            if iso_path is None:
                raise ExtractionError(
                    "Extraction succeeded but no .iso file was found in the archive."
                )
            self.status.emit(f"ISO found: {iso_path.name}")
        else:
            self.status.emit("File is already an ISO – skipping extraction.")

        # ── 5. Convert ISO ────────────────────────────────────────────────
        self.status.emit(f"Converting ISO to {self._fmt} format…")
        convert_out_dir = self._temp_dir / "converted"
        conversion_service.convert_iso(
            iso_path=iso_path,
            output_dir=convert_out_dir,
            fmt=self._fmt,
            progress_callback=self._on_convert_progress,
        )
        self.status.emit("Conversion complete.")

        # ── 6. Install (move to destination) ──────────────────────────────
        self.status.emit(f"Installing to: {self._install_dir}")
        install_path = storage_service.install(convert_out_dir, self._install_dir)
        self.status.emit(f"Installed at: {install_path}")

        # ── 7. Cleanup temp directory ─────────────────────────────────────
        self.status.emit("Cleaning up temporary files…")
        storage_service.cleanup_temp(self._temp_dir)
        self.status.emit("Done.")

        # ── 8. Emit success ───────────────────────────────────────────────
        self.finished.emit(str(install_path))

    # ── Callbacks (called from worker thread; emit signals thread-safely) ─────

    def _on_download_progress(self, downloaded: int, total: int) -> None:
        self.progress.emit(float(downloaded), float(total if total > 0 else 0))

    def _on_convert_progress(self, current: int, total: int) -> None:
        # Conversion progress is coarse (0 or 100); map to a visual range.
        # Download occupies 0-80 %, conversion occupies 80-100 %.
        # The progress bar receives raw byte-like values; MainWindow interprets them.
        pass  # Individual conversion signals emitted directly in conversion_service


# ── Helper ────────────────────────────────────────────────────────────────────


def _find_iso(directory: Path) -> Optional[Path]:
    """Recursively find the first .iso file inside *directory*."""
    for candidate in sorted(directory.rglob("*.iso")):
        if candidate.is_file():
            return candidate
    return None
