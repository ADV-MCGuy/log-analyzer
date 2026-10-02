"""
database.py - SQLite database operations for log analysis
"""

import sqlite3
from datetime import datetime

SCHEMA_VERSION = 1

# Rows per executemany() call when inserting entries
BATCH_SIZE = 5000

# Timestamps are stored as text in this format so they sort chronologically
DB_TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S'

ERROR_LEVELS = ('ERROR', 'CRITICAL', 'FATAL')
WARNING_LEVELS = ('WARNING', 'WARN')


class DatabaseError(Exception):
    """A problem with the database that the user needs to know about."""


class LogDatabase:
    """Handle all database operations for log analysis."""

    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        """Connect to database and create tables."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute('PRAGMA foreign_keys = ON')
        self._create_tables()

    def _create_tables(self):
        """Create tables if they don't exist."""
        version = self.conn.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise DatabaseError(f"{self.db_path} was created by a newer version of this tool")
        if version == 0:
            existing = self.conn.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
            if existing:
                raise DatabaseError(
                    f"{self.db_path} was created by an older version of this tool; "
                    "delete it or use a different --db path")

        with self.conn:
            # One row per ingested file
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY,
                    path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    ingested_at TEXT NOT NULL,
                    entry_count INTEGER NOT NULL DEFAULT 0,
                    unparsed_count INTEGER NOT NULL DEFAULT 0
                )
            ''')

            # Parsed log entries
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY,
                    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    line_no INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    component TEXT NOT NULL,
                    message TEXT NOT NULL,
                    pattern TEXT NOT NULL
                )
            ''')

            self.conn.execute('CREATE INDEX IF NOT EXISTS idx_entries_source_ts ON entries(source_id, timestamp)')
            self.conn.execute('CREATE INDEX IF NOT EXISTS idx_entries_level ON entries(level)')
            self.conn.execute('CREATE INDEX IF NOT EXISTS idx_entries_component ON entries(component)')
            self.conn.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')

    def transaction(self):
        """
        Context manager that commits on success and rolls back on error.

        Usage: with db.transaction(): ...
        """
        return self.conn

    # --- Sources ---

    def find_sources(self, path, sha256):
        """Get sources already ingested from this path or with these exact contents."""
        return self.conn.execute('''
            SELECT id, path, sha256, ingested_at, entry_count, unparsed_count
            FROM sources
            WHERE path = ? OR sha256 = ?
            ORDER BY id
        ''', (path, sha256)).fetchall()

    def insert_source(self, path, sha256):
        """Insert a source row and return its id."""
        cursor = self.conn.execute('''
            INSERT INTO sources (path, sha256, ingested_at) VALUES (?, ?, ?)
        ''', (path, sha256, datetime.now().strftime(DB_TIMESTAMP_FORMAT)))
        return cursor.lastrowid

    def finish_source(self, source_id, entry_count, unparsed_count):
        """Record the final counts for a source."""
        self.conn.execute('''
            UPDATE sources SET entry_count = ?, unparsed_count = ? WHERE id = ?
        ''', (entry_count, unparsed_count, source_id))

    def remove_source(self, source_id):
        """Delete a source and its entries. Returns True if it existed."""
        cursor = self.conn.execute('DELETE FROM sources WHERE id = ?', (source_id,))
        return cursor.rowcount > 0

    def get_source(self, source_id):
        """Get one source, or None."""
        return self.conn.execute('''
            SELECT id, path, sha256, ingested_at, entry_count, unparsed_count
            FROM sources WHERE id = ?
        ''', (source_id,)).fetchone()

    def list_sources(self):
        """Get all sources."""
        return self.conn.execute('''
            SELECT id, path, sha256, ingested_at, entry_count, unparsed_count
            FROM sources ORDER BY id
        ''').fetchall()

    # --- Entries ---

    def insert_entries(self, source_id, rows):
        """
        Insert entries in batches.

        Args:
            source_id (int): Source the entries belong to
            rows (iterable): (line_no, timestamp, level, component, message, pattern)
                tuples, where timestamp is a datetime

        Returns:
            int: Number of entries inserted
        """
        sql = '''
            INSERT INTO entries (source_id, line_no, timestamp, level, component, message, pattern)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        '''
        count = 0
        batch = []
        for line_no, timestamp, level, component, message, pattern in rows:
            # isoformat() matches DB_TIMESTAMP_FORMAT and is much faster than strftime()
            batch.append((source_id, line_no, timestamp.isoformat(sep=' ', timespec='seconds'),
                          level, component, message, pattern))
            if len(batch) >= BATCH_SIZE:
                self.conn.executemany(sql, batch)
                count += len(batch)
                batch = []
        if batch:
            self.conn.executemany(sql, batch)
            count += len(batch)
        return count

    # --- Summary queries (all optionally limited to one source) ---

    @staticmethod
    def _where(source_id, levels=None):
        """Build a WHERE clause and its parameters."""
        clauses, params = [], []
        if source_id is not None:
            clauses.append('source_id = ?')
            params.append(source_id)
        if levels:
            clauses.append(f"level IN ({', '.join('?' for _ in levels)})")
            params.extend(levels)
        where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
        return where, params

    def get_total_by_level(self, source_id=None):
        """Get counts of each log level."""
        where, params = self._where(source_id)
        return self.conn.execute(f'''
            SELECT level, COUNT(*) AS count FROM entries
            {where}
            GROUP BY level
            ORDER BY count DESC
        ''', params).fetchall()

    def get_time_span(self, source_id=None):
        """Get (first timestamp, last timestamp), or (None, None) if empty."""
        where, params = self._where(source_id)
        return self.conn.execute(f'''
            SELECT MIN(timestamp), MAX(timestamp) FROM entries {where}
        ''', params).fetchone()

    def get_top_patterns(self, levels, limit=10, source_id=None):
        """
        Get the most frequent message patterns at the given levels.

        Returns:
            list: (pattern, level, component, count, first_seen, last_seen) tuples
        """
        where, params = self._where(source_id, levels)
        return self.conn.execute(f'''
            SELECT pattern, level, component, COUNT(*) AS count, MIN(timestamp), MAX(timestamp)
            FROM entries
            {where}
            GROUP BY pattern, level, component
            ORDER BY count DESC, MIN(timestamp)
            LIMIT ?
        ''', params + [limit]).fetchall()

    def get_top_errors(self, limit=10, source_id=None):
        """Get most frequent errors."""
        return self.get_top_patterns(ERROR_LEVELS, limit, source_id)

    def get_top_warnings(self, limit=10, source_id=None):
        """Get most frequent warnings."""
        return self.get_top_patterns(WARNING_LEVELS, limit, source_id)

    def get_errors_by_component(self, source_id=None):
        """Get error counts by component."""
        where, params = self._where(source_id, ERROR_LEVELS)
        return self.conn.execute(f'''
            SELECT component, level, COUNT(*) AS count
            FROM entries
            {where}
            GROUP BY component, level
            ORDER BY count DESC
        ''', params).fetchall()

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
