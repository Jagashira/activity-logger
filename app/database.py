# app/database.py
import sqlite3
import os
import datetime as _dt

class DatabaseManager:

    def __init__(self, db_path):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        # 複数のスレッドから呼び出される可能性があるため、check_same_thread=False を設定
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._setup_table()

    def _setup_table(self):

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                content TEXT
            )
        ''')
        self.conn.commit()

    def add_log_entry(self, event_type: str, content: str = ''):

        timestamp = _dt.datetime.now().isoformat()
        try:
            self.cursor.execute("INSERT INTO logs (timestamp, event_type, content) VALUES (?, ?, ?)",
                                (timestamp, event_type, content))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Database error: {e}")

    def close(self):

        if self.conn:
            self.conn.close()
