# Balkan Frontier 1999 — HOI4 1.20.x

## Исправление дескриптора
Корневой `descriptor.mod` ранее содержал настройки от The Fire Rises (1.19.*), включая массовые `replace_path`. Они перекрывали стандартные файлы стран и вызывали ошибки отсутствующих тегов (например SOV, CSA, DDR, WGR). Дескриптор заменён на профиль Balkan Frontier 1999 для HOI4 1.20.x; оставлены только `history/states` и `map`.

## CMD-лаунчер
Файл [Balkan_Frontier_1999_CMD_Launcher.bat](Balkan_Frontier_1999_CMD_Launcher.bat) создаёт визуальное меню, устанавливает папку мода в Documents\Paradox Interactive\Hearts of Iron IV\mod и запускает `hoi4.exe` напрямую с локальным .mod-файлом, минуя Paradox Launcher.

Для работы BAT нужен распакованный рядом каталог `Balkan_Frontier_1999`. Полный ZIP-пакет с модом и лаунчером приложен в ответе ChatGPT, поскольку бинарные архивы нельзя загрузить через текстовый API коммитов.

Проверка структуры и дескриптора не заменяет тест на реальном клиенте HOI4 1.20.x. Если игра продолжит аварийно завершаться, нужны новые `error.log` и `exception.txt`.
