# Начните отсюда

Этот файл помогает быстро выбрать нужный маршрут. Основное описание и возможности проекта находятся в [README.md](README.md).

## Я хочу просто запустить Network Launcher

1. Скачайте ZIP со страницы [Latest Release](https://github.com/dartino21/network_launcher/releases/latest).
2. Полностью распакуйте архив в отдельную папку.
3. Запустите `NetworkLauncher.exe`.
4. На вкладке **Настройки** сохраните [ngrok authtoken](https://dashboard.ngrok.com/get-started/your-authtoken).
5. Выберите корневую папку сайта, нажмите **Запустить проект** и дождитесь статуса **Работает**.

Готовая сборка предназначена для Windows x64. Не запускайте EXE внутри ZIP: приложению нужен доступ на запись к папкам `data/` и `data/logs/` рядом с ним.

Если проект не распознаётся или ссылка не открывается, перейдите к [руководству по диагностике](docs/TROUBLESHOOTING.md).

## Я клонировал репозиторий

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt pytest
.\scripts\run_dev.ps1
```

После установки зависимостей можно использовать `RUN_APP.bat`. Рекомендуемая версия Python для локальной разработки — 3.12; минимальная версия пакета — 3.10.

## Я изучаю проект как разработчик или технический ревьюер

Начните с этих файлов:

1. [README.md](README.md) — задача, возможности и пользовательский сценарий.
2. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — схема компонентов и жизненный цикл публикации.
3. [`src/network_launcher/server_manager.py`](src/network_launcher/server_manager.py) — планирование и управление локальным проектом.
4. [`src/network_launcher/gateway_proxy.py`](src/network_launcher/gateway_proxy.py) — HTTP/SSE/WebSocket reverse proxy.
5. [`src/network_launcher/gui.py`](src/network_launcher/gui.py) — GUI и фоновые workers.
6. [`tests/`](tests/) — 39 автоматических проверок текущего поведения.

Локальная проверка:

```powershell
$env:PYTHONPATH = "src"
python -m pytest -p no:cacheprovider
```

## Я хочу внести изменения

Используйте [руководство разработчика](docs/DEVELOPMENT.md): там описаны окружение, тестовые группы, ручной end-to-end smoke-сценарий и проверка сборки.

## Я выпускаю новую версию

Следуйте [docs/RELEASING.md](docs/RELEASING.md). Релиз создаётся тегом `v<версия>` только после синхронизации версии и успешного прохождения тестов.
