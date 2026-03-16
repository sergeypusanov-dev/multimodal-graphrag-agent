import psycopg2, psycopg2.extras, os
from typing import Optional

_conn = None

def get_db():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(
            os.environ["POSTGRES_URL"],
            cursor_factory=psycopg2.extras.RealDictCursor
        )
    return DBWrapper(_conn)

class DBWrapper:
    def __init__(self, conn): self.conn = conn

    def fetch(self, sql: str, params=None) -> list:
        with self.conn.cursor() as cur:
            cur.execute(sql, params or [])
            return [dict(r) for r in cur.fetchall()]

    def fetchone(self, sql: str, params=None) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params or [])
            r = cur.fetchone()
            return dict(r) if r else None

    def execute(self, sql: str, params=None):
        with self.conn.cursor() as cur:
            cur.execute(sql, params or [])
        self.conn.commit()

    def execute_script(self, sql: str):
        with self.conn.cursor() as cur:
            cur.execute(sql)
        self.conn.commit()
