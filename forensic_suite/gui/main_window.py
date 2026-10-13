"""Main application window: menu, toolbar, sidebar, tab stack, inspector."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QPushButton,
                               QSplitter, QStackedWidget, QVBoxLayout, QWidget)

from gui import load_stylesheet
from gui.case_explorer import CaseExplorer
from gui.right_panel import RightPanel
from gui.sidebar import Sidebar
from gui.status_bar import StatusBar
from gui.tabs.ai_assistant_tab import AIAssistantTab
from gui.tabs.dashboard_tab import DashboardTab
from gui.tabs.data_viewer_tab import DataViewerTab
from gui.tabs.extraction_tab import ExtractionTab
from gui.tabs.files_tab import FilesTab
from gui.tabs.home_tab import HomeTab
from gui.tabs.overview_tab import OverviewTab
from gui.tabs.reports_tab import ReportsTab
from gui.tabs.settings_tab import SettingsTab
from gui.tabs.timeline_tab import TimelineTab
from gui.tabs.tools_tab import ToolsTab
from gui.toolbar import TopToolBar
from gui.workers import ImportWorker, IndexWorker

TAB_KEYS = ["home", "dashboard", "extraction", "overview", "files", "data",
            "timeline", "reports", "tools", "ai", "settings"]


class Toast(QLabel):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setStyleSheet("QLabel{background:#1F2630;color:#00E5FF;"
                           "border:1px solid #00E5FF;border-radius:8px;"
                           "padding:10px 16px;font-weight:600;}")
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str) -> None:
        self.setText(text)
        self.adjustSize()
        self._move()
        self.raise_()
        self.show()
        self._timer.start(3800)

    def _move(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.move(max(parent.width() - self.width() - 24, 24), 24)


class NewCaseDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New case")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        self.case_id = QLineEdit()
        self.case_id.setPlaceholderText("e.g. CASE-2026-014")
        self.title = QLineEdit()
        self.title.setPlaceholderText("Case title")
        self.examiner = QLineEdit()
        self.examiner.setPlaceholderText("Your name")
        self.authorization = QLineEdit()
        self.authorization.setPlaceholderText(
            "Warrant / court order / consent reference")
        for label, widget in (("Case ID", self.case_id), ("Title", self.title),
                              ("Examiner", self.examiner),
                              ("Authorization reference", self.authorization)):
            lab = QLabel(label)
            lab.setProperty("role", "muted")
            layout.addWidget(lab)
            layout.addWidget(widget)

        buttons = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        create = QPushButton("Create case")
        create.setObjectName("Primary")
        create.clicked.connect(self._accept)
        buttons.addWidget(cancel)
        buttons.addStretch()
        buttons.addWidget(create)
        layout.addLayout(buttons)
        self.result_data: dict | None = None

    def _accept(self) -> None:
        data = {"case_id": self.case_id.text().strip(),
                "title": self.title.text().strip(),
                "examiner": self.examiner.text().strip(),
                "authorization": self.authorization.text().strip()}
        if not all(data.values()):
            QMessageBox.warning(self, "New case", "All fields are required.")
            return
        self.result_data = data
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, ctx, config) -> None:
        super().__init__()
        self.ctx = ctx
        self.config = config
        self.settings = QSettings("ForensicSuite", "ForensicSuite")
        self.toast: Toast | None = None
        self.tabs: dict[str, QWidget] = {}
        self._index_queue: list[tuple[str, int, str]] = []
        self._index_worker: IndexWorker | None = None
        self._import_worker: ImportWorker | None = None
        self._inspector_wanted = True

        self.setWindowTitle("Forensic Suite \u2014 Mobile Device Analysis")
        self.resize(1440, 900)

        # Explicit window flags so Linux WMs (XFCE/GNOME/KDE) render
        # working minimize / maximize / close buttons + the system menu.
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowSystemMenuHint
        )
        self.setMinimumSize(900, 600)
        self.setMaximumSize(16777215, 16777215)

        self._build_menus()
        self._build_central()
        self._wire_ctx()
        self._wire_signals()
        self._build_shortcuts()
        self._load_geometry()
        self._populate_devices()

        cases = self.ctx.case_manager.list_cases()
        self.ctx.current_case = cases[0]["case_id"] if cases else "\u2014"
        self._apply_case_context()
        self.explorer.refresh()
        self.status_bar.set_connection("ok")
        self.log("Forensic Suite ready.", "#00E5FF")
        self.show_tab("home")
        QTimer.singleShot(500, self._first_refresh)

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        file_menu.addAction("New Case\u2026", self._new_case_dialog,
                            QKeySequence("Ctrl+N"))
        file_menu.addAction("Import evidence\u2026", lambda: self.import_evidence("any"),
                            QKeySequence("Ctrl+I"))
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close, QKeySequence("Ctrl+Q"))

        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction("Search artifacts", self._focus_search,
                            QKeySequence("Ctrl+F"))
        edit_menu.addAction("Refresh all views", self._refresh_all, "F5")

        view_menu = menubar.addMenu("&View")
        view_menu.addAction("Toggle inspector panel", self._toggle_panel)
        view_menu.addAction("Toggle case explorer", self._toggle_explorer,
                            QKeySequence("Ctrl+B"))
        for index, key in enumerate(TAB_KEYS, start=1):
            view_menu.addAction(key.title().replace("_", " "),
                                lambda _=False, k=key: self.show_tab(k),
                                f"Ctrl+{index}" if index <= 9 else "")

        tools_menu = menubar.addMenu("&Tools")
        tools_menu.addAction("External Tools\u2026",
                             lambda: self.show_tab("tools"),
                             QKeySequence("Ctrl+T"))
        tools_menu.addSeparator()
        tools_menu.addAction("Extraction", lambda: self.show_tab("extraction"),
                             QKeySequence("Ctrl+E"))
        tools_menu.addAction("Data Viewer", lambda: self.show_tab("data"),
                             "Ctrl+2")
        tools_menu.addAction("Timeline", lambda: self.show_tab("timeline"),
                             "Ctrl+3")

        reports_menu = menubar.addMenu("&Reports")
        reports_menu.addAction("Generate preview", self._focus_reports)
        reports_menu.addAction("Export PDF",
                               lambda: self._export_action("pdf"))
        reports_menu.addAction("Export HTML",
                               lambda: self._export_action("html"))

        help_menu = menubar.addMenu("&Help")
        help_menu.addAction("About", self._about)
        help_menu.addAction("Keyboard shortcuts", self._shortcuts_help)

    def _build_central(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.toolbar = TopToolBar()
        self.toolbar.setObjectName("MainToolBar")
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        splitter = QSplitter(Qt.Horizontal)
        self.sidebar = Sidebar()
        splitter.addWidget(self.sidebar)
        self.explorer = CaseExplorer(self.ctx)
        self.explorer.setMinimumWidth(180)
        splitter.addWidget(self.explorer)

        self.stack = QStackedWidget()
        self.home = HomeTab(self.ctx)
        self.overview = OverviewTab(self.ctx)
        self.files_tab = FilesTab(self.ctx)
        self.dashboard = DashboardTab(self.ctx)
        self.extraction = ExtractionTab(self.ctx)
        self.data_viewer = DataViewerTab(self.ctx)
        self.timeline = TimelineTab(self.ctx)
        self.reports = ReportsTab(self.ctx)
        self.tools = ToolsTab(self.ctx)
        self.ai = AIAssistantTab(self.ctx)
        self.settings_tab = SettingsTab(self.ctx)
        for key, widget in (("home", self.home),
                            ("dashboard", self.dashboard),
                            ("extraction", self.extraction),
                            ("overview", self.overview),
                            ("files", self.files_tab),
                            ("data", self.data_viewer),
                            ("timeline", self.timeline),
                            ("reports", self.reports),
                            ("tools", self.tools),
                            ("ai", self.ai),
                            ("settings", self.settings_tab)):
            self.tabs[key] = widget
            self.stack.addWidget(widget)
        splitter.addWidget(self.stack)

        self.right_panel = RightPanel()
        splitter.addWidget(self.right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 1)
        splitter.setStretchFactor(3, 0)
        splitter.setSizes([200, 270, 760, 310])

        layout.addWidget(splitter, 1)
        self.status_bar = StatusBar()
        self.setStatusBar(self.status_bar)
        self.setCentralWidget(central)
        self.toast = Toast(central)

    def _wire_ctx(self) -> None:
        self.ctx.navigate = self.show_tab
        self.ctx.notify = self.notify
        self.ctx.status = self._set_status
        self.ctx.log = self.right_panel.log
        self.ctx.add_custody = self.right_panel.add_custody
        self.ctx.show_new_case_dialog = self._new_case_dialog
        self.ctx.open_extraction = self.open_extraction
        self.ctx.open_section = self.open_section
        self.ctx.refresh_explorer = self.explorer.refresh
        self.ctx.import_evidence = self.import_evidence
        self.ctx.process_extraction = self.process_extraction

    def _set_status(self, task: str, state: str, progress: int) -> None:
        self.status_bar.set_task(task if task else "Idle", progress)
        self.status_bar.set_connection(state)

    def _wire_signals(self) -> None:
        self.sidebar.navigation_requested.connect(self.show_tab)
        self.explorer.activated.connect(self._explorer_activated)
        self.explorer.reindex_requested.connect(self._reindex)
        self.explorer.deleted.connect(self._after_delete)
        self.toolbar.new_case_clicked.connect(self._new_case_dialog)
        self.toolbar.extract_clicked.connect(lambda: self.show_tab("extraction"))
        self.toolbar.import_clicked.connect(lambda: self.import_evidence("any"))
        self.toolbar.export_clicked.connect(lambda: self.show_tab("reports"))
        self.toolbar.search_clicked.connect(self._focus_search)
        self.toolbar.settings_clicked.connect(lambda: self.show_tab("settings"))
        self.data_viewer.set_selection_callback(self._show_selection)
        self.ai.ai_state_changed.connect(self.toolbar.set_ai_status)
        self.settings_tab.config_changed.connect(self._apply_config)

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._new_case_dialog)
        QShortcut(QKeySequence("Ctrl+E"), self,
                  activated=lambda: self.show_tab("extraction"))
        QShortcut(QKeySequence("Ctrl+T"), self,
                  activated=lambda: self.show_tab("tools"))
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)
        QShortcut(QKeySequence("F5"), self, activated=self._refresh_all)
        QShortcut(QKeySequence("Ctrl+,"), self,
                  activated=lambda: self.show_tab("settings"))
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)

    def show_tab(self, key: str) -> None:
        widget = self.tabs.get(key)
        if widget is None:
            return
        self.stack.setCurrentWidget(widget)
        # these pages carry their own detail panels; give them the width
        self.right_panel.setVisible(self._inspector_wanted and key not in ("home", "overview", "files"))
        self.sidebar.set_active(key)
        if key == "dashboard":
            self.dashboard.refresh()
        elif key == "home":
            self.home.refresh()
        elif key == "timeline":
            self.timeline.set_case(self.ctx.current_case)
        elif key == "files" and self.files_tab.case_id is None:
            self.files_tab.set_scope(self.ctx.current_case, self.ctx.current_extraction)
        elif key == "overview" and self.ctx.current_extraction:
            self.overview.show_extraction(self.ctx.current_extraction)  # counts may have changed

    def notify(self, title: str, message: str) -> None:
        if self.toast is not None:
            self.toast.show_message(f"{title}: {message}")
        self.status_bar.showMessage(f"{title}: {message}", 4000)
        self.status_bar.add_notification(f"{title}: {message}")

    def log(self, message: str, color: str = "#8B949E") -> None:
        self.right_panel.log(message, color)

    def _show_selection(self, info: dict, md5: str, sha: str) -> None:
        self.right_panel.show_selection(info)
        self.right_panel.show_hashes(md5, sha)
        self.right_panel.set_suggestions(
            "AI hint: verify this artifact's SHA-256 against the acquisition "
            "manifest before treating it as evidentially sound.")

    def _new_case_dialog(self) -> None:
        dialog = NewCaseDialog(self)
        if dialog.exec() != QDialog.Accepted or dialog.result_data is None:
            return
        data = dialog.result_data
        try:
            case = self.ctx.case_manager.create_case(
                data["case_id"], data["title"], data["examiner"],
                data["authorization"])
        except ValueError as exc:
            QMessageBox.warning(self, "New case", str(exc))
            return
        self.ctx.current_case = case.case_id
        self._apply_case_context()
        self.right_panel.add_custody("analyst", "case_created")
        self.notify("Case", f"Case {case.case_id} created")
        self.dashboard.refresh()
        self.explorer.refresh()
        self.home.refresh()

    def _apply_case_context(self) -> None:
        case_id = self.ctx.current_case
        self.status_bar.set_case(case_id)
        self.data_viewer.set_case(case_id)
        self.log(f"Active case set to {case_id}", "#00E5FF")

    # ------------------------------------------------------------ navigation
    def _toggle_explorer(self) -> None:
        self.explorer.setVisible(not self.explorer.isVisible())

    def _explorer_activated(self, kind: str, case_id: str, ext_id: int, section: str) -> None:
        if kind == "case":
            self.ctx.current_case = case_id
            self.ctx.current_extraction = None
            self._apply_case_context()
            self.explorer.refresh()
            self.files_tab.case_id = None      # re-scope on next visit
        elif kind == "extraction":
            self.open_extraction(ext_id)
        else:
            self.open_section(section, ext_id)

    def open_extraction(self, extraction_id: int) -> None:
        ext = self.ctx.case_manager.get_extraction(extraction_id)
        if ext is None:
            return
        self.ctx.current_case = ext["case"]
        self.ctx.current_extraction = extraction_id
        self._apply_case_context()
        self.overview.show_extraction(extraction_id)
        self.show_tab("overview")

    def open_section(self, section: str, extraction_id: int | None = None) -> None:
        ext = self.ctx.case_manager.get_extraction(extraction_id) if extraction_id else None
        if ext is not None:
            self.ctx.current_case = ext["case"]
            self.ctx.current_extraction = extraction_id
            self._apply_case_context()
        case_id, ext_id = self.ctx.current_case, self.ctx.current_extraction
        if section == "overview" and ext_id:
            self.open_extraction(ext_id)
        elif section in ("files", "images", "key", "hashhits", "search"):
            self.files_tab.reset_filters() if self.files_tab.case_id else None
            self.files_tab.set_scope(case_id, ext_id,
                                     category="images" if section == "images" else "all",
                                     key_only=section == "key")
            if section == "hashhits":
                self.files_tab.adv = {"hash_hit": True}
                self.files_tab.reload()
            self.show_tab("files")
            if section == "search":
                self.files_tab.search.setFocus()
        elif section in ("contacts", "calls", "messages", "calendar", "apps", "whatsapp"):
            self.show_tab("data")
            self.data_viewer.show_category({"messages": "sms"}.get(section, section))
        elif section == "timeline":
            self.show_tab("timeline")
        elif section == "reports":
            self.show_tab("reports")

    def _after_delete(self) -> None:
        self.overview.ext = None
        self.ctx.current_extraction = None
        self.files_tab.case_id = None
        self.home.refresh()
        self.dashboard.refresh()

    # ------------------------------------------------------------ indexing queue
    def process_extraction(self, case_id: str, extraction_id: int, root: str) -> None:
        self._index_queue.append((case_id, extraction_id, root))
        self._next_index()

    def _reindex(self, extraction_id: int) -> None:
        ext = self.ctx.case_manager.get_extraction(extraction_id)
        if ext and ext["out_dir"]:
            self.process_extraction(ext["case"], extraction_id, ext["out_dir"])

    def _next_index(self) -> None:
        if (self._index_worker is not None and self._index_worker.isRunning()) or not self._index_queue:
            return
        case_id, ext_id, root = self._index_queue.pop(0)
        worker = IndexWorker(self.ctx, case_id, ext_id, root, self)
        worker.progress.connect(self._index_progress)
        worker.done.connect(self._index_done)
        worker.failed.connect(self._index_failed)
        self._index_worker = worker
        self.notify("Indexing", f"Parsing and indexing extraction #{ext_id}\u2026")
        worker.start()

    def _index_progress(self, message: str, percent: int) -> None:
        self._set_status(message[:40], "busy", percent)
        self.extraction.index_progress(message, percent)

    def _index_done(self, ext_id: int, summary: dict) -> None:
        self._set_status("Idle", "ok", 100)
        self.extraction.index_done(True)
        parsed = sum(summary.get("artifacts", {}).values()) + summary.get("whatsapp", 0)
        msg = f"{summary.get('files', 0):,} files indexed, {parsed:,} records parsed"
        if summary.get("hash_hits"):
            msg += f", {summary['hash_hits']} hash-set hit(s)"
        self.notify("Indexing", msg)
        self.ctx.add_custody(self.ctx.current_case, f"indexed extraction={ext_id} {msg}")
        self.ctx.current_extraction = ext_id
        self.explorer.refresh()
        self.home.refresh()
        self.dashboard.refresh()
        self.files_tab.case_id = None
        if self.overview.ext and self.overview.ext["id"] == ext_id:
            self.overview.show_extraction(ext_id)
        self.timeline.set_case(self.ctx.current_case)
        self._next_index()

    def _index_failed(self, ext_id: int, error: str) -> None:
        self._set_status("Idle", "error", 0)
        self.extraction.index_done(False)
        self.notify("Indexing failed", error)
        self._next_index()

    # ------------------------------------------------------------ import
    def import_evidence(self, kind: str) -> None:
        case = self.ctx.case_manager.get_case(self.ctx.current_case)
        if case is None:
            self.notify("Import", "Create a case first; it records the examiner and authorization.")
            self._new_case_dialog()
            return
        if self._import_worker is not None and self._import_worker.isRunning():
            self.notify("Import", "An import is already running.")
            return
        source, label = "", ""
        if kind == "folder":
            source, label = QFileDialog.getExistingDirectory(self, "Select evidence folder"), "folder"
        elif kind == "archive":
            source, _ = QFileDialog.getOpenFileName(
                self, "Select file-system archive", "", "Archives (*.zip *.tar *.tgz *.tar.gz);;All files (*)")
            label = "file-system archive"
        elif kind == "whatsapp":
            source, _ = QFileDialog.getOpenFileName(
                self, "Select a decrypted msgstore.db", "", "SQLite (*.db *.sqlite);;All files (*)")
            label = "WhatsApp database"
        elif kind == "any":
            box = QMessageBox(self)
            box.setWindowTitle("Import evidence")
            box.setText("What do you want to import?")
            f_btn = box.addButton("Folder", QMessageBox.AcceptRole)
            a_btn = box.addButton("File (image / archive / backup)", QMessageBox.AcceptRole)
            box.addButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is f_btn:
                return self.import_evidence("folder")
            if box.clickedButton() is a_btn:
                return self.import_evidence("image")
            return
        else:  # "image": any single file
            source, _ = QFileDialog.getOpenFileName(self, "Select image / backup file")
            label = "image / backup"
        if not source:
            return
        answer = QMessageBox.question(
            self, "Confirm authorization",
            f"Import '{source}' into case {case.case_id}?\n\nAuthorization: "
            f"{case.authorization_ref}\nExaminer: {case.examiner}\n\nThe original is copied, "
            "hash-verified and logged; it is never modified. Continue only if you hold "
            "authorization to examine this material.", QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        root = self.extraction.output_path.text()
        worker = ImportWorker(self.ctx, root, case, source, label, self)
        worker.progress.connect(self._index_progress)
        worker.done.connect(self._import_done)
        worker.failed.connect(self._import_failed)
        self._import_worker = worker
        self.ctx.add_custody(case.examiner, f"import_started source={source}")
        self.notify("Import", f"Importing {Path(source).name}\u2026")
        worker.start()

    def _import_done(self, ext_id: int, summary: dict) -> None:
        self._index_done(ext_id, summary)
        self.open_extraction(ext_id)

    def _import_failed(self, error: str) -> None:
        self._set_status("Idle", "error", 0)
        self.notify("Import failed", error)

    def _focus_search(self) -> None:
        self.show_tab("data")
        self.data_viewer.table.search_box.setFocus()
        self.data_viewer.table.search_box.selectAll()

    def _focus_reports(self) -> None:
        self.show_tab("reports")
        self.reports._generate()

    def _export_action(self, kind: str) -> None:
        self.show_tab("reports")
        self.reports._export(kind)

    def _refresh_all(self) -> None:
        self.dashboard.refresh()
        self.explorer.refresh()
        self.extraction.refresh_devices()
        self.log("All views refreshed", "#8B949E")

    def _toggle_panel(self) -> None:
        self._inspector_wanted = not self._inspector_wanted
        self.right_panel.setVisible(self._inspector_wanted)

    def _populate_devices(self) -> None:
        # The Extraction tab detects devices in the background and reports
        # back through devices_changed; nothing blocks startup here.
        self.sidebar.set_devices("\u25cb  Checking\u2026")
        self.extraction.devices_changed.connect(self._on_devices_changed)

    def _on_devices_changed(self, devices: list) -> None:
        if devices:
            text = "\n".join(
                f"\u25cf {d.model}" + ("" if d.state == "device" else f" ({d.state})")
                for d in devices[:3])
        else:
            text = "\u25cb  No device"
        self.sidebar.set_devices(text)

    def _first_refresh(self) -> None:
        self.dashboard.refresh()
        self.extraction.refresh_devices()
        self._apply_case_context()

    def _apply_config(self) -> None:
        theme = self.config.get("appearance", "theme", "dark")
        size = int(self.config.get("appearance", "font_size", 13))
        app = QApplication.instance()
        if app is not None:
            app.setFont(QFont("Segoe UI", size))
            if theme == "dark":
                app.setStyleSheet(load_stylesheet())
            else:
                app.setStyleSheet("")
                self._apply_light_palette(app)
        self.log(f"Appearance: {theme} theme, {size} px font", "#00E5FF")

    @staticmethod
    def _apply_light_palette(app: QApplication) -> None:
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#F5F6F8"))
        palette.setColor(QPalette.Base, QColor("#FFFFFF"))
        palette.setColor(QPalette.Text, QColor("#1F2328"))
        palette.setColor(QPalette.WindowText, QColor("#1F2328"))
        palette.setColor(QPalette.ButtonText, QColor("#1F2328"))
        palette.setColor(QPalette.Highlight, QColor("#00E5FF"))
        palette.setColor(QPalette.HighlightedText, QColor("#04121F"))
        app.setPalette(palette)

    def _load_geometry(self) -> None:
        geometry = self.settings.value("geometry")
        state = self.settings.value("windowState")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            self.restoreState(state)

    def closeEvent(self, event) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.toast is not None:
            self.toast._move()

    def mouseDoubleClickEvent(self, event) -> None:
        """Double-click on the top toolbar toggles maximize (Linux fallback)."""
        from PySide6.QtWidgets import QToolBar
        widget = self.childAt(event.position().toPoint())
        if isinstance(widget, QToolBar) or (widget is not None
                                            and widget.parent() is self.toolbar):
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
        super().mouseDoubleClickEvent(event)

    def _about(self) -> None:
        QMessageBox.about(
            self, "About Forensic Suite",
            "<b>Forensic Suite</b> v0.1.0<br/>Master's research project in "
            "Digital Forensics.<br/><br/><i>Authorized use only.</i>")

    def _shortcuts_help(self) -> None:
        QMessageBox.information(
            self, "Keyboard shortcuts",
            "Ctrl+N   New case\nCtrl+E   Extraction tab\n"
            "Ctrl+T   External tools\n"
            "Ctrl+F   Search artifacts\nCtrl+1..8   Switch tabs\n"
            "F5       Refresh all\nCtrl+,    Settings\n"
            "Ctrl+Q   Quit")