"""
services/exceptions.py – Structured custom exception hierarchy for ROMTool.

All service-level errors derive from ROMToolError so callers can catch broadly
or specifically depending on context.
"""


class ROMToolError(Exception):
    """Base class for all ROMTool exceptions."""


class SearchError(ROMToolError):
    """Raised when the catalogue cannot be fetched or parsed."""


class DownloadError(ROMToolError):
    """Raised when the file download fails or is interrupted."""


class ExtractionError(ROMToolError):
    """Raised when archive extraction fails or produces unexpected output."""


class ConversionError(ROMToolError):
    """Raised when exiso.exe or iso2god.exe exits with a non-zero code."""


class StorageError(ROMToolError):
    """Raised on filesystem errors during installation / move operations."""


class InsufficientDiskSpaceError(StorageError):
    """
    Raised when the target drive does not have enough free space.

    Attributes
    ----------
    required_bytes  : How many bytes the operation needs.
    available_bytes : How many bytes are currently free.
    """

    def __init__(self, required_bytes: int, available_bytes: int) -> None:
        self.required_bytes = required_bytes
        self.available_bytes = available_bytes
        super().__init__(
            f"Insufficient disk space: need {required_bytes:,} bytes, "
            f"have {available_bytes:,} bytes free."
        )
