"""
database.py - SQLite database operations for log analysis
"""

import sqlite3
from datetime import datetime


class LogDatabase:
    """Handle all database operations for log analysis."""
    
    def __init__(self, db_path='data/logs.db'):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
    
    def connect(self):
        """Connect to database and create tables."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            self._create_tables()
            print(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            print(f"Database error: {e}")
    
    def _create_tables(self):
        """Create tables if they don't exist."""
        # Raw log entries
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS log_entries (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                component TEXT NOT NULL,
                message TEXT NOT NULL,
                error_pattern TEXT,
                parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Error metrics (summary of errors)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS error_metrics (
                id INTEGER PRIMARY KEY,
                error_pattern TEXT UNIQUE,
                level TEXT,
                component TEXT,
                occurrence_count INTEGER DEFAULT 1,
                first_seen TEXT,
                last_seen TEXT
            )
        ''')
        
        self.conn.commit()
    
    def insert_log_entry(self, log_entry, error_pattern=None):
        """
        Insert a log entry into the database.
        
        Args:
            log_entry (LogEntry): The log entry to store
            error_pattern (str): Optional error pattern for grouping
        """
        try:
            self.cursor.execute('''
                INSERT INTO log_entries (timestamp, level, component, message, error_pattern)
                VALUES (?, ?, ?, ?, ?)
            ''', (log_entry.timestamp, log_entry.level, log_entry.component, 
                  log_entry.message, error_pattern))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error inserting entry: {e}")
    
    def insert_error_metric(self, error_pattern, level, component, timestamp):
        """
        Insert or update error metrics.
        
        Args:
            error_pattern (str): The error pattern
            level (str): Log level
            component (str): Component name
            timestamp (str): When error occurred
        """
        try:
            # Check if pattern exists
            self.cursor.execute('''
                SELECT id, occurrence_count FROM error_metrics WHERE error_pattern = ?
            ''', (error_pattern,))
            
            result = self.cursor.fetchone()
            
            if result:
                # Update existing
                entry_id, count = result
                self.cursor.execute('''
                    UPDATE error_metrics 
                    SET occurrence_count = ?, last_seen = ?
                    WHERE id = ?
                ''', (count + 1, timestamp, entry_id))
            else:
                # Insert new
                self.cursor.execute('''
                    INSERT INTO error_metrics (error_pattern, level, component, 
                                               occurrence_count, first_seen, last_seen)
                    VALUES (?, ?, ?, 1, ?, ?)
                ''', (error_pattern, level, component, timestamp, timestamp))
            
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error updating metrics: {e}")
    
    def get_top_errors(self, limit=10):
        """Get most frequent errors."""
        self.cursor.execute('''
            SELECT error_pattern, level, component, occurrence_count, first_seen, last_seen
            FROM error_metrics
            WHERE level IN ('ERROR', 'CRITICAL')
            ORDER BY occurrence_count DESC
            LIMIT ?
        ''', (limit,))
        return self.cursor.fetchall()
    
    def get_top_warnings(self, limit=10):
        """Get most frequent warnings."""
        self.cursor.execute('''
            SELECT error_pattern, level, component, occurrence_count, first_seen, last_seen
            FROM error_metrics
            WHERE level = 'WARNING'
            ORDER BY occurrence_count DESC
            LIMIT ?
        ''', (limit,))
        return self.cursor.fetchall()
    
    def get_errors_by_component(self):
        """Get error counts by component."""
        self.cursor.execute('''
            SELECT component, level, COUNT(*) as count
            FROM log_entries
            WHERE level IN ('ERROR', 'CRITICAL')
            GROUP BY component, level
            ORDER BY count DESC
        ''')
        return self.cursor.fetchall()
    
    def get_all_by_level(self, level):
        """Get all entries of a specific level."""
        self.cursor.execute('''
            SELECT timestamp, component, message FROM log_entries
            WHERE level = ?
            ORDER BY timestamp
        ''', (level,))
        return self.cursor.fetchall()
    
    def get_entries_by_component(self, component):
        """Get all entries for a component."""
        self.cursor.execute('''
            SELECT timestamp, level, message FROM log_entries
            WHERE component = ?
            ORDER BY timestamp
        ''', (component,))
        return self.cursor.fetchall()
    
    def get_total_by_level(self):
        """Get counts of each log level."""
        self.cursor.execute('''
            SELECT level, COUNT(*) as count FROM log_entries
            GROUP BY level
            ORDER BY count DESC
        ''')
        return self.cursor.fetchall()
    
    def clear_database(self):
        """Clear all data (useful for testing)."""
        self.cursor.execute('DELETE FROM log_entries')
        self.cursor.execute('DELETE FROM error_metrics')
        self.conn.commit()
        print("Database cleared")
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            print("Database connection closed")