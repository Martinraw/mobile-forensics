"""Matplotlib chart canvas styled to match the forensic theme."""
from __future__ import annotations

import matplotlib

matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PySide6.QtWidgets import QVBoxLayout, QWidget

PALETTE = ["#00E5FF", "#7C4DFF", "#00E676", "#FFAB00",
           "#FF1744", "#3AA6FF", "#F48FB1", "#8B949E"]
BG = "#161B22"
GRID = "#30363D"
TEXT = "#E6EDF3"
MUTED = "#8B949E"


class ChartWidget(QWidget):
    """Embedded matplotlib canvas that draws bar/donut/line charts."""

    def __init__(self, parent: QWidget | None = None, title: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("ChartCanvas")
        self.setMinimumHeight(240)
        self._title = title
        self.figure = Figure(figsize=(5, 3), dpi=100, facecolor=BG, tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.mpl_connect("pick_event", self._on_pick)
        self.pick_callback = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.canvas)
        if title:
            self.figure.suptitle(title, color=TEXT, fontsize=11, fontweight="bold")

    def set_pick_callback(self, callback) -> None:
        """Register a callable(index) invoked when a scatter point is picked."""
        self.pick_callback = callback

    def _on_pick(self, event) -> None:
        if self.pick_callback is None or not hasattr(event, "ind"):
            return
        if len(event.ind):
            self.pick_callback(int(event.ind[0]))

    def clear(self) -> None:
        self.figure.clear()
        if self._title:
            self.figure.suptitle(self._title, color=TEXT, fontsize=11, fontweight="bold")
        self.canvas.draw_idle()

    @staticmethod
    def _style_axes(ax) -> None:
        ax.set_facecolor(BG)
        ax.tick_params(colors=MUTED, labelsize=9)
        for spine in ax.spines.values():
            spine.set_color(GRID)

    def set_bar(self, labels: list[str], values: list[int]) -> None:
        self.clear()
        ax = self.figure.add_subplot(111)
        colors = [PALETTE[i % len(PALETTE)] for i in range(len(labels))]
        bars = ax.bar(labels, values, color=colors, width=0.6)
        self._style_axes(ax)
        ax.set_ylabel("Items", color=MUTED, fontsize=9)
        top = max(values) if values else 1
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, value + top * 0.02,
                    f"{value:,}", ha="center", va="bottom", color=TEXT, fontsize=8)
        ax.set_ylim(0, top * 1.15)
        self.canvas.draw_idle()

    def set_donut(self, labels: list[str], values: list[int]) -> None:
        self.clear()
        ax = self.figure.add_subplot(111)
        colors = [PALETTE[i % len(PALETTE)] for i in range(len(labels))]
        wedges, _ = ax.pie(values, colors=colors, startangle=90,
                           counterclock=False,
                           wedgeprops={"width": 0.42, "edgecolor": BG})
        self._style_axes(ax)
        ax.legend(wedges, [f"{label}  ({value})" for label, value in zip(labels, values)],
                  loc="center left", bbox_to_anchor=(1.0, 0.5),
                  facecolor=BG, edgecolor=GRID, labelcolor=TEXT, fontsize=8)
        self.canvas.draw_idle()

    def set_line(self, labels: list[str], values: list[int]) -> None:
        self.clear()
        ax = self.figure.add_subplot(111)
        x = list(range(len(values)))
        ax.plot(x, values, color="#00E5FF", linewidth=2, marker="o", markersize=4,
                markerfacecolor="#7C4DFF")
        ax.fill_between(x, values, color="#00E5FF", alpha=0.12)
        self._style_axes(ax)
        if labels:
            ticks = list(range(0, len(labels), max(len(labels) // 6, 1)))
            ax.set_xticks(ticks)
            ax.set_xticklabels([labels[i] for i in ticks], rotation=30, ha="right")
        ax.set_ylabel("Events", color=MUTED, fontsize=9)
        self.canvas.draw_idle()

    def set_scatter_timeline(self, xs: list[float], ys: list[str],
                             colors: list[str], annotations: list) -> None:
        """Scatter of events used by the timeline tab (xs are matplotlib dates)."""
        import matplotlib.dates as mdates

        self.clear()
        ax = self.figure.add_subplot(111)
        unique_y = sorted(set(ys))
        y_index = {name: i for i, name in enumerate(unique_y)}
        ax.scatter(xs, [y_index[y] for y in ys], c=colors, s=60, picker=6)
        ax.set_yticks(range(len(unique_y)))
        ax.set_yticklabels(unique_y, color=MUTED, fontsize=9)
        self._style_axes(ax)
        if xs:
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
            for label in ax.get_xticklabels():
                label.set_rotation(30)
                label.set_ha("right")
        self._annotations = list(zip(xs, ys, annotations, colors))
        self.canvas.draw_idle()

    @property
    def annotations(self) -> list:
        return getattr(self, "_annotations", [])