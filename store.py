import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Dict, List, Optional


DB_PATH = os.getenv("SPOTIFY_APP_DB", os.path.join(os.path.dirname(__file__), "app.db"))


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS members (
                spotify_user_id TEXT PRIMARY KEY,
                tokens_json TEXT NOT NULL
            )
            """
        )
        conn.commit()


@contextmanager
def _conn():
    connection = sqlite3.connect(DB_PATH)
    try:
        yield connection
    finally:
        connection.close()


def upsert_member(spotify_user_id: str, tokens: Dict[str, str]) -> None:
    payload = json.dumps(tokens)
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO members(spotify_user_id, tokens_json)
            VALUES(?, ?)
            ON CONFLICT(spotify_user_id) DO UPDATE SET tokens_json=excluded.tokens_json
            """,
            (spotify_user_id, payload),
        )
        conn.commit()


def list_member_ids() -> List[str]:
    with _conn() as conn:
        cur = conn.execute("SELECT spotify_user_id FROM members ORDER BY spotify_user_id")
        return [row[0] for row in cur.fetchall()]


def get_member_tokens(spotify_user_id: str) -> Optional[Dict[str, str]]:
    with _conn() as conn:
        cur = conn.execute(
            "SELECT tokens_json FROM members WHERE spotify_user_id=?",
            (spotify_user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None


def update_member_tokens(spotify_user_id: str, tokens: Dict[str, str]) -> None:
    upsert_member(spotify_user_id, tokens)

