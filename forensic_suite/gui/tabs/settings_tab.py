"""Global settings: appearance, extraction, AI, privacy, advanced."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSlider, QVBoxLayout, QWidget)


class SettingsTab(QWidget):
    """Edits the JSON-backed Config and emits ``config_changed`` on save."""

    config_changed = Signal()

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        heading = QLabel("\u2699\uFE0F  Settings")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)

        appearance = self._card()
        form = QFormLayout(appearance)
        form.setContentsMargins(12, 12, 12, 12)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark (forensic lab)", "Light (daylight)"])
        form.addRow("Theme", self.theme_combo)
        font_row = QHBoxLayout()
        self.font_slider = QSlider(Qt.Horizontal)
        self.font_slider.setRange(10, 18)
        self.font_value = QLabel("13 px")
        self.font_value.setFixedWidth(44)
        self.font_slider.valueChanged.connect(
            lambda v: self.font_value.setText(f"{v} px"))
        font_row.addWidget(self.font_slider, 1)
        font_row.addWidget(self.font_value)
        form.addRow("Font size", font_row)
        self.language_combo = QComboBox()
        self.language_combo.addItems(["English", "Fran\u00e7ais", "Portugu\u00eas"])
        form.addRow("Language", self.language_combo)
        layout.addWidget(appearance)

        extraction = self._card()
        xform = QFormLayout(extraction)
        xform.setContentsMargins(12, 12, 12, 12)
        out_row = QHBoxLayout()
        self.out_path = QLineEdit()
        browse = QPushButton("Browse")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._browse_out)
        out_row.addWidget(self.out_path, 1)
        out_row.addWidget(browse)
        xform.addRow("Default output", out_row)
        self.verify_hashes = QCheckBox("Verify SHA-256 hashes after acquisition")
        xform.addRow("", self.verify_hashes)
        layout.addWidget(extraction)

        ai = self._card()
        aform = QFormLayout(ai)
        aform.setContentsMargins(12, 12, 12, 12)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("DeepSeek API key (sk-\u2026)")
        aform.addRow("API key", self.api_key)
        self.ai_model = QComboBox()
        self.ai_model.addItems(["DeepSeek V4-Flash (free)", "DeepSeek V4-Pro"])
        aform.addRow("Model", self.ai_model)
        temp_row = QHBoxLayout()
        self.temp_slider = QSlider(Qt.Horizontal)
        self.temp_slider.setRange(0, 100)
        self.temp_label = QLabel("0.4")
        self.temp_label.setFixedWidth(32)
        self.temp_slider.valueChanged.connect(
            lambda v: self.temp_label.setText(f"{v / 100:.1f}"))
        temp_row.addWidget(self.temp_slider, 1)
        temp_row.addWidget(self.temp_label)
        aform.addRow("Temperature", temp_row)
        layout.addWidget(ai)

        privacy = self._card()
        pform = QFormLayout(privacy)
        pform.setContentsMargins(12, 12, 12, 12)
        self.telemetry = QCheckBox("Anonymous usage telemetry")
        self.autosave = QCheckBox("Auto-save work in progress")
        pform.addRow("", self.telemetry)
        pform.addRow("", self.autosave)
        layout.addWidget(privacy)

        buttons = QHBoxLayout()
        save = QPushButton("Save changes")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        reset = QPushButton("Reset to defaults")
        reset.setObjectName("Danger")
        reset.clicked.connect(self._reset)
        buttons.addWidget(save)
        buttons.addWidget(reset)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addStretch()

        self._load()

    @staticmethod
    def _card() -> QWidget:
        card = QWidget()
        card.setObjectName("Card")
        return card

    def _load(self) -> None:
        config = self.ctx.config
        theme = config.get("appearance", "theme", "dark")
        self.theme_combo.setCurrentIndex(0 if theme == "dark" else 1)
        size = int(config.get("appearance", "font_size", 13))
        self.font_slider.setValue(size)
        self.font_value.setText(f"{size} px")
        lang = config.get("appearance", "language", "English")
        index = self.language_combo.findText(lang)
        self.language_combo.setCurrentIndex(max(index, 0))
        self.out_path.setText(config.get("extraction", "default_out", ""))
        self.verify_hashes.setChecked(
            bool(config.get("extraction", "verify_hashes", True)))
        self.api_key.setText(config.get("ai", "api_key", ""))
        model = config.get("ai", "model", "deepseek-chat")
        self.ai_model.setCurrentIndex(1 if model != "deepseek-chat" else 0)
        temp = float(config.get("ai", "temperature", 0.4))
        self.temp_slider.setValue(int(temp * 100))
        self.temp_label.setText(f"{temp:.1f}")
        self.telemetry.setChecked(bool(config.get("privacy", "telemetry", False)))
        self.autosave.setChecked(bool(config.get("privacy", "autosave", True)))

    def _browse_out(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Default output folder")
        if path:
            self.out_path.setText(path)

    def _save(self) -> None:
        config = self.ctx.config
        config.set("appearance", "theme",
                   "dark" if self.theme_combo.currentIndex() == 0 else "light")
        config.set("appearance", "font_size", self.font_slider.value())
        config.set("appearance", "language", self.language_combo.currentText())
        config.set("extraction", "default_out", self.out_path.text().strip())
        config.set("extraction", "verify_hashes", self.verify_hashes.isChecked())
        config.set("ai", "api_key", self.api_key.text().strip())
        config.set("ai", "model", "deepseek-chat"
                   if self.ai_model.currentIndex() == 0 else "deepseek-reasoner")
        config.set("ai", "temperature", round(self.temp_slider.value() / 100, 2))
        config.set("privacy", "telemetry", self.telemetry.isChecked())
        config.set("privacy", "autosave", self.autosave.isChecked())
        self.ctx.notify("Settings", "Configuration saved.")
        self.config_changed.emit()

    def _reset(self) -> None:
        self.ctx.config.reset()
        self._load()
        self.ctx.notify("Settings", "Configuration reset to defaults.")
        self.config_changed.emit()
