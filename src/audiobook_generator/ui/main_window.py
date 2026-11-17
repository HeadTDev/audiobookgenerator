"""Main window: file table, settings sidebar, player bar, progress and log."""
import html
import os
import re
import shutil
from datetime import datetime

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.config import (
    API_KEY_VAR,
    CHUNK_CACHE_DIR,
    ENV_PATH,
    GEMINI_KEY_VAR,
    LANGUAGE_CODE,
    LIST_PRICE_USD_PER_1K_CHARS,
    LOG_DIR,
    MODEL_ID,
    VOICES,
    load_api_key,
    load_gemini_key,
)
from ..core.preflight import MISREAD, check_script, count_by_severity
from ..core.script_writer import ScriptWriterThread
from ..core.text import audio_metadata_for, clean_markdown_text, output_name_for
from ..core.worker import GeneratorThread
from . import theme
from .player import SKIP_MS, PlayerBar, format_time

COL_CHECK, COL_NUM, COL_TITLE, COL_CHARS, COL_ISSUES, COL_STATUS, COL_PLAY = range(7)
SORTABLE_COLUMNS = (COL_NUM, COL_TITLE, COL_CHARS, COL_ISSUES)
SORT_ROLE = Qt.ItemDataRole.UserRole

STATUS_LABELS = {
    "new": ("New", theme.MUTED),
    "queued": ("Queued", theme.INFO),
    "generating": ("Generating", theme.ACCENT),
    "merging": ("Merging…", theme.ACCENT),
    "done": ("✓ Done", theme.SUCCESS),
    "failed": ("✗ Failed", theme.DANGER),
    "partial": ("⏸ Partial", theme.WARNING),
}
LOG_COLORS = {"❌": theme.DANGER, "✅": theme.SUCCESS, "⚠": theme.WARNING, "🛑": theme.WARNING}


def natural_sort_key(name):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


