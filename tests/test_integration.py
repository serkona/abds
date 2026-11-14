import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.config import load_env
from app.db import ClickHouse


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load_env()
        cls.base = "http://localhost:" + os.environ["APP_PORT"]
        cls.db = ClickHouse()
        cls.ids = []
        cls.gauges = []

    def setUp(self):
        self.ident = 900001 + len(self.ids)
        self.gauge = self.ident * 10
        self.ids.append(self.ident)
        self.gauges.extend([self.gauge, self.gauge + 1])
        created = "2026-01-01 00:00:00"
        self.db.insert("dim_users", [{
            "id": self.ident, "fio": "Тестовый собственник", "phone": "+79000000000",
            "phone_prev": "", "created_at": created, "updated_at": created,
        }])
        self.db.insert("dim_realty", [{
            "id": self.ident, "address": "Тестовый адрес", "square": 42,
            "type": "flat", "number": "1", "rooms": 2, "floor": 1, "porch": 1,
            "created_at": created,
        }])
        self.db.insert("dim_gauges", [
            {"id": gauge, "name": "Тестовый счётчик", "country": "Россия", "created_at": created}
            for gauge in (self.gauge, self.gauge + 1)
        ])

    @classmethod
    def tearDownClass(cls):
        ids = ",".join(map(str, cls.ids))
        gauges = ",".join(map(str, cls.gauges))
        for table, column, values in (
            ("dim_realty", "id", ids), ("dim_users", "id", ids),
            ("dim_gauges", "id", gauges),
            ("fact_meter_readings", "realty_id", ids),
            ("fact_gauge_bindings", "realty_id", ids),
        ):
            cls.db.execute(f"ALTER TABLE {table} DELETE WHERE {column} IN ({values}) SETTINGS mutations_sync=1")

    def call(self, method, path, body=None, expected=200):
        req = Request(
            self.base + path, method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urlopen(req, timeout=10)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            self.assertEqual(response.status, expected, raw.decode())
            if expected >= 400:
                self.assertEqual(set(json.loads(raw)), {"message"})
            return json.loads(raw) if raw else None

    def reading(self, **changes):
        return {
            "user_id": self.ident, "gauge_id": self.gauge, "tariff_id": 1,
            "reading_date": "2026-10-01", "day_kw": 1250, "night_kw": 300,
            **changes,
        }

    def test_ping_has_empty_body(self):
        self.assertIsNone(self.call("GET", "/ping"))

    def test_scd1_and_scd3(self):
        path = f"/users/{self.ident}"
        for patch in ({"fio": "Новое имя"}, {"phone": "+79111111111"}, {"phone": "+79222222222"}):
            self.call("PATCH", path, patch, 204)
        user = self.call("GET", path)
        self.assertEqual(user["fio"], "Новое имя")
        self.assertEqual((user["phone"], user["phone_prev"]), ("+79222222222", "+79111111111"))
        self.call("PATCH", path, {"phone": "+79222222222"}, 204)
        self.assertEqual(self.call("GET", path)["phone_prev"], "+79111111111")
        rows = self.db.rows("SELECT fio FROM dim_users FINAL WHERE id = {id:UInt64}", {"id": self.ident})
        self.assertEqual(rows, [{"fio": "Новое имя"}])

    def test_concurrent_patches_do_not_lose_fields(self):
        path = f"/users/{self.ident}"
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(self.call, "PATCH", path, patch, 204) for patch in
                    ({"fio": "Параллельное изменение"}, {"phone": "+79333333333"})]
            for job in jobs:
                job.result()
        user = self.call("GET", path)
        self.assertEqual(user["fio"], "Параллельное изменение")
        self.assertEqual(user["phone"], "+79333333333")

    def test_reading_correction_and_inclusive_dates(self):
        path = f"/realty/{self.ident}/readings"
        self.call("POST", path, self.reading(), 201)
        self.call("POST", path, self.reading(day_kw=1260), 201)
        result = self.call("GET", path + "?date_from=2026-10-01&date_to=2026-10-01")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["readings"][0]["day_kw"], 1260)
        self.assertEqual(self.call("GET", path + "?date_from=1900-01-01&date_to=1900-02-01"),
                         {"readings": [], "count": 0})

    def test_gauge_cancellation_and_reinstallation(self):
        path = f"/realty/{self.ident}/gauges"
        for gauge in (self.gauge, self.gauge + 1, self.gauge):
            self.call("POST", path, {"gauge_id": gauge}, 201)
        rows = self.db.rows(
            "SELECT gauge_id, sign, version FROM fact_gauge_bindings FINAL WHERE realty_id = {id:UInt64}",
            {"id": self.ident},
        )
        self.assertEqual(rows, [{"gauge_id": self.gauge, "sign": 1, "version": 3}])

    def test_tariff_boundaries(self):
        old = self.call("GET", "/tariffs?date=2025-10-31")
        new = self.call("GET", "/tariffs?date=2025-11-01")
        self.assertEqual(old["valid_to"], new["valid_from"])
        self.assertNotEqual(old["price_day_kwph"], new["price_day_kwph"])
        self.call("GET", "/tariffs?date=1900-01-01", expected=404)
        self.call("GET", "/tariffs?date=2099-01-01", expected=404)

    def test_invoice_pagination_and_historical_prices(self):
        first = self.call("GET", "/realty/1/invoices?limit=1&offset=0")
        second = self.call("GET", "/realty/1/invoices?limit=1&offset=1")
        empty = self.call("GET", "/realty/1/invoices?limit=0")
        self.assertEqual(first["count"], 36)
        self.assertEqual(empty, {"invoices": [], "count": 36})
        self.assertGreater(first["invoices"][0]["created_at"], second["invoices"][0]["created_at"])
        invoice = first["invoices"][0]
        prices = self.call("GET", "/tariffs?date=" + invoice["created_at"][:10])
        self.assertEqual(invoice["price"], invoice["day_kw"] * prices["price_day_kwph"] +
                         invoice["night_kw"] * prices["price_night_kwph"])

    def test_validation_and_missing_entities(self):
        user = f"/users/{self.ident}"
        for body in ({}, {"fio": ""}, {"phone": None}, {"fio": 7}, {"unknown": "value"}):
            self.call("PATCH", user, body, 400)
        path = f"/realty/{self.ident}/readings"
        for value in (-1, 1.5, True, "12", 2**32):
            self.call("POST", path, self.reading(day_kw=value), 400)
        self.call("POST", path, self.reading(reading_date="2026-02-30"), 400)
        self.call("POST", path, self.reading(user_id=2**63), 404)
        for suffix in ("?date_from=2026-10-02&date_to=2026-10-01", "?date_from=x", ""):
            self.call("GET", path + suffix, expected=400)
        self.call("GET", "/tariffs", expected=400)
        self.call("GET", "/tariffs?date=2026-02-30", expected=400)
        self.call("GET", "/realty/1/invoices?limit=-1", expected=400)
        self.call("GET", "/users/18446744073709551615", expected=404)
        self.call("GET", "/users/18446744073709551616", expected=400)

    def test_generated_data(self):
        self.assertEqual(self.db.rows(
            "SELECT count() AS n FROM fact_meter_readings FINAL WHERE realty_id <= 1000"
        )[0]["n"], 1096000)
        self.assertEqual(self.db.rows("SELECT count() AS n FROM fact_invoice")[0]["n"], 36000)
        self.assertEqual(self.db.rows(
            "SELECT count() AS n FROM fact_invoice WHERE toDayOfMonth(deadline) != 10"
        )[0]["n"], 0)
        self.assertEqual(self.db.rows(
            "SELECT count() AS n FROM dim_tariffs FINAL WHERE id = 1"
        )[0]["n"], 3)

    def test_delete_erroneous_row(self):
        self.db.insert("fact_meter_readings", [{
            "realty_id": self.ident, **self.reading(day_kw=12500),
            "created_at": "2026-10-02 00:00:00",
        }])
        self.db.execute(
            "ALTER TABLE fact_meter_readings DELETE WHERE realty_id = {id:UInt64} "
            "AND day_kw = 12500 SETTINGS mutations_sync=1", {"id": self.ident},
        )
        result = self.call("GET", f"/realty/{self.ident}/readings?date_from=2026-10-01&date_to=2026-10-01")
        self.assertEqual(result, {"readings": [], "count": 0})


if __name__ == "__main__":
    unittest.main()
