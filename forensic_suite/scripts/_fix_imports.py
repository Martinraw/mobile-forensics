"""Convert relative imports in the suite to absolute (root-package) imports."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REPLACEMENTS: dict[str, list[tuple[str, str]]] = {
    "gui/__init__.py": [
        ("from ..core.ai_client import AIClient", "from core.ai_client import AIClient"),
        ("from ..core.case_manager import CaseManager",
         "from core.case_manager import CaseManager"),
        ("from ..core.config import Config", "from core.config import Config"),
        ("from ..core.database import Database", "from core.database import Database"),
    ],
    "gui/main_window.py": [
        ("from ..core.device_manager import connected_devices",
         "from core.device_manager import connected_devices"),
        ("from . import load_stylesheet", "from gui import load_stylesheet"),
        ("from .right_panel import RightPanel", "from gui.right_panel import RightPanel"),
        ("from .sidebar import Sidebar", "from gui.sidebar import Sidebar"),
        ("from .status_bar import StatusBar", "from gui.status_bar import StatusBar"),
        ("from .toolbar import TopToolBar", "from gui.toolbar import TopToolBar"),
        ("from .tabs.ai_assistant_tab import AIAssistantTab",
         "from gui.tabs.ai_assistant_tab import AIAssistantTab"),
        ("from .tabs.dashboard_tab import DashboardTab",
         "from gui.tabs.dashboard_tab import DashboardTab"),
        ("from .tabs.data_viewer_tab import DataViewerTab",
         "from gui.tabs.data_viewer_tab import DataViewerTab"),
        ("from .tabs.extraction_tab import ExtractionTab",
         "from gui.tabs.extraction_tab import ExtractionTab"),
        ("from .tabs.reports_tab import ReportsTab",
         "from gui.tabs.reports_tab import ReportsTab"),
        ("from .tabs.settings_tab import SettingsTab",
         "from gui.tabs.settings_tab import SettingsTab"),
        ("from .tabs.timeline_tab import TimelineTab",
         "from gui.tabs.timeline_tab import TimelineTab"),
    ],
    "gui/tabs/dashboard_tab.py": [
        ("from ...widgets.chart_widget import ChartWidget",
         "from widgets.chart_widget import ChartWidget"),
        ("from ...widgets.stat_card import StatCard",
         "from widgets.stat_card import StatCard"),
    ],
    "gui/tabs/extraction_tab.py": [
        ("from ...core.device_manager import connected_devices",
         "from core.device_manager import connected_devices"),
        ("from ...widgets.device_card import DeviceCard",
         "from widgets.device_card import DeviceCard"),
    ],
    "gui/tabs/data_viewer_tab.py": [
        ("from ...widgets.data_table import DataTable",
         "from widgets.data_table import DataTable"),
    ],
    "gui/tabs/timeline_tab.py": [
        ("from ...widgets.chart_widget import ChartWidget",
         "from widgets.chart_widget import ChartWidget"),
    ],
    "gui/tabs/ai_assistant_tab.py": [
        ("from ...core.ai_client import MODEL_OPTIONS",
         "from core.ai_client import MODEL_OPTIONS"),
    ],
    "widgets/device_card.py": [
        ("from ..core.device_manager import Device",
         "from core.device_manager import Device"),
    ],
}


def main() -> None:
    for rel, pairs in REPLACEMENTS.items():
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        for old, new in pairs:
            if old in text:
                text = text.replace(old, new)
            else:
                print(f"WARN: not found in {rel}: {old!r}")
        path.write_text(text, encoding="utf-8")
        print(f"updated {rel}")


if __name__ == "__main__":
    main()