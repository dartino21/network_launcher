"""Переиспользуемые компоненты интерфейса Network Launcher."""

from __future__ import annotations

from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout


def repolish(widget) -> None:
    """Повторно применяет QSS после изменения динамического свойства."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class StatusValueLabel(QLabel):
    """Убирает служебные префиксы из текста внутри подписанной карточки."""

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API
        for prefix in ("Режим: ", "Туннель: ", "Бэкенд: "):
            if text.startswith(prefix):
                text = text[len(prefix) :]
                break
        if text.startswith("Пользователи: "):
            text = text[len("Пользователи: ") :]
            current, separator, total = text.partition(" / всего ")
            if separator:
                text = f"{current} сейчас · {total} всего"
        super().setText(text)


class StatusCard(QFrame):
    """Небольшая карточка состояния с заголовком, значением и пояснением."""

    def __init__(self, title: str, value: str = "—", detail: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("statusCard")
        self.setProperty("tone", "neutral")
        self.setMinimumHeight(112)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("statusTitle")
        self.value_label = StatusValueLabel(value)
        self.value_label.setObjectName("statusValue")
        self.value_label.setWordWrap(True)
        self.detail_label = QLabel(detail)
        self.detail_label.setObjectName("caption")
        self.detail_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)
        layout.addStretch(1)

    def set_tone(self, tone: str) -> None:
        self.setProperty("tone", tone)
        repolish(self)

    def set_content(self, value: str, detail: str | None = None, tone: str | None = None) -> None:
        self.value_label.setText(value)
        if detail is not None:
            self.detail_label.setText(detail)
        if tone is not None:
            self.set_tone(tone)
