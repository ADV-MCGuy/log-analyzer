"""
log_parser.py - Parse log files in syslog format
"""

import re
from datetime import datetime


class LogEntry:
    """Represents a single log entry."""
    
    def __init__(self, timestamp, level, component, message):
        self.timestamp = timestamp
        self.level = level
        self.component = component
        self.message = message
    
    def __repr__(self):
        return f"LogEntry({self.timestamp}, {self.level}, {self.component})"


def parse_log_line(line):
    """
    Parse a single log line.
    
    Expected format: DD Mon HH:MM:SS [LEVEL] Component | Message
    Example: 07 Sep 14:27:29 [INFO] Laser Range Finder | Sent command to stop
    
    Args:
        line (str): A log line
        
    Returns:
        LogEntry or None if parsing fails
    """
    try:
        # Match the pattern: DD Mon HH:MM:SS [LEVEL] Component | Message
        pattern = r'(\d{2}\s\w{3}\s\d{2}:\d{2}:\d{2})\s\[(\w+)\]\s(.+?)\s\|\s(.+)'
        match = re.match(pattern, line.strip())
        
        if not match:
            return None
        
        timestamp_str, level, component, message = match.groups()
        
        # Parse timestamp (we'll store as string for now, but could parse to datetime)
        timestamp = timestamp_str
        
        return LogEntry(
            timestamp=timestamp,
            level=level.upper(),
            component=component.strip(),
            message=message.strip()
        )
    
    except Exception as e:
        print(f"Error parsing line: {e}")
        return None


def parse_log_file(filepath):
    """
    Parse an entire log file.
    
    Args:
        filepath (str): Path to log file
        
    Returns:
        list: List of LogEntry objects
    """
    entries = []
    
    try:
        with open(filepath, 'r') as file:
            for line_num, line in enumerate(file, 1):
                if not line.strip():
                    continue
                
                entry = parse_log_line(line)
                if entry:
                    entries.append(entry)
                else:
                    print(f"Warning: Could not parse line {line_num}: {line.strip()[:50]}...")
        
        print(f"Successfully parsed {len(entries)} log entries")
        return entries
    
    except FileNotFoundError:
        print(f"Error: File '{filepath}' not found")
        return None
    except Exception as e:
        print(f"Error reading file: {e}")
        return None


def get_error_pattern(message):
    """
    Extract a pattern from an error message for grouping similar errors.
    
    This helps group similar errors together (e.g., multiple "Connection timeout" errors).
    
    Args:
        message (str): The log message
        
    Returns:
        str: A simplified pattern
    """
    # Remove variable parts (numbers, IPs, etc.) to find the pattern
    pattern = re.sub(r'\d+', 'NUM', message)
    pattern = re.sub(r'\d\.\d', 'NUM', pattern)
    
    # Limit to first 50 characters to keep patterns useful
    return pattern[:80]