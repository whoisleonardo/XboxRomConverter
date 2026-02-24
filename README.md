# XboxRomConverter# ROMTool – Windows Xbox ISO Download & Conversion Utility

A modular Windows desktop application built with Python 3.12 + PySide6 that
downloads Xbox 360 ISOs from an online catalogue, extracts archives, converts
to XEX or GOD format, and installs into a user-selected directory.

---

## Project Structure

```
romtool/
├── main.py                      # Entry point; PyInstaller base-path setup
├── main_window.py               # PySide6 main window + UI
├── romtool.spec                 # PyInstaller build spec
├── requirements.txt
│
├── services/
│   ├── exceptions.py            # Structured custom exception hierarchy
│   ├── search_service.py        # Catalogue fetch + in-memory search + mirror parse
│   ├── download_service.py      # Streaming httpx download with progress
│   ├── extraction_service.py    # ZIP / RAR / 7z extraction (path-traversal safe)
│   ├── conversion_service.py    # exiso.exe / iso2god.exe subprocess wrappers
│   └── storage_service.py       # Disk-space check + file installation + cleanup
│
├── workers/
│   └── install_worker.py        # QThread: full download→extract→convert→install
│
├── models/
│   └── game_entry.py            # GameEntry + MirrorLink dataclasses
│
└── bin/
    ├── exiso.exe                # (provide yourself – see bin/README.md)
    ├── iso2god.exe              # (provide yourself – see bin/README.md)
    └── README.md
```

---

## Setup

### 1. Prerequisites

- Python 3.12 (Windows)
- `pip install -r requirements.txt`
- Place `exiso.exe` and `iso2god.exe` in the `bin/` directory.
- Optionally install `unrar` on your PATH for RAR extraction.

### 2. Configure the catalogue URL

Edit `services/search_service.py` and set `CATALOGUE_URL` to point to the
actual online ROM repository you intend to use.  Also adjust the CSS selectors
(`ROW_SELECTOR`, `TITLE_ANCHOR_SELECTOR`, etc.) to match the site's HTML
structure.

### 3. Run (development)

```bat
cd romtool
python main.py
```

---

## Packaging (PyInstaller)

```bat
cd romtool
pyinstaller romtool.spec --noconfirm
```

The distributable is written to `dist/ROMTool/`.

---

## Exception Hierarchy

```
ROMToolError
├── SearchError              – catalogue / mirror fetch failures
├── DownloadError            – network / I/O errors during download
├── ExtractionError          – archive extraction failures / path traversal
├── ConversionError          – exiso.exe / iso2god.exe non-zero exit
└── StorageError             – filesystem / install failures
    └── InsufficientDiskSpaceError
```

---

## Worker Signal Contract

| Signal            | Type        | Meaning                              |
|-------------------|-------------|--------------------------------------|
| `progress(a, b)`  | `int, int`  | Bytes downloaded / total bytes       |
| `status(msg)`     | `str`       | Human-readable step description      |
| `finished(path)`  | `str`       | Absolute path to installed directory |
| `error(msg)`      | `str`       | User-friendly error description      |

---

## Security Notes

- Archive extraction validates every member path to prevent ZIP-slip attacks.
- All subprocess calls use argument lists (never `shell=True`).
- Binary paths are resolved from `BASE_PATH` (controlled at startup), never
  from user input.
- Temp files are written to an isolated UUID-named subdirectory of the system
  temp folder and cleaned up on success.

---

## License

MIT – see LICENSE (add your own).
