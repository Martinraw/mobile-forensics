"""Timeline: zoomable event visualization with filters and click details."""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from matplotlib import dates as mdates

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QComboBox, QDateEdit, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

from widgets.chart_widget import ChartWidget

CATEGORIES = ["messages", "calls", "media", "locations"]
PALETTE = {"messages": "#00E5FF", "calls": "#7C4DFF", "media": "#00E676",
           "locations": "#FFAB00", "contacts": "#3AA6FF", "cloud": "#F48FB1",
           "deleted": "#FF1744", "apps": "#8B949E"}

_TEMPLATES = [
    "Contact circled the suspect location twice the same evening",
    "Messaging traffic spikes just before the incident window",
    "Deleted SMS recovered from the WAL journal",
    "Media file shared minutes after the outgoing call",
    "Location ping 800 m from the crime scene",
]


class TimelineTab(QWidget):
    """Interactive, filterable, zoomable artifact timeline."""

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.events = self._generate_events()
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

    def _generate_events(self) -> list[dict]:
        now = datetime.now()
        events = []
        for _ in range(140):
            days_back = random.randint(0, 30)
            minutes = random.randint(0, 1439)
            ts = now - timedelta(days=days_back, minutes=minutes)
            category = random.choice(CATEGORIES)
            template = random.choice(_TEMPLATES)
            events.append({
                "ts": ts, "category": category,
                "detail": f"{category.capitalize()} event on {ts:%Y-%m-%d %H:%M} "
                          f"\u2014 {template}",
            })
        return events
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
        self.ctx.log(f"Timeline filtered: {len(annotations)} events", "#00E5FF")

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
