# Лабораторная 1: проверка сценариев

SQL выполняется в базе `energosbyt`, изменения — через Swagger.

SCD 1 и 3: после смены ФИО и двух смен телефона видны новое имя, последний и предпоследний телефоны.

```sql
SELECT fio, phone, phone_prev FROM dim_users FINAL WHERE id = 1;
```

SCD 2: версии тарифа до и после 1 ноября 2025 года имеют разные цены и соседние интервалы.

```sql
SELECT valid_from, valid_to, price_day_kwph, price_night_kwph
FROM dim_tariffs FINAL WHERE id = 1 ORDER BY valid_from;
```

Пересчёт старого счёта: `price` совпадает с `recalculated`, используется тариф на дату счёта.

```sql
SELECT i.price, i.day_kw * t.price_day_kwph + i.night_kw * t.price_night_kwph AS recalculated
FROM fact_invoice AS i INNER JOIN (SELECT * FROM dim_tariffs FINAL) AS t ON i.tariff_id = t.id
WHERE i.realty_id = 1 AND i.created_at >= t.valid_from AND i.created_at < t.valid_to
ORDER BY i.created_at LIMIT 1;
```

Корректировка: после двух передач показаний за одну дату остаётся одно актуальное значение.

```sql
SELECT day_kw, night_kw FROM fact_meter_readings FINAL
WHERE realty_id = 1 AND reading_date = '2026-10-01';
```

Замена счётчика: после установки другого счётчика остаётся его активная привязка с новой версией.

```sql
SELECT gauge_id, sign, version FROM fact_gauge_bindings FINAL WHERE realty_id = 1 AND sign = 1;
```

Удаление ошибки: после передачи тестового показания `day_kw = 12500` за `2026-10-01` удаляем его. Проверка возвращает `0`.

```sql
ALTER TABLE fact_meter_readings DELETE WHERE realty_id = 1 AND reading_date = '2026-10-01' AND day_kw = 12500 SETTINGS mutations_sync = 1;
SELECT count() FROM fact_meter_readings WHERE realty_id = 1 AND reading_date = '2026-10-01' AND day_kw = 12500;
```
