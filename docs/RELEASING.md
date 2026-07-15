# Выпуск версии

1. Проверьте `python -m pytest` на Windows.
2. Обновите версию в `pyproject.toml` и `src/network_launcher/__init__.py`.
3. Создайте и отправьте тег формата `v1.0.0`.
4. GitHub Actions соберёт Windows ZIP и приложит его к GitHub Release.

Локальная проверка архива: `powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1`.
