"""Bottom status bar: case/device, active task progress, telemetry, clock."""
from __future__ import annotations

from datetime import datetime

try:
    import psutil
except ImportError:  # tolerate the dependency being unavailable
    psutil = None

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QMenu, QProgressBar, QStatusBar, QToolButton, QWidget

_CONN_TEXT = {
    "ok": "\U0001F7E2  Connected",
    "busy": "\U0001F7E1  Busy",
    "error": "\U0001F534  Error",
    "idle": "\u26AA  Idle",
}
_CONN_STYLE = {
    "ok": "color:#00E676;",
    "busy": "color:#FFAB00;",
    "error": "color:#FF1744;",
    "idle": "color:#8B949E;",
}


class StatusBar(QStatusBar):
    """Live status area: context on the left, telemetry/progress on the right."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizeGripEnabled(False)

        self.case_label = QLabel("Case: \u2014")
        self.case_label.setObjectName("StatusAccent")
        self.addWidget(self.case_label)

        self.device_label = QLabel("Device: \u2014")
        self.addWidget(self.device_label)

        self._history: list[str] = []
        self._unread = 0
        self.notif_btn = QToolButton()
        self.notif_btn.setAutoRaise(True)
        self.notif_btn.setToolTip("Notifications")
        self.notif_btn.clicked.connect(self._show_notifications)
        self._update_notif()
        self.addPermanentWidget(self.notif_btn)

        self.task_label = QLabel("Idle")
        self.task_label.setStyleSheet("color:#8B949E;")
        self.addPermanentWidget(self.task_label)

        self.progress = QProgressBar()
        self.progress.setFixedWidth(180)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.addPermanentWidget(self.progress)

        self.resources = QLabel("CPU \u2014  \u00b7  RAM \u2014")
        self.resources.setStyleSheet("color:#8B949E;")
        self.addPermanentWidget(self.resources)

        self.connection = QLabel(_CONN_TEXT["idle"])
        self.connection.setStyleSheet(_CONN_STYLE["idle"])
        self.addPermanentWidget(self.connection)

        self.clock = QLabel("")
        self.clock.setStyleSheet("color:#8B949E;")
        self.addPermanentWidget(self.clock)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

    def _tick(self) -> None:
        self.clock.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        if psutil is not None:
            try:
                cpu = psutil.cpu_percent(None)
                ram = psutil.virtual_memory().percent
                self.resources.setText(f"CPU {cpu:.0f}%  \u00b7  RAM {ram:.0f}%")
            except Exception:
                pass

    def set_case(self, text: str) -> None:
        self.case_label.setText(f"Case: {text}")

    def set_device(self, text: str) -> None:
        self.device_label.setText(f"Device: {text}")

    def set_task(self, text: str, progress: int) -> None:
        self.task_label.setText(text)
        self.progress.setValue(max(0, min(progress, 100)))

    def set_connection(self, state: str) -> None:
        self.connection.setText(_CONN_TEXT.get(state, state))
        self.connection.setStyleSheet(_CONN_STYLE.get(state, _CONN_STYLE["idle"]))

    # ---- notification centre ----
    def add_notification(self, text: str) -> None:
        self._history.append(f"{datetime.now():%H:%M:%S}  {text}")
        self._history = self._history[-50:]
        self._unread += 1
        self._update_notif()

    def _update_notif(self) -> None:
        self.notif_btn.setText(f"\U0001F514 {self._unread}" if self._unread else "\U0001F514")

    def _show_notifications(self) -> None:
        menu = QMenu(self)
        if not self._history:
            menu.addAction("No notifications").setEnabled(False)
        for line in reversed(self._history[-15:]):
            menu.addAction(line[:140]).setEnabled(False)
        menu.addSeparator()
        menu.addAction("Clear", self._clear_notifications)
        self._unread = 0
        self._update_notif()
        menu.exec(self.notif_btn.mapToGlobal(self.notif_btn.rect().topLeft()
                                              - self.notif_btn.rect().bottomLeft()))

    def _clear_notifications(self) -> None:
        self._history.clear()
        self._unread = 0
        self._update_notif()
