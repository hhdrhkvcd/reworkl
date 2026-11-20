ПАТЧ BALKAN FRONTIER 1999 v0.1.2 — NO DLC

Полный архив сборки находится в приложенном ZIP в чате. В этой ветке GitHub сохранены текстовые файлы патча.

Исправления:
1. Убран replace_path common/country_tags: он скрывал ванильные теги (в том числе SOV), что совпадает с массовыми ошибками из error.log.
2. Закладка 01.03.1999 теперь явно выбирает YUG.
3. В полном ZIP удалены DLC-зависимые точки появления special_project_facility_spawn, floating_harbor, naval_supply_hub, naval_headquarters, landmark_spawn, dam_spawn и locks_spawn.

Основная ветка main не изменялась. Ветка содержит только патчевые текстовые файлы; полный ZIP скачивается из ответа ChatGPT.

Проверено статически: ZIP цел, country tag YUG присутствует, country_tags не заменяется, перечисленные DLC spawn types отсутствуют. Запуск в исполняемом файле HOI4 здесь не выполнялся.
