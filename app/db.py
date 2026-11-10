import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import load_env


class DatabaseError(Exception):
    pass


class ClickHouse:
    def __init__(self):
        load_env()
        self.database = os.environ["CLICKHOUSE_DATABASE"]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.database):
            raise ValueError("Invalid CLICKHOUSE_DATABASE")
        self.url = "http://{}:{}/".format(
            os.environ["CLICKHOUSE_HOST"], os.environ["CLICKHOUSE_HTTP_PORT"]
        )
        self.headers = {
            "X-ClickHouse-User": os.environ["CLICKHOUSE_USER"],
            "X-ClickHouse-Key": os.environ["CLICKHOUSE_PASSWORD"],
        }

    def execute(self, sql, params=None, *, data=None, size=None, use_database=True):
        query = {"query": sql, "output_format_json_quote_64bit_integers": "0"}
        if use_database:
            query["database"] = self.database
        for key, value in (params or {}).items():
            query["param_" + key] = str(value)
        headers = dict(self.headers)
        if size is not None:
            headers["Content-Length"] = str(size)
        request = Request(
            self.url + "?" + urlencode(query),
            data=b"" if data is None else data,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                return response.read().decode()
        except HTTPError as exc:
            message = exc.read().decode(errors="replace")
            raise DatabaseError(message) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise DatabaseError("ClickHouse is unavailable") from exc

    def rows(self, sql, params=None):
        result = self.execute(sql + " FORMAT JSONEachRow", params)
        return [json.loads(line) for line in result.splitlines() if line]

    def insert(self, table, rows):
        if not rows:
            return
        columns = ", ".join(rows[0])
        payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows).encode()
        self.execute(f"INSERT INTO {table} ({columns}) FORMAT JSONEachRow", data=payload)
