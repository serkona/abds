import argparse

from app.config import ROOT
from app.db import ClickHouse

TABLES = (
    "dim_realty", "dim_gauges", "dim_tariffs", "dim_users",
    "fact_gauge_bindings", "fact_meter_readings", "fact_invoice",
)


def create_schema(db):
    db.execute(
        "CREATE DATABASE IF NOT EXISTS {name:Identifier}",
        {"name": db.database}, use_database=False,
    )
    for statement in (ROOT / "sql/schema.sql").read_text().split(";"):
        if statement.strip():
            db.execute(statement)
    print("Схема создана")


def load(db):
    for table in TABLES:
        if not (ROOT / "data" / (table + ".csv")).is_file():
            raise RuntimeError(f"Нет data/{table}.csv; сначала выполните make gen")
        if db.rows(f"SELECT count() AS n FROM {table}")[0]["n"]:
            raise RuntimeError("База не пуста; выполните make teardown и make setup")
    for table in TABLES:
        path = ROOT / "data" / (table + ".csv")
        with path.open("rb") as source:
            db.execute(
                f"INSERT INTO {table} FORMAT CSVWithNames",
                data=source, size=path.stat().st_size,
            )
        print(f"Загружена {table}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["schema", "load", "teardown"])
    action = parser.parse_args().action
    db = ClickHouse()
    if action == "schema":
        create_schema(db)
    elif action == "load":
        load(db)
    else:
        db.execute(
            "DROP DATABASE IF EXISTS {name:Identifier} SYNC",
            {"name": db.database}, use_database=False,
        )
        db.execute(
            "CREATE DATABASE {name:Identifier}",
            {"name": db.database}, use_database=False,
        )
        print("Таблицы и данные удалены")


if __name__ == "__main__":
    main()
