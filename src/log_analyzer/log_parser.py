"""
log_parser.py - Parse log files in syslog-like format
"""

import re
from datetime import datetime

# DD Mon HH:MM:SS [LEVEL] Component | Message
LINE_RE = re.compile(r'(\d{2})\s(\w{3})\s(\d{2}):(\d{2}):(\d{2})\s\[(\w+)\]\s(.+?)\s\|\s(.+)')

# Looked up directly rather than with strptime('%b'), which is slow and locale-dependent
MONTHS = {name: i for i, name in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], 1)}

NUMBER_RE = re.compile(r'\d+(?:\.\d+)?')

# A timestamp this many days *earlier* than the previous one means the log
# crossed New Year (e.g. "31 Dec" followed by "01 Jan"), since the format has no year.
YEAR_ROLLOVER_DAYS = 180

# How many unparsed lines to keep for display
MAX_UNPARSED_SAMPLES = 5


class LogEntry:
    """Represents a single log entry."""

    def __init__(self, timestamp, level, component, message, line_no=None):
        self.timestamp = timestamp  # datetime
        self.level = level
        self.component = component
        self.message = message
        self.line_no = line_no

    def __repr__(self):
        return f"LogEntry({self.timestamp}, {self.level}, {self.component})"


class ParseStats:
    """Counts of what happened while parsing a file."""

    def __init__(self):
        self.parsed = 0
        self.unparsed = 0
        self.unparsed_samples = []  # (line_no, text)


def parse_log_line(line, year):
    """
    Parse a single log line.

    Expected format: DD Mon HH:MM:SS [LEVEL] Component | Message
    Example: 07 Sep 14:27:29 [INFO] Laser Range Finder | Sent command to stop

    Args:
        line (str): A log line
        year (int): Year to assume, since the format doesn't include one

    Returns:
        LogEntry or None if parsing fails
    """
    match = LINE_RE.match(line.strip())
    if not match:
        return None

    day, month, hour, minute, second, level, component, message = match.groups()

    try:
        timestamp = datetime(year, MONTHS[month.capitalize()], int(day), int(hour), int(minute), int(second))
    except (KeyError, ValueError):
        # Bad month name, or 29 Feb in a non-leap year
        return None

    return LogEntry(
        timestamp=timestamp,
        level=level.upper(),
        component=component.strip(),
        message=message.strip()
    )


def parse_log_file(filepath, year, stats):
    """
    Parse a log file one line at a time.

    Entries are yielded rather than collected so large files aren't held in memory.

    Args:
        filepath (str): Path to log file
        year (int): Year of the first entry in the file
        stats (ParseStats): Updated with parsed/unparsed counts as lines are read

    Yields:
        LogEntry
    """
    previous = None

    # errors='replace' so stray binary bytes in a log don't abort the whole file
    with open(filepath, 'r', encoding='utf-8', errors='replace') as file:
        for line_no, line in enumerate(file, 1):
            if not line.strip():
                continue

            entry = parse_log_line(line, year)
            if entry and previous and (previous - entry.timestamp).days > YEAR_ROLLOVER_DAYS:
                year += 1
                entry = parse_log_line(line, year)

            if not entry:
                stats.unparsed += 1
                if len(stats.unparsed_samples) < MAX_UNPARSED_SAMPLES:
                    stats.unparsed_samples.append((line_no, line.rstrip('\n')))
                continue

            entry.line_no = line_no
            stats.parsed += 1
            previous = entry.timestamp
            yield entry


def get_message_pattern(message):
    """
    Reduce a message to a pattern for grouping similar messages.

    Variable parts are masked, so "Connection timeout after 5 seconds" and
    "Connection timeout after 30 seconds" group together.

    Args:
        message (str): The log message

    Returns:
        str: The message with numbers replaced by NUM
    """
    return NUMBER_RE.sub('NUM', message)
