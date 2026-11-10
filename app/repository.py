from datetime import date, datetime, timedelta, timezone
from threading import RLock

from app.db import ClickHouse


def next_timestamp(previous=None):
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    if previous:
        now = max(now, datetime.fromisoformat(previous) + timedelta(seconds=1))
    return now.strftime("%Y-%m-%d %H:%M:%S")


class NotFound(Exception):
    pass


class Repository:
    def __init__(self):
        self.db = ClickHouse()
        self.write_lock = RLock()

    def entity(self, table, ident):
        final = " FINAL" if table in ("dim_users", "dim_tariffs") else ""
        rows = self.db.rows(
            f"SELECT * FROM {table}{final} WHERE id = {{id:UInt64}} LIMIT 1", {"id": ident}
        )
        if not rows:
            raise NotFound
        return rows[0]

    def update_user(self, ident, changes):
        with self.write_lock:
            user = self.entity("dim_users", ident)
            if "phone" in changes and changes["phone"] != user["phone"]:
                user["phone_prev"] = user["phone"]
            user.update(changes)
            user["updated_at"] = next_timestamp(user["updated_at"])
            self.db.insert("dim_users", [user])

    def add_reading(self, realty, values):
        with self.write_lock:
            self.entity("dim_realty", realty)
            for table, key in (("dim_users", "user_id"), ("dim_gauges", "gauge_id"), ("dim_tariffs", "tariff_id")):
                self.entity(table, values[key])
            previous = self.db.rows(
                "SELECT created_at FROM fact_meter_readings FINAL "
                "WHERE realty_id = {id:UInt64} AND reading_date = {day:Date}",
                {"id": realty, "day": values["reading_date"]},
            )
            self.db.insert("fact_meter_readings", [{
                "realty_id": realty, **values,
                "created_at": next_timestamp(previous[0]["created_at"] if previous else None),
            }])

    def readings(self, realty, date_from, date_to):
        self.entity("dim_realty", realty)
        date_from, date_to = max(date_from, date(1970, 1, 1)), min(date_to, date(2149, 6, 6))
        if date_from > date_to:
            return []
        return self.db.rows(
            "SELECT reading_date, user_id, tariff_id, gauge_id, day_kw, night_kw "
            "FROM fact_meter_readings FINAL WHERE realty_id = {id:UInt64} "
            "AND reading_date BETWEEN {start:Date} AND {end:Date} ORDER BY reading_date",
            {"id": realty, "start": date_from, "end": date_to},
        )

    def invoices(self, realty, limit, offset):
        self.entity("dim_realty", realty)
        params = {"id": realty, "limit": limit, "offset": offset}
        rows = self.db.rows(
            "SELECT tariff_id, gauge_id, day_kw, night_kw, price, deadline, created_at "
            "FROM fact_invoice WHERE realty_id = {id:UInt64} "
            "ORDER BY created_at DESC LIMIT {limit:UInt64} OFFSET {offset:UInt64}", params,
        )
        count = self.db.rows(
            "SELECT count() AS count FROM fact_invoice WHERE realty_id = {id:UInt64}", params
        )[0]["count"]
        return {"invoices": rows, "count": count}

    def tariff(self, day):
        rows = self.db.rows(
            "SELECT id, name, price_day_kwph, price_night_kwph, valid_from, valid_to "
            "FROM dim_tariffs FINAL WHERE toString(valid_from) <= {day:String} "
            "AND {day:String} < toString(valid_to) ORDER BY id LIMIT 1", {"day": day + " 00:00:00"},
        )
        if not rows:
            raise NotFound
        return rows[0]

    def install_gauge(self, realty, gauge):
        with self.write_lock:
            self.entity("dim_realty", realty)
            self.entity("dim_gauges", gauge)
            active = self.db.rows(
                "SELECT * FROM fact_gauge_bindings FINAL "
                "WHERE realty_id = {id:UInt64} AND sign = 1", {"id": realty},
            )
            version = max((row["version"] for row in active), default=0) + 1
            rows = [{**row, "sign": -1} for row in active]
            rows.append({
                "gauge_id": gauge, "realty_id": realty, "created_at": next_timestamp(),
                "sign": 1, "version": version,
            })
            self.db.insert("fact_gauge_bindings", rows)
