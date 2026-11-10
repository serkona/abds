import csv
import os
import random
from contextlib import ExitStack
from datetime import date, timedelta

from app.config import ROOT, load_env

START = date(2023, 11, 1)
END = date(2026, 10, 31)
REPLACEMENT = date(2025, 11, 1)
CREATED = "2023-11-01 00:00:00"
TARIFFS = (
    ("2023-11-01", "2025-11-01", 560, 280),
    ("2025-11-01", "2026-11-01", 620, 310),
    ("2026-11-01", "2099-01-01", 680, 340),
)
HEADERS = {
    "dim_realty": "id address square type number rooms floor porch created_at",
    "dim_gauges": "id name country created_at",
    "dim_tariffs": "id name price_day_kwph price_night_kwph valid_from valid_to created_at updated_at",
    "dim_users": "id fio phone phone_prev created_at updated_at",
    "fact_gauge_bindings": "gauge_id realty_id created_at sign version",
    "fact_meter_readings": "realty_id user_id tariff_id gauge_id reading_date day_kw night_kw created_at",
    "fact_invoice": "realty_id user_id tariff_id gauge_id day_kw night_kw price deadline created_at",
}


def tariff_prices(day):
    for start, end, day_price, night_price in TARIFFS:
        if start <= day.isoformat() < end:
            return day_price, night_price
    raise ValueError("Нет тарифа на дату")


def generate():
    load_env()
    rng = random.Random(int(os.environ["GEN_SEED"]))
    directory = ROOT / "data"
    directory.mkdir(exist_ok=True)
    corrections = 0
    days = [START + timedelta(days=i) for i in range((END - START).days + 1)]

    with ExitStack() as stack:
        writers = {}
        for table, header in HEADERS.items():
            stream = stack.enter_context(
                (directory / (table + ".csv")).open("w", newline="", encoding="utf-8")
            )
            writers[table] = csv.writer(stream)
            writers[table].writerow(header.split())

        for start, end, day_price, night_price in TARIFFS:
            writers["dim_tariffs"].writerow([
                1, "День–Ночь", day_price, night_price,
                start + " 00:00:00", end + " 00:00:00", CREATED, CREATED,
            ])

        for ident in range(1, 1001):
            non_residential = ident % 10 == 0
            writers["dim_realty"].writerow([
                ident, f"Учебная улица, дом {(ident - 1) // 100 + 1}",
                rng.randint(30, 120), "nrcp" if non_residential else "flat",
                "" if non_residential else str((ident - 1) % 100 + 1),
                0 if non_residential else rng.randint(1, 4),
                (ident - 1) % 10 + 1, (ident - 1) % 4 + 1, CREATED,
            ])
            writers["dim_users"].writerow([
                ident, f"Собственник {ident}", f"+7900{ident:07d}", "", CREATED, CREATED,
            ])
            writers["dim_gauges"].writerow([ident, "Меркурий 200", "Россия", CREATED])
            writers["fact_gauge_bindings"].writerow([ident, ident, CREATED, 1, 1])
            if non_residential:
                replacement_time = REPLACEMENT.isoformat() + " 00:00:00"
                writers["dim_gauges"].writerow([
                    1000 + ident, "Меркурий 230", "Россия", replacement_time,
                ])
                writers["fact_gauge_bindings"].writerow([ident, ident, CREATED, -1, 1])
                writers["fact_gauge_bindings"].writerow([
                    1000 + ident, ident, replacement_time, 1, 2,
                ])

            gauge = ident
            day_total = night_total = month_day = month_night = 0
            for day in days:
                if non_residential and day == REPLACEMENT:
                    gauge = 1000 + ident
                    day_total = night_total = 0
                day_delta, night_delta = rng.randint(4, 15), rng.randint(1, 7)
                day_total += day_delta
                night_total += night_delta
                month_day += day_delta
                month_night += night_delta
                corrected = rng.random() < 0.03
                prefix = [ident, ident, 1, gauge, day.isoformat()]
                writers["fact_meter_readings"].writerow(prefix + [
                    day_total - int(corrected), night_total,
                    day.isoformat() + " 20:00:00",
                ])
                if corrected:
                    writers["fact_meter_readings"].writerow(prefix + [
                        day_total, night_total, day.isoformat() + " 21:00:00",
                    ])
                    corrections += 1
                next_day = day + timedelta(days=1)
                if next_day.day == 1:
                    day_price, night_price = tariff_prices(day)
                    writers["fact_invoice"].writerow([
                        ident, ident, 1, gauge, month_day, month_night,
                        month_day * day_price + month_night * night_price,
                        next_day.replace(day=10).isoformat(), day.isoformat() + " 23:00:00",
                    ])
                    month_day = month_night = 0
    print(f"Создано {len(days) * 1000} показаний, {corrections} корректировок и 36000 счетов")


if __name__ == "__main__":
    generate()
