"""
main_window.py – ROMTool main window.

Layout
------
  ┌──────────────────────────────────────────────────────┐
  │  [Search bar]                                        │  ← TOP
  ├───────────────────────────┬──────────────────────────┤
  │                           │  Mirror selection        │
  │  Game list                │  Format (XEX / GOD)      │
  │  (QListWidget)            │  Destination + Browse    │
  │                           │  [Download & Convert]    │
  ├───────────────────────────┴──────────────────────────┤
  │  Progress bar                                        │  ← BOTTOM
  │  Status log (QPlainTextEdit, read-only)              │
  └──────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtGui import QFont, QPalette, QColor, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
    QTextEdit,
)

from models.game_entry import GameEntry
from services import search_service
from workers.install_worker import InstallWorker

# ── Colour palette ─────────────────────────────────────────────────────────────
_BG         = "#0f1117"
_BG2        = "#1a1d27"
_BG3        = "#22263a"
_ACCENT     = "#4f8ef7"
_ACCENT2    = "#7c5af0"
_TEXT       = "#e2e8f0"
_TEXT_DIM   = "#718096"
_SUCCESS    = "#48bb78"
_WARNING    = "#ed8936"
_ERROR      = "#fc8181"
_BORDER     = "#2d3748"

_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {_BG};
    color: {_TEXT};
    font-family: 'Segoe UI', 'Consolas', monospace;
    font-size: 13px;
}}

/* ── Search bar ─────────────────────────────────────────────────────────── */
QLineEdit#searchBar {{
    background-color: {_BG2};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 14px;
    color: {_TEXT};
    selection-background-color: {_ACCENT};
}}
QLineEdit#searchBar:focus {{
    border-color: {_ACCENT};
}}

/* ── Game list ──────────────────────────────────────────────────────────── */
QListWidget#gameList {{
    background-color: {_BG2};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    outline: none;
    padding: 4px;
}}
QListWidget#gameList::item {{
    padding: 8px 12px;
    border-radius: 4px;
}}
QListWidget#gameList::item:selected {{
    background-color: {_ACCENT};
    color: white;
}}
QListWidget#gameList::item:hover {{
    background-color: {_BG3};
}}

/* ── Group boxes ────────────────────────────────────────────────────────── */
QGroupBox {{
    background-color: {_BG2};
    border: 1px solid {_BORDER};
    border-radius: 8px;
    margin-top: 18px;
    padding: 12px 10px 10px 10px;
    font-weight: bold;
    color: {_TEXT_DIM};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 10px;
}}

/* ── Radio buttons ──────────────────────────────────────────────────────── */
QRadioButton {{
    spacing: 8px;
    color: {_TEXT};
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 8px;
    border: 2px solid {_BORDER};
    background-color: {_BG};
}}
QRadioButton::indicator:checked {{
    background-color: {_ACCENT};
    border-color: {_ACCENT};
}}

/* ── Destination path field ─────────────────────────────────────────────── */
QLineEdit#destPath {{
    background-color: {_BG};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    padding: 6px 10px;
    color: {_TEXT};
}}

/* ── Buttons ────────────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {_BG3};
    border: 1px solid {_BORDER};
    border-radius: 5px;
    padding: 7px 14px;
    color: {_TEXT};
}}
QPushButton:hover {{
    background-color: {_ACCENT};
    border-color: {_ACCENT};
    color: white;
}}
QPushButton:pressed {{
    background-color: {_ACCENT2};
}}
QPushButton#downloadBtn {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {_ACCENT}, stop:1 {_ACCENT2});
    color: white;
    font-size: 14px;
    font-weight: bold;
    border: none;
    border-radius: 8px;
    padding: 12px 20px;
    letter-spacing: 0.5px;
}}
QPushButton#downloadBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {_ACCENT2}, stop:1 {_ACCENT});
}}
QPushButton#downloadBtn:disabled {{
    background: {_BG3};
    color: {_TEXT_DIM};
}}

/* ── Progress bar ───────────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {_BG2};
    border: 1px solid {_BORDER};
    border-radius: 5px;
    text-align: center;
    color: {_TEXT};
    height: 18px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {_ACCENT}, stop:1 {_ACCENT2});
    border-radius: 5px;
}}

/* ── Log area ───────────────────────────────────────────────────────────── */
QPlainTextEdit#logArea {{
    background-color: {_BG};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 6px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    color: {_TEXT_DIM};
}}

/* ── Scrollbars ─────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    width: 8px;
    background: {_BG};
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {_BG3};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* ── Status bar ─────────────────────────────────────────────────────────── */
QStatusBar {{
    background: {_BG2};
    color: {_TEXT_DIM};
    border-top: 1px solid {_BORDER};
    font-size: 11px;
}}

/* ── Splitter handle ────────────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {_BORDER};
    width: 2px;
}}
"""


