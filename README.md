# ЭнергоСбыт

Запуск: `make run && make setup`. Проверки: `make test`.
Остановка: `make stop`.
Для повторной загрузки данных: `make teardown && make setup`.

Swagger UI: http://localhost:8080/docs. Спецификация OpenAPI: http://localhost:8080/openapi.json.
FastAPI формирует спецификацию из маршрутов и моделей приложения.

## Ключи и партиции

- `dim_realty`, `dim_gauges`, `dim_users`: `ORDER BY id` для поиска по идентификатору; у пользователей заменяются версии одной записи.
- `dim_tariffs`: `(id, valid_from)` сохраняет отдельные интервалы тарифа.
- `fact_gauge_bindings`: `(realty_id, gauge_id)` объединяет установку и аннулирование одного счётчика на объекте.
- `fact_meter_readings`: `(realty_id, reading_date)` объединяет корректировки за один день.
- `fact_invoice`: `(realty_id, created_at)` для выборки счетов объекта по времени.

Показания и счета разбиты по месяцам для выборок за период. Небольшие справочники и привязки — без партиционирования.

[Проверка сценариев лабораторной 1](docs/lab-01.md).
