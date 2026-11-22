# Запуск Balkan Frontier 1999 вместе с игрой

В репозиторий добавлены три файла:
- START_BF1999_WITH_MOD.bat — запускаемый файл;
- BF1999_ForceLaunch.ps1 — установка, включение мода и прямой запуск;
- START_WITH_MOD_RU.md — эта инструкция.

## Как пользоваться
1. Скачай полный мод и распакуй его так, чтобы рядом с BAT была папка Balkan_Frontier_1999.
2. Оставь Steam запущенным.
3. Запусти START_BF1999_WITH_MOD.bat.
4. Если игра не найдена, укажи полный путь к hoi4.exe.
5. Скрипт создаёт внешний дескриптор balkan_frontier_1999.mod, добавляет его в dlc_load.json и запускает hoi4.exe напрямую.

Для чистой проверки активируется только Balkan Frontier 1999. Предыдущий dlc_load.json сохраняется в резервную копию. Отчёт появится на рабочем столе: BF1999_LAUNCH_REPORT.txt.

## Важно
В репозитории пока нет полной папки Balkan_Frontier_1999. Для запуска нужны её игровые файлы: descriptor.mod, common, history, map, events, gfx и localisation.
