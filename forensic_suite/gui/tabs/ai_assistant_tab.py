"""AI Assistant: DeepSeek chat with markdown bubbles and model settings."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QScrollArea, QSlider,
                               QTextBrowser, QVBoxLayout, QWidget)

from core.ai_client import MODEL_OPTIONS

SUGGESTED_PROMPTS = [
    "Summarize what happened in this case",
    "Analyze the recovered deleted messages",
    "Extract all geo-locations from the artifacts",
    "Draft a formal forensic report",
]

SYSTEM_PROMPT = (
    "You are a forensic examiner's assistant embedded in a mobile forensics suite. "
    "Be precise and structured, reference artifact categories explicitly, and never "
    "invent evidence. If you lack data, state exactly what extra acquisition or "
    "analysis you would need."
)


def render_markdown(text: str) -> str:
    """Convert markdown to styled inline-HTML for the QTextBrowser bubbles."""
    import markdown as md
    body = md.markdown(text, extensions=["fenced_code", "codehilite", "nl2br"],
                       extension_configs={"codehilite": {"guess_lang": False,
                                                        "noclasses": True}})
    return (f'<div style="font-family:\'Segoe UI\',sans-serif;font-size:13px;'
            f'color:#E6EDF3;line-height:1.5;">{body}</div>')


class ChatWorker(QThread):
    """Streams the DeepSeek reply on a background thread."""

    chunk = Signal(str)
    failed = Signal(str)
    done = Signal()

    def __init__(self, client, messages, model, temperature, parent=None) -> None:
        super().__init__(parent)
        self.client = client
        self.messages = messages
        self.model = model
        self.temperature = temperature

    def run(self) -> None:
        try:
            for piece in self.client.stream_chat(self.messages, self.model,
                                                 self.temperature):
                if self.isInterruptionRequested():
                    break
                self.chunk.emit(piece)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.done.emit()


class AIAssistantTab(QWidget):
    """Full chat interface with streaming responses and markdown rendering."""

    ai_state_changed = Signal(str)  # idle | busy | error

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.history: list[dict] = []
        self._worker: ChatWorker | None = None
        self._current_text = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        heading = QLabel("\U0001F916  AI Assistant")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)

        config_row = QHBoxLayout()
        config_row.addWidget(QLabel("Model"))
        self.model_combo = QComboBox()
        for label, model_id in MODEL_OPTIONS.items():
            self.model_combo.addItem(label, model_id)
        self.model_combo.setMinimumWidth(180)
        config_row.addWidget(self.model_combo)

        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("DeepSeek API key (sk-...)")
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setText(self.ctx.config.get("ai", "api_key", ""))
        config_row.addWidget(self.key_edit, 1)
        save_key = QPushButton("Save key")
        save_key.setObjectName("Ghost")
        save_key.clicked.connect(self._save_key)
        config_row.addWidget(save_key)

        config_row.addWidget(QLabel("Temp"))
        self.temp_slider = QSlider(Qt.Horizontal)
        self.temp_slider.setRange(0, 100)
        self.temp_slider.setValue(int(float(self.ctx.config.get("ai", "temperature", 0.4)) * 100))
        self.temp_slider.setMaximumWidth(120)
        config_row.addWidget(self.temp_slider)
        self.attach_ctx = QCheckBox("Attach case context")
        self.attach_ctx.setChecked(True)
        config_row.addWidget(self.attach_ctx)
        layout.addLayout(config_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea{border:none;} QScrollArea > QWidget > QWidget{background:#0D1117;}")
        self.chat_box = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_box)
        self.chat_layout.setContentsMargins(8, 8, 8, 8)
        self.chat_layout.setSpacing(10)
        self.chat_layout.addStretch()
        self.scroll.setWidget(self.chat_box)
        layout.addWidget(self.scroll, 1)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        for prompt in SUGGESTED_PROMPTS:
            chip = QPushButton(prompt)
            chip.setObjectName("Ghost")
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda _=False, p=prompt: self._quick_prompt(p))
            chips.addWidget(chip)
        layout.addLayout(chips)

        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask about this case, artifacts, or forensic procedure\u2026")
        self.input.returnPressed.connect(self._send)
        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("Primary")
        self.send_btn.clicked.connect(self._send)
        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.send_btn)
        layout.addLayout(input_row)

        self._welcome()

    # ---- helpers / actions ----
    def _save_key(self) -> None:
        self.ctx.config.set("ai", "api_key", self.key_edit.text().strip())
        self.ctx.notify("AI", "API key saved in config.")
        self.ctx.log("DeepSeek API key updated", "#00E5FF")

    def _quick_prompt(self, prompt: str) -> None:
        self.input.setText(prompt)
        self._send()

    def _case_context(self) -> str:
        stats = self.ctx.case_manager.stats()
        return (f"[CASE CONTEXT] case={self.ctx.current_case} "
                f"categories={stats['categories']} devices={stats['devices']}")

    def _send(self) -> None:
        text = self.input.text().strip()
        if not text or self._worker is not None:
            return
        if self.attach_ctx.isChecked():
            text = f"{self._case_context()}\n\n{text}"
        self.history.append({"role": "user", "content": text})
        self._add_user_bubble(text)
        self.input.clear()
        self._start_stream()

    def _start_stream(self) -> None:
        self.ai_state_changed.emit("busy")
        self.send_btn.setEnabled(False)
        self._current_text = ""
        self._bubble = self._add_assistant_bubble("")
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self.history
        self._worker = ChatWorker(self.ctx.ai_client, messages,
                                  self.model_combo.currentData(),
                                  self.temp_slider.value() / 100.0, self)
        self._worker.chunk.connect(self._on_chunk)
        self._worker.failed.connect(self._on_failed)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_chunk(self, piece: str) -> None:
        self._current_text += piece
        if self._bubble is not None:
            self._bubble.setHtml(render_markdown(self._current_text))
            self._scroll_down()

    def _on_failed(self, message: str) -> None:
        self.history.append({"role": "assistant", "content": f"Error: {message}"})
        if self._bubble is not None:
            self._bubble.setHtml(
                render_markdown(f"**Request failed:** {message}"))
        self.ai_state_changed.emit("error")
        self._on_done()

    def _on_done(self) -> None:
        if self._current_text:
            self.history.append({"role": "assistant", "content": self._current_text})
        self.send_btn.setEnabled(True)
        self.ai_state_changed.emit("idle")
        self._worker = None
        self._scroll_down()

    def _add_user_bubble(self, text: str) -> None:
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet(
            "background:#0E2A33;border:1px solid #00E5FF;border-radius:10px;"
            "padding:10px 12px;color:#E6EDF3;max-width:520px;")
        lay.addStretch()
        lay.addWidget(label, 0)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, wrap)
        self._scroll_down()

    def _add_assistant_bubble(self, text: str) -> QTextBrowser:
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setFixedWidth(640)
        browser.setMinimumHeight(80)
        browser.setStyleSheet(
            "QTextBrowser{background:#1A1F2B;border:1px solid #7C4DFF;"
            "border-radius:10px;padding:8px;color:#E6EDF3;}")
        browser.setHtml(render_markdown(text) if text else "&hellip;")
        lay.addWidget(browser)
        lay.addStretch()
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, wrap)
        self._scroll_down()
        return browser

    def _welcome(self) -> None:
        welcome = ("**Assistant online.** Ask me about artifacts, timelines, "
                   "acquisition best practice, or authorization requirements.\n\n"
                   "*Tip:* no API key detected \u2014 paste one above to enable live "
                   "DeepSeek responses.")
        self._add_assistant_bubble(welcome)

    def _scroll_down(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())