class MainWindow(QMainWindow):
    """Primary application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ROMTool  ·  Xbox ISO Utility")
        self.setMinimumSize(1020, 700)
        self.resize(1200, 780)
        self.setStyleSheet(_STYLESHEET)

        # State
        self._catalogue: List[GameEntry] = []
        self._filtered: List[GameEntry] = []
        # Mirrors removed
        self._worker: Optional[InstallWorker] = None

        self._build_ui()
        self._connect_signals()
        self._set_status("Loading catalogue...")
        self._on_load_catalogue()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(24, 24, 24, 16)
        root_layout.setSpacing(16)

        # ── Zone A: Top bar ────────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(16)

        self._search_bar = QLineEdit()
        self._search_bar.setObjectName("searchBar")
        self._search_bar.setPlaceholderText("Search game titles in database...")
        self._search_bar.setClearButtonEnabled(True)
        self._search_bar.setMinimumHeight(40)
        self._search_bar.setFont(QFont('Segoe UI', 15))

        self._load_btn = QPushButton("⟳  Refresh List")
        self._load_btn.setFixedHeight(40)
        self._load_btn.setMinimumWidth(140)
        self._load_btn.setFont(QFont('Segoe UI', 14, QFont.Bold))

        top.addWidget(self._search_bar, 7)
        top.addWidget(self._load_btn, 1)
        root_layout.addLayout(top)

        # ── Zone B: Main Workspace (70/30 Split) ───────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)

        # Left – Game Browser (Table)
        self._game_list = QListWidget()
        self._game_list.setObjectName("gameList")
        self._game_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._game_list.setMinimumWidth(600)
        self._game_list.setStyleSheet("font-size: 15px; font-family: 'Segoe UI';")
        self._game_list.setSelectionMode(QListWidget.MultiSelection)
        splitter.addWidget(self._game_list)

        # Right – Action Sidebar
        sidebar = self._build_sidebar()
        splitter.addWidget(sidebar)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([840, 360])

        root_layout.addWidget(splitter, stretch=1)

        # ── Zone C: Status & Monitoring ─────────────────────────────────────
        bottom = self._build_bottom()
        root_layout.addLayout(bottom)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

    def _build_sidebar(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(310)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.setSpacing(10)

        # ...existing code...

        # ── Conversion format ──────────────────────────────────────────────
        fmt_group = QGroupBox("Output Format")
        fmt_layout = QVBoxLayout(fmt_group)
        fmt_layout.setSpacing(4)
        self._xex_radio = QRadioButton("XEX  (extracted game folder)")
        self._god_radio = QRadioButton("GOD  (Games on Demand container)")
        self._xex_radio.setChecked(True)
        self._fmt_btn_group = QButtonGroup(self)
        self._fmt_btn_group.addButton(self._xex_radio)
        self._fmt_btn_group.addButton(self._god_radio)
        fmt_layout.addWidget(self._xex_radio)
        fmt_layout.addWidget(self._god_radio)
        layout.addWidget(fmt_group)

        # ── Destination ────────────────────────────────────────────────────
        dest_group = QGroupBox("Install Destination")
        dest_layout = QVBoxLayout(dest_group)
        dest_layout.setSpacing(6)
        path_row = QHBoxLayout()
        self._dest_path = QLineEdit()
        self._dest_path.setObjectName("destPath")
        self._dest_path.setPlaceholderText("Choose install folder…")
        self._browse_btn = QPushButton("Browse")
        self._browse_btn.setFixedWidth(72)
        path_row.addWidget(self._dest_path)
        path_row.addWidget(self._browse_btn)
        dest_layout.addLayout(path_row)
        layout.addWidget(dest_group)

        # ── Selected Games List ────────────────────────────────────────────
        # ── Selected Games Container ────────────────────────────────────────
        selected_group = QGroupBox("Selected Games")
        selected_layout = QVBoxLayout(selected_group)
        selected_layout.setSpacing(4)
        self._selected_games_list = QTextEdit()
        self._selected_games_list.setReadOnly(True)
        self._selected_games_list.setStyleSheet("color: #E5E5E5; background: #232323; border-radius: 6px; font-size: 14px;")
        self._selected_games_list.setMinimumHeight(80)
        self._selected_games_list.setMaximumHeight(120)
        selected_layout.addWidget(self._selected_games_list)
        layout.addWidget(selected_group)

        # ── Download button ────────────────────────────────────────────────
        self._download_btn = QPushButton("Download & Convert")
        self._download_btn.setObjectName("downloadBtn")
        self._download_btn.setMinimumHeight(48)
        self._download_btn.setEnabled(False)
        layout.addWidget(self._download_btn)

        layout.addStretch()
        return w

    def _build_bottom(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(4)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("Idle")
        self._progress_bar.setFixedHeight(20)
        layout.addWidget(self._progress_bar)

        self._log_area = QPlainTextEdit()
        self._log_area.setObjectName("logArea")
        self._log_area.setReadOnly(True)
        self._log_area.setMaximumBlockCount(500)
        self._log_area.setFixedHeight(140)
        layout.addWidget(self._log_area)

        return layout

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._search_bar.textChanged.connect(self._on_search_changed)
        self._load_btn.clicked.connect(self._on_load_catalogue)
        self._game_list.itemSelectionChanged.connect(self._on_selected_games_changed)
        self._game_list.currentItemChanged.connect(self._on_game_selected)
        self._browse_btn.clicked.connect(self._on_browse)
        self._download_btn.clicked.connect(self._on_download)
    def _on_selected_games_changed(self):
        selected_items = self._game_list.selectedItems()
        if not selected_items:
            self._selected_games_list.setText("Nenhum jogo selecionado.")
        else:
            titles = [item.data(Qt.ItemDataRole.UserRole).title for item in selected_items]
            self._selected_games_list.setText("\n".join(titles))

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot()
    def _on_load_catalogue(self) -> None:
        self._log("Loading catalogue…")
        self._load_btn.setEnabled(False)
        self._game_list.clear()
        self._set_status("Fetching catalogue…")
        self._progress_bar.setFormat("Loading catalogue…")
        self._progress_bar.setRange(0, 0)  # indeterminate

        # Run in a simple QThread to avoid blocking the UI.
        self._catalogue_worker = _CatalogueLoader(self)
        self._catalogue_worker.finished.connect(self._on_catalogue_loaded)
        self._catalogue_worker.error.connect(self._on_catalogue_error)
        self._catalogue_worker.start()

    @Slot(object)
    def _on_catalogue_loaded(self, entries: List[GameEntry]) -> None:
        self._catalogue = entries
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("Idle")
        self._load_btn.setEnabled(True)
        self._apply_search()
        self._log(f"Catalogue loaded: {len(entries)} titles.")
        self._set_status(f"{len(entries)} games loaded.")

    @Slot(str)
    def _on_catalogue_error(self, msg: str) -> None:
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("Idle")
        self._load_btn.setEnabled(True)
        self._log(f"ERROR: {msg}", error=True)
        self._set_status("Catalogue load failed.")
        QMessageBox.critical(self, "Catalogue Error", msg)

    @Slot(str)
    def _on_search_changed(self, text: str) -> None:
        self._apply_search()

    @Slot()
    def _on_game_selected(self) -> None:
        item = self._game_list.currentItem()
        if item is None:
            return
        entry: GameEntry = item.data(Qt.ItemDataRole.UserRole)
        self._log(f"Selected: {entry.title}")
        self._set_status(f"Selected: {entry.title}")

    @Slot(object)
    # Mirrors removed

    @Slot(str)
    # Mirrors removed

    @Slot()
    def _on_browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Install Directory", self._dest_path.text() or ""
        )
        if folder:
            self._dest_path.setText(folder)
            self._update_download_button()

    @Slot()
    def _on_download(self) -> None:
        dest = self._dest_path.text().strip()
        fmt = "GOD" if self._god_radio.isChecked() else "XEX"

        if not dest:
            QMessageBox.warning(
                self, "No Destination", "Please choose an install directory."
            )
            return

        install_dir = Path(dest)

        selected_items = self._game_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Games Selected", "Selecione ao menos um jogo para instalar.")
            return

        # Disable controls during download.
        self._set_busy(True)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("Starting…")
        self._log(f"Iniciando instalação de {len(selected_items)} jogos [{fmt}] para: {install_dir}")

        def process_next(index):
            if index >= len(selected_items):
                self._set_busy(False)
                self._progress_bar.setRange(0, 100)
                self._progress_bar.setValue(100)
                self._progress_bar.setFormat("Complete ✓")
                return
            item = selected_items[index]
            entry = item.data(Qt.ItemDataRole.UserRole)
            self._log(f"Instalando: {entry.title}")
            from models.game_entry import MirrorLink
            mirror = MirrorLink(label=entry.title, url=entry.detail_url)
            worker = InstallWorker(
                mirror=mirror,
                install_dir=Path(dest),
                fmt=fmt,
                parent=self
            )
            self._worker = worker
            worker.progress.connect(self._on_progress)
            worker.status.connect(self._on_worker_status)
            worker.finished.connect(lambda path: (self._on_worker_finished(path), process_next(index + 1)))
            worker.error.connect(lambda msg: (self._on_worker_error(msg), process_next(index + 1)))
            worker.start()
        self._set_busy(True)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("Starting…")
        process_next(0)

    @Slot(int, int)
    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            pct = min(int(done * 100 / total), 100)
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(pct)
            mb_done = done / 1024**2
            mb_total = total / 1024**2
            self._progress_bar.setFormat(f"{mb_done:.1f} / {mb_total:.1f} MiB  ({pct}%)")
        else:
            self._progress_bar.setRange(0, 0)
            self._progress_bar.setFormat("Downloading…")

    @Slot(str)
    def _on_worker_status(self, msg: str) -> None:
        self._log(msg)
        self._set_status(msg)

    @Slot(str)
    def _on_worker_finished(self, path: str) -> None:
        self._set_busy(False)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(100)
        self._progress_bar.setFormat("Complete ✓")
        self._log(f"✓ Installed successfully: {path}", success=True)
        self._set_status("Installation complete.")
        QMessageBox.information(
            self,
            "Done",
            f"Installation complete!\n\nFiles installed to:\n{path}",
        )

    @Slot(str)
    def _on_worker_error(self, msg: str) -> None:
        self._set_busy(False)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("Error")
        self._log(f"✗ {msg}", error=True)
        self._set_status("Error – see log.")
        QMessageBox.critical(self, "Error", msg)

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _apply_search(self) -> None:
        query = self._search_bar.text()
        self._filtered = search_service.search(self._catalogue, query)
        self._game_list.clear()
        for entry in self._filtered:
            item = QListWidgetItem(str(entry))
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self._game_list.addItem(item)

    # Mirrors removed

    def _update_download_button(self) -> None:
        has_dest = bool(self._dest_path.text().strip())
        self._download_btn.setEnabled(has_dest)

    def _set_busy(self, busy: bool) -> None:
        self._download_btn.setEnabled(not busy)
        self._load_btn.setEnabled(not busy)
        self._game_list.setEnabled(not busy)

    def _set_status(self, msg: str) -> None:
        self._status_bar.showMessage(msg)

    def _log(self, msg: str, *, error: bool = False, success: bool = False) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        if error:
            prefix = f'<span style="color:{_ERROR}">[{ts}] ✗  {msg}</span>'
        elif success:
            prefix = f'<span style="color:{_SUCCESS}">[{ts}] ✓  {msg}</span>'
        else:
            prefix = f'<span style="color:{_TEXT_DIM}">[{ts}]  {msg}</span>'
        self._log_area.appendHtml(prefix)
        # Scroll to bottom.
        sb = self._log_area.verticalScrollBar()
        sb.setValue(sb.maximum())


# ── Lightweight helper workers (catalogue loading) ───────────────────────────

from PySide6.QtCore import Signal as _Signal  # noqa: E402


class _CatalogueLoader(QThread):
    finished = _Signal(object)
    error = _Signal(str)

    def run(self) -> None:
        try:
            entries = search_service.fetch_catalogue()
            self.finished.emit(entries)
        except Exception as exc:
            self.error.emit(str(exc))


    # Mirrors removed
