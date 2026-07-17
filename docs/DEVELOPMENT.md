# Руководство разработчика

## Требования

- Windows 10/11 x64 — основная среда разработки и единственная публикуемая готовая сборка;
- Python 3.10 или новее; Python 3.12 рекомендуется и используется в CI;
- Git;
- интернет для первой установки Python-пакетов и, если бинарник не bundled, ngrok;
- Node.js, Flask или Docker Desktop нужны только для ручной проверки соответствующих типов проектов.

## Подготовка окружения

```powershell
git clone https://github.com/dartino21/network_launcher.git
cd network_launcher
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pytest
```

Если PowerShell запрещает активацию окружения, можно вызывать интерпретатор напрямую:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
```

## Запуск приложения

Предпочтительный вариант:

```powershell
.\scripts\run_dev.ps1
```

Эквивалентная команда:

```powershell
$env:PYTHONPATH = "src"
python -m network_launcher
```

`RUN_APP.bat` запускает тот же PowerShell-скрипт и удобен после однократной установки зависимостей.

## Автоматические тесты

Полный набор:

```powershell
python -m pytest -p no:cacheprovider
```

Полезные выборочные запуски:

```powershell
python -m pytest tests\test_gateway_proxy.py -q
python -m pytest tests\test_profiles_and_docker.py -q
python -m pytest tests\test_gui_smoke.py -q
```

`tests/conftest.py` добавляет `src/` в `sys.path`, поэтому отдельная установка пакета для pytest не требуется. GUI smoke-тесты запускаются без интерактивного управления окном.

## Ручная проверка

Минимальная проверка без внешних runtime:

1. Запустите Network Launcher.
2. Выберите `tests/fixtures/static_project`.
3. Сохраните действующий ngrok authtoken.
4. Запустите проект и дождитесь статуса **Работает**.
5. Проверьте локальное превью и публичный URL.
6. Остановите сессию и убедитесь, что ссылка больше не активна.

CLI smoke-runner для настоящего проекта:

```powershell
python tests\manual_publish_smoke.py C:\path\to\web-project
```

Runner пишет состояние в `data/runtime/smoke_state.json` и работает до появления `data/runtime/smoke_stop`. Это ручной инструмент: он требует ngrok и реальные зависимости выбранного проекта.

## Локальные данные

При запуске из исходников writable-каталоги создаются в корне репозитория:

```text
data/config.json
data/logs/app.log
data/runtime/
bin/ngrok.exe
```

Они исключены из Git. Не добавляйте реальные токены, пользовательские пути, логи и скачанные бинарники в коммиты.

## Сборка Windows EXE

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Скрипт:

1. устанавливает зависимости и pytest;
2. выполняет полный набор тестов;
3. читает версию из `network_launcher.__version__`;
4. запускает PyInstaller со `scripts/network_launcher.spec`;
5. собирает portable ZIP в `release/`.

Выходные файлы:

```text
dist/NetworkLauncher.exe
release/NetworkLauncher-v<версия>-windows-x64/
release/NetworkLauncher-v<версия>-windows-x64.zip
```

PyInstaller включает assets и, если присутствует `bin/ngrok.exe`, bundled-копию ngrok. Каталоги `build/`, `dist/` и `release/` не коммитятся.

## Карта изменений

- Новый тип проекта или стратегия запуска: `server_manager.py` и тесты диагностики.
- Docker Compose: `docker_manager.py`, `publish_profile.py` и `test_profiles_and_docker.py`.
- Маршрутизация или протоколы: `gateway_proxy.py` и `test_gateway_proxy.py`.
- Туннель/ngrok: `tunnel_manager.py`, `ngrok_bundle.py` и `test_tunnel_manager.py`.
- UI: `gui.py`, `ui_components.py`, `ui_theme.py` и `test_gui_smoke.py`.
- Конфигурация: повышайте `config_version` и добавляйте обратимо тестируемую миграцию.

## Перед коммитом

```powershell
git diff --check
python -m pytest -p no:cacheprovider
git status --short
```

Если пользовательское поведение, требования или команды изменились, обновите README и соответствующий документ в `docs/` в том же коммите.

Процесс публикации описан отдельно в [RELEASING.md](RELEASING.md).
