"""Интерфейс Network Launcher (View + Controller)."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt5.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .config import data_dir, load_config, save_config
from .publish_profile import PublishProfile, profile_from_config, save_profile_to_config
from .server_manager import ServerManager, detect_project_type
from .stats_collector import StatsCollector
from .tunnel_manager import TunnelManager
from .ui_components import StatusCard, repolish
from .ui_theme import COLORS, DARK_QSS as MODERN_QSS, app_icon, svg_icon

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView

    HAS_WEBENGINE = True
except ImportError:
    QWebEngineView = None  # type: ignore
    HAS_WEBENGINE = False

DARK_QSS = """
QMainWindow, QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    font-family: Segoe UI, sans-serif;
    font-size: 13px;
}
QLineEdit, QPlainTextEdit, QSpinBox, QComboBox {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px;
}
QPushButton {
    background-color: #3c3c3c;
    color: #e0e0e0;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 6px 14px;
}
QPushButton:hover {
    background-color: #4a4a4a;
}
QPushButton:disabled {
    background-color: #2a2a2a;
    color: #777;
}
QPushButton#startBtn {
    background-color: #2e7d32;
    border-color: #1b5e20;
    color: #fff;
}
QPushButton#startBtn:hover {
    background-color: #388e3c;
}
QPushButton#startBtn:disabled {
    background-color: #1b3d1e;
    color: #777;
}
QPushButton#stopBtn {
    background-color: #c62828;
    border-color: #8e0000;
    color: #fff;
}
QPushButton#stopBtn:hover {
    background-color: #d32f2f;
}
QPushButton#stopBtn:disabled {
    background-color: #3d1515;
    color: #777;
}
QLabel {
    color: #e0e0e0;
}
QLabel#publicUrlLabel a {
    color: #64b5f6;
}
QCheckBox {
    color: #e0e0e0;
}
QSplitter::handle {
    background: #444;
}
"""


def setup_file_logging() -> logging.Logger:
    """Пишет события в logs/app.log рядом с приложением."""
    log_dir = os.path.join(data_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "app.log")

    logger = logging.getLogger("network_launcher")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        logger.addHandler(handler)
    return logger


APP_LOG = setup_file_logging()


class DockerLogsDialog(QDialog):
    """Окно с логами docker compose."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Логи Docker")
        self.resize(700, 450)
        layout = QVBoxLayout(self)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(text or "(пусто)")
        layout.addWidget(view)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class HelpDialog(QDialog):
    """Compact offline help for people using the portable EXE."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Справка Network Launcher")
        self.resize(760, 570)
        layout = QVBoxLayout(self)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setHtml(
            """
            <h2>Быстрый старт</h2>
            <ol><li>Настройте ngrok authtoken один раз.</li>
            <li>Нажмите «Выбрать папку» и выберите корень сайта.</li>
            <li>Нажмите «Запустить проект», дождитесь статуса «Работает» и передайте публичную ссылку.</li></ol>
            <p>Поддерживаются: <b>index.html</b>, <b>package.json</b>, <b>app.py</b> (Flask) и Docker Compose.</p>
            <h3>Как работает публикация</h3>
            <p>Программа запускает сайт только на вашем компьютере, создаёт локальный proxy и подключает к нему ngrok. В интернет попадает один HTTPS-адрес; маршруты /api, /health, /ws и похожие можно направить в backend.</p>
            <h3>Настройки</h3>
            <p><b>Порт</b> — желаемый порт сайта. <b>Автозапуск</b> запускает выбранную папку сразу. В разделе «Настройки» можно выбрать frontend/backend, перечислить backend-пути, включить совместимость Dev/HMR, сохранить public Host или передать публичный URL в переменные окружения, например NEXTAUTH_URL.</p>
            <h3>Если ссылка не появляется или сайт долго запускается</h3>
            <p>Откройте вкладку «Логи»: там указан текущий этап. Для Node.js нужен Node/npm; для Docker — запущенный Docker Desktop; для Flask — Python с Flask, предпочтительно в .venv. Если ссылка создана, но сайт не отвечает, проверьте, что сам сайт слушает указанный порт и не обращается из браузера к localhost.</p>
            <p>Полная инструкция находится в README.md. Журнал программы: <b>data/logs/app.log</b>.</p>
            """
        )
        layout.addWidget(view)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class LogReaderThread(QThread):
    """Читает stdout/stderr процесса сервера без блокировки GUI."""

    line_received = pyqtSignal(str)
    finished_reading = pyqtSignal()

    def __init__(self, process):
        super().__init__()
        self._process = process
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        proc = self._process
        try:
            while not self._stop and proc.poll() is None:
                if proc.stdout is None:
                    break
                line = proc.stdout.readline()
                if line:
                    self.line_received.emit(line.rstrip("\r\n"))
                elif proc.poll() is not None:
                    break

            if proc.stderr:
                while True:
                    err = proc.stderr.readline()
                    if not err:
                        break
                    self.line_received.emit(err.rstrip("\r\n"))
        finally:
            self.finished_reading.emit()


class StartWorker(QThread):
    """Запускает сервер и ngrok в фоне, чтобы окно не зависало."""

    finished_start = pyqtSignal(dict)
    progress = pyqtSignal(str)
    public_url_ready = pyqtSignal(str)

    def __init__(
        self,
        server: ServerManager,
        tunnel: TunnelManager,
        path: str,
        port: int,
        profile: PublishProfile,
    ):
        super().__init__()
        self._server = server
        self._tunnel = tunnel
        self._path = path
        self._port = port
        self._profile = profile

    def run(self):
        def report(msg: str) -> None:
            self.progress.emit(msg)

        try:
            self._server.set_progress(report)
            self._tunnel.set_progress(report)
            report("Подготовка профиля публикации…")
            plan = self._server.prepare_launch(
                self._path,
                preferred_port=self._port,
                profile=self._profile,
            )
            if not plan.get("ok"):
                self.finished_start.emit(plan)
                return
            for finding in plan.get("preflight_findings", []):
                report(
                    "Preflight: browser URL указывает на loopback: "
                    f"{finding['file']}:{finding['line']} -> {finding['url']}"
                )
            proxy = self._server.start_proxy(plan)
            if not proxy.get("ok"):
                self.finished_start.emit(proxy)
                return
            report("Proxy готов — получаем публичный HTTPS URL…")
            tunnel = self._tunnel.start_tunnel(plan["proxy_port"])
            if not tunnel.get("ok"):
                self._server.stop_server()
                self.finished_start.emit(tunnel)
                return
            self.public_url_ready.emit(tunnel["public_url"])
            report("Публичный URL получен — запускаем проект с runtime-окружением…")
            result = self._server.start_prepared(plan, tunnel["public_url"])
            if not result.get("ok"):
                self._tunnel.stop_tunnel()
                self._server.stop_server()
                self.finished_start.emit(result)
                return
            self.finished_start.emit({"ok": True, "server": result, "tunnel": tunnel})
        except Exception as exc:  # noqa: BLE001
            try:
                self._tunnel.stop_tunnel()
                self._server.stop_server()
            except Exception:  # noqa: BLE001
                pass
            self.finished_start.emit({"ok": False, "error": str(exc)})
        finally:
            self._server.set_progress(None)
            self._tunnel.set_progress(None)

class VisitsChart(FigureCanvasQTAgg):
    """График уникальных посетителей по минутам сессии."""

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(4, 2.2), dpi=100)
        self.fig.patch.set_facecolor(COLORS["surface"])
        super().__init__(self.fig)
        self.setParent(parent)
        self.ax = self.fig.add_subplot(111)
        self._style_axes()
        self.redraw([])

    def _style_axes(self):
        self.ax.set_facecolor(COLORS["surface"])
        self.ax.tick_params(colors=COLORS["muted"], labelsize=8, length=0)
        for spine in self.ax.spines.values():
            spine.set_color(COLORS["border"])
        self.ax.grid(axis="y", color=COLORS["border"], linewidth=0.7, alpha=0.65)
        self.ax.set_title("Уникальные посетители по времени", color=COLORS["text"], fontsize=10)
        self.ax.set_ylabel("Посетители", color=COLORS["muted"], fontsize=8)

    def redraw(self, history: list[tuple[str, int]]):
        self.ax.clear()
        self._style_axes()
        if history:
            labels = [h[0] for h in history]
            values = [h[1] for h in history]
            self.ax.plot(
                labels,
                values,
                color=COLORS["accent"],
                marker="o",
                markerfacecolor=COLORS["success"],
                markersize=4,
                linewidth=2,
            )
            self.ax.set_ylim(bottom=0)
            if len(labels) > 8:
                step = max(1, len(labels) // 8)
                self.ax.set_xticks(range(0, len(labels), step))
                self.ax.set_xticklabels(
                    [labels[i] for i in range(0, len(labels), step)], rotation=30
                )
        else:
            self.ax.text(
                0.5,
                0.5,
                "Нет данных",
                ha="center",
                va="center",
                color=COLORS["muted"],
                transform=self.ax.transAxes,
            )
        self.fig.tight_layout()
        self.draw_idle()


class BaseMainWindow(QMainWindow):
    """Главное окно: выбор проекта, запуск, превью, статистика."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Network Launcher")
        self.resize(900, 650)
        self._project_path = ""
        self._running = False
        self._last_users = -1
        self._local_url = ""
        self.server = ServerManager()
        self.tunnel = TunnelManager()
        self.stats = StatsCollector()
        self._log_thread = None
        self._start_worker = None
        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(5000)
        self._stats_timer.timeout.connect(self._poll_tunnel_stats)
        self._config = load_config()
        self._build_ui()
        self._set_idle_buttons()
        self._reset_tunnel_ui()
        self.export_btn.setEnabled(False)
        self._apply_config(self._config)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter()
        root.addWidget(splitter)

        left = QWidget()
        layout = QVBoxLayout(left)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 8, 0)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Путь к папке проекта…")
        self.path_edit.setReadOnly(True)
        self.browse_btn = QPushButton("Обзор")
        self.browse_btn.clicked.connect(self.browse_folder)
        path_row.addWidget(self.path_edit, stretch=1)
        path_row.addWidget(self.browse_btn)
        layout.addLayout(path_row)

        self.path_label = QLabel("Выбранный путь: —")
        layout.addWidget(self.path_label)

        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("Порт:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(8080)
        port_row.addWidget(self.port_spin)
        self.autostart_cb = QCheckBox("Автозапуск при выборе папки")
        port_row.addWidget(self.autostart_cb)
        port_row.addStretch()
        layout.addLayout(port_row)

        self.advanced_group = QGroupBox("Расширенные настройки публикации")
        self.advanced_group.setCheckable(True)
        self.advanced_group.setChecked(False)
        advanced_layout = QVBoxLayout(self.advanced_group)

        upstream_row = QHBoxLayout()
        upstream_row.addWidget(QLabel("Frontend:"))
        self.frontend_edit = QLineEdit("auto")
        self.frontend_edit.setPlaceholderText("auto, сервис или порт")
        upstream_row.addWidget(self.frontend_edit)
        upstream_row.addWidget(QLabel("Backend:"))
        self.backend_edit = QLineEdit("auto")
        self.backend_edit.setPlaceholderText("auto, none, сервис или порт")
        upstream_row.addWidget(self.backend_edit)
        advanced_layout.addLayout(upstream_row)

        prefixes_row = QHBoxLayout()
        prefixes_row.addWidget(QLabel("Backend-пути:"))
        self.prefixes_edit = QLineEdit("/api, /health, /ws, /socket.io, /graphql")
        prefixes_row.addWidget(self.prefixes_edit)
        advanced_layout.addLayout(prefixes_row)

        compatibility_row = QHBoxLayout()
        compatibility_row.addWidget(QLabel("Dev/HMR:"))
        self.dev_combo = QComboBox()
        self.dev_combo.addItem("Авто", "auto")
        self.dev_combo.addItem("Включено", "on")
        self.dev_combo.addItem("Выключено", "off")
        compatibility_row.addWidget(self.dev_combo)
        compatibility_row.addWidget(QLabel("Host upstream:"))
        self.host_combo = QComboBox()
        self.host_combo.addItem("Авто", "auto")
        self.host_combo.addItem("Сохранять публичный", "on")
        self.host_combo.addItem("Подменять на локальный", "off")
        compatibility_row.addWidget(self.host_combo)
        advanced_layout.addLayout(compatibility_row)

        env_row = QHBoxLayout()
        env_row.addWidget(QLabel("Переменные public URL:"))
        self.public_env_edit = QLineEdit("NEXTAUTH_URL, AUTH_URL")
        env_row.addWidget(self.public_env_edit)
        advanced_layout.addLayout(env_row)
        layout.addWidget(self.advanced_group)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Запустить")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self.start)
        self.stop_btn = QPushButton("Остановить")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.clicked.connect(self.stop)
        self.export_btn = QPushButton("Экспорт")
        self.export_btn.clicked.connect(self.export_report)
        self.docker_logs_btn = QPushButton("Логи Docker")
        self.docker_logs_btn.clicked.connect(self.show_docker_logs)
        self.docker_logs_btn.setEnabled(False)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addWidget(self.export_btn)
        btn_row.addWidget(self.docker_logs_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.mode_label = QLabel("Режим: —")
        layout.addWidget(self.mode_label)

        self.docker_status_label = QLabel("Docker: —")
        self.docker_status_label.setWordWrap(True)
        layout.addWidget(self.docker_status_label)

        self.backend_health_label = QLabel("Бэкенд: —")
        layout.addWidget(self.backend_health_label)

        self.tunnel_status_label = QLabel("Туннель: отключён")
        layout.addWidget(self.tunnel_status_label)

        self.public_url_label = QLabel("Публичный URL: —")
        self.public_url_label.setObjectName("publicUrlLabel")
        self.public_url_label.setOpenExternalLinks(True)
        layout.addWidget(self.public_url_label)

        self.users_label = QLabel("Пользователи: 0 / всего 0")
        layout.addWidget(self.users_label)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Лог: статус, URL, количество пользователей…")
        layout.addWidget(self.log, stretch=1)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.addWidget(QLabel("Превью"))

        if HAS_WEBENGINE:
            self.preview = QWebEngineView()
            self.preview.setMinimumHeight(200)
            right_layout.addWidget(self.preview, stretch=2)
        else:
            self.preview = None
            fallback = QLabel("Превью недоступно (установите PyQtWebEngine)")
            fallback.setMinimumHeight(200)
            fallback.setStyleSheet("background:#2d2d2d; padding:12px;")
            right_layout.addWidget(fallback, stretch=2)

        self.chart = VisitsChart()
        right_layout.addWidget(self.chart, stretch=1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

    def _apply_config(self, cfg: dict):
        """Восстанавливает порт, autostart и последний путь из config.json."""
        self.port_spin.setValue(int(cfg.get("port", 8080)))
        self.autostart_cb.setChecked(bool(cfg.get("autostart", False)))
        path = cfg.get("project_path") or ""
        if path and os.path.isdir(path):
            self._set_project_path(path, save=False, maybe_autostart=False)

    def _persist_config(self):
        self._config.update(
            {
                "project_path": self._project_path,
                "port": self.port_spin.value(),
                "autostart": self.autostart_cb.isChecked(),
            }
        )
        if self._project_path:
            save_profile_to_config(self._config, self._project_path, self._profile_from_ui())
        save_config(self._config)

    def _profile_from_ui(self) -> PublishProfile:
        prefixes = [item.strip() for item in self.prefixes_edit.text().split(",") if item.strip()]
        env_names = [item.strip() for item in self.public_env_edit.text().split(",") if item.strip()]
        return PublishProfile.from_dict(
            {
                "frontend": self.frontend_edit.text().strip() or "auto",
                "backend": self.backend_edit.text().strip() or "auto",
                "backend_prefixes": prefixes,
                "dev_compatibility": self.dev_combo.currentData(),
                "preserve_host": self.host_combo.currentData(),
                "public_url_env_names": env_names,
            }
        )

    def _load_profile_ui(self, project_path: str) -> None:
        profile = profile_from_config(self._config, project_path)
        self.frontend_edit.setText(str(profile.frontend))
        self.backend_edit.setText("none" if profile.backend is None else str(profile.backend))
        self.prefixes_edit.setText(", ".join(profile.backend_prefixes))
        self.public_env_edit.setText(", ".join(profile.public_url_env_names))
        for combo, value in (
            (self.dev_combo, profile.dev_compatibility),
            (self.host_combo, profile.preserve_host),
        ):
            index = combo.findData(value)
            combo.setCurrentIndex(max(0, index))

    def update_status(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{ts}] {message}")
        APP_LOG.info(message)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку проекта")
        if not folder:
            return
        self._set_project_path(folder, save=True, maybe_autostart=True)

    def _set_project_path(self, folder: str, save: bool, maybe_autostart: bool):
        self.path_edit.setText(folder)
        self.path_label.setText(f"Выбранный путь: {folder}")
        self._project_path = folder
        self._load_profile_ui(folder)

        ptype = detect_project_type(folder)
        if ptype != "unknown":
            self.update_status(f"Папка OK (тип: {ptype}): {folder}")
            if ptype == "docker":
                self.mode_label.setText("Режим: Docker (определён compose)")
            else:
                self.mode_label.setText(f"Режим: {ptype}")
                self.docker_status_label.setText("Docker: —")
                self.backend_health_label.setText("Бэкенд: —")
            if not self._running:
                self.start_btn.setEnabled(True)
            if save:
                self._persist_config()
            if maybe_autostart and self.autostart_cb.isChecked() and not self._running:
                self.start()
        else:
            self.update_status(
                "Ошибка: нужен docker-compose.yml, index.html, package.json или app.py."
            )
            self._project_path = ""
            self.mode_label.setText("Режим: —")
            if not self._running:
                self.start_btn.setEnabled(False)

    def start(self):
        if self._running or (self._start_worker and self._start_worker.isRunning()):
            return
        if not self._project_path:
            self.update_status("Сначала выберите валидную папку проекта.")
            return

        self._persist_config()
        self.start_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.port_spin.setEnabled(False)
        self.advanced_group.setEnabled(False)
        self.update_status(
            "Запуск сервера и туннеля… (Docker/сборка Next.js может занять несколько минут — "
            "смотрите шаги ниже)"
        )

        worker = StartWorker(
            self.server,
            self.tunnel,
            self._project_path,
            self.port_spin.value(),
            self._profile_from_ui(),
        )
        worker.progress.connect(self.update_status)
        worker.public_url_ready.connect(self._on_public_url_ready)
        worker.finished_start.connect(self._on_start_finished)
        self._start_worker = worker
        worker.start()

    def _on_public_url_ready(self, public_url: str):
        """Expose the URL while the local project is still warming up."""
        self._set_tunnel_connected(public_url)
        self.update_status("Ссылка готова; ожидаем запуск локального сайта…")

    def _on_start_finished(self, payload: dict):
        self._start_worker = None
        if not payload.get("ok"):
            self.update_status(f"Ошибка запуска: {payload.get('error', 'неизвестно')}")
            self._reset_tunnel_ui()
            self.browse_btn.setEnabled(True)
            self.port_spin.setEnabled(True)
            self.advanced_group.setEnabled(True)
            self.start_btn.setEnabled(bool(self._project_path))
            self.docker_logs_btn.setEnabled(
                detect_project_type(self._project_path) == "docker"
                if self._project_path
                else False
            )
            return

        result = payload["server"]
        tunnel = payload["tunnel"]
        preferred = self.port_spin.value()

        if result.get("port_changed"):
            self.update_status(
                f"Порт {preferred} занят — используется {result['port']}"
            )

        self._running = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.browse_btn.setEnabled(False)
        self.port_spin.setEnabled(False)
        self.export_btn.setEnabled(True)
        is_docker = result.get("type") == "docker"
        self.docker_logs_btn.setEnabled(is_docker)

        public_url = tunnel["public_url"]
        self._local_url = result["url"]
        self.stats.reset()
        self.stats.set_session_meta(
            project_path=self._project_path,
            local_url=result["url"],
            public_url=public_url,
        )

        if is_docker:
            self.mode_label.setText("Режим: Docker")
            self._refresh_docker_status()
            gw = result.get("gateway_mode")
            if gw == "proxy":
                self.update_status(
                    f"Публичный вход: proxy :{result['proxy_port']} "
                    f"(FE :{result.get('frontend_port')}, API :{result.get('backend_port')})"
                )
            elif gw in ("compose", "compose+proxy"):
                self.update_status(
                    f"Публичный вход: proxy :{result['proxy_port']} -> "
                    f"compose-gateway :{result.get('frontend_port')}"
                )
            if result.get("backend_port"):
                if result.get("backend_ok"):
                    self.backend_health_label.setText(
                        f"Бэкенд: OK ({result.get('backend_health_url', '')})"
                    )
                    self.update_status("Бэкенд готов")
                else:
                    self.backend_health_label.setText(
                        f"Бэкенд: не отвечает на /health (:{result['backend_port']})"
                    )
                    self.update_status(
                        f"Предупреждение: бэкенд :{result['backend_port']} не ответил на health — "
                        f"кнопки API могут не работать. Откройте «Логи Docker»."
                    )
                    dm = self.server.get_docker_manager()
                    if dm:
                        self.update_status(
                            "Логи backend:\n"
                            + dm.get_docker_logs(self._project_path)[-1500:]
                        )
            else:
                self.backend_health_label.setText("Бэкенд: не обнаружен в compose")
        else:
            self.mode_label.setText(f"Режим: {result['type']}")
            self.docker_status_label.setText("Docker: —")
            self.backend_health_label.setText("Бэкенд: —")

        if tunnel.get("backend_warning"):
            self.update_status(tunnel["backend_warning"])

        self.update_status(f"Статус: запущен ({result['type']})")
        self.update_status(f"Команда: {result['cmd']}")
        self.update_status(f"Локальный URL: {result['url']}")
        self.update_status(f"Публичный URL: {public_url}")
        self.update_status(
            f"Порты: frontend={result.get('frontend_port')}, "
            f"backend={result.get('backend_port') or '—'}, proxy={result.get('proxy_port')}"
        )
        routes = ", ".join(result.get("backend_prefixes") or []) or "не заданы"
        checks = result.get("checks") or {}
        self.update_status(f"Backend-маршруты: {routes}")
        self.update_status(
            "Проверки proxy: "
            f"HTTP={'OK ' + str(checks.get('status')) if checks.get('http_ok') else 'FAIL'}, "
            f"WebSocket relay={'готов' if checks.get('websocket_ready') else 'не готов'}, "
            f"dev compatibility={'on' if result.get('dev_compatibility') else 'off'}"
        )
        if result.get("auth_url_applied"):
            self.update_status(
                "AUTH/NEXTAUTH_URL привязан к публичному URL. "
                "Откройте именно публичную ссылку, пройдите warning ngrok (если есть) "
                "и войдите заново на этом хосте (сессия с localhost не переносится)."
            )
        self._set_tunnel_connected(public_url)
        self._last_users = 0
        self.users_label.setText("Пользователи: 0 / всего 0")
        self._load_preview(result["url"])
        self.chart.redraw([])
        self._stats_timer.start()

        proc = self.server.get_process()
        if proc:
            self._start_log_reader(proc)

    def show_docker_logs(self):
        """Открывает окно с docker compose logs."""
        path = self._project_path
        if not path or detect_project_type(path) != "docker":
            self.update_status("Логи Docker доступны только для compose-проектов.")
            return
        dm = self.server.get_docker_manager()
        if dm is None:
            from .docker_manager import DockerManager

            dm = DockerManager(path)
        text = dm.get_docker_logs(path)
        DockerLogsDialog(text, self).exec_()

    def _refresh_docker_status(self):
        """Обновляет строку статуса контейнеров."""
        path = self._project_path
        dm = self.server.get_docker_manager()
        if not path or not dm:
            self.docker_status_label.setText("Docker: —")
            return
        status = dm.get_container_status(path)
        if not status:
            self.docker_status_label.setText("Docker: нет сервисов")
            return
        parts = []
        for name, info in status.items():
            role = info.get("role", "other")
            state = info.get("state", "unknown")
            mark = "OK" if state == "running" else state
            parts.append(f"{name}[{role}]: {mark}")
        self.docker_status_label.setText("Docker: " + " | ".join(parts))
        self.update_status("Контейнеры: " + ", ".join(parts))

    def stop(self):
        self._shutdown_all()
        self._running = False
        self.stop_btn.setEnabled(False)
        self.browse_btn.setEnabled(True)
        self.port_spin.setEnabled(True)
        self.advanced_group.setEnabled(True)
        self.start_btn.setEnabled(bool(self._project_path))
        self.export_btn.setEnabled(False)
        self.docker_logs_btn.setEnabled(
            bool(self._project_path)
            and detect_project_type(self._project_path) == "docker"
        )
        self._persist_config()
        self.update_status("Статус: остановлен")

    def export_report(self):
        default_name = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт отчёта",
            default_name,
            "HTML (*.html)",
        )
        if not path:
            return
        try:
            saved = self.stats.generate_report(path)
            self.update_status(f"Отчёт сохранён: {saved}")
        except OSError as exc:
            self.update_status(f"Не удалось сохранить отчёт: {exc}")

    def _shutdown_all(self):
        self._stats_timer.stop()
        self._stop_log_reader()
        if self._start_worker and self._start_worker.isRunning():
            self._start_worker.wait(3000)
        self.tunnel.stop_tunnel()
        self.server.stop_server()
        self.stats.reset()
        self._reset_tunnel_ui()
        self._clear_preview()
        self.chart.redraw([])

    def _load_preview(self, url: str):
        if self.preview is not None:
            self.preview.load(QUrl(url))

    def _clear_preview(self):
        if self.preview is not None:
            self.preview.setHtml(
                "<html><body style='background:#2d2d2d;color:#777;"
                "font-family:sans-serif;padding:16px'>Превью остановлено</body></html>"
            )

    def _set_tunnel_connected(self, public_url: str):
        self.tunnel_status_label.setText("Туннель: подключён")
        self.public_url_label.setText(
            f'Публичный URL: <a href="{public_url}">{public_url}</a>'
        )

    def _reset_tunnel_ui(self):
        self.tunnel_status_label.setText("Туннель: отключён")
        self.public_url_label.setText("Публичный URL: —")
        self.users_label.setText("Пользователи: 0 / всего 0")
        self.docker_status_label.setText("Docker: —")
        self.backend_health_label.setText("Бэкенд: —")
        if self._project_path and detect_project_type(self._project_path) == "docker":
            self.mode_label.setText("Режим: Docker (определён compose)")
        elif self._project_path:
            self.mode_label.setText(f"Режим: {detect_project_type(self._project_path)}")
        else:
            self.mode_label.setText("Режим: —")
        self._last_users = -1

    def _poll_tunnel_stats(self):
        if not self._running:
            return

        # для Docker периодически обновляем статусы контейнеров
        status = self.server.get_server_status()
        if status.get("type") == "docker":
            self._refresh_docker_status()

        url = self.tunnel.get_public_url()
        if url:
            self._set_tunnel_connected(url)
            self.stats.set_session_meta(
                project_path=self._project_path,
                local_url=self._local_url,
                public_url=url,
            )
        else:
            self.tunnel_status_label.setText("Туннель: отключён")
            self.public_url_label.setText("Публичный URL: —")

        data = self.stats.update_stats()
        current = data["current"]
        total = data["total"]
        self.users_label.setText(f"Пользователи: {current} / всего {total}")
        self.chart.redraw(self.stats.history_for_chart())
        if current != self._last_users:
            self._last_users = current
            self.update_status(f"Пользователи: {current} (всего {total})")

    def _start_log_reader(self, process):
        self._stop_log_reader()
        thread = LogReaderThread(process)
        thread.line_received.connect(self.update_status)
        thread.finished_reading.connect(self._on_process_exited)
        self._log_thread = thread
        thread.start()

    def _stop_log_reader(self):
        thread = self._log_thread
        if thread is None:
            return
        thread.stop()
        thread.wait(1000)
        self._log_thread = None

    def _on_process_exited(self):
        if not self._running:
            return
        status = self.server.get_server_status()
        if not status["running"]:
            self._shutdown_all()
            self._running = False
            self.stop_btn.setEnabled(False)
            self.browse_btn.setEnabled(True)
            self.port_spin.setEnabled(True)
            self.advanced_group.setEnabled(True)
            self.start_btn.setEnabled(bool(self._project_path))
            self.export_btn.setEnabled(False)
            self.update_status("Статус: процесс сервера завершился")

    def closeEvent(self, event):
        self._persist_config()
        self._shutdown_all()
        event.accept()

    def _set_idle_buttons(self):
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)


class MainWindow(BaseMainWindow):
    """Современное представление поверх проверенной управляющей логики."""

    def __init__(self):
        self._public_url = ""
        super().__init__()
        self.setWindowIcon(app_icon())
        self.resize(1120, 760)
        self.setMinimumSize(940, 660)

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("appRoot")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 14, 18, 14)
        header_layout.setSpacing(13)

        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(46, 46))
        logo.setFixedSize(48, 48)
        header_layout.addWidget(logo)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title = QLabel("Network Launcher")
        title.setObjectName("appTitle")
        subtitle = QLabel("Локальный запуск и безопасная публикация веб-проектов")
        subtitle.setObjectName("subtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header_layout.addLayout(title_col)
        header_layout.addStretch(1)

        self.state_badge = QLabel("●  Не запущено")
        self.state_badge.setObjectName("stateBadge")
        self.state_badge.setProperty("state", "idle")
        self.help_btn = self._icon_button("help", "Справка")
        self.help_btn.clicked.connect(self._show_help)
        header_layout.addWidget(self.help_btn, alignment=Qt.AlignVCenter)
        header_layout.addWidget(self.state_badge, alignment=Qt.AlignVCenter)
        root.addWidget(header)

        self.main_tabs = QTabWidget()
        self.main_tabs.setDocumentMode(True)
        root.addWidget(self.main_tabs, stretch=1)

        self._build_overview_tab()
        self._build_preview_tab()
        self._build_logs_tab()
        self._build_settings_tab()

        self.main_tabs.setTabIcon(0, svg_icon("play", COLORS["accent"]))
        self.main_tabs.setTabIcon(1, svg_icon("external"))
        self.main_tabs.setTabIcon(2, svg_icon("terminal"))
        self.main_tabs.setTabIcon(3, svg_icon("file"))

    def _build_overview_tab(self):
        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        page.setObjectName("tabPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 4)
        layout.setSpacing(14)
        scroll.setWidget(page)

        project_card = QFrame()
        project_card.setObjectName("card")
        project_layout = QVBoxLayout(project_card)
        project_layout.setContentsMargins(18, 16, 18, 17)
        project_layout.setSpacing(11)
        project_title = QLabel("Проект и запуск")
        project_title.setObjectName("sectionTitle")
        project_layout.addWidget(project_title)

        path_row = QHBoxLayout()
        path_row.setSpacing(9)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Путь к папке проекта…")
        self.path_edit.setReadOnly(True)
        self.browse_btn = QPushButton("Выбрать папку")
        self.browse_btn.setIcon(svg_icon("folder"))
        self.browse_btn.clicked.connect(self.browse_folder)
        path_row.addWidget(self.path_edit, stretch=1)
        path_row.addWidget(self.browse_btn)
        project_layout.addLayout(path_row)

        self.path_label = QLabel(
            "Поддерживаются: Docker Compose, Node.js, Flask и статические сайты"
        )
        self.path_label.setObjectName("caption")
        self.path_label.setWordWrap(True)
        project_layout.addWidget(self.path_label)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        controls.addWidget(QLabel("Порт"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(8080)
        self.port_spin.setFixedWidth(112)
        controls.addWidget(self.port_spin)
        self.autostart_cb = QCheckBox("Автозапуск при выборе папки")
        controls.addWidget(self.autostart_cb)
        controls.addStretch(1)
        self.start_btn = QPushButton("Запустить проект")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.setIcon(svg_icon("play", "#FFFFFF"))
        self.start_btn.clicked.connect(self.start)
        self.stop_btn = QPushButton("Остановить")
        self.stop_btn.setObjectName("dangerButton")
        self.stop_btn.setIcon(svg_icon("stop", "#FF9AA7"))
        self.stop_btn.clicked.connect(self.stop)
        controls.addWidget(self.start_btn)
        controls.addWidget(self.stop_btn)
        project_layout.addLayout(controls)
        layout.addWidget(project_card)

        status_grid = QGridLayout()
        status_grid.setContentsMargins(0, 0, 0, 0)
        status_grid.setSpacing(12)
        self.mode_card = StatusCard("Режим проекта", "Не выбран", "Выберите папку проекта")
        self.mode_label = self.mode_card.value_label
        self.tunnel_card = StatusCard("Публичный туннель", "Отключён", "Ожидает запуска")
        self.tunnel_status_label = self.tunnel_card.value_label
        self.service_card = StatusCard("Сервисы", "Бэкенд: —", "Docker: —")
        self.backend_health_label = self.service_card.value_label
        self.docker_status_label = self.service_card.detail_label
        self.users_card = StatusCard(
            "Посетители", "0 сейчас · 0 всего", "Статистика текущей сессии"
        )
        self.users_label = self.users_card.value_label
        status_grid.addWidget(self.mode_card, 0, 0)
        status_grid.addWidget(self.tunnel_card, 0, 1)
        status_grid.addWidget(self.service_card, 1, 0)
        status_grid.addWidget(self.users_card, 1, 1)
        status_grid.setColumnStretch(0, 1)
        status_grid.setColumnStretch(1, 1)
        layout.addLayout(status_grid)

        url_card = QFrame()
        url_card.setObjectName("urlCard")
        url_layout = QHBoxLayout(url_card)
        url_layout.setContentsMargins(16, 12, 12, 12)
        url_layout.setSpacing(8)
        url_title = QLabel("Публичный адрес")
        url_title.setObjectName("statusTitle")
        url_layout.addWidget(url_title)
        self.public_url_label = QLabel("Не создан")
        self.public_url_label.setObjectName("publicUrlLabel")
        self.public_url_label.setOpenExternalLinks(True)
        self.public_url_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        url_layout.addWidget(self.public_url_label, stretch=1)
        self.copy_url_btn = self._icon_button("copy", "Копировать публичный URL")
        self.copy_url_btn.clicked.connect(self._copy_public_url)
        self.open_url_btn = self._icon_button("external", "Открыть публичный URL")
        self.open_url_btn.clicked.connect(self._open_public_url)
        url_layout.addWidget(self.copy_url_btn)
        url_layout.addWidget(self.open_url_btn)
        layout.addWidget(url_card)

        chart_card = QFrame()
        chart_card.setObjectName("card")
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(14, 12, 14, 10)
        chart_title = QLabel("Активность")
        chart_title.setObjectName("sectionTitle")
        chart_layout.addWidget(chart_title)
        self.chart = VisitsChart()
        self.chart.setMinimumHeight(230)
        chart_layout.addWidget(self.chart)
        layout.addWidget(chart_card)

        self.main_tabs.addTab(scroll, "Обзор")

    def _build_preview_tab(self):
        page = QWidget()
        page.setObjectName("tabPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 4)
        layout.setSpacing(12)

        toolbar = QFrame()
        toolbar.setObjectName("card")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(14, 10, 10, 10)
        self.preview_url_label = QLabel("Превью появится после запуска проекта")
        self.preview_url_label.setObjectName("caption")
        toolbar_layout.addWidget(self.preview_url_label, stretch=1)
        self.preview_reload_btn = QPushButton("Обновить")
        self.preview_reload_btn.setIcon(svg_icon("refresh"))
        self.preview_reload_btn.clicked.connect(self._reload_preview)
        self.preview_open_btn = QPushButton("Открыть в браузере")
        self.preview_open_btn.setIcon(svg_icon("external"))
        self.preview_open_btn.clicked.connect(self._open_preview)
        toolbar_layout.addWidget(self.preview_reload_btn)
        toolbar_layout.addWidget(self.preview_open_btn)
        layout.addWidget(toolbar)

        if HAS_WEBENGINE:
            self.preview = QWebEngineView()
            self.preview.setMinimumHeight(420)
            layout.addWidget(self.preview, stretch=1)
        else:
            self.preview = None
            fallback = QFrame()
            fallback.setObjectName("card")
            fallback_layout = QVBoxLayout(fallback)
            fallback_label = QLabel(
                "Встроенное превью недоступно\n"
                "Установите PyQtWebEngine или откройте сайт в браузере"
            )
            fallback_label.setObjectName("caption")
            fallback_label.setAlignment(Qt.AlignCenter)
            fallback_layout.addWidget(fallback_label)
            layout.addWidget(fallback, stretch=1)
        self.main_tabs.addTab(page, "Предпросмотр")

    def _build_logs_tab(self):
        page = QWidget()
        page.setObjectName("tabPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 4)
        layout.setSpacing(12)

        toolbar = QFrame()
        toolbar.setObjectName("card")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(14, 10, 10, 10)
        title = QLabel("Журнал работы")
        title.setObjectName("sectionTitle")
        toolbar_layout.addWidget(title)
        toolbar_layout.addStretch(1)
        self.docker_logs_btn = QPushButton("Docker-логи")
        self.docker_logs_btn.setIcon(svg_icon("terminal"))
        self.docker_logs_btn.clicked.connect(self.show_docker_logs)
        self.docker_logs_btn.setEnabled(False)
        self.export_btn = QPushButton("Экспорт отчёта")
        self.export_btn.setIcon(svg_icon("file"))
        self.export_btn.clicked.connect(self.export_report)
        self.copy_log_btn = QPushButton("Копировать")
        self.copy_log_btn.setIcon(svg_icon("copy"))
        self.copy_log_btn.clicked.connect(self._copy_log)
        self.clear_log_btn = QPushButton("Очистить")
        self.clear_log_btn.setIcon(svg_icon("trash"))
        toolbar_layout.addWidget(self.docker_logs_btn)
        toolbar_layout.addWidget(self.export_btn)
        toolbar_layout.addWidget(self.copy_log_btn)
        toolbar_layout.addWidget(self.clear_log_btn)
        layout.addWidget(toolbar)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText(
            "Здесь появятся этапы запуска, URL и диагностические сообщения…"
        )
        self.clear_log_btn.clicked.connect(self.log.clear)
        layout.addWidget(self.log, stretch=1)
        self.main_tabs.addTab(page, "Логи")

    def _build_settings_tab(self):
        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        page.setObjectName("tabPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 4)
        layout.setSpacing(14)

        intro = QFrame()
        intro.setObjectName("card")
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(18, 15, 18, 15)
        title = QLabel("Профиль публикации")
        title.setObjectName("sectionTitle")
        text = QLabel(
            "Настройки сохраняются отдельно для каждого выбранного проекта. "
            "Значение «auto» подходит для большинства конфигураций."
        )
        text.setObjectName("caption")
        text.setWordWrap(True)
        intro_layout.addWidget(title)
        intro_layout.addWidget(text)
        layout.addWidget(intro)

        self.advanced_group = QGroupBox("Маршрутизация и совместимость")
        form = QFormLayout(self.advanced_group)
        form.setContentsMargins(18, 24, 18, 18)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(13)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.frontend_edit = QLineEdit("auto")
        self.frontend_edit.setPlaceholderText("auto, сервис или порт")
        self.backend_edit = QLineEdit("auto")
        self.backend_edit.setPlaceholderText("auto, none, сервис или порт")
        self.prefixes_edit = QLineEdit("/api, /health, /ws, /socket.io, /graphql")
        self.dev_combo = QComboBox()
        self.dev_combo.addItem("Авто", "auto")
        self.dev_combo.addItem("Включено", "on")
        self.dev_combo.addItem("Выключено", "off")
        self.host_combo = QComboBox()
        self.host_combo.addItem("Авто", "auto")
        self.host_combo.addItem("Сохранять публичный", "on")
        self.host_combo.addItem("Подменять на локальный", "off")
        self.public_env_edit = QLineEdit("NEXTAUTH_URL, AUTH_URL")
        form.addRow("Frontend", self.frontend_edit)
        form.addRow("Backend", self.backend_edit)
        form.addRow("Backend-пути", self.prefixes_edit)
        form.addRow("Dev/HMR", self.dev_combo)
        form.addRow("Host upstream", self.host_combo)
        form.addRow("Переменные public URL", self.public_env_edit)
        layout.addWidget(self.advanced_group)
        layout.addStretch(1)
        scroll.setWidget(page)
        self.main_tabs.addTab(scroll, "Настройки")

    @staticmethod
    def _icon_button(icon_name: str, tooltip: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("iconButton")
        button.setIcon(svg_icon(icon_name))
        button.setToolTip(tooltip)
        button.setFixedWidth(38)
        return button

    def _set_app_state(self, state: str, text: str) -> None:
        self.state_badge.setProperty("state", state)
        self.state_badge.setText(text)
        repolish(self.state_badge)

    def _show_help(self):
        HelpDialog(self).exec_()

    def _set_project_path(self, folder: str, save: bool, maybe_autostart: bool):
        super()._set_project_path(folder, save, maybe_autostart)
        if self._project_path:
            self.mode_card.set_tone("info")
            self.mode_card.detail_label.setText("Проект распознан и готов к запуску")
            if not self._running:
                self._set_app_state("idle", "●  Не запущено")
        else:
            self.mode_card.set_content("Не распознан", "Проверьте структуру папки", "danger")
            self._set_app_state("error", "●  Ошибка проекта")

    def start(self):
        super().start()
        if self._start_worker and self._start_worker.isRunning():
            self._set_app_state("starting", "●  Запускается")
            self.tunnel_card.set_content("Подключение…", "Подготовка сервера и ngrok", "warning")

    def _on_start_finished(self, payload: dict):
        super()._on_start_finished(payload)
        if payload.get("ok"):
            self._set_app_state("running", "●  Работает")
            self.mode_card.set_tone("success")
            self.service_card.set_tone("success")
            self.users_card.set_tone("info")
        else:
            self._set_app_state("error", "●  Ошибка запуска")
            self.tunnel_card.set_content("Ошибка", "Подробности находятся в журнале", "danger")
            self.main_tabs.setCurrentIndex(2)

    def stop(self):
        super().stop()
        self._set_app_state("idle", "●  Не запущено")

    def _set_tunnel_connected(self, public_url: str):
        super()._set_tunnel_connected(public_url)
        self._public_url = public_url
        self.tunnel_card.set_content("Подключён", "Публичный HTTPS-адрес активен", "success")
        self.copy_url_btn.setEnabled(True)
        self.open_url_btn.setEnabled(True)

    def _on_public_url_ready(self, public_url: str):
        super()._on_public_url_ready(public_url)
        self._public_url = public_url
        self.tunnel_card.set_content("Ссылка создана", "Сайт ещё запускается — не закрывайте программу", "warning")

    def _reset_tunnel_ui(self):
        super()._reset_tunnel_ui()
        self._public_url = ""
        self.public_url_label.setText("Не создан")
        self.tunnel_card.set_content("Отключён", "Ожидает запуска", "neutral")
        self.service_card.set_tone("neutral")
        self.users_card.set_tone("neutral")
        self.copy_url_btn.setEnabled(False)
        self.open_url_btn.setEnabled(False)

    def _poll_tunnel_stats(self):
        super()._poll_tunnel_stats()
        if self._running and not self.tunnel.get_public_url():
            self._public_url = ""
            self.public_url_label.setText("Не создан")
            self.copy_url_btn.setEnabled(False)
            self.open_url_btn.setEnabled(False)
            self.tunnel_card.set_content(
                "Отключён", "Соединение с ngrok потеряно", "warning"
            )

    def _load_preview(self, url: str):
        super()._load_preview(url)
        self.preview_url_label.setText(url)
        self.preview_reload_btn.setEnabled(self.preview is not None)
        self.preview_open_btn.setEnabled(True)

    def _clear_preview(self):
        super()._clear_preview()
        self.preview_url_label.setText("Превью остановлено")
        self.preview_reload_btn.setEnabled(False)
        self.preview_open_btn.setEnabled(False)

    def _on_process_exited(self):
        was_running = self._running
        super()._on_process_exited()
        if was_running and not self._running:
            self._set_app_state("error", "●  Процесс завершён")
            self.main_tabs.setCurrentIndex(2)

    def _copy_public_url(self):
        if self._public_url:
            QApplication.clipboard().setText(self._public_url)
            self.update_status("Публичный URL скопирован в буфер обмена")

    def _open_public_url(self):
        if self._public_url:
            QDesktopServices.openUrl(QUrl(self._public_url))

    def _reload_preview(self):
        if self.preview is not None and self._local_url:
            self.preview.reload()

    def _open_preview(self):
        if self._local_url:
            QDesktopServices.openUrl(QUrl(self._local_url))

    def _copy_log(self):
        text = self.log.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.update_status("Журнал скопирован в буфер обмена")


# Сохраняем прежнее имя темы для main.py и внешних импортов.
DARK_QSS = MODERN_QSS
