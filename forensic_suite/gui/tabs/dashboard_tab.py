"""Dashboard tab: animated stat cards, charts, recent activity, quick actions."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout,
                               QWidget)

from widgets.chart_widget import ChartWidget
from widgets.stat_card import StatCard

QUICK_ACTIONS = [
    ("New Case", "\U0001F4C1", "new_case"),
    ("Start Extraction", "\U0001F4F1", "extraction"),
    ("Open Data Viewer", "\U0001F50D", "data"),
    ("Open Timeline", "\U0001F4C8", "timeline"),
    ("Generate Report", "\U0001F4C4", "reports"),
    ("Ask AI", "\U0001F916", "ai"),
]

_ACTIVITY_COLORS = {
    "case": "#00E5FF", "extract": "#7C4DFF", "import": "#00E676",
    "report": "#FFAB00", "parse": "#3AA6FF", "export": "#F48FB1",
}


class DashboardTab(QWidget):
    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        heading = QLabel("\U0001F4C2  Dashboard")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)

        cards = QHBoxLayout()
        cards.setSpacing(14)
        self.case_card = StatCard("Total Cases", "\U0001F4C2", "#00E5FF")
        self.device_card = StatCard("Devices Extracted", "\U0001F4F1", "#7C4DFF")
        self.data_card = StatCard("Data Extracted", "\U0001F4BE", "#00E676")
        self.task_card = StatCard("Active Tasks", "\u23F3", "#FFAB00")
        for card in (self.case_card, self.device_card, self.data_card, self.task_card):
            cards.addWidget(card)
        layout.addLayout(cards)

        charts = QHBoxLayout()
        charts.setSpacing(14)
        self.bar_chart = ChartWidget(title="Data by category")
        self.donut_chart = ChartWidget(title="Device distribution")
        self.line_chart = ChartWidget(title="Extraction activity (7 days)")
        charts.addWidget(self.bar_chart, 1)
        charts.addWidget(self.donut_chart, 1)
        charts.addWidget(self.line_chart, 1)
        layout.addLayout(charts, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(14)

        activity_wrap = QWidget()
        activity_wrap.setObjectName("Card")
        act_lay = QVBoxLayout(activity_wrap)
        act_lay.setContentsMargins(12, 12, 12, 12)
        self.activity = QListWidget()
        act_lay.addWidget(QLabel("Recent Activity"))
        act_lay.addWidget(self.activity)
        bottom.addWidget(activity_wrap, 3)

        quick_wrap = QWidget()
        quick_wrap.setObjectName("Card")
        q_lay = QGridLayout(quick_wrap)
        q_lay.setContentsMargins(12, 12, 12, 12)
        q_lay.addWidget(QLabel("Quick Actions"), 0, 0, 1, 2)
        for i, (label, icon, key) in enumerate(QUICK_ACTIONS):
            btn = QPushButton(f"{icon}  {label}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._quick(k))
            q_lay.addWidget(btn, 1 + i // 2, i % 2)
        bottom.addWidget(quick_wrap, 2)
        layout.addLayout(bottom, 1)

    def _quick(self, key: str) -> None:
        if key == "new_case":
            self.ctx.show_new_case_dialog()
        else:
            self.ctx.navigate(key)

    def refresh(self) -> None:
        """Pull fresh statistics from the case manager and repaint widgets."""
        stats = self.ctx.case_manager.stats()
        self.case_card.set_value(stats["cases"])
        self.device_card.set_value(stats["devices"])
        self.data_card.set_text(f"{stats['data_gb']} GB")
        self.task_card.set_value(stats["active_tasks"])

        if stats["categories"]:
            self.bar_chart.set_bar(list(stats["categories"]),
                                   list(stats["categories"].values()))
        if stats["platforms"]:
            self.donut_chart.set_donut(list(stats["platforms"]),
                                       list(stats["platforms"].values()))
        if stats["activity"]:
            labels, values = zip(*stats["activity"])
            self.line_chart.set_line(list(labels), list(values))

        self.activity.clear()
        for entry in self.ctx.case_manager.recent_activity(30):
            color = next((c for kw, c in _ACTIVITY_COLORS.items()
                          if kw in entry["action"]), "#8B949E")
            item = QListWidgetItem(
                f'[{entry["time"]}] {entry["user"]} \u2014 {entry["action"]} '
                f'({entry["case"]})')
            item.setForeground(QColor(color))
            self.activity.addItem(item)