class SortableItem(QTableWidgetItem):
    """Table item that sorts by SORT_ROLE (numbers stay numeric, titles case-insensitive)."""

    def __init__(self, text, sort_value):
        super().__init__(text)
        self.setData(SORT_ROLE, sort_value)

    def __lt__(self, other):
        return self.data(SORT_ROLE) < other.data(SORT_ROLE)


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings or QSettings("AudiobookGenerator", "AudiobookGenerator")
        self.worker = None
        self.script_worker = None
        self.log_file = None
        self.rows = {}  # script path -> row info (items keep their identity across sorting)
        self.failed = {}  # script path -> detail, kept visible after the post-run refresh
        self.generating = False
        self.sort_column, self.sort_order = COL_NUM, Qt.SortOrder.AscendingOrder

        self.setWindowTitle("Audiobook Generator")
        self.setWindowIcon(theme.app_icon())
        self.setMinimumSize(960, 600)
        self.resize(1280, 780)
        self.setStyleSheet(theme.build_stylesheet())

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addLayout(self._build_main_area(), 1)
        root_layout.addLayout(body, 1)
        self.setCentralWidget(root)

        self._setup_shortcuts()
        self._load_settings()

    # ------------------------------------------------------------------ layout

    def _build_header(self):
        header = QFrame(objectName="header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(theme.logo_pixmap(28))
        logo.setStyleSheet("background: transparent;")
        layout.addWidget(logo)
        layout.addWidget(QLabel("Audiobook Generator", objectName="appTitle"))
        layout.addStretch()

        model = MODEL_ID.replace("eleven_", "Eleven ").replace("_", " ")
        ffmpeg_ok = shutil.which("ffmpeg") is not None
        ffmpeg = (
            f'<span style="color:{theme.SUCCESS}">FFmpeg ✓</span>'
            if ffmpeg_ok
            else f'<span style="color:{theme.DANGER}">FFmpeg missing</span>'
        )
        key_ok = bool(load_api_key())
        api_key = (
            f'<span style="color:{theme.SUCCESS}">API key ✓</span>'
            if key_ok
            else f'<span style="color:{theme.DANGER}">API key missing</span>'
        )
        info = QLabel(
            f"{model} · {LANGUAGE_CODE.upper()} · {api_key} · {ffmpeg}", objectName="headerInfo"
        )
        info.setTextFormat(Qt.TextFormat.RichText)
        hints = []
        if not key_ok:
            hints.append(f"Set {API_KEY_VAR} in {ENV_PATH}.")
        if not ffmpeg_ok:
            hints.append("FFmpeg is required to merge the generated chunks. Install it and restart.")
        info.setToolTip("\n".join(hints))
        layout.addWidget(info)
        return header

    def _section_label(self, text):
        return QLabel(text.upper(), objectName="sectionLabel")

    def _folder_field(self, label, placeholder, browse_handler):
        box = QVBoxLayout()
        box.setSpacing(4)
        box.addWidget(QLabel(label, objectName="fieldLabel"))
        row = QHBoxLayout()
        row.setSpacing(6)
        edit = QLineEdit(readOnly=True, placeholderText=placeholder)
        button = QPushButton("Browse…")
        button.clicked.connect(browse_handler)
        row.addWidget(edit, 1)
        row.addWidget(button)
        box.addLayout(row)
        return box, edit, button

    def _build_sidebar(self):
        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(320)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(10)

        layout.addWidget(self._section_label("Source"))
        box, self.input_edit, self.browse_in_btn = self._folder_field(
            "Scripts folder", "Folder with the .md scripts", self.browse_input_folder
        )
        layout.addLayout(box)
        box, self.output_edit, self.browse_out_btn = self._folder_field(
            "Output folder", "Where the MP3 files go", self.browse_output_folder
        )
        layout.addLayout(box)

        self.notes_btn = QPushButton("Notes → Script…")
        self.notes_btn.setToolTip(
            "Write a narration script from .txt/.md notes with Gemini; saved into the scripts folder."
        )
        self.notes_btn.clicked.connect(self.start_notes_to_script)
        layout.addWidget(self.notes_btn)
        privacy = QLabel(
            "Gemini free tier: Google may use the notes to improve its products.", objectName="mutedLabel"
        )
        privacy.setWordWrap(True)
        layout.addWidget(privacy)

        layout.addSpacing(6)
        layout.addWidget(self._section_label("Narration"))
        layout.addWidget(QLabel("Voice", objectName="fieldLabel"))
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(list(VOICES))
        layout.addWidget(self.voice_combo)

        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Narration speed", objectName="fieldLabel"))
        speed_row.addStretch()
        self.speed_value = QLabel("1.2x", objectName="summaryMain")
        speed_row.addWidget(self.speed_value)
        layout.addLayout(speed_row)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(10, 20)
        self.speed_slider.setValue(12)
        self.speed_slider.setPageStep(1)
        self.speed_slider.setToolTip(
            "Applied with FFmpeg after generation; costs nothing extra. It is baked into the "
            "MP3; the player has its own live speed."
        )
        self.speed_slider.valueChanged.connect(
            lambda v: self.speed_value.setText(f"{v / 10:.1f}x")
        )
        layout.addWidget(self.speed_slider)

        layout.addSpacing(6)
        layout.addWidget(self._section_label("Summary"))
        card = QFrame(objectName="card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(4)
        self.summary_main = QLabel("No files selected", objectName="summaryMain")
        self.summary_detail = QLabel("", objectName="summaryDetail")
        self.summary_detail.setWordWrap(True)
        card_layout.addWidget(self.summary_main)
        card_layout.addWidget(self.summary_detail)
        layout.addWidget(card)

        layout.addStretch()
        self.generate_btn = QPushButton("Select files to generate", objectName="primaryButton")
        self.generate_btn.setToolTip("Ctrl+Enter")
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self.start_generation)
        layout.addWidget(self.generate_btn)
        self.stop_btn = QPushButton("Stop", objectName="dangerButton")
        self.stop_btn.setToolTip("Chunks already in progress finish and are kept.")
        self.stop_btn.clicked.connect(self.stop_generation)
        self.stop_btn.hide()
        layout.addWidget(self.stop_btn)
        return sidebar

    def _build_main_area(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(16, 12, 16, 8)
        toolbar.setSpacing(8)
        self.search_edit = QLineEdit(placeholderText="Search titles…  (Ctrl+F)")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.apply_filters)
        toolbar.addWidget(self.search_edit, 1)

        self.filter_group = QButtonGroup(self)
        for mode, text in (("all", "All"), ("missing", "Missing"), ("done", "Done")):
            button = QPushButton(text, objectName="filterButton", checkable=True)
            button.setProperty("mode", mode)
            button.setChecked(mode == "all")
            self.filter_group.addButton(button)
            toolbar.addWidget(button)
        self.filter_group.buttonClicked.connect(lambda _: self.apply_filters())

        refresh = QPushButton("Refresh")
        refresh.setToolTip("Re-scan the folders")
        refresh.clicked.connect(self.refresh_file_list)
        toolbar.addWidget(refresh)
        layout.addLayout(toolbar)

        self.empty_label = QLabel(
            "Choose a scripts folder on the left to get started.", objectName="mutedLabel"
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label, 1)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["✓", "#", "TITLE", "CHARS", "CHECK", "STATUS", ""])
        self.table.horizontalHeaderItem(COL_CHECK).setToolTip("Select or deselect all")
        self.table.horizontalHeaderItem(COL_ISSUES).setToolTip(
            "Pre-flight check: notation the voice may misread. Click a value for details."
        )
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setMouseTracking(True)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self._on_header_clicked)
        for column, width in ((COL_CHECK, 44), (COL_NUM, 56), (COL_CHARS, 90), (COL_ISSUES, 80),
                              (COL_STATUS, 210), (COL_PLAY, 80)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        header.setSectionResizeMode(COL_TITLE, QHeaderView.ResizeMode.Stretch)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.hide()
        layout.addWidget(self.table, 1)

        self.player_bar = PlayerBar(self.settings)
        if not self.player_bar.available:
            self.player_bar.hide()  # rows still play through the system default player
        self.player_bar.progress_changed.connect(self._on_progress_changed)
        layout.addWidget(self.player_bar)
        layout.addWidget(self._build_progress_area())
        return layout

    def _build_progress_area(self):
        area = QFrame(objectName="progressArea")
        layout = QVBoxLayout(area)
        layout.setContentsMargins(16, 10, 16, 12)
        layout.setSpacing(8)

        row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Ready")
        self.progress_bar.setFixedHeight(22)
        row.addWidget(self.progress_bar, 1)
        self.eta_label = QLabel("", objectName="etaLabel")
        self.eta_label.setMinimumWidth(130)
        self.eta_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.eta_label)
        self.log_toggle = QPushButton("▸ Show log", objectName="linkButton")
        self.log_toggle.clicked.connect(lambda: self.set_log_visible(self.log_view.isHidden()))
        row.addWidget(self.log_toggle)
        layout.addLayout(row)

        self.log_view = QTextEdit(readOnly=True)
        self.log_view.setFixedHeight(170)
        self.log_view.hide()
        layout.addWidget(self.log_view)
        return area

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._shortcut_generate)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search_edit.setFocus)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.player_bar.toggle)
        QShortcut(
            QKeySequence("Ctrl+Left"), self, activated=lambda: self.player_bar.skip(-SKIP_MS)
        )
        QShortcut(
            QKeySequence("Ctrl+Right"), self, activated=lambda: self.player_bar.skip(SKIP_MS)
        )

    def _shortcut_generate(self):
        if self.generate_btn.isEnabled():
            self.start_generation()

    # ---------------------------------------------------------------- settings

    def _load_settings(self):
        s = self.settings
        geometry = s.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        voice = s.value("voice", "", type=str)
        self.voice_combo.setCurrentIndex(max(0, self.voice_combo.findText(voice)))
        self.speed_slider.setValue(s.value("speed", 12, type=int))
        self.player_bar.set_rate(s.value("player_rate", 1.0, type=float))
        output_folder = s.value("output_folder", "", type=str)
        if output_folder and os.path.isdir(output_folder):
            self.output_edit.setText(output_folder)
            self.output_edit.setToolTip(output_folder)
        input_folder = s.value("input_folder", "", type=str)
        if input_folder and os.path.isdir(input_folder):
            self.input_edit.setText(input_folder)
            self.input_edit.setToolTip(input_folder)
            self.refresh_file_list()
        self.set_log_visible(s.value("log_visible", False, type=bool))

    def _save_settings(self):
        s = self.settings
        s.setValue("geometry", self.saveGeometry())
        s.setValue("input_folder", self.input_edit.text())
        s.setValue("output_folder", self.output_edit.text())
        s.setValue("voice", self.voice_combo.currentText())
        s.setValue("speed", self.speed_slider.value())
        s.setValue("player_rate", self.player_bar.rate)
        s.setValue("log_visible", not self.log_view.isHidden())
        s.sync()

    # --------------------------------------------------------------- file list

    def browse_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select scripts folder", self.input_edit.text())
        if folder:
            self.input_edit.setText(folder)
            self.input_edit.setToolTip(folder)
            if not self.output_edit.text():
                self.output_edit.setText(folder)
                self.output_edit.setToolTip(folder)
            self.refresh_file_list()

    def browse_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder", self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)
            self.output_edit.setToolTip(folder)
            self.refresh_file_list()

    @staticmethod
    def _cached_chunk_count(output_folder, mp3_name):
        if not output_folder:
            return 0
        cache_dir = os.path.join(output_folder, CHUNK_CACHE_DIR, os.path.splitext(mp3_name)[0])
        try:
            return sum(name.endswith(".mp3") for name in os.listdir(cache_dir))
        except OSError:
            return 0

    def _read_script(self, path, output_folder, existing_files):
        file_name = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            metadata = audio_metadata_for(path, text)
            chars = len(clean_markdown_text(text))
            issues = check_script(text)
        except (OSError, UnicodeDecodeError):
            metadata, chars, issues = {"title": file_name}, 0, []
        mp3_name = output_name_for(file_name)
        mp3_path = os.path.join(output_folder, mp3_name) if mp3_name in existing_files else None
        return {
            "path": path,
            "file_name": file_name,
            "title": metadata["title"],
            "track": int(metadata.get("track", 0)),
            "chars": chars,
            "issues": issues,
            "mp3": mp3_path,
            "cached": 0 if mp3_path else self._cached_chunk_count(output_folder, mp3_name),
        }

    def refresh_file_list(self):
        input_folder = self.input_edit.text()
        output_folder = self.output_edit.text()
        self.rows = {}
        self.table.blockSignals(True)
        self.table.setRowCount(0)

        scripts = []
        if input_folder and os.path.isdir(input_folder):
            existing = set(os.listdir(output_folder)) if output_folder and os.path.isdir(output_folder) else set()
            names = sorted((n for n in os.listdir(input_folder) if n.lower().endswith(".md")), key=natural_sort_key)
            scripts = [self._read_script(os.path.join(input_folder, n), output_folder, existing) for n in names]

        self.table.setRowCount(len(scripts))
        for row_index, info in enumerate(scripts):
            self._fill_row(row_index, info)
            self.rows[info["path"]] = info
        self.table.blockSignals(False)

        self._sort_table()
        self.table.setVisible(bool(scripts))
        self.empty_label.setVisible(not scripts)
        if input_folder and not scripts:
            self.empty_label.setText("No .md scripts found in this folder.")
        self.update_summary()

    def _fill_row(self, row_index, info):
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        # Files that already have an MP3 start unchecked so they are not paid for twice.
        check.setCheckState(Qt.CheckState.Unchecked if info["mp3"] else Qt.CheckState.Checked)
        check.setData(Qt.ItemDataRole.UserRole + 1, info["path"])
        number = SortableItem(str(info["track"]) if info["track"] else "–", info["track"])
        number.setForeground(QColor(theme.MUTED))
        title = SortableItem(info["title"], info["title"].lower())
        title.setToolTip(info["file_name"])
        chars = SortableItem(f"{info['chars']:,}", info["chars"])
        chars.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        chars.setForeground(QColor(theme.MUTED))
        issues = SortableItem("", 0)
        issues.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        status = QTableWidgetItem()
        play = QTableWidgetItem()
        info["items"] = {"check": check, "issues": issues, "status": status, "play": play}
        for column, item in ((COL_CHECK, check), (COL_NUM, number), (COL_TITLE, title),
                             (COL_CHARS, chars), (COL_ISSUES, issues), (COL_STATUS, status),
                             (COL_PLAY, play)):
            self.table.setItem(row_index, column, item)
        self._update_issue_cell(info)

        if info["path"] in self.failed:
            self._set_row_status(info, "failed", self.failed[info["path"]])
        elif info["mp3"]:
            self._set_row_status(info, "done")
        elif info["cached"]:
            self._set_row_status(info, "partial", f"{info['cached']} chunks cached")
        else:
            self._set_row_status(info, "new")
        self._update_play_cell(info)

    def _update_issue_cell(self, info):
        item = info["items"]["issues"]
        misread, to_check = count_by_severity(info["issues"])
        if misread:
            item.setText(f"⚠ {misread + to_check}")
            item.setForeground(QColor(theme.WARNING))
        elif to_check:
            item.setText(f"? {to_check}")
            item.setForeground(QColor(theme.MUTED))
        else:
            item.setText("✓")
            item.setForeground(QColor(theme.SUCCESS))
        item.setData(SORT_ROLE, misread * 10_000 + to_check)
        item.setToolTip(
            f"{misread} will be misread · {to_check} to check by ear. Click for details."
            if info["issues"] else "No notation problems found."
        )

    def _recheck_issues(self, info):
        """Re-read one script, e.g. right before paying, in case it was edited since the scan."""
        try:
            with open(info["path"], "r", encoding="utf-8") as f:
                info["issues"] = check_script(f.read())
        except (OSError, UnicodeDecodeError):
            return
        self._update_issue_cell(info)

    def show_issues(self, info):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Pre-flight check · {info['title']}")
        dialog.resize(820, 520)
        layout = QVBoxLayout(dialog)
        misread, to_check = count_by_severity(info["issues"])
        layout.addWidget(QLabel(
            f"<b>{misread}</b> will be misread (confirmed) · <b>{to_check}</b> to check by ear "
            "(not verified). Fix the script, then press Refresh."
        ))
        view = QTextEdit(readOnly=True)
        blocks = []
        for issue in info["issues"]:
            label, color = (
                ("Misread", theme.WARNING) if issue.severity == MISREAD else ("Check", theme.MUTED)
            )
            # Escape every piece: script text may contain "<", "&" and the like.
            left = ("…" if issue.start > 50 else "") + html.escape(
                issue.text[max(0, issue.start - 50):issue.start]
            )
            hit = html.escape(issue.text[issue.start:issue.end])
            right = html.escape(issue.text[issue.end:issue.end + 50]) + (
                "…" if issue.end + 50 < len(issue.text) else ""
            )
            blocks.append(
                f'<p><span style="color:{theme.MUTED}">Line {issue.line}</span> · '
                f'<span style="color:{color}"><b>{label}</b></span> · {html.escape(issue.message)}<br>'
                f'<span style="color:{theme.MUTED}">{left}</span>'
                f'<span style="background:{color}; color:{theme.ACCENT_TEXT}">&nbsp;{hit}&nbsp;</span>'
                f'<span style="color:{theme.MUTED}">{right}</span></p>'
            )
        view.setHtml("".join(blocks))
        layout.addWidget(view, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        open_btn = QPushButton("Open script")
        open_btn.clicked.connect(lambda: os.startfile(info["path"]))
        close_btn = QPushButton("Close", objectName="primaryButton")
        close_btn.clicked.connect(dialog.accept)
        buttons.addWidget(open_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)
        dialog.exec()

    def _set_row_status(self, info, state, detail=""):
        label, color = STATUS_LABELS[state]
        item = info["items"]["status"]
        item.setText(f"{label} · {detail}" if detail else label)
        item.setForeground(QColor(color))
        info["state"] = state

    def _update_play_cell(self, info):
        item = info["items"]["play"]
        if info["mp3"]:
            listened, pos = self.player_bar.progress_for(info["mp3"])
            if listened:
                item.setText("✓ Listened")
                item.setForeground(QColor(theme.MUTED))
            else:
                item.setText(f"▶ {format_time(pos)}" if pos > 0 else "▶ Play")
                item.setForeground(QColor(theme.ACCENT))
            item.setToolTip(info["mp3"])
        else:
            item.setText("")
            item.setToolTip("")

    def _on_progress_changed(self, path):
        """Refresh the play cell of the row showing this MP3 (no full list refresh)."""
        key = os.path.normcase(os.path.normpath(path))
        for info in self.rows.values():
            if info["mp3"] and os.path.normcase(os.path.normpath(info["mp3"])) == key:
                self._update_play_cell(info)

    def _row_info(self, row_index):
        check = self.table.item(row_index, COL_CHECK)
        return self.rows.get(check.data(Qt.ItemDataRole.UserRole + 1)) if check else None

    def _on_header_clicked(self, column):
        if column == COL_CHECK:
            if not self.generating:
                self._toggle_all()
        elif column in SORTABLE_COLUMNS:
            if column == self.sort_column:
                self.sort_order = (
                    Qt.SortOrder.DescendingOrder
                    if self.sort_order == Qt.SortOrder.AscendingOrder
                    else Qt.SortOrder.AscendingOrder
                )
            else:
                self.sort_column, self.sort_order = column, Qt.SortOrder.AscendingOrder
            self._sort_table()
        else:
            self._sort_table()  # keep the indicator on the real sort column

    def _sort_table(self):
        # One-shot sort (sorting stays disabled), so live status updates never reorder rows.
        self.table.sortItems(self.sort_column, self.sort_order)
        self.table.horizontalHeader().setSortIndicator(self.sort_column, self.sort_order)
        self.apply_filters()  # hidden flags belong to row positions, which just changed

    def _toggle_all(self):
        visible = [info for info in self.rows.values() if not self.table.isRowHidden(info["items"]["check"].row())]
        target = (
            Qt.CheckState.Unchecked
            if visible and all(i["items"]["check"].checkState() == Qt.CheckState.Checked for i in visible)
            else Qt.CheckState.Checked
        )
        self.table.blockSignals(True)
        for info in visible:
            info["items"]["check"].setCheckState(target)
        self.table.blockSignals(False)
        self.update_summary()

    def _on_cell_clicked(self, row_index, column):
        info = self._row_info(row_index)
        if not info:
            return
        if column == COL_ISSUES:
            if info["issues"]:
                self.show_issues(info)
            return
        if column == COL_PLAY:
            # A file being regenerated must not be loaded: Windows would lock it and the
            # final os.replace of the merge would fail.
            busy = self.generating and info.get("state") in ("queued", "generating", "merging")
            if info["mp3"] and not busy:
                self.play_file(info)
        elif column != COL_CHECK and not self.generating:
            # Qt toggles the checkbox column itself; the rest of the row toggles here.
            check = info["items"]["check"]
            check.setCheckState(
                Qt.CheckState.Unchecked
                if check.checkState() == Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )

    def _on_item_changed(self, item):
        if item.column() == COL_CHECK:
            self.update_summary()

    def apply_filters(self):
        mode = self.filter_group.checkedButton().property("mode")
        needle = self.search_edit.text().strip().lower()
        for info in self.rows.values():
            visible = (
                (mode == "all" or (mode == "done") == bool(info["mp3"]))
                and (not needle or needle in info["title"].lower() or needle in info["file_name"].lower())
            )
            self.table.setRowHidden(info["items"]["check"].row(), not visible)

    def selected_rows(self):
        return [
            info for info in self.rows.values()
            if info["items"]["check"].checkState() == Qt.CheckState.Checked
        ]

    def update_summary(self):
        selected = self.selected_rows()
        chars = sum(info["chars"] for info in selected)
        if not selected:
            self.summary_main.setText("No files selected")
            self.summary_detail.setText("Tick the files you want to generate.")
        else:
            cost = chars / 1000 * LIST_PRICE_USD_PER_1K_CHARS
            noun = "file" if len(selected) == 1 else "files"
            self.summary_main.setText(f"{len(selected)} {noun} selected")
            self.summary_detail.setText(f"{chars:,} characters · ≈ ${cost:.2f} at list price (upper bound)")
        if not self.generating:
            count = len(selected)
            self.generate_btn.setEnabled(count > 0)
            self.generate_btn.setText(
                f"Generate {count} file{'s' if count != 1 else ''}" if count else "Select files to generate"
            )

    # -------------------------------------------------------------- generation

    def _confirm_cost(self, selected):
        chars = sum(info["chars"] for info in selected)
        cost = chars / 1000 * LIST_PRICE_USD_PER_1K_CHARS
        misread = to_check = files_with_issues = 0
        for info in selected:
            m, c = count_by_severity(info["issues"])
            misread, to_check = misread + m, to_check + c
            files_with_issues += bool(m or c)
        preflight = (
            f"⚠ Pre-flight: {misread} place(s) will be misread and {to_check} should be checked "
            f"by ear, in {files_with_issues} file(s). See the CHECK column.\n\n"
            if misread or to_check
            else "✓ Pre-flight: no notation problems found.\n\n"
        )
        answer = QMessageBox.question(
            self,
            "Start generation?",
            f"Files: {len(selected)}\nCharacters: {chars:,}\n"
            f"Upper bound at list price (${LIST_PRICE_USD_PER_1K_CHARS}/1K chars): ~${cost:.2f}\n\n"
            + preflight
            + "Chunks cached from an earlier interrupted run are not billed again.",
        )
        return answer == QMessageBox.StandardButton.Yes

    def start_notes_to_script(self):
        input_folder = self.input_edit.text()
        if not input_folder or not os.path.isdir(input_folder):
            QMessageBox.warning(self, "Scripts folder", "Choose a valid scripts folder first.")
            return
        api_key = load_gemini_key()
        if not api_key:
            QMessageBox.warning(
                self, "Gemini API key missing", f"Set {GEMINI_KEY_VAR} in the .env file:\n{ENV_PATH}"
            )
            return
        start = self.settings.value("notes_folder", "", type=str)
        if not start or not os.path.isdir(start):
            start = input_folder
        notes_path, _ = QFileDialog.getOpenFileName(
            self, "Select notes", start, "Notes (*.txt *.md)"
        )
        if not notes_path:
            return
        self.settings.setValue("notes_folder", os.path.dirname(notes_path))
        name = os.path.basename(notes_path)
        # Every *.md in the scripts folder is listed as a script and starts ticked, so raw
        # notes there would be sent to ElevenLabs by accident.
        if (
            name.lower().endswith(".md")
            and not name.upper().endswith("_SCRIPT.MD")
            and os.path.samefile(os.path.dirname(notes_path), input_folder)
        ):
            QMessageBox.warning(
                self,
                "Notes → Script",
                "Notes in the scripts folder are listed as scripts and would be generated. "
                "Move the notes out of this folder first.",
            )
            return
        self.notes_btn.setEnabled(False)
        self.notes_btn.setText("Writing script…")
        self.script_worker = ScriptWriterThread(api_key, notes_path, input_folder)
        self.script_worker.log_msg.connect(self.log)
        self.script_worker.done.connect(self._script_written)
        self.script_worker.start()

    def _script_written(self, success, message, path):
        self.notes_btn.setEnabled(True)
        self.notes_btn.setText("Notes → Script…")
        if success:
            self.log(message)
            if not self.generating:
                self.refresh_file_list()
        else:  # the thread already logged the error
            QMessageBox.warning(self, "Notes → Script", message)

    def start_generation(self):
        selected = self.selected_rows()
        if not selected:
            QMessageBox.warning(self, "Nothing selected", "Tick at least one file to generate.")
            return
        output_folder = self.output_edit.text()
        if not output_folder or not os.path.isdir(output_folder):
            QMessageBox.warning(self, "Output folder", "Choose a valid output folder first.")
            return
        if shutil.which("ffmpeg") is None:
            QMessageBox.warning(self, "FFmpeg missing", "FFmpeg was not found on PATH. It is needed to merge the chunks.")
            return
        api_key = load_api_key()
        if not api_key:
            QMessageBox.warning(
                self, "API key missing", f"Set {API_KEY_VAR} in the .env file:\n{ENV_PATH}"
            )
            return
        for info in selected:
            self._recheck_issues(info)  # scripts may have been edited since the last scan
        if not self._confirm_cost(selected):
            return

        # Release the file lock Windows holds on a loaded MP3; replacing it would fail otherwise.
        self.player_bar.release()

        self.failed = {}
        self._set_generating(True)
        self.log_view.clear()
        self._open_log_file(output_folder)
        self.log("=== Generation started ===")
        self.log(f"Files: {len(selected)} · Output: {output_folder}")
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Preparing…")
        self.eta_label.setText("")
        for info in selected:
            self._set_row_status(info, "queued")

        self.worker = GeneratorThread(
            api_key=api_key,
            script_files=[info["path"] for info in selected],
            output_folder=output_folder,
            voice_id=VOICES[self.voice_combo.currentText()],
            speed=self.speed_slider.value() / 10.0,
        )
        self.worker.log_msg.connect(self.log)
        self.worker.progress.connect(self._on_progress)
        self.worker.eta_update.connect(self._on_eta)
        self.worker.file_status.connect(self._on_file_status)
        self.worker.done.connect(self.generation_finished)
        self.worker.start()

    def _set_generating(self, generating):
        self.generating = generating
        for widget in (self.browse_in_btn, self.browse_out_btn, self.voice_combo, self.speed_slider):
            widget.setEnabled(not generating)
        flags = Qt.ItemFlag.ItemIsEnabled | (Qt.ItemFlag(0) if generating else Qt.ItemFlag.ItemIsUserCheckable)
        self.table.blockSignals(True)
        for info in self.rows.values():
            info["items"]["check"].setFlags(flags)
        self.table.blockSignals(False)
        self.stop_btn.setVisible(generating)
        self.stop_btn.setEnabled(generating)
        self.stop_btn.setText("Stop")
        if generating:
            self.generate_btn.setEnabled(False)
            self.generate_btn.setText("Generating…")
        else:
            self.update_summary()

    def stop_generation(self):
        if self.worker and self.worker.isRunning():
            self.stop_btn.setEnabled(False)
            self.stop_btn.setText("Stopping…")
            self.log("⚠️ Stop requested. Chunks already in progress will finish and be kept.")
            self.worker.stop()

    def _on_progress(self, done, total):
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(done)
        self.progress_bar.setFormat(f"%p%  ·  {done}/{total} chunks")

    def _on_eta(self, seconds):
        minutes, secs = divmod(seconds, 60)
        self.eta_label.setText(f"~{minutes} min {secs} s left" if minutes else f"~{secs} s left")

    def _on_file_status(self, path, state, detail):
        info = self.rows.get(path)
        if not info:
            return
        if state in ("queued", "generating", "partial") and detail:
            detail += " chunks"
        if state == "failed":
            self.failed[path] = detail
        if state == "done":
            output_folder = self.output_edit.text()
            info["mp3"] = os.path.join(output_folder, output_name_for(info["file_name"]))
            self._update_play_cell(info)
        self._set_row_status(info, state, detail)

    def generation_finished(self, success, message):
        self.log(f"\n{message}")
        self._close_log_file()
        self.eta_label.setText("")
        self.progress_bar.setFormat(("Finished" if success else "Stopped") + "  ·  %v/%m chunks")
        self._set_generating(False)
        # Re-scan: Done/Partial come from the files on disk, Failed from self.failed.
        self.refresh_file_list()

    # ------------------------------------------------------------------ player

    def play_file(self, info):
        if self.player_bar.available:
            self.player_bar.load(info["mp3"], info["title"])
        else:
            os.startfile(info["mp3"])

    # --------------------------------------------------------------------- log

    def set_log_visible(self, visible):
        self.log_view.setVisible(visible)
        self.log_toggle.setText("▾ Hide log" if visible else "▸ Show log")

    def _open_log_file(self, output_folder):
        # A log file is a convenience: failing to create it must not block generation.
        try:
            log_dir = os.path.join(output_folder, LOG_DIR)
            os.makedirs(log_dir, exist_ok=True)
            name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".log"
            self.log_file = open(os.path.join(log_dir, name), "a", encoding="utf-8")
        except OSError as e:
            self.log_file = None
            self.log(f"⚠️ Could not create the log file: {e}")

    def _close_log_file(self):
        if self.log_file:
            self.log_file.close()
            self.log_file = None

    def log(self, message):
        if self.log_file:
            try:
                self.log_file.write(message + "\n")
                self.log_file.flush()
            except OSError:
                pass
        color = next((c for prefix, c in LOG_COLORS.items() if message.lstrip().startswith(prefix)), theme.TEXT)
        escaped = html.escape(message).replace("\n", "<br>")
        self.log_view.append(f'<span style="color:{color}">{escaped}</span>')
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        if message.lstrip().startswith("❌"):
            self.set_log_visible(True)

    # ------------------------------------------------------------------- close

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            # Waits for the chunks already in flight so they are saved.
            self.worker.stop()
            self.worker.wait()
        if self.script_worker and self.script_worker.isRunning():
            self.script_worker.wait()
        self.player_bar.shutdown()
        self._close_log_file()
        self._save_settings()
        theme.cleanup_icons()
        event.accept()
