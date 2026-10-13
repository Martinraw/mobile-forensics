"""Timeline: zoomable event visualization with filters and click details."""
from __future__ import annotations

from datetime import datetime

from matplotlib import dates as mdates

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QComboBox, QDateEdit, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

from widgets.chart_widget import ChartWidget

CATEGORIES = ["messages", "calls", "calendar", "media", "documents"]
PALETTE = {"messages": "#00E5FF", "calls": "#7C4DFF", "media": "#00E676",
           "calendar": "#FFAB00", "documents": "#3AA6FF"}


class TimelineTab(QWidget):
    """Interactive, filterable, zoomable artifact timeline."""

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.events: list[dict] = []
        self._case_id: str | None = None
        self._filtered_events: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        heading = QLabel("\U0001F4C8  Timeline")
        heading.setObjectName("SectionTitle")
        toolbar.addWidget(heading)
        toolbar.addStretch()

        self.cat_filter = QComboBox()
        self.cat_filter.addItem("All categories", "")
        for name in CATEGORIES:
            self.cat_filter.addItem(name.capitalize(), name)
        self.cat_filter.setMinimumWidth(140)
        toolbar.addWidget(self.cat_filter)

        self.keyword = QLineEdit()
        self.keyword.setPlaceholderText("Keyword\u2026")
        self.keyword.setMaximumWidth(170)
        toolbar.addWidget(self.keyword)

        self.start_date = QDateEdit(QDate.currentDate().addDays(-30))
        self.end_date = QDateEdit(QDate.currentDate())
        for widget in (self.start_date, self.end_date):
            widget.setCalendarPopup(True)
        toolbar.addWidget(QLabel("From"))
        toolbar.addWidget(self.start_date)
        toolbar.addWidget(QLabel("To"))
        toolbar.addWidget(self.end_date)

        apply = QPushButton("Apply filters")
        apply.setObjectName("Primary")
        apply.clicked.connect(self._apply)
        toolbar.addWidget(apply)
        layout.addLayout(toolbar)

        zoom = QHBoxLayout()
        self.count_label = QLabel("")
        self.count_label.setProperty("role", "muted")
        zoom.addWidget(self.count_label)
        zoom.addStretch()
        zoom_in = QPushButton("Zoom +")
        zoom_out = QPushButton("Zoom \u2212")
        reset = QPushButton("Reset")
        for btn in (zoom_in, zoom_out, reset):
            btn.setObjectName("Ghost")
        zoom_in.clicked.connect(lambda: self._zoom(0.5))
        zoom_out.clicked.connect(lambda: self._zoom(1.5))
        reset.clicked.connect(self._reset_zoom)
        zoom.addWidget(zoom_in)
        zoom.addWidget(zoom_out)
        zoom.addWidget(reset)
        layout.addLayout(zoom)

        self.chart = ChartWidget(title="Artifact timeline")
        self.chart.set_pick_callback(self._on_pick)
        layout.addWidget(self.chart, 1)

        self.detail = QLabel("Click a point for details.")
        self.detail.setObjectName("Card")
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)

    def set_case(self, case_id: str | None) -> None:
        """Load real dated events (artifacts + file modification times) for the case."""
        self._case_id = case_id
        self.events = self.ctx.case_manager.timeline_events(case_id) if case_id else []
        if self.events:
            self.start_date.setDate(QDate(self.events[0]["ts"].year, self.events[0]["ts"].month,
                                          self.events[0]["ts"].day))
            last = self.events[-1]["ts"]
            self.end_date.setDate(QDate(last.year, last.month, last.day))
        self._apply()

    def _apply(self) -> None:
        start = self.start_date.date().toPython()
        end = self.end_date.date().toPython()
        term = self.keyword.text().strip().lower()
        category = self.cat_filter.currentData()

        xs, ys, colors, annotations = [], [], [], []
        for event in self.events:
            day = event["ts"].date()
            if day < start or day > end:
                continue
            if category and event["category"] != category:
                continue
            if term and term not in event["detail"].lower():
                continue
            xs.append(mdates.date2num(event["ts"]))
            ys.append(event["category"].capitalize())
            colors.append(PALETTE.get(event["category"], "#8B949E"))
            annotations.append(event)

        self.chart.set_scatter_timeline(xs, ys, colors, annotations)
        self._filtered_events = annotations
        self.count_label.setText(f"{len(annotations)} events")
        self.ctx.log(f"Timeline: {len(annotations)} events", "#00E5FF")

    def _on_pick(self, index: int) -> None:
        if index >= len(self._filtered_events):
            return
        event = self._filtered_events[index]
        self.detail.setText(f"\U0001F4CC  {event['detail']}")
        self.ctx.log(f"Timeline event: {event['detail']}", "#FFAB00")

    def _zoom(self, factor: float) -> None:
        if not self.chart.figure.axes:
            return
        ax = self.chart.figure.axes[0]
        xmin, xmax = ax.get_xlim()
        mid = (xmin + xmax) / 2
        half = max((xmax - xmin) * factor / 2, 0.25)
        ax.set_xlim(mid - half, mid + half)
        self.chart.canvas.draw_idle()

    def _reset_zoom(self) -> None:
        if not self.chart.figure.axes:
            return
        ax = self.chart.figure.axes[0]
        ax.autoscale()
        self.chart.canvas.draw_idle()
