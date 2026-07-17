# Выпуск версии

Релиз создаётся GitHub Actions после отправки тега `v<версия>`. Значение тега
должно совпадать с версиями в `pyproject.toml` и
`src/network_launcher/__init__.py`.

## Подготовка

1. Обновите версию в обоих файлах.
2. Запустите тесты:

   ```powershell
   python -m pytest -p no:cacheprovider
   ```

3. При необходимости локально соберите и проверьте архив:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
   ```

   Архив появится в `release/NetworkLauncher-v<версия>-windows-x64.zip`.
   Каталоги `build/`, `dist/` и `release/` являются локальными артефактами и
   не добавляются в Git.

## Публикация

Пример для версии `1.0.3`:

```powershell
git status --short
git add -A
git commit -m "Release v1.0.3"
git push origin master
git tag -a v1.0.3 -m "Network Launcher v1.0.3"
git push origin v1.0.3
```

После отправки тега workflow `Test and release Windows build` повторно запустит
тесты, соберёт Windows ZIP и создаст GitHub Release с автоматически
сформированными примечаниями. Ход выполнения виден на вкладке **Actions**, а
готовый архив — на странице **Releases**.

Не создавайте тег до коммита с нужной версией. Если версия другая, замените
`1.0.3` во всех командах и в обоих файлах версии.
