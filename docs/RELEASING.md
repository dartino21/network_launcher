# Выпуск версии

Windows-релиз собирается GitHub Actions после отправки тега формата `v<версия>`. Workflow повторно запускает тесты, проверяет соответствие тега версии пакета, создаёт ZIP и публикует GitHub Release.

## Где хранится версия

Перед релизом одинаковое значение должно находиться в двух файлах:

- `pyproject.toml` → `project.version`;
- `src/network_launcher/__init__.py` → `__version__`.

Тег должен быть тем же значением с префиксом `v`. Например, версии `1.1.0` соответствует тег `v1.1.0`.

## Чек-лист перед релизом

1. Убедитесь, что рабочее дерево содержит только ожидаемые изменения:

   ```powershell
   git status --short
   git diff --check
   ```

2. Обновите версию в обоих файлах и проверьте, что приложение её импортирует:

   ```powershell
   python -c "import sys; sys.path.insert(0, 'src'); import network_launcher; print(network_launcher.__version__)"
   ```

3. Обновите README и связанную документацию, если изменились интерфейс, требования, поддерживаемые проекты или команды.

4. Выполните автоматические проверки:

   ```powershell
   python -m pytest -p no:cacheprovider
   ```

5. Соберите и проверьте локальный архив:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
   ```

   Результат: `release/NetworkLauncher-v<версия>-windows-x64.zip`.

6. Распакуйте ZIP в чистую временную папку и вручную проверьте:

   - запуск `NetworkLauncher.exe` без исходников и виртуального окружения;
   - создание `data/` рядом с EXE;
   - распознавание простого статического проекта;
   - настройку ngrok и появление проверенного публичного URL;
   - остановку сессии без оставшихся процессов.

## Публикация

Укажите фактическую версию без префикса `v` в переменной:

```powershell
$version = "1.1.0"
git add -A
git commit -m "Release v$version"
git push origin master
git tag -a "v$version" -m "Network Launcher v$version"
git push origin "v$version"
```

Тег создавайте только на коммите с нужной версией. Workflow `Test and release Windows build`:

1. устанавливает Python 3.12 и зависимости;
2. запускает `python -m pytest`;
3. сравнивает имя тега с `network_launcher.__version__`;
4. запускает `scripts/build_windows.ps1`;
5. прикладывает `release/NetworkLauncher-v<версия>-windows-x64.zip` к GitHub Release.

Ход выполнения виден на вкладке [Actions](https://github.com/dartino21/network_launcher/actions), результат — на странице [Releases](https://github.com/dartino21/network_launcher/releases).

## Если workflow завершился ошибкой

- **Tag does not match package version** — исправьте обе версии, создайте новый коммит и новый тег. Не перемещайте уже опубликованный тег без необходимости.
- **Tests failed** — воспроизведите `python -m pytest -p no:cacheprovider` на Python 3.12.
- **PyInstaller build failed** — локально запустите `scripts/build_windows.ps1` и проверьте скрытые импорты и файлы в `scripts/network_launcher.spec`.
- **Release upload failed** — проверьте разрешение `contents: write` у release job и отсутствие релиза с конфликтующим asset.

Каталоги `build/`, `dist/` и `release/` являются локальными артефактами и исключены из Git.
