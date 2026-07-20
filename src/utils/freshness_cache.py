import sqlite3
import hashlib
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class FreshnessCache:
    """
    SQLite-backed URL/content-hash deduplication cache.
    Ensures we never process the same article or job posting twice,
    even across distributed crawler runs.
    """
    def __init__(self, db_path: str = "freshness_cache.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_items (
                url_hash  TEXT PRIMARY KEY,
                url       TEXT,
                seen_at   TEXT DEFAULT (datetime('now'))
            )
        """)
        self.conn.commit()

    def _hash(self, url: str) -> str:
        return hashlib.md5(url.strip().encode()).hexdigest()

    def is_seen(self, url: str) -> bool:
        h = self._hash(url)
        row = self.conn.execute(
            "SELECT 1 FROM seen_items WHERE url_hash = ?", (h,)
        ).fetchone()
        return row is not None

    def mark_seen(self, url: str):
        h = self._hash(url)
        self.conn.execute(
            "INSERT OR IGNORE INTO seen_items (url_hash, url) VALUES (?, ?)",
            (h, url)
